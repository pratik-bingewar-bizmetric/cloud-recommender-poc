"""Owner-bound persistent cloud connections: validate, encrypt, store, rotate, reuse.

One implementation for every environment (local, Fabric frontend, App Service backend). The
application user (identified by the Entra token, or the explicit development identity) is kept
strictly separate from the cloud account being connected: the cloud credentials are supplied by
the user, validated directly with Microsoft Entra ID, and stored only as ciphertext.
"""

from __future__ import annotations

import builtins
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
from cloud_recommender.schemas.gcp import (
    GcpConnectionResponse,
    GcpServiceConnectivityState,
    GcpServiceStatus,
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


def to_gcp_connection_response(record: StoredConnection) -> GcpConnectionResponse:
    last_val = record.last_validation or {}
    services_raw = last_val.get("services", [])
    services: list[GcpServiceStatus] = []
    for s in services_raw:
        if isinstance(s, dict):
            try:
                services.append(GcpServiceStatus(**s))
            except Exception:
                pass
        elif isinstance(s, GcpServiceStatus):
            services.append(s)
    return GcpConnectionResponse(
        id=record.id,
        name=record.name,
        provider="gcp",
        project_id=record.scope_id,
        client_email=record.credential_client_id or "",
        private_key_id=str(record.integration_config.get("private_key_id", "")),
        status=record.status,
        billing_status="DEFERRED",
        ownership="owned",
        created_at=record.created_at,
        last_verified_at=record.last_validated_at,
        services=services,
        warnings=list(last_val.get("warnings", [])),
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
        if record.provider == "gcp":
            services_data = validation.get("services", [])
            integrations: list[IntegrationStatus] = []
            for s in services_data:
                state_val = s.get("status") if isinstance(s, dict) else getattr(s, "status", None)
                if state_val is not None and hasattr(state_val, "value"):
                    state_val = state_val.value
                istate = (
                    IntegrationState.CONNECTED
                    if state_val == "SUCCESS"
                    else (
                        IntegrationState.DEFERRED
                        if state_val == "DEFERRED"
                        else (
                            IntegrationState.PERMISSION_DENIED
                            if state_val == "PERMISSION_DENIED"
                            else IntegrationState.UNAVAILABLE
                        )
                    )
                )
                svc_id = str(s.get("service") if isinstance(s, dict) else getattr(s, "service", ""))
                svc_msg = s.get("message") if isinstance(s, dict) else getattr(s, "message", None)
                svc_role = (
                    s.get("required_role_or_permission")
                    if isinstance(s, dict)
                    else getattr(s, "required_role_or_permission", None)
                )
                integrations.append(
                    IntegrationStatus(
                        integration=svc_id,
                        state=istate,
                        message=svc_msg,
                        required_permission=svc_role,
                        details=s.get("details", {})
                        if isinstance(s, dict)
                        else getattr(s, "details", {}),
                    )
                )
        else:
            integrations = [IntegrationStatus(**i) for i in validation.get("integrations", [])]

        labels = {
            "resource_manager": "resource_inventory",
            "cost_management": "cost_management",
            "monitor": "metrics",
            "databricks": "databricks",
            "fabric": "fabric",
            "cloud_resource_manager": "resource_inventory",
            "cloud_asset_inventory": "asset_inventory",
            "cloud_storage": "storage",
            "cloud_sql": "sql",
            "compute_engine": "compute",
            "cloud_monitoring": "metrics",
            "cloud_recommender": "recommendations",
            "service_usage": "service_usage",
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
        if req.provider == CloudProvider.GCP:
            if not req.gcp_service_account_json:
                raise _err(
                    422,
                    "MISSING_REQUIRED_FIELDS",
                    "Service Account JSON is required for GCP persistent connection.",
                    fields=["gcp_service_account_json"],
                )
            gcp_resp = await self.create_gcp(
                owner_key=owner_key,
                name=req.name,
                project_id=req.scope_id,
                service_account_json=req.gcp_service_account_json,
            )
            stored_gcp = await self._owned(owner_key, gcp_resp.id)
            return self._view(stored_gcp)

        if req.provider != CloudProvider.AZURE:
            raise _err(
                400, "UNSUPPORTED_PROVIDER", "Persistent connections support Azure and GCP only."
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
        if record.provider == "gcp":
            secret = self._decrypt(record)
            if not secret:
                raise _err(
                    400, "MISSING_CREDENTIALS", "Stored GCP Service Account credentials not found."
                )
            from cloud_recommender.services.gcp.connectivity_service import (
                get_gcp_connectivity_service,
            )

            conn_service = get_gcp_connectivity_service()
            test_res = await conn_service.test_connection(
                service_account_json=secret,
                project_id=record.scope_id,
                connection_name=record.name,
            )
            status_str = (
                "connected"
                if test_res.overall_status in ("Connected", "Partially Connected")
                else (
                    "permission_denied"
                    if test_res.overall_status == "Permission Denied"
                    else "auth_failed"
                )
            )
            record.last_validation = {
                "services": [s.model_dump(mode="json") for s in test_res.services],
                "overall_status": test_res.overall_status,
                "warnings": [
                    s.message
                    for s in test_res.services
                    if s.status != GcpServiceConnectivityState.SUCCESS and s.message
                ],
            }
            record.status = status_str
            record.last_validated_at = datetime.now(UTC)
            return self._view(await self._repo.update(record))

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

    # ------------------------------------------------------------- GCP Methods

    async def create_gcp(
        self,
        owner_key: str,
        name: str,
        project_id: str,
        service_account_json: str,
    ) -> GcpConnectionResponse:
        if not name or not name.strip() or len(name.strip()) < 2 or len(name.strip()) > 100:
            raise _err(
                422,
                "INVALID_CONNECTION_NAME",
                "Connection name must be between 2 and 100 characters.",
            )
        clean_project = (project_id or "").strip()
        if not clean_project or len(clean_project) < 4 or len(clean_project) > 30:
            raise _err(
                422,
                "INVALID_PROJECT_ID",
                "GCP project ID must be between 4 and 30 characters.",
            )

        existing = await self._repo.list(owner_key)
        for ec in existing:
            if ec.provider == "gcp" and ec.scope_id.lower() == clean_project.lower():
                raise _err(
                    409,
                    "DUPLICATE_CONNECTION",
                    f"A connection for GCP project '{clean_project}' already exists.",
                )

        from cloud_recommender.services.gcp.connectivity_service import (
            get_gcp_connectivity_service,
        )

        conn_service = get_gcp_connectivity_service()
        test_res = await conn_service.test_connection(
            service_account_json=service_account_json,
            project_id=clean_project,
            connection_name=name.strip(),
        )
        if not test_res.success and test_res.overall_status in (
            "Authentication Failed",
            "Permission Denied",
        ):
            raise _err(
                400,
                "GCP_VALIDATION_FAILED",
                test_res.error_summary
                or f"Failed to validate GCP project '{project_id}': {test_res.overall_status}",
            )

        if await self._repo.count(owner_key) >= self._settings.connections_max_per_user:
            raise _err(
                409,
                "CONNECTION_LIMIT_REACHED",
                "Maximum number of connections reached. Delete one first.",
            )

        cipher = self._cipher()
        connection_id = str(uuid.uuid4())
        ciphertext, kid = cipher.encrypt(service_account_json.strip(), connection_id, owner_key)

        status_str = (
            "connected"
            if test_res.overall_status in ("Connected", "Partially Connected")
            else (
                "permission_denied"
                if test_res.overall_status == "Permission Denied"
                else "auth_failed"
            )
        )
        record = StoredConnection(
            id=connection_id,
            owner_key=owner_key,
            provider="gcp",
            auth_method="service_account",
            name=name.strip(),
            scope_id=test_res.project_id,
            credential_tenant_id=None,
            credential_client_id=test_res.client_email,
            secret_ciphertext=ciphertext,
            secret_kid=kid,
            integration_config={
                "private_key_id": test_res.private_key_id,
                "client_email": test_res.client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            last_validation={
                "services": [s.model_dump(mode="json") for s in test_res.services],
                "overall_status": test_res.overall_status,
                "warnings": [
                    s.message
                    for s in test_res.services
                    if s.status != GcpServiceConnectivityState.SUCCESS and s.message
                ],
            },
            status=status_str,
            last_validated_at=datetime.now(UTC),
        )
        try:
            stored = await self._repo.add(record)
        except DuplicateConnectionError:
            raise _err(
                409,
                "DUPLICATE_CONNECTION",
                "You already have a connection for this GCP project and Service Account.",
            ) from None
        logger.info(
            "gcp_connection_created",
            connection_id=stored.id,
            project_id=stored.scope_id,
            client_email=stored.credential_client_id,
        )
        return to_gcp_connection_response(stored)

    async def list_gcp(self, owner_key: str) -> builtins.list[GcpConnectionResponse]:
        records = await self._repo.list(owner_key)
        return [to_gcp_connection_response(r) for r in records if r.provider == "gcp"]

    async def get_gcp(self, owner_key: str, connection_id: str) -> GcpConnectionResponse:
        record = await self._owned(owner_key, connection_id)
        if record.provider != "gcp":
            raise _err(
                404,
                "CONNECTION_NOT_FOUND",
                f"Connection '{connection_id}' is not a GCP connection.",
            )
        return to_gcp_connection_response(record)

    async def decrypt_gcp_secret(
        self, owner_key: str, connection_id: str
    ) -> tuple[StoredConnection, str]:
        record = await self._owned(owner_key, connection_id)
        if record.provider != "gcp":
            raise _err(
                404,
                "CONNECTION_NOT_FOUND",
                f"Connection '{connection_id}' is not a GCP connection.",
            )
        secret = self._decrypt(record)
        if not secret:
            raise _err(
                400, "MISSING_CREDENTIALS", "Stored GCP Service Account credentials not found."
            )
        return record, secret


def is_persistent_connection_id(value: str) -> bool:
    return is_guid(value)
