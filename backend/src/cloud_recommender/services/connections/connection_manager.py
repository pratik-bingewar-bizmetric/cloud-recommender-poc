"""Owner-bound persistent cloud connections: validate, encrypt, store, rotate, reuse.

One implementation for every environment (local, Fabric frontend, App Service backend). The
application user (identified by the Entra token, or the explicit development identity) is kept
strictly separate from the cloud account being connected: the cloud credentials are supplied by
the user, validated directly with Microsoft Entra ID, and stored only as ciphertext.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from fastapi import HTTPException

from cloud_recommender.core.config import Settings
from cloud_recommender.core.secret_vault import CredentialCipher, SecretUnavailableError, VaultError
from cloud_recommender.db.repositories.connection_repo import (
    ConnectionRepository,
    DuplicateConnectionError,
    StoredConnection,
)
from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.connections import (
    CloudConnection,
    CreateConnectionRequest,
    IntegrationState,
    IntegrationStatus,
    UpdateConnectionRequest,
)
from cloud_recommender.services.azure_live.arm_client import AzureArmClient
from cloud_recommender.services.azure_live.credentials import (
    ARM_SCOPE,
    DATABRICKS_SCOPE,
    FABRIC_SCOPE,
    AzureCredentialError,
    AzureToken,
    acquire_cli_token,
    acquire_managed_identity_token,
    acquire_service_principal_token,
)
from cloud_recommender.services.azure_live.session_store import AzureSession, AzureSessionStore
from cloud_recommender.services.azure_live.validation import is_guid, require_guid
from cloud_recommender.services.connections.integration_checks import (
    azure_integration_statuses,
    check_databricks,
    check_fabric,
    fetch_permission_report,
)

logger = structlog.get_logger(__name__)

AUTH_SP = "service_principal"
AUTH_CLI = "azure_cli"
AUTH_MI = "managed_identity"
API_SUBSCRIPTIONS = "2022-12-01"


def _err(code: int, error_code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=code, detail={"error_code": error_code, "message": message, **extra}
    )


class ConnectionManager:
    """Application service behind /api/v1/connections for user-owned (persistent) connections."""

    def __init__(
        self,
        repo: ConnectionRepository,
        cipher_factory: Callable[[], CredentialCipher],
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        sessions: AzureSessionStore | None = None,
    ) -> None:
        self._repo = repo
        self._cipher_factory = cipher_factory
        self._settings = settings
        self._transport = transport
        self._sessions = sessions

    # ------------------------------------------------------------------ helpers

    def _cipher(self) -> CredentialCipher:
        try:
            return self._cipher_factory()
        except SecretUnavailableError:
            raise _err(
                503,
                "CREDENTIAL_STORE_UNAVAILABLE",
                "Secure credential storage is not configured on this server, so credentials "
                "cannot be saved. Configure the encryption key (see the deployment guide).",
            ) from None

    def _view(self, record: StoredConnection) -> CloudConnection:
        validation = record.last_validation or {}
        integrations = [IntegrationStatus(**i) for i in validation.get("integrations", [])]
        labels = {
            "resource_manager": "resource_inventory",
            "cost_management": "cost_management",
            "monitor": "metrics",
            "databricks": "databricks",
            "fabric": "fabric",
        }
        capabilities = [
            labels[i.integration]
            for i in integrations
            if i.state == IntegrationState.CONNECTED and i.integration in labels
        ]
        return CloudConnection(
            id=record.id,
            name=record.name,
            provider=CloudProvider(record.provider),
            scope_id=record.scope_id,
            display_name=f"{record.name} ({record.scope_id})",
            tenant_or_org_id=record.credential_tenant_id,
            auth_method=record.auth_method,
            status=record.status,  # type: ignore[arg-type]
            last_verified_at=record.last_validated_at,
            is_live=True,
            capabilities=capabilities,
            access_limitations=["Strictly read-only access; credentials are stored encrypted."],
            ownership="owned",
            integrations=integrations,
            warnings=list(validation.get("warnings", [])),
        )

    async def _token(
        self,
        method: str,
        tenant_id: str | None,
        client_id: str | None,
        secret: str | None,
        scope: str,
    ) -> AzureToken:
        if method == AUTH_SP:
            assert tenant_id and client_id and secret
            return await acquire_service_principal_token(
                scope=scope,
                authority_url=self._settings.azure_authority_url,
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=secret,
                timeout=float(self._settings.azure_live_request_timeout_seconds),
                transport=self._transport,
            )
        if method == AUTH_MI:
            resource = scope.removesuffix("/.default")
            return await acquire_managed_identity_token(
                resource=resource, transport=self._transport
            )
        if scope != ARM_SCOPE:  # CLI tokens are ARM only
            raise AzureCredentialError(
                "cli_scope", "The Azure CLI method supports Azure Resource Manager only."
            )
        return acquire_cli_token()

    # ----------------------------------------------------------------- validation

    async def _validate(
        self,
        method: str,
        tenant_id: str | None,
        client_id: str | None,
        secret: str | None,
        subscription_id: str,
        databricks_url: str | None,
        databricks_workspace_id: str | None,
        fabric_workspace_id: str | None,
    ) -> dict[str, Any]:
        """Authenticate, verify subscription/tenant, evaluate every integration. Raises 400/422."""
        try:
            arm_token = await self._token(method, tenant_id, client_id, secret, ARM_SCOPE)
        except AzureCredentialError as exc:
            raise _err(
                502 if exc.upstream else 400,
                "ENTRA_UNAVAILABLE" if exc.upstream else "INVALID_AZURE_CREDENTIALS",
                exc.message,
                category=exc.category,
                aadsts=exc.aadsts,
            ) from None

        arm = AzureArmClient(
            arm_token.value,
            self._settings.azure_arm_base_url,
            float(self._settings.azure_live_request_timeout_seconds),
            self._transport,
        )
        sub = await arm.get(f"/subscriptions/{subscription_id}", API_SUBSCRIPTIONS)
        if sub.status_code in (403, 404):
            raise _err(
                400,
                "SUBSCRIPTION_NOT_ACCESSIBLE",
                "The service principal cannot access this subscription. Check the subscription ID "
                "and assign at least the Reader role on it.",
                required_permission="Reader",
            )
        if not sub.ok:
            raise _err(502, "AZURE_UNAVAILABLE", "Azure Resource Manager could not be reached.")
        sub_tenant = str((sub.body or {}).get("tenantId", ""))
        if tenant_id and sub_tenant and sub_tenant.lower() != tenant_id.lower():
            raise _err(
                400,
                "SUBSCRIPTION_TENANT_MISMATCH",
                "The subscription does not belong to the supplied tenant.",
            )

        report, permission_response = await fetch_permission_report(arm, subscription_id)
        integrations = azure_integration_statuses(report, permission_response)
        warnings: list[str] = []
        if report is not None and report.has_write_access:
            message = (
                "This service principal holds write-capable permissions ("
                + ", ".join(report.write_patterns[:3])
                + "). "
                "Use a read-only role (Reader, Cost Management Reader, Monitoring Reader)."
            )
            if self._settings.connection_reject_write_principals:
                raise _err(
                    400,
                    "WRITE_PERMISSIONS_DETECTED",
                    message,
                    write_permissions=report.write_patterns,
                )
            warnings.append(message)

        # Databricks / Fabric reuse the same service principal with their own audiences.
        db_token = fabric_token = None
        db_error = fabric_error = None
        if databricks_url:
            try:
                db_token = (
                    await self._token(method, tenant_id, client_id, secret, DATABRICKS_SCOPE)
                ).value
            except AzureCredentialError as exc:
                db_error = exc.message
        if fabric_workspace_id:
            try:
                fabric_token = (
                    await self._token(method, tenant_id, client_id, secret, FABRIC_SCOPE)
                ).value
            except AzureCredentialError as exc:
                fabric_error = exc.message
        integrations.append(
            await check_databricks(
                databricks_url, databricks_workspace_id, db_token, db_error, self._transport
            )
        )
        integrations.append(
            await check_fabric(
                self._settings.fabric_api_base_url,
                fabric_workspace_id,
                fabric_token,
                fabric_error,
                self._transport,
            )
        )
        return {
            "integrations": [i.model_dump(mode="json") for i in integrations],
            "warnings": warnings,
            "token": arm_token,
        }

    @staticmethod
    def _overall_status(validation: dict[str, Any]) -> str:
        arm = next(
            (i for i in validation["integrations"] if i["integration"] == "resource_manager"), None
        )
        return "connected" if arm and arm["state"] == "connected" else "permission_denied"

    # ------------------------------------------------------------------- commands

    async def create(self, owner_key: str, req: CreateConnectionRequest) -> CloudConnection:
        if req.provider != CloudProvider.AZURE:
            raise _err(
                400, "UNSUPPORTED_PROVIDER", "Persistent connections currently support Azure only."
            )
        method = req.auth_method or AUTH_SP
        subscription_id = require_guid(req.scope_id, "scope_id (subscription ID)")
        tenant_id = client_id = secret = None
        if method == AUTH_SP:
            missing = [
                name
                for name, value in (
                    ("azure_tenant_id", req.azure_tenant_id),
                    ("azure_client_id", req.azure_client_id),
                    ("azure_client_secret", req.azure_client_secret),
                )
                if not value
            ]
            if missing:
                raise _err(
                    422,
                    "MISSING_REQUIRED_FIELDS",
                    "Tenant ID, Client ID and Client Secret are required for service principal authentication.",
                    fields=missing,
                )
            tenant_id = require_guid(req.azure_tenant_id or "", "azure_tenant_id")
            client_id = require_guid(req.azure_client_id or "", "azure_client_id")
            secret = req.azure_client_secret.get_secret_value() if req.azure_client_secret else None
        elif method == AUTH_CLI and not self._settings.allow_cli_connections:
            raise _err(
                400,
                "AUTH_METHOD_NOT_AVAILABLE",
                "Azure CLI authentication is available only in local development when explicitly enabled.",
            )
        tenant_id = tenant_id or (
            require_guid(req.azure_tenant_id, "azure_tenant_id") if req.azure_tenant_id else None
        )

        if await self._repo.count(owner_key) >= self._settings.connections_max_per_user:
            raise _err(
                409,
                "CONNECTION_LIMIT_REACHED",
                "Maximum number of connections reached. Delete one first.",
            )

        cipher = (
            self._cipher() if method == AUTH_SP else None
        )  # fail before any cloud call if no key
        validation = await self._validate(
            method,
            tenant_id,
            client_id,
            secret,
            subscription_id,
            req.databricks_workspace_url,
            req.databricks_workspace_id,
            req.fabric_workspace_id,
        )
        validation.pop("token")

        connection_id = str(uuid.uuid4())
        ciphertext = kid = None
        if cipher is not None and secret is not None:
            ciphertext, kid = cipher.encrypt(secret, connection_id, owner_key)
        record = StoredConnection(
            id=connection_id,
            owner_key=owner_key,
            provider=req.provider.value,
            auth_method=method,
            name=req.name.strip(),
            scope_id=subscription_id,
            credential_tenant_id=tenant_id,
            credential_client_id=client_id,
            secret_ciphertext=ciphertext,
            secret_kid=kid,
            integration_config={
                "databricks_workspace_url": req.databricks_workspace_url,
                "databricks_workspace_id": req.databricks_workspace_id,
                "fabric_workspace_id": req.fabric_workspace_id,
            },
            last_validation=validation,
            status=self._overall_status(validation),
            last_validated_at=datetime.now(UTC),
        )
        try:
            stored = await self._repo.add(record)
        except DuplicateConnectionError:
            raise _err(
                409,
                "DUPLICATE_CONNECTION",
                "You already have a connection for this subscription and client.",
            ) from None
        logger.info(
            "connection_created", connection_id=stored.id, provider=stored.provider, method=method
        )
        return self._view(stored)

    async def list(self, owner_key: str) -> list[CloudConnection]:
        return [self._view(r) for r in await self._repo.list(owner_key)]

    async def _owned(self, owner_key: str, connection_id: str) -> StoredConnection:
        record = await self._repo.get(owner_key, connection_id)
        if record is None:  # other users' and unknown ids are indistinguishable
            raise _err(404, "CONNECTION_NOT_FOUND", "The connection was not found.")
        return record

    async def get(self, owner_key: str, connection_id: str) -> CloudConnection:
        return self._view(await self._owned(owner_key, connection_id))

    def _decrypt(self, record: StoredConnection) -> str | None:
        if record.secret_ciphertext is None or record.secret_kid is None:
            return None
        try:
            return self._cipher().decrypt(
                record.secret_ciphertext, record.secret_kid, record.id, record.owner_key
            )
        except VaultError:
            raise _err(
                409,
                "CREDENTIAL_UNREADABLE",
                "The stored credential cannot be read (encryption key changed). Re-enter the client secret.",
            ) from None

    async def validate(self, owner_key: str, connection_id: str) -> CloudConnection:
        """Re-validate with the stored credential (decrypted only for this call)."""
        record = await self._owned(owner_key, connection_id)
        secret = self._decrypt(record)
        cfg = record.integration_config
        validation = await self._validate(
            record.auth_method,
            record.credential_tenant_id,
            record.credential_client_id,
            secret,
            record.scope_id,
            cfg.get("databricks_workspace_url"),
            cfg.get("databricks_workspace_id"),
            cfg.get("fabric_workspace_id"),
        )
        validation.pop("token")
        record.last_validation = validation
        record.status = self._overall_status(validation)
        record.last_validated_at = datetime.now(UTC)
        return self._view(await self._repo.update(record))

    async def update(
        self, owner_key: str, connection_id: str, req: UpdateConnectionRequest
    ) -> CloudConnection:
        """Rename / change integrations / rotate the secret. Revalidated BEFORE anything is saved."""
        record = await self._owned(owner_key, connection_id)
        client_id = record.credential_client_id
        if req.azure_client_id:
            client_id = require_guid(req.azure_client_id, "azure_client_id")
        new_secret = req.azure_client_secret.get_secret_value() if req.azure_client_secret else None
        secret = new_secret if new_secret is not None else self._decrypt(record)
        cfg = dict(record.integration_config)
        for key in ("databricks_workspace_url", "databricks_workspace_id", "fabric_workspace_id"):
            value = getattr(req, key)
            if value is not None:
                cfg[key] = value or None
        validation = await self._validate(
            record.auth_method,
            record.credential_tenant_id,
            client_id,
            secret,
            record.scope_id,
            cfg.get("databricks_workspace_url"),
            cfg.get("databricks_workspace_id"),
            cfg.get("fabric_workspace_id"),
        )
        validation.pop("token")
        if new_secret is not None:
            record.secret_ciphertext, record.secret_kid = self._cipher().encrypt(
                new_secret, record.id, owner_key
            )
        record.credential_client_id = client_id
        record.integration_config = cfg
        if req.name:
            record.name = req.name.strip()
        record.last_validation = validation
        record.status = self._overall_status(validation)
        record.last_validated_at = datetime.now(UTC)
        try:
            saved = await self._repo.update(record)
        except DuplicateConnectionError:
            raise _err(
                409, "DUPLICATE_CONNECTION", "Another connection already uses this client."
            ) from None
        logger.info("connection_updated", connection_id=saved.id, rotated=new_secret is not None)
        return self._view(saved)

    async def delete(self, owner_key: str, connection_id: str) -> None:
        if not await self._repo.delete(owner_key, connection_id):
            raise _err(404, "CONNECTION_NOT_FOUND", "The connection was not found.")
        if self._sessions is not None:
            self._sessions.discard(connection_id)  # drop any cached Azure token immediately
        logger.info("connection_deleted", connection_id=connection_id)

    # ------------------------------------------------------- use by data endpoints

    async def activate_session(self, owner_key: str, connection_id: str) -> AzureSession:
        """Mint a fresh Azure token from the stored credential and register it for data calls."""
        if self._sessions is None:
            raise _err(500, "SESSION_STORE_UNAVAILABLE", "Session store is not available.")
        record = await self._owned(owner_key, connection_id)
        secret = self._decrypt(record)
        try:
            token = await self._token(
                record.auth_method,
                record.credential_tenant_id,
                record.credential_client_id,
                secret,
                ARM_SCOPE,
            )
        except AzureCredentialError as exc:
            raise _err(
                502 if exc.upstream else 400,
                "ENTRA_UNAVAILABLE" if exc.upstream else "STORED_CREDENTIAL_REJECTED",
                exc.message
                + (" Update the connection with a new client secret." if not exc.upstream else ""),
                category=exc.category,
            ) from None
        return self._sessions.create(
            owner_key,
            record.credential_tenant_id or "",
            record.credential_client_id or "",
            token,
            connection_id=record.id,
        )


def is_persistent_connection_id(value: str) -> bool:
    return is_guid(value)
