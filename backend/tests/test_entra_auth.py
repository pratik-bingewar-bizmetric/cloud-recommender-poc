"""Automated unit and integration tests for Microsoft Entra ID JWT authentication."""

import time
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from cloud_recommender.core.auth import (
    EntraTokenValidator,
    get_token_validator,
    require_roles,
)
from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.main import create_app

TENANT_ID = "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"
AUDIENCE = "api://cloud-recommender-poc"
VALID_V2_ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
VALID_V1_ISSUER = f"https://sts.windows.net/{TENANT_ID}/"


@pytest.fixture(scope="module")
def rsa_key_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate a 2048-bit RSA key pair for cryptographic token signing and verification."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(scope="module")
def foreign_rsa_key_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate a separate RSA key pair to simulate invalid cryptographic signatures."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def make_token(
    private_key: rsa.RSAPrivateKey,
    kid: str = "test-key-id",
    issuer: str = VALID_V2_ISSUER,
    audience: str = AUDIENCE,
    sub: str = "user-12345",
    tid: str = TENANT_ID,
    roles: list[str] | None = None,
    scopes: str = "Workload.Read Workload.Write",
    expires_in_seconds: int = 3600,
) -> str:
    """Helper to generate and cryptographically sign a test Entra ID JWT."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": sub,
        "oid": str(uuid4()),
        "tid": tid,
        "name": "Jane FinOps Architect",
        "preferred_username": "jane@enterprise.com",
        "roles": roles if roles is not None else ["Admin", "Reader"],
        "scp": scopes,
        "iat": now,
        "nbf": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def auth_enabled_settings() -> Settings:
    return Settings(
        app_env="testing",
        catalog_offline_mode=True,
        entra_auth_enabled=True,
        entra_tenant_id=TENANT_ID,
        entra_audience=AUDIENCE,
    )


@pytest.fixture
def app_with_entra(
    auth_enabled_settings: Settings,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> FastAPI:
    """Create FastAPI test app with Entra ID authentication strictly enabled and test JWKS."""
    _priv, pub = rsa_key_pair
    app = create_app(settings=auth_enabled_settings)
    app.dependency_overrides[get_settings] = lambda: auth_enabled_settings

    # Provide token validator configured with the test RSA public key
    validator = EntraTokenValidator(
        settings=auth_enabled_settings,
        test_keys={"test-key-id": pub, "default": pub},
    )
    app.dependency_overrides[get_token_validator] = lambda: validator
    return app


@pytest.mark.asyncio
async def test_valid_token_authenticated_successfully(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify cryptographically signed token is accepted on protected endpoints."""
    priv, _ = rsa_key_pair
    token = make_token(priv)

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_valid_v1_issuer_token_accepted(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify STS Windows Net v1 issuer is accepted alongside v2 login issuer."""
    priv, _ = rsa_key_pair
    token = make_token(priv, issuer=VALID_V1_ISSUER)

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_missing_token_on_protected_route_rejected_401(
    app_with_entra: FastAPI,
) -> None:
    """Verify missing Authorization header returns 401 MISSING_BEARER_TOKEN."""
    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/connections")

    assert response.status_code == 401
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "MISSING_BEARER_TOKEN"


@pytest.mark.asyncio
async def test_expired_token_rejected_401(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify expired token returns 401 TOKEN_EXPIRED."""
    priv, _ = rsa_key_pair
    token = make_token(priv, expires_in_seconds=-300)  # Expired 5 minutes ago

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_invalid_signature_rejected_401(
    app_with_entra: FastAPI,
    foreign_rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify token signed with an unknown private key returns 401 INVALID_SIGNATURE."""
    foreign_priv, _ = foreign_rsa_key_pair
    token = make_token(foreign_priv, kid="test-key-id")

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INVALID_SIGNATURE"


@pytest.mark.asyncio
async def test_invalid_audience_rejected_401(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify mismatched token audience returns 401 INVALID_AUDIENCE."""
    priv, _ = rsa_key_pair
    token = make_token(priv, audience="api://some-other-app")

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INVALID_AUDIENCE"


@pytest.mark.asyncio
async def test_invalid_issuer_rejected_401(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify token from untrusted tenant/issuer returns 401 INVALID_ISSUER."""
    priv, _ = rsa_key_pair
    token = make_token(priv, issuer="https://login.microsoftonline.com/attacker-tenant-guid/v2.0")

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INVALID_ISSUER"


@pytest.mark.asyncio
async def test_wrong_tenant_id_in_claims_rejected_401(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify token with mismatched tenant ID claim returns 401 INVALID_TENANT."""
    priv, _ = rsa_key_pair
    token = make_token(priv, tid="11111111-2222-3333-4444-555555555555")

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INVALID_TENANT"


@pytest.mark.asyncio
async def test_malformed_token_rejected_401(
    app_with_entra: FastAPI,
) -> None:
    """Verify unparseable garbage token string returns 401 MALFORMED_TOKEN."""
    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/connections",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )

    assert response.status_code == 401
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "MALFORMED_TOKEN"


@pytest.mark.asyncio
async def test_public_health_endpoints_accessible_without_token(
    app_with_entra: FastAPI,
) -> None:
    """Verify health and readiness probes remain publicly accessible when auth is enabled."""
    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_live = await client.get("/health")
        resp_v1_live = await client.get("/api/v1/health")

    assert resp_live.status_code == 200
    assert resp_live.json()["status"] == "ok"
    assert resp_v1_live.status_code == 200
    assert resp_v1_live.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dev_mode_allows_unauthenticated_requests() -> None:
    """Verify default development configuration (entra_auth_enabled=False) passes through."""
    s = Settings(
        app_env="development",
        entra_auth_enabled=False,
        catalog_offline_mode=True,
    )
    dev_app = create_app(settings=s)
    dev_app.dependency_overrides[get_settings] = lambda: s

    transport = ASGITransport(app=dev_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/connections")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_require_roles_enforcement(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify require_roles rejects callers lacking mandatory application roles with 403."""
    admin_router = APIRouter()

    @admin_router.get(
        "/api/v1/admin-only",
        dependencies=[Depends(require_roles("FinOpsSuperAdmin"))],
    )
    async def admin_only() -> dict[str, str]:
        return {"status": "authorized"}

    app_with_entra.include_router(admin_router)

    priv, _ = rsa_key_pair
    # Regular token has roles ["Admin", "Reader"], lacks "FinOpsSuperAdmin"
    regular_token = make_token(priv, roles=["Admin", "Reader"])

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin-only",
            headers={"Authorization": f"Bearer {regular_token}"},
        )

    assert response.status_code == 403
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INSUFFICIENT_PERMISSIONS"

    # Token WITH "FinOpsSuperAdmin" role should succeed
    admin_token = make_token(priv, roles=["FinOpsSuperAdmin"])
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok_response = await client.get(
            "/api/v1/admin-only",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert ok_response.status_code == 200
    assert ok_response.json() == {"status": "authorized"}


@pytest.mark.asyncio
async def test_create_connection_requires_admin_role_rejects_reader_403(
    app_with_entra: FastAPI,
    rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Verify POST /api/v1/connections rejects authenticated user with only Reader role (403)."""
    priv, _ = rsa_key_pair
    reader_token = make_token(priv, roles=["Reader"])

    payload = {
        "provider": "azure",
        "name": "Production Subscription",
        "tenant_id": TENANT_ID,
        "subscription_id": "11111111-2222-3333-4444-555555555555",
        "client_id": "test-client-id",
        "client_secret": "test-secret-mock",
    }

    transport = ASGITransport(app=app_with_entra)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/connections",
            json=payload,
            headers={"Authorization": f"Bearer {reader_token}"},
        )

    assert response.status_code == 403
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INSUFFICIENT_PERMISSIONS"
