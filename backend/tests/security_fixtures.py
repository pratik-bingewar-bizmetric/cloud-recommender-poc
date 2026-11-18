"""Shared helpers for security tests: valid production settings and throw-away signed tokens.

Production startup rejects missing/insecure auth, secrets and CORS configuration, so suites that
exercise production-only behaviour must supply these. Every value below is a throw-away string
generated for tests; none is a real secret, and tokens are signed with in-process RSA keys.
"""

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI

from cloud_recommender.core.auth import EntraTokenValidator, get_token_validator
from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.main import create_app

TENANT_ID = "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"
AUDIENCE = "api://cloud-recommender-test-audience"
APPROVED_CLIENT_ID = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
STRONG_SECRET = "Zq8vK2mP9xLw4TnB7yHc1RdF6sGj3UeA0"
STRONG_SIGNING = "Hb5Nw2Qe8TyU1Pv6Cm3Zr9Ks4Dg7Lj0X"
FABRIC_ORIGIN = "https://portal.contoso.net"
REQUIRED_SCOPE = "access_as_user"

PRODUCTION_SECURITY: dict[str, Any] = {
    "debug": False,
    "dev_auth_enabled": False,
    "entra_auth_enabled": True,
    "entra_tenant_id": TENANT_ID,
    "entra_audience": AUDIENCE,
    "entra_required_scopes": [REQUIRED_SCOPE],
    "entra_allowed_client_ids": [APPROVED_CLIENT_ID],
    "secret_key": STRONG_SECRET,
    "finops_signing_secret": STRONG_SIGNING,
    "cors_origins": [FABRIC_ORIGIN],
    # persistent connections: production uses the database store and a managed encryption key
    "connection_store": "database",
    "connection_key_provider": "env",
    "connection_encryption_keys": '{"test-1": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="}',
    "connection_active_key_id": "test-1",
}


def new_rsa_key() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def make_token(
    private_key: rsa.RSAPrivateKey,
    *,
    drop: tuple[str, ...] = (),
    nbf_offset: int = 0,
    **claims: Any,
) -> str:
    """Sign a delegated-style token (scp=access_as_user, approved azp) with claim overrides."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-1",
        "tid": TENANT_ID,
        "azp": APPROVED_CLIENT_ID,
        "scp": REQUIRED_SCOPE,
        "roles": [],
        "preferred_username": "analyst@contoso.net",
        "iat": now,
        "nbf": now + nbf_offset,
        "exp": now + 3600,
    }
    payload.update(claims)
    for key in drop:
        payload.pop(key, None)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "k"})


def build_app(settings: Settings, public_key: rsa.RSAPublicKey) -> FastAPI:
    """Create the app with a test JWKS (public key) injected into the validator."""
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    validator = EntraTokenValidator(settings=settings, test_keys={"k": public_key})
    app.dependency_overrides[get_token_validator] = lambda: validator
    return app
