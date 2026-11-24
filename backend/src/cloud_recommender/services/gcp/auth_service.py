"""GCP Service Account authentication, credential validation, and OAuth2 token management.

Strict Security Invariants:
1. Production Service Account credentials only: never uses gcloud CLI or human ADC fallbacks.
2. Private keys and generated tokens are strictly redacted from logs, traces, and API outputs.
3. RSA private keys are validated cryptographically via google-auth and cryptography.
4. Token acquisition uses strictly read-only cloud-platform scopes.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import structlog
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import service_account

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

from cloud_recommender.schemas.gcp import GcpServiceAccountInfo

logger = structlog.get_logger(__name__)

READONLY_SCOPE = "https://www.googleapis.com/auth/cloud-platform.read-only"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DEFAULT_SCOPES = [CLOUD_PLATFORM_SCOPE]
AZURE_UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
GCP_PROJECT_ID_REGEX = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


def _sanitize_auth_error(msg: str) -> str:
    """Scrub tokens, keys, and secret parameters from error strings before returning to clients."""
    clean = re.sub(r"ya29\.[a-zA-Z0-9_\-]+", "[REDACTED_TOKEN]", msg, flags=re.IGNORECASE)
    clean = re.sub(
        r"-----BEGIN[^-]+-----.*?-----END[^-]+-----",
        "[REDACTED_KEY]",
        clean,
        flags=re.DOTALL,
    )
    clean = re.sub(r"key=[^&\s]+", "key=[REDACTED]", clean, flags=re.IGNORECASE)
    return clean.strip()


class GcpAuthenticationError(Exception):
    """Raised when Service Account credentials fail validation or token exchange."""

    def __init__(self, message: str, error_code: str = "AUTHENTICATION_FAILED") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class GcpToken:
    """In-memory wrapper for a validated GCP OAuth2 bearer token."""

    def __init__(self, token: str, expiry: datetime | None = None) -> None:
        self.token = token
        self.expiry = expiry

    def is_expired(self, buffer_seconds: int = 180) -> bool:
        """Check whether token is expired or within a safety buffer window."""
        if not self.expiry:
            return False
        return (self.expiry - datetime.now(UTC)).total_seconds() < buffer_seconds


class GcpAuthService:
    """Validates GCP Service Account credentials and produces OAuth2 access tokens."""

    def __init__(self) -> None:
        self._token_cache: dict[str, GcpToken] = {}

    def parse_and_validate_json(
        self, raw_json: str | dict[str, Any], expected_project_id: str | None = None
    ) -> tuple[dict[str, Any], GcpServiceAccountInfo]:
        """Validate Service Account JSON structure and return parsed dict and safe info.

        Never logs or exposes the private_key field.
        """
        if isinstance(raw_json, str):
            clean_str = raw_json.strip()
            if not clean_str:
                raise GcpAuthenticationError(
                    "Service Account JSON is empty.", "MALFORMED_CREDENTIALS"
                )
            try:
                data: dict[str, Any] = json.loads(clean_str)
            except json.JSONDecodeError as exc:
                raise GcpAuthenticationError(
                    f"Service Account key is not valid JSON: {exc.msg}", "INVALID_JSON"
                ) from exc
        elif isinstance(raw_json, dict):
            data = dict(raw_json)
        else:
            raise GcpAuthenticationError(
                "Service Account credentials must be a JSON string or dictionary.",
                "INVALID_CREDENTIAL_TYPE",
            )

        # 1. Validate 'type'
        cred_type = data.get("type")
        if cred_type != "service_account":
            raise GcpAuthenticationError(
                f"Invalid credential type '{cred_type}'. Must be 'service_account'. "
                "User OAuth2 Client credentials and API keys are not permitted.",
                "INVALID_CREDENTIAL_TYPE",
            )

        # 2. Validate client_email
        client_email = str(data.get("client_email", "")).strip()
        if not client_email or "@" not in client_email:
            raise GcpAuthenticationError(
                "Missing or invalid 'client_email' in Service Account JSON.",
                "INVALID_CLIENT_EMAIL",
            )

        # 3. Validate project_id
        project_id = str(data.get("project_id", "")).strip()
        if not project_id:
            raise GcpAuthenticationError(
                "Missing 'project_id' in Service Account JSON.",
                "INVALID_PROJECT_ID",
            )

        if AZURE_UUID_REGEX.match(project_id):
            raise GcpAuthenticationError(
                f"Invalid GCP Project ID '{project_id}': Project ID is formatted as an Azure UUID.",
                "INVALID_PROJECT_ID",
            )

        if expected_project_id:
            exp = expected_project_id.strip()
            if exp and exp != project_id:
                raise GcpAuthenticationError(
                    f"Configured Project ID '{exp}' does not match Service Account project '{project_id}'.",
                    "PROJECT_ID_MISMATCH",
                )

        # 4. Validate private_key
        private_key = str(data.get("private_key", "")).strip()
        if not private_key:
            raise GcpAuthenticationError(
                "Missing 'private_key' in Service Account JSON.",
                "MISSING_PRIVATE_KEY",
            )
        if "-----BEGIN PRIVATE KEY-----" not in private_key:
            raise GcpAuthenticationError(
                "Malformed 'private_key': Missing PEM header '-----BEGIN PRIVATE KEY-----'.",
                "INVALID_PRIVATE_KEY_FORMAT",
            )

        # 5. Validate private_key_id
        private_key_id = str(data.get("private_key_id", "")).strip()
        if not private_key_id:
            raise GcpAuthenticationError(
                "Missing 'private_key_id' in Service Account JSON.",
                "MISSING_KEY_ID",
            )

        # Safe non-secret info model
        info = GcpServiceAccountInfo(
            project_id=project_id,
            client_email=client_email,
            private_key_id=private_key_id,
            client_id=str(data.get("client_id", "")) or None,
            auth_uri=str(data.get("auth_uri", "")) or None,
            token_uri=str(data.get("token_uri", "https://oauth2.googleapis.com/token")),
        )

        return data, info

    def acquire_token(self, creds_data: dict[str, Any], scopes: list[str] | None = None) -> str:
        """Obtain a valid OAuth2 access token using official Google Service Account JWT signing.

        Caches active tokens in memory partitioned by (client_email, private_key_id, scopes).
        """
        client_email = str(creds_data.get("client_email", "")).strip().lower()
        key_id = str(creds_data.get("private_key_id", "")).strip()
        effective_scopes = list(scopes) if scopes else DEFAULT_SCOPES
        scope_str = ",".join(sorted(effective_scopes))
        cache_key = f"{client_email}:{key_id}:{scope_str}"

        cached = self._token_cache.get(cache_key)
        if cached and not cached.is_expired():
            return cached.token

        try:
            creds = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
                creds_data,
                scopes=effective_scopes,
            )
            request = Request()
            creds.refresh(request)
        except TransportError as exc:
            logger.warning(
                "gcp_token_acquisition_transport_error",
                client_email=creds_data.get("client_email"),
                error_type=type(exc).__name__,
            )
            clean_err = _sanitize_auth_error(str(exc))
            raise GcpAuthenticationError(
                f"Network transport error connecting to Google OAuth2 token endpoint: {clean_err}",
                "SERVICE_UNAVAILABLE",
            ) from exc
        except GoogleAuthError as exc:
            logger.warning(
                "gcp_token_acquisition_auth_error",
                client_email=creds_data.get("client_email"),
                error_type=type(exc).__name__,
            )
            clean_err = _sanitize_auth_error(str(exc))
            raise GcpAuthenticationError(
                f"Google Service Account authentication failed: {clean_err}",
                "AUTHENTICATION_FAILED",
            ) from exc
        except Exception as exc:
            logger.error(
                "gcp_token_acquisition_unexpected_error",
                client_email=creds_data.get("client_email"),
                error_type=type(exc).__name__,
            )
            raise GcpAuthenticationError(
                f"Failed to sign JWT or acquire token: {type(exc).__name__}",
                "TOKEN_EXCHANGE_ERROR",
            ) from exc

        token_str = str(creds.token) if creds.token else ""
        if not token_str:
            raise GcpAuthenticationError(
                "Google OAuth2 token endpoint returned an empty access token.",
                "EMPTY_TOKEN_RECEIVED",
            )

        expiry = creds.expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)

        self._token_cache[cache_key] = GcpToken(token=token_str, expiry=expiry)
        return token_str

    async def verify_principal(
        self,
        token: str,
        expected_client_id: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        """Verify the acquired OAuth2 token and establish principal identity via Google's tokeninfo.

        Validates that Google's token servers recognize the token as active and unexpired,
        and that the authorized party (azp) matches the Service Account's OAuth2 client ID.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"access_token": token},
                )
                if resp.status_code != 200:
                    clean_detail = _sanitize_auth_error(resp.text)
                    raise GcpAuthenticationError(
                        f"Google tokeninfo rejected token with HTTP {resp.status_code}: {clean_detail}",
                        "TOKEN_VERIFICATION_FAILED",
                    )
                data: dict[str, Any] = resp.json()

                azp = data.get("azp") or data.get("aud")
                if expected_client_id and azp != expected_client_id:
                    raise GcpAuthenticationError(
                        f"Principal mismatch: Token authorized party '{azp}' does not match expected client ID '{expected_client_id}'.",
                        "PRINCIPAL_MISMATCH",
                    )
                return data
        except GcpAuthenticationError:
            raise
        except Exception as exc:
            clean_err = _sanitize_auth_error(str(exc))
            raise GcpAuthenticationError(
                f"Failed to verify principal identity with Google tokeninfo: {clean_err}",
                "TOKEN_VERIFICATION_NETWORK_ERROR",
            ) from exc


# Singleton instance
_auth_service: GcpAuthService | None = None


def get_gcp_auth_service() -> GcpAuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = GcpAuthService()
    return _auth_service
