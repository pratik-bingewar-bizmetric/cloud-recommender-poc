"""Backend security hardening tests.

Covers: explicit environment (M5), tenant (M1), docs exposure (M2), operational scripts (M3),
baseline authorization (H2), write authorization (H1), JWT strictness, dev auth, CORS, health.
All tokens are signed with throw-away RSA keys generated in-process.
"""

import importlib.util
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from security_fixtures import (
    APPROVED_CLIENT_ID,
    AUDIENCE,
    FABRIC_ORIGIN,
    ISSUER,
    PRODUCTION_SECURITY,
    STRONG_SECRET,
    TENANT_ID,
    build_app,
    make_token,
    new_rsa_key,
)

from cloud_recommender.core.auth import (
    RESTRICTED_ROLES,
    ROLE_FINOPS_ADMIN,
    ROLE_FINOPS_DAEMON,
    USER_NON_GET_ENDPOINTS,
    EntraTokenValidator,
    get_current_user,
)
from cloud_recommender.core.config import (
    InsecureConfigurationError,
    Settings,
    get_operational_settings,
    get_settings,
    is_insecure_secret,
    is_local_origin,
    redact_connection_string,
)
from cloud_recommender.main import create_app

OTHER_TENANT_ID = "11111111-2222-3333-4444-555555555555"
RESTRICTED_PATHS = [
    "/api/v1/configuration",
    "/api/v1/connections",
    "/api/v1/connections/validate",
    "/api/v1/finops/ingestion/run",
    "/api/v1/finops/ingestion/approval-token",
    "/api/v1/ingestion/c1/runs",
    "/api/v1/ingestion/runs/00000000-0000-0000-0000-000000000000/retry",
]


def prod_kwargs(**overrides: Any) -> dict[str, Any]:
    """Return a fully valid production configuration, with optional overrides."""
    base: dict[str, Any] = {
        "app_env": "production",
        "catalog_offline_mode": True,
        **PRODUCTION_SECURITY,
    }
    base.update(overrides)
    return base


def serve(**overrides: Any) -> Settings:
    """Construct production settings and run the web-server validation."""
    settings = Settings(_env_file=None, **prod_kwargs(**overrides))
    settings.validate_for_serving()
    return settings


@pytest.fixture(scope="module")
def keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    return new_rsa_key()


@pytest.fixture(scope="module")
def foreign_keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    return new_rsa_key()


async def call(
    app: FastAPI, method: str, path: str, token: str | None = None, **kwargs: Any
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.request(method, path, headers=headers, **kwargs)


def error_code(response: Any) -> str:
    return str(response.json()["error"]["message"]["error_code"])


# --------------------------------------------------------------------------------------
# Web-server (production) configuration must fail closed
# --------------------------------------------------------------------------------------


def test_valid_production_configuration_starts() -> None:
    assert serve().entra_auth_enabled is True


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"entra_auth_enabled": False}, "ENTRA_AUTH_ENABLED"),
        ({"entra_audience": None, "entra_auth_enabled": False}, "ENTRA_AUDIENCE"),
        ({"entra_tenant_id": None, "entra_auth_enabled": False}, "ENTRA_TENANT_ID"),
        ({"entra_tenant_id": "not-a-guid", "entra_auth_enabled": False}, "ENTRA_TENANT_ID"),
        ({"entra_required_scopes": []}, "ENTRA_REQUIRED_SCOPES"),
        ({"entra_allowed_client_ids": []}, "ENTRA_ALLOWED_CLIENT_IDS"),
        ({"entra_allowed_client_ids": ["not-a-guid"]}, "ENTRA_ALLOWED_CLIENT_IDS"),
        (
            {"secret_key": "insecure-default-development-secret-key-change-in-production"},
            "SECRET_KEY",
        ),
        ({"secret_key": ""}, "SECRET_KEY"),
        ({"secret_key": "short"}, "SECRET_KEY"),
        ({"finops_signing_secret": None}, "FINOPS_SIGNING_SECRET"),
        ({"finops_signing_secret": "changeme-changeme-changeme-changeme"}, "FINOPS_SIGNING_SECRET"),
        ({"cors_origins": ["http://localhost:3000"]}, "CORS_ORIGINS"),
        ({"cors_origins": ["*"]}, "CORS_ORIGINS"),
        ({"cors_origins": []}, "CORS_ORIGINS"),
        ({"cors_origins": ["http://portal.contoso.net"]}, "CORS_ORIGINS"),
        ({"debug": True}, "DEBUG"),
    ],
)
def test_production_misconfiguration_fails_startup(override: dict[str, Any], expected: str) -> None:
    with pytest.raises(InsecureConfigurationError) as excinfo:
        serve(**override)
    assert expected in str(excinfo.value)


def test_production_requires_explicitly_provided_cors_origins() -> None:
    kwargs = prod_kwargs()
    del kwargs["cors_origins"]  # default list contains localhost -> must not be trusted
    with pytest.raises(InsecureConfigurationError, match="CORS_ORIGINS"):
        Settings(_env_file=None, **kwargs).validate_for_serving()


def test_configuration_error_never_echoes_secret_values() -> None:
    leaked = "my-super-private-but-too-short"
    with pytest.raises(InsecureConfigurationError) as excinfo:
        serve(secret_key=leaked, finops_signing_secret=leaked)
    assert leaked not in str(excinfo.value)


def test_create_app_refuses_insecure_production_settings() -> None:
    """The server cannot be built with unsafe production settings (validation not skippable)."""
    insecure = Settings(_env_file=None, **prod_kwargs(secret_key="short"))
    with pytest.raises(InsecureConfigurationError, match="SECRET_KEY"):
        create_app(settings=insecure)


@pytest.mark.asyncio
async def test_lifespan_refuses_insecure_production_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_recommender.main import lifespan

    insecure = Settings(_env_file=None, **prod_kwargs(finops_signing_secret=None))
    monkeypatch.setattr("cloud_recommender.main.get_settings", lambda: insecure)
    with pytest.raises(InsecureConfigurationError, match="FINOPS_SIGNING_SECRET"):
        async with lifespan(FastAPI()):
            pass


def test_entra_enabled_requires_audience_in_any_environment() -> None:
    with pytest.raises(InsecureConfigurationError, match="ENTRA_AUDIENCE"):
        Settings(
            _env_file=None,
            app_env="development",
            entra_auth_enabled=True,
            entra_tenant_id=TENANT_ID,
        )


def test_secret_and_origin_helpers() -> None:
    assert is_insecure_secret(None)
    assert is_insecure_secret("x" * 40)  # low entropy
    assert not is_insecure_secret(STRONG_SECRET)
    assert is_local_origin("http://localhost:3000")
    assert is_local_origin("http://127.0.0.1:5173")
    assert not is_local_origin(FABRIC_ORIGIN)


# --------------------------------------------------------------------------------------
# M1: tenant must be explicit, no hard-coded default
# --------------------------------------------------------------------------------------


def test_no_hardcoded_default_tenant() -> None:
    assert Settings(_env_file=None, app_env="development").entra_tenant_id is None


def test_production_without_tenant_fails_even_with_auth_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    kwargs = prod_kwargs()
    del kwargs["entra_tenant_id"]
    with pytest.raises(InsecureConfigurationError, match="ENTRA_TENANT_ID"):
        Settings(_env_file=None, **kwargs)  # auth enabled + no tenant: rejected at construction


def test_tenant_guid_format_validated() -> None:
    with pytest.raises(InsecureConfigurationError, match="ENTRA_TENANT_ID"):
        Settings(_env_file=None, **prod_kwargs(entra_tenant_id="contoso.onmicrosoft.com"))


# --------------------------------------------------------------------------------------
# M5: explicit APP_ENV, no accidental dev authentication
# --------------------------------------------------------------------------------------


def test_missing_app_env_fails_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(InsecureConfigurationError, match="APP_ENV"):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["", "prod", "DEV", "local"])
def test_invalid_app_env_fails_safely(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("APP_ENV", value)
    with pytest.raises(InsecureConfigurationError, match="APP_ENV"):
        Settings(_env_file=None)


def test_explicit_app_env_from_environment_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "false")
    assert Settings(_env_file=None).app_env == "staging"


@pytest.mark.parametrize("env", ["production", "staging"])
def test_dev_auth_rejected_outside_dev_and_test(env: str) -> None:
    with pytest.raises(InsecureConfigurationError, match="DEV_AUTH_ENABLED"):
        Settings(_env_file=None, app_env=env, dev_auth_enabled=True)


@pytest.mark.parametrize(
    "marker",
    ["CONTAINER_APP_NAME", "WEBSITE_SITE_NAME", "DATABRICKS_APP_PORT", "KUBERNETES_SERVICE_HOST"],
)
def test_dev_auth_rejected_on_hosted_runtime(monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
    monkeypatch.setenv(marker, "1")
    with pytest.raises(InsecureConfigurationError, match="hosting platform"):
        Settings(_env_file=None, app_env="development", dev_auth_enabled=True)


def test_dev_identity_unavailable_if_runtime_becomes_hosted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime re-check: even a valid dev configuration yields 401 once a hosting marker exists."""
    settings = Settings(_env_file=None, app_env="development", dev_auth_enabled=True)
    monkeypatch.setenv("WEBSITE_SITE_NAME", "x")
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(None, settings, EntraTokenValidator(settings=settings))
    assert excinfo.value.status_code == 401


def test_dev_identity_unreachable_in_production_even_if_settings_bypassed() -> None:
    """Defence in depth: skipping validation (model_construct) still yields 401, not Admin."""
    settings = Settings.model_construct(
        app_env="production",
        entra_auth_enabled=False,
        dev_auth_enabled=True,
        dev_auth_roles=["FinOpsAdmin"],
        entra_tenant_id=None,
        entra_audience=None,
        entra_jwks_cache_ttl_hours=1,
    )
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(None, settings, EntraTokenValidator(settings=settings))
    assert excinfo.value.status_code == 401


# --------------------------------------------------------------------------------------
# M2: API documentation
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_disabled_in_production(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], path: str
) -> None:
    app = build_app(Settings(_env_file=None, **prod_kwargs()), keys[1])
    assert (await call(app, "GET", path)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_available_in_development(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], path: str
) -> None:
    settings = Settings(_env_file=None, app_env="development", catalog_offline_mode=True)
    app = build_app(settings, keys[1])
    assert (await call(app, "GET", path)).status_code == 200


@pytest.mark.asyncio
async def test_root_endpoint_does_not_advertise_docs_in_production(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app = build_app(Settings(_env_file=None, **prod_kwargs()), keys[1])
    assert (await call(app, "GET", "/")).json()["docs"] == "disabled"


# --------------------------------------------------------------------------------------
# M3: operational scripts do not inherit web-server requirements
# --------------------------------------------------------------------------------------


@pytest.fixture
def minimal_production_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Production env with ONLY what a migration job needs (no Entra/secrets/CORS)."""
    for name in (
        "ENTRA_AUTH_ENABLED",
        "ENTRA_TENANT_ID",
        "ENTRA_AUDIENCE",
        "DEV_AUTH_ENABLED",
        "SECRET_KEY",
        "FINOPS_SIGNING_SECRET",
        "CORS_ORIGINS",
        "DEBUG",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://migrator:S3cretPw!@db.test:5432/app")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("minimal_production_env")
def test_operational_settings_do_not_require_web_security() -> None:
    settings = get_operational_settings()
    assert settings.app_env == "production"
    # ...but the same settings can never start the web server:
    with pytest.raises(InsecureConfigurationError):
        settings.validate_for_serving()
    with pytest.raises(InsecureConfigurationError):
        create_app(settings=settings)


def test_operational_settings_still_require_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(InsecureConfigurationError, match="APP_ENV"):
            get_operational_settings()
    finally:
        get_settings.cache_clear()


@pytest.mark.usefixtures("minimal_production_env")
def test_operational_settings_cannot_enable_dev_auth_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    get_settings.cache_clear()
    with pytest.raises(InsecureConfigurationError, match="DEV_AUTH_ENABLED"):
        get_operational_settings()


def _load_script(name: str) -> Any:
    path = Path(__file__).resolve().parent.parent / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.usefixtures("minimal_production_env")
def test_migration_runner_builds_config_with_minimal_production_env() -> None:
    """The migration runner loads under APP_ENV=production with only database settings."""
    runner = _load_script("run_migrations")
    config = runner.get_alembic_config()  # builds config only; no DB access, no migration
    assert config.get_main_option("sqlalchemy.url")


def test_scripts_use_operational_settings_only() -> None:
    for name in ("run_migrations", "databricks_access_audit"):
        source = (Path(__file__).resolve().parent.parent / "scripts" / f"{name}.py").read_text(
            encoding="utf-8"
        )
        assert "get_operational_settings" in source
        assert "get_settings()" not in source


def test_connection_string_redaction() -> None:
    url = "postgresql+asyncpg://migrator:S3cretPw%21@db.test:5432/app"
    text = "failed to connect to postgresql+asyncpg://migrator:S3cretPw!@db.test:5432/app"
    redacted = redact_connection_string(text, url)
    assert "S3cretPw" not in redacted
    assert "db.test" in redacted


# --------------------------------------------------------------------------------------
# JWT validation (production-style settings)
# --------------------------------------------------------------------------------------


@pytest.fixture
def prod_app(keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]) -> FastAPI:
    return build_app(Settings(_env_file=None, **prod_kwargs()), keys[1])


@pytest.mark.asyncio
async def test_missing_bearer_token_returns_401(prod_app: FastAPI) -> None:
    response = await call(prod_app, "GET", "/api/v1/connections")
    assert response.status_code == 401
    assert error_code(response) == "MISSING_BEARER_TOKEN"


@pytest.mark.asyncio
async def test_malformed_token_returns_401(prod_app: FastAPI) -> None:
    assert (await call(prod_app, "GET", "/api/v1/connections", "not.a.jwt")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 10},
        {"iss": "https://sts.windows.net/99999999-0000-0000-0000-000000000000/"},
        {"aud": "api://someone-else"},
        {"tid": OTHER_TENANT_ID},
    ],
)
async def test_invalid_claims_return_401(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], claims: dict[str, Any]
) -> None:
    token = make_token(keys[0], **claims)
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["tid", "aud", "exp", "nbf", "iss"])
async def test_missing_required_claims_return_401(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], missing: str
) -> None:
    token = make_token(keys[0], drop=(missing,))
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 401


@pytest.mark.asyncio
async def test_not_yet_valid_token_returns_401(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], nbf_offset=600)
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 401


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(
    prod_app: FastAPI, foreign_keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(foreign_keys[0])
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 401


@pytest.mark.asyncio
async def test_non_rs256_token_returns_401(prod_app: FastAPI) -> None:
    forged = jwt.encode({"aud": AUDIENCE, "iss": ISSUER, "tid": TENANT_ID}, "k" * 40, "HS256")
    assert (await call(prod_app, "GET", "/api/v1/connections", forged)).status_code == 401


@pytest.mark.asyncio
async def test_valid_token_is_authenticated(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    response = await call(prod_app, "GET", "/api/v1/connections", make_token(keys[0]))
    assert response.status_code == 200


def test_validator_without_audience_rejects_every_token(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    settings = Settings(
        _env_file=None, app_env="testing", entra_auth_enabled=False, entra_tenant_id=TENANT_ID
    )
    validator = EntraTokenValidator(settings=settings, test_keys={"k": keys[1]})
    with pytest.raises(HTTPException) as excinfo:
        validator.validate_token(make_token(keys[0]))
    assert excinfo.value.status_code == 401
    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail["error_code"] == "AUTH_NOT_CONFIGURED"


# --------------------------------------------------------------------------------------
# Baseline authorization (scope for users, separate permission for daemons); 401 vs 403
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_token_without_scope_is_forbidden_403(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """A user token with a role but no required scope gets no access (roles are not scopes)."""
    token = make_token(keys[0], scp="Other.Scope", roles=["FinOpsAdmin"])
    response = await call(prod_app, "GET", "/api/v1/connections", token)
    assert response.status_code == 403
    assert error_code(response) == "INSUFFICIENT_SCOPE"


@pytest.mark.asyncio
async def test_wrong_scope_is_forbidden_403(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], scp="User.Read Mail.Read", roles=[])
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 403


@pytest.mark.asyncio
async def test_user_token_with_scope_and_no_roles_has_full_user_access(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], roles=[])
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 200


@pytest.mark.asyncio
async def test_unapproved_client_is_forbidden_403(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], azp="99999999-9999-9999-9999-999999999999", roles=["FinOpsAdmin"])
    response = await call(prod_app, "GET", "/api/v1/connections", token)
    assert response.status_code == 403
    assert error_code(response) == "UNAPPROVED_CLIENT_APPLICATION"


@pytest.mark.asyncio
async def test_missing_client_claim_is_forbidden_when_allow_list_configured(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], drop=("azp",))
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 403


@pytest.mark.asyncio
async def test_v1_appid_claim_is_accepted_as_client_id(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], drop=("azp",), appid=APPROVED_CLIENT_ID)
    assert (await call(prod_app, "GET", "/api/v1/connections", token)).status_code == 200


@pytest.mark.asyncio
async def test_roles_claim_as_string_is_interpreted(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """A single role delivered as a string still opens the restricted gate (422 = body check)."""
    token = make_token(keys[0], roles="FinOpsAdmin")
    response = await call(
        prod_app, "POST", "/api/v1/finops/ingestion/approval-token", token, json=[]
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_401_for_authentication_failures_403_for_authorization_failures(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    assert (await call(prod_app, "GET", "/api/v1/connections")).status_code == 401
    forged = make_token(new_rsa_key()[0])
    assert (await call(prod_app, "GET", "/api/v1/connections", forged)).status_code == 401
    assert (
        await call(prod_app, "GET", "/api/v1/connections", make_token(keys[0], scp=""))
    ).status_code == 403


# --------------------------------------------------------------------------------------
# Restricted operations: single role FinOpsAdmin on a user token
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", RESTRICTED_PATHS)
async def test_scoped_user_without_role_cannot_use_restricted_endpoints(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], path: str
) -> None:
    token = make_token(keys[0], roles=[])
    response = await call(prod_app, "POST", path, token, json={})
    assert response.status_code == 403
    assert error_code(response) == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retired", ["Admin", "FinOpsAdministrator", "PlatformAdministrator", "Reader"]
)
async def test_retired_roles_no_longer_grant_restricted_access(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], retired: str
) -> None:
    token = make_token(keys[0], roles=[retired])
    response = await call(
        prod_app, "POST", "/api/v1/finops/ingestion/approval-token", token, json=[]
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_finops_admin_passes_the_restricted_gate(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], roles=[ROLE_FINOPS_ADMIN])
    # Invalid body -> 422 from validation, proving authorization passed without running a handler.
    response = await call(prod_app, "POST", "/api/v1/connections", token, json=[])
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_user_operations_need_no_role(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = make_token(keys[0], roles=[])
    for path in (
        "/api/v1/pricing/simulate",
        "/api/v1/pricing/refresh",
        "/api/v1/finops/anomalies/a1/status",
        "/api/v1/finops/optimization-advisor/d1/action",
    ):
        response = await call(prod_app, "POST", path, token, json=[])
        assert response.status_code == 422, path  # authorized; stopped by body validation only


def test_user_operation_allow_list_is_explicit_and_small() -> None:
    assert len(USER_NON_GET_ENDPOINTS) == 21
    assert RESTRICTED_ROLES == ("FinOpsAdmin",)


# --------------------------------------------------------------------------------------
# Application-only (daemon) tokens: separate permission, no user permissions
# --------------------------------------------------------------------------------------


def daemon_token(private_key: rsa.RSAPrivateKey, **claims: Any) -> str:
    return make_token(private_key, scp="", roles=[ROLE_FINOPS_DAEMON], **claims)


@pytest.mark.asyncio
async def test_daemon_without_application_permission_is_forbidden(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    for roles in ([], ["Reader"], ["FinOpsAdmin"]):
        token = make_token(keys[0], scp="", roles=roles)
        response = await call(prod_app, "GET", "/api/v1/databricks/connections", token)
        assert response.status_code == 403
        assert error_code(response) == "INSUFFICIENT_APPLICATION_PERMISSION"


@pytest.mark.asyncio
async def test_daemon_can_call_designated_read_only_status_endpoint(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    response = await call(prod_app, "GET", "/api/v1/databricks/connections", daemon_token(keys[0]))
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/connections"),
        ("GET", "/api/v1/finops/overview"),
        ("GET", "/api/v1/inventory/azure/subscriptions"),
        ("POST", "/api/v1/pricing/simulate"),
        ("POST", "/api/v1/pricing/refresh"),
        ("POST", "/api/v1/connections"),
        ("POST", "/api/v1/finops/ingestion/run"),
        ("POST", "/api/v1/finops/ingestion/approval-token"),
        ("POST", "/api/v1/finops/anomalies/a1/status"),
    ],
)
async def test_daemon_has_no_user_or_restricted_permissions(
    prod_app: FastAPI,
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    method: str,
    path: str,
) -> None:
    response = await call(prod_app, method, path, daemon_token(keys[0]), json=[])
    assert response.status_code == 403
    assert error_code(response) == "OPERATION_NOT_PERMITTED_FOR_APPLICATION"


@pytest.mark.asyncio
async def test_daemon_permission_does_not_help_a_user_token(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """A delegated token carrying the daemon role still needs the user scope."""
    token = make_token(keys[0], scp="Other.Scope", roles=[ROLE_FINOPS_DAEMON])
    assert (await call(prod_app, "GET", "/api/v1/databricks/connections", token)).status_code == 403


@pytest.mark.asyncio
async def test_daemon_client_must_still_be_approved(
    prod_app: FastAPI, keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    token = daemon_token(keys[0], azp="99999999-9999-9999-9999-999999999999")
    response = await call(prod_app, "GET", "/api/v1/databricks/connections", token)
    assert response.status_code == 403
    assert error_code(response) == "UNAPPROVED_CLIENT_APPLICATION"


def test_application_token_is_detected_by_missing_scp(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    settings = Settings(_env_file=None, **prod_kwargs())
    validator = EntraTokenValidator(settings=settings, test_keys={"k": keys[1]})
    assert validator.validate_token(daemon_token(keys[0])).is_application_token is True
    assert validator.validate_token(make_token(keys[0])).is_application_token is False


# --------------------------------------------------------------------------------------
# Development authentication
# --------------------------------------------------------------------------------------


def dev_settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "app_env": "development",
        "catalog_offline_mode": True,
        "entra_auth_enabled": False,
        "dev_auth_enabled": True,
        "dev_auth_roles": [],
    }
    kwargs.update(overrides)
    return Settings(_env_file=None, **kwargs)


@pytest.mark.asyncio
async def test_dev_mode_explicitly_enabled_allows_tokenless_user_access(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app = build_app(dev_settings(), keys[1])
    assert (await call(app, "GET", "/api/v1/connections")).status_code == 200


@pytest.mark.asyncio
async def test_dev_identity_needs_finops_admin_for_restricted_operations(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    plain_app = build_app(dev_settings(), keys[1])
    admin_app = build_app(dev_settings(dev_auth_roles=["FinOpsAdmin"]), keys[1])
    assert (await call(plain_app, "POST", "/api/v1/connections", json={})).status_code == 403
    assert (await call(admin_app, "POST", "/api/v1/connections", json=[])).status_code == 422


@pytest.mark.asyncio
async def test_dev_mode_not_enabled_returns_401(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app = build_app(dev_settings(dev_auth_enabled=False), keys[1])
    response = await call(app, "GET", "/api/v1/connections")
    assert response.status_code == 401
    assert error_code(response) == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["garbage", "a.b.c"])
async def test_invalid_token_in_dev_mode_returns_401(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], token: str
) -> None:
    app = build_app(dev_settings(), keys[1])
    assert (await call(app, "GET", "/api/v1/connections", token)).status_code == 401


@pytest.mark.asyncio
async def test_forged_token_in_dev_mode_never_becomes_admin(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    foreign_keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app = build_app(dev_settings(entra_tenant_id=TENANT_ID, entra_audience=AUDIENCE), keys[1])
    forged = make_token(foreign_keys[0], roles=["FinOpsAdmin"])
    assert (await call(app, "GET", "/api/v1/connections", forged)).status_code == 401


def test_dev_identity_has_no_roles_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEV_AUTH_ROLES", raising=False)
    settings = Settings(
        _env_file=None, app_env="development", dev_auth_enabled=True, catalog_offline_mode=True
    )
    user = get_current_user(None, settings, EntraTokenValidator(settings=settings))
    assert user.roles == []
    assert user.is_development_identity
    assert not user.is_application_token


# --------------------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_production_cors_is_origin_and_method_restricted(
    prod_app: FastAPI,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=prod_app), base_url="http://t") as client:
        ok = await client.options(
            "/api/v1/connections",
            headers={
                "Origin": FABRIC_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        local = await client.options(
            "/api/v1/connections",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        verb = await client.options(
            "/api/v1/connections",
            headers={"Origin": FABRIC_ORIGIN, "Access-Control-Request-Method": "DELETE"},
        )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == FABRIC_ORIGIN
    assert local.status_code == 400
    assert verb.status_code == 400


# --------------------------------------------------------------------------------------
# Health endpoints
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoints_do_not_leak_internals(
    prod_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    leaky = {
        "status": "disconnected",
        "error": "password authentication failed for user finops_app_user at db.internal.corp",
        "target": "postgresql+asyncpg://db.internal.corp:5432/cloud_recommender",
        "url_host": "db.internal.corp",
        "configured_env": "production",
    }
    monkeypatch.setattr(
        "cloud_recommender.api.routes.health.check_db_health", AsyncMock(return_value=leaky)
    )
    live = await call(prod_app, "GET", "/health")
    ready = await call(prod_app, "GET", "/health/ready")

    assert live.status_code == 200
    assert live.json()["environment"] is None
    assert ready.status_code == 503
    body = ready.text
    for forbidden in (
        "finops_app_user",
        "db.internal.corp",
        "5432",
        "postgresql+asyncpg",
        STRONG_SECRET,
    ):
        assert forbidden not in body
    assert ready.json()["dependencies"]["database"] == {
        "status": "disconnected",
        "error": "database_unreachable",
    }
