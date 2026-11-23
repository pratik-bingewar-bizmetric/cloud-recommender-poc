"""Microsoft Entra ID cryptographic JWT authentication and role-based authorization."""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from cloud_recommender.core.config import Settings, get_settings, is_hosted_runtime

logger = structlog.get_logger(__name__)

security = HTTPBearer(auto_error=False)

# --------------------------------------------------------------------------------------
# Authorization model (simplified: authenticated user + restricted operations)
#
# Layers (all applied to every protected route through ``enforce_route_policy``):
#   1. Authentication  - valid Entra JWT (401 otherwise).
#   2. Client approval - ``azp``/``appid`` must be in ENTRA_ALLOWED_CLIENT_IDS when configured
#                        (mandatory in production)                              -> 403.
#   3. API access      - delegated (user) tokens need a required scope (``scp``, default
#                        ``access_as_user``); application-only (daemon) tokens need the separate
#                        application permission ``FinOpsDaemon`` and nothing else   -> 403.
#   4. Operation class - see below                                              -> 403.
#
# Operation classes
#   P  public        : health/catalog/root, excluded from the protected routers.
#   U  user          : any authenticated *user* (delegated token): every GET, plus the explicit
#                      non-GET list ``USER_NON_GET_ENDPOINTS``.
#   R  restricted    : needs the single role ``FinOpsAdmin`` on a *user* token. Default for any
#                      non-GET endpoint that is not explicitly classified (secure by default).
#   D  daemon        : application tokens may call ONLY ``DAEMON_ALLOWED_ENDPOINTS`` (read-only
#                      organization status endpoints). Daemon tokens never receive user or
#                      restricted permissions, and restricted/human-approval operations are
#                      unreachable for them.
# Personal-connection (owner) operations are introduced with the persistent connection layer
# (Stage B); until then the connection create/validate/configuration operations stay restricted.
# A valid signature + audience alone never grants access.
# --------------------------------------------------------------------------------------
ROLE_FINOPS_ADMIN = "FinOpsAdmin"
ROLE_FINOPS_DAEMON = "FinOpsDaemon"
RESTRICTED_ROLES: tuple[str, ...] = (ROLE_FINOPS_ADMIN,)

SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})

_ROUTES = "cloud_recommender.api.routes"

# Class U: non-GET endpoints open to any authenticated user. Each one persists nothing that
# affects other users beyond attributed audit records / advisory status, executes no SQL or
# warehouse compute, and mutates no cloud resource. Keyed by "<module>.<function>".
USER_NON_GET_ENDPOINTS: frozenset[str] = frozenset(
    {
        # read-only computations
        f"{_ROUTES}.analysis.analyze_requirements",
        f"{_ROUTES}.architecture.generate_architecture",
        f"{_ROUTES}.finops.simulate_scenario",
        f"{_ROUTES}.inventory.analyze_azure_subscription",
        f"{_ROUTES}.inventory.analyze_gcp_project",
        f"{_ROUTES}.inventory.compare_multi_cloud",
        f"{_ROUTES}.monitoring.get_monitoring_overview",
        f"{_ROUTES}.monitoring.get_resource_monitoring_detail",
        f"{_ROUTES}.monitoring.search_monitoring_logs",
        f"{_ROUTES}.monitoring.get_token_economics",
        f"{_ROUTES}.pricing.simulate_costs",
        # organization (Databricks) connectivity checks: REST only, no SQL, no compute
        f"{_ROUTES}.databricks.test_databricks_connection",
        f"{_ROUTES}.databricks.refresh_workspace_discovery",
        f"{_ROUTES}.finops.validate_ingestion",
        f"{_ROUTES}.finops.preview_ingestion",
        # advisory records with actor attribution (zero-execution: nothing is applied)
        f"{_ROUTES}.finops.record_decision_action",
        f"{_ROUTES}.finops.update_finops_anomaly_status",
        # shared price cache refresh, throttled by a cooldown (see core/refresh_guard.py)
        f"{_ROUTES}.pricing.refresh_prices",
        # live Azure connection (user-supplied service principal); ownership is enforced by the
        # owner-bound session store (404 for another user's connection)
        f"{_ROUTES}.azure_live.connect_azure",
        f"{_ROUTES}.azure_live.validate_azure_connection",
        f"{_ROUTES}.azure_live.disconnect_azure",
        # service-principal authentication and session management
        f"{_ROUTES}.auth.connect",
        f"{_ROUTES}.auth.logout",
        # owner-bound persistent connections (ownership enforced by the repository: 404 otherwise)
        f"{_ROUTES}.connections.create_connection",
        f"{_ROUTES}.connections.validate_connection",
        f"{_ROUTES}.connections.validate_owned_connection",
        f"{_ROUTES}.connections.update_connection",
        f"{_ROUTES}.connections.delete_connection",
        # GCP Service Account connections and validation
        f"{_ROUTES}.gcp.test_gcp_connection",
        f"{_ROUTES}.gcp.create_gcp_connection",
        f"{_ROUTES}.gcp.delete_gcp_connection",
    }
)

# Class D: the only endpoints an application-only (daemon) token may call. Read-only
# organization status endpoints; no user data, no mutation, no restricted operation.
DAEMON_ALLOWED_ENDPOINTS: frozenset[str] = frozenset(
    {
        f"{_ROUTES}.databricks.list_databricks_connections",
        f"{_ROUTES}.databricks.get_workspace_health",
        f"{_ROUTES}.finops.get_ingestion_status",
        f"{_ROUTES}.finops.get_ingestion_runs",
    }
)


class AuthenticatedUser(BaseModel):
    """Normalized identity representation of an authenticated Entra ID caller."""

    sub: str = Field(description="Subject identifier (unique user or service principal ID)")
    oid: str | None = Field(default=None, description="Microsoft Entra object ID")
    tid: str | None = Field(default=None, description="Microsoft Entra tenant ID")
    name: str | None = Field(default=None, description="Display name of the user or caller")
    preferred_username: str | None = Field(default=None, description="User principal name or email")
    roles: list[str] = Field(
        default_factory=list, description="Application roles assigned in Entra ID"
    )
    scopes: list[str] = Field(
        default_factory=list, description="Delegated permission scopes granted"
    )
    raw_claims: dict[str, Any] = Field(
        default_factory=dict, description="Complete verified JWT claims payload"
    )
    is_authenticated: bool = Field(
        default=True, description="Whether the token was cryptographically verified"
    )
    client_id: str | None = Field(
        default=None, description="Calling application (azp for v2 tokens, appid for v1 tokens)"
    )
    is_development_identity: bool = Field(
        default=False, description="True only for the explicit local-development identity"
    )
    is_session_token: bool = Field(
        default=False, description="True for application session bearer tokens"
    )
    session_id: str | None = Field(
        default=None, description="Active session ID if authenticated via app session"
    )
    is_application_token: bool = Field(
        default=False,
        description="True for application-only (daemon) tokens, i.e. tokens without a `scp` claim",
    )


class EntraTokenValidator:
    """Cryptographic validator for Microsoft Entra ID issued RS256 JWTs."""

    def __init__(
        self,
        settings: Settings | None = None,
        jwks_client: Any = None,
        test_keys: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tenant_id = (self.settings.entra_tenant_id or "").strip()
        self.audience = (self.settings.entra_audience or "").strip() or None
        self.test_keys = test_keys or {}

        # Valid Microsoft Entra ID token issuers (v1 and v2 formats)
        self.valid_issuers: list[str] = []
        if self.tenant_id:
            self.valid_issuers = [
                f"https://login.microsoftonline.com/{self.tenant_id}/v2.0",
                f"https://sts.windows.net/{self.tenant_id}/",
            ]

        # Initialize PyJWKClient for live key retrieval if not in test/override mode
        self.jwks_client = jwks_client
        if not self.jwks_client and not self.test_keys and self.tenant_id:
            jwks_url = f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"
            try:
                self.jwks_client = jwt.PyJWKClient(
                    jwks_url,
                    cache_keys=True,
                    max_cached_keys=16,
                )
            except Exception as exc:
                logger.warning("entra_jwks_client_init_failed", error=str(exc))

    def _get_signing_key(self, token: str) -> Any:
        """Resolve public key from unverified JWT header using JWKS or test keys."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "MALFORMED_TOKEN",
                    "message": f"Unable to parse JWT header: {exc}",
                },
            ) from exc

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg")

        if alg != "RS256":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "UNSUPPORTED_ALGORITHM",
                    "message": f"Unsupported token algorithm '{alg}'. RS256 is required.",
                },
            )

        # Check injected test keys first (for isolated offline tests)
        if kid and kid in self.test_keys:
            return self.test_keys[kid]
        if "default" in self.test_keys:
            return self.test_keys["default"]

        # Retrieve live key from Microsoft JWKS
        if self.jwks_client:
            try:
                signing_key = self.jwks_client.get_signing_key_from_jwt(token)
                return signing_key.key
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error_code": "KEY_NOT_FOUND",
                        "message": f"Public key for token kid '{kid}' not found in JWKS: {exc}",
                    },
                ) from exc

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "JWKS_UNAVAILABLE",
                "message": "Signing keys could not be resolved from Entra ID JWKS endpoint.",
            },
        )

    def validate_token(self, token: str) -> AuthenticatedUser:
        """Cryptographically verify token signature, expiry, not-before, audience, issuer, tenant.

        Fails closed: a missing tenant or audience configuration rejects every token (401).
        """
        if not self.tenant_id or not self.audience or not self.valid_issuers:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "AUTH_NOT_CONFIGURED",
                    "message": (
                        "Bearer tokens cannot be validated because ENTRA_TENANT_ID and "
                        "ENTRA_AUDIENCE are not configured."
                    ),
                },
            )

        public_key = self._get_signing_key(token)

        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                key=public_key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.valid_issuers,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "require": ["exp", "nbf", "iss", "aud"],
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "TOKEN_EXPIRED",
                    "message": "The Entra ID authentication token has expired.",
                },
            ) from exc
        except jwt.InvalidAudienceError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_AUDIENCE",
                    "message": (
                        f"Token audience does not match configured backend audience: {exc}"
                    ),
                },
            ) from exc
        except jwt.MissingRequiredClaimError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "MALFORMED_TOKEN",
                    "message": f"Token is missing a required claim: {exc.claim}.",
                },
            ) from exc
        except jwt.InvalidIssuerError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_ISSUER",
                    "message": f"Token issuer does not match Microsoft Entra tenant: {exc}",
                },
            ) from exc
        except jwt.InvalidSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_SIGNATURE",
                    "message": "Cryptographic signature verification failed for Entra ID token.",
                },
            ) from exc
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "MALFORMED_TOKEN",
                    "message": f"Token decoding failed: {exc}",
                },
            ) from exc

        # Explicit tenant ID check for multi-tenant token isolation
        token_tid = payload.get("tid")
        if not token_tid or str(token_tid).lower() != self.tenant_id.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_TENANT",
                    "message": (
                        "Token tenant does not match the configured Microsoft Entra tenant."
                    ),
                },
            )

        # Parse roles and scopes
        raw_roles = payload.get("roles", [])
        roles = [raw_roles] if isinstance(raw_roles, str) else list(raw_roles)

        raw_scp = payload.get("scp", "")
        scopes = raw_scp.split(" ") if isinstance(raw_scp, str) and raw_scp else []

        return AuthenticatedUser(
            sub=str(payload.get("sub", payload.get("oid", "unknown-user"))),
            oid=payload.get("oid"),
            tid=payload.get("tid"),
            name=payload.get("name"),
            preferred_username=payload.get("preferred_username") or payload.get("upn"),
            roles=roles,
            scopes=scopes,
            raw_claims=payload,
            is_authenticated=True,
            client_id=str(payload.get("azp") or payload.get("appid") or "") or None,
            is_application_token=not scopes,
        )


@lru_cache
def get_token_validator() -> EntraTokenValidator:
    """Return cached EntraTokenValidator instance."""
    settings = get_settings()
    return EntraTokenValidator(settings=settings)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
    validator: EntraTokenValidator = Depends(get_token_validator),
) -> AuthenticatedUser:
    """Resolve the caller identity.

    - A supplied bearer token is ALWAYS validated; an invalid token yields 401 in every mode
      and is never downgraded to a development identity.
    - Without a token: 401 when Entra auth is enabled. Only when Entra auth is disabled, the
      environment is development/testing AND DEV_AUTH_ENABLED is set, a least-privilege
      development identity is returned. Production can never reach that branch (the settings
      validator rejects it at startup, and it is re-checked here).
    """
    token = credentials.credentials if credentials and credentials.credentials else None
    if token:
        if token.startswith("finops_sess_"):
            from cloud_recommender.core.app_sessions import get_app_session_store

            session_store = get_app_session_store()
            session = session_store.get_session_by_token(token)
            if not session:
                token_hash = session_store.hash_token(token)
                cached = session_store.get_session_by_hash(token_hash)
                if cached:
                    if cached.revoked_at is not None:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={
                                "error_code": "SESSION_REVOKED",
                                "message": "The application session has been revoked. Please reconnect.",
                            },
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                    if datetime.now(UTC) >= cached.expires_at:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={
                                "error_code": "SESSION_EXPIRED",
                                "message": "The application session has expired. Please reconnect.",
                            },
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error_code": "INVALID_SESSION_TOKEN",
                        "message": "The application session token is invalid or does not exist.",
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return AuthenticatedUser(
                sub=session.account_id,
                oid=session.account_id,
                tid=session.tenant_id,
                name=session.account_name,
                preferred_username=f"{session.client_id}@{session.tenant_id}",
                roles=list(session.roles),
                scopes=["access_as_user"],
                raw_claims={
                    "session_id": session.session_id,
                    "account_id": session.account_id,
                    "account_name": session.account_name,
                    "subscription_id": session.subscription_id,
                    "subscription_name": session.subscription_name,
                    "connection_id": session.connection_id,
                    "tenant_id": session.tenant_id,
                    "client_id": session.client_id,
                    "permissions": session.permissions,
                },
                is_authenticated=True,
                client_id=session.client_id,
                is_session_token=True,
                session_id=session.session_id,
            )

        return validator.validate_token(token)

    if settings.entra_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "MISSING_BEARER_TOKEN",
                "message": (
                    "Authorization header with a valid Bearer token is required to "
                    "access this endpoint."
                ),
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    if (
        settings.dev_auth_enabled
        and settings.app_env in ("development", "testing")
        and not is_hosted_runtime()
    ):
        logger.warning("development_authentication_identity_used")
        return AuthenticatedUser(
            sub="local-dev-user",
            name="Local FinOps Developer",
            preferred_username="developer@local.internal",
            roles=list(settings.dev_auth_roles),
            is_authenticated=True,
            is_development_identity=True,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error_code": "AUTHENTICATION_REQUIRED",
            "message": (
                "Authentication is required. Configure ENTRA_AUTH_ENABLED=true "
                "(or DEV_AUTH_ENABLED=true for local development only)."
            ),
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_authenticated_user(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Enforce that the caller is authenticated (identity only; see ``require_api_access``)."""
    return user


def describe_auth_mode(settings: Settings) -> tuple[str, str]:
    """Return (mode, hint) describing how protected endpoints authenticate callers.

    Modes: ``entra`` (bearer tokens required), ``development_identity`` (tokenless requests get
    the local development identity) or ``none`` (every protected request returns 401 until
    authentication is configured). Used for an actionable startup message; contains no secrets.
    """
    if settings.entra_auth_enabled:
        return "entra", "Microsoft Entra bearer tokens are required."
    if settings.dev_auth_enabled and settings.app_env in ("development", "testing"):
        roles = ",".join(settings.dev_auth_roles) or "none"
        return (
            "development_identity",
            f"Tokenless requests use the local development identity (roles: {roles}). "
            "Local development only.",
        )
    return (
        "none",
        "Protected endpoints will return 401. For local development set DEV_AUTH_ENABLED=true "
        '(and DEV_AUTH_ROLES=["FinOpsAdmin"] for restricted operations) in the .env file the '
        "backend loads, or enable Entra authentication.",
    )


def owner_key_for(user: AuthenticatedUser) -> str:
    """Ownership key derived from the validated token: tenant + object id (never client input)."""
    if user.is_development_identity:
        return "dev:local-development"
    return f"{user.tid or 'no-tenant'}:{user.oid or user.sub}"


def actor_for(user: AuthenticatedUser) -> str:
    """Stable audit identity derived from the validated token (never from request input)."""
    if not isinstance(
        user, AuthenticatedUser
    ):  # route invoked directly, outside dependency injection
        return "unattributed"
    return user.preferred_username or user.name or user.oid or user.sub


def _forbidden(error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error_code": error_code, "message": message},
    )


def require_api_access(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    """Baseline authorization: approved client + scope (user tokens) or daemon permission."""
    if user.is_development_identity or user.is_session_token:
        return user

    allowed_clients = {c.lower() for c in settings.entra_allowed_client_ids}
    if allowed_clients and (user.client_id or "").lower() not in allowed_clients:
        raise _forbidden(
            "UNAPPROVED_CLIENT_APPLICATION",
            "The calling application is not approved to use this API.",
        )

    if user.is_application_token:
        if ROLE_FINOPS_DAEMON not in user.roles:
            raise _forbidden(
                "INSUFFICIENT_APPLICATION_PERMISSION",
                "The application token does not carry the required application permission.",
            )
    elif not set(user.scopes) & set(settings.entra_required_scopes):
        raise _forbidden(
            "INSUFFICIENT_SCOPE",
            "The token does not carry a required scope for this API.",
        )
    return user


def _endpoint_id(request: Request) -> str | None:
    endpoint = getattr(request.scope.get("route"), "endpoint", None)
    if endpoint is None:
        return None
    return f"{endpoint.__module__}.{endpoint.__qualname__}"


def enforce_route_policy(
    request: Request,
    user: AuthenticatedUser = Depends(require_api_access),
) -> AuthenticatedUser:
    """Router-level policy: operation class U / R for users, class D for daemon tokens."""
    endpoint = _endpoint_id(request)

    if user.is_application_token:
        if endpoint not in DAEMON_ALLOWED_ENDPOINTS:
            raise _forbidden(
                "OPERATION_NOT_PERMITTED_FOR_APPLICATION",
                "Application tokens may only call the designated read-only status endpoints.",
            )
        return user

    if request.method in SAFE_METHODS or endpoint in USER_NON_GET_ENDPOINTS:
        return user

    if not set(user.roles) & set(RESTRICTED_ROLES):
        raise _forbidden(
            "INSUFFICIENT_PERMISSIONS",
            f"This operation requires the application role {list(RESTRICTED_ROLES)}.",
        )
    return user


def require_roles(*allowed_roles: str) -> Callable[..., AuthenticatedUser]:
    """FastAPI dependency factory enforcing that caller holds at least one of the specified roles."""

    def role_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not allowed_roles:
            return user
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "INSUFFICIENT_PERMISSIONS",
                    "message": (
                        f"Caller lacks required roles. Required one of: {list(allowed_roles)}. "
                        f"Assigned roles: {user.roles}."
                    ),
                },
            )
        return user

    return role_checker
