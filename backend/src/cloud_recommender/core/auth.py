"""Microsoft Entra ID cryptographic JWT authentication and role-based authorization."""

from collections.abc import Callable
from functools import lru_cache
from typing import Any

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from cloud_recommender.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

security = HTTPBearer(auto_error=False)


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
        """Cryptographically verify token signature, expiry, audience, and issuer."""
        public_key = self._get_signing_key(token)

        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": bool(self.audience),
                "verify_iss": bool(self.valid_issuers),
            },
        }

        if self.audience:
            decode_kwargs["audience"] = self.audience

        if self.valid_issuers:
            decode_kwargs["issuer"] = self.valid_issuers

        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                key=public_key,
                **decode_kwargs,
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
        if self.tenant_id and token_tid and str(token_tid).lower() != self.tenant_id.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_TENANT",
                    "message": (
                        f"Token tenant '{token_tid}' does not match configured tenant '{self.tenant_id}'."
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
    """Extract and validate caller identity, enforcing Entra ID JWT verification when enabled."""
    if not settings.entra_auth_enabled:
        # If disabled (local dev / test), allow optional token parsing or fall back to dev identity
        if credentials and credentials.credentials:
            try:
                return validator.validate_token(credentials.credentials)
            except Exception:
                pass
        return AuthenticatedUser(
            sub="local-dev-user",
            name="Local FinOps Developer",
            preferred_username="developer@local.internal",
            roles=["Admin", "Reader", "CostManagementReader"],
            is_authenticated=True,
        )

    # Entra authentication is strictly enabled
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "MISSING_BEARER_TOKEN",
                "message": (
                    "Authorization header with a valid Bearer token is required to "
                    "access this endpoint."
                ),
            },
        )

    return validator.validate_token(credentials.credentials)


def require_authenticated_user(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Enforce that the caller is authenticated."""
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
