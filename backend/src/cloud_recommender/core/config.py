"""Application configuration management using Pydantic Settings."""

import logging
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

import structlog
from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_GUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_INSECURE_SECRET_MARKERS: tuple[str, ...] = (
    "insecure",
    "default",
    "placeholder",
    "changeme",
    "change-me",
    "change_me",
    "change-in-production",
    "replace",
    "your_",
    "your-",
    "xxx",
    "example",
    "{{secrets/",
)
MIN_PRODUCTION_SECRET_LENGTH = 32
_LOCAL_ORIGIN_PATTERN = re.compile(
    r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(:\d+)?(/.*)?$", re.IGNORECASE
)


VALID_APP_ENVIRONMENTS: tuple[str, ...] = ("development", "testing", "staging", "production")
# Environment variables set by hosting platforms. Development authentication is refused when any
# of them is present, so a dev flag copied into a hosted deployment cannot take effect.
HOSTED_RUNTIME_MARKERS: tuple[str, ...] = (
    "CONTAINER_APP_NAME",
    "WEBSITE_SITE_NAME",
    "DATABRICKS_APP_PORT",
    "KUBERNETES_SERVICE_HOST",
    "FUNCTIONS_WORKER_RUNTIME",
)


def is_hosted_runtime() -> bool:
    """Return True when the process appears to run on a managed hosting platform."""
    return any(os.environ.get(marker) for marker in HOSTED_RUNTIME_MARKERS)


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when production security settings are missing or unsafe.

    Deliberately NOT a ``ValueError``: pydantic echoes ``input_value`` for ValueErrors raised in
    validators, which would copy secret values into logs. Messages here name variables only.
    """


def is_insecure_secret(value: str | None) -> bool:
    """Return True when a secret is missing, too short, low-entropy or a known placeholder."""
    if value is None:
        return True
    cleaned = value.strip()
    if len(cleaned) < MIN_PRODUCTION_SECRET_LENGTH or len(set(cleaned)) < 8:
        return True
    lowered = cleaned.lower()
    return any(marker in lowered for marker in _INSECURE_SECRET_MARKERS)


def is_local_origin(origin: str) -> bool:
    """Return True for localhost / loopback CORS origins."""
    return bool(_LOCAL_ORIGIN_PATTERN.match(origin.strip()))


class Settings(BaseSettings):
    """Central application settings validated at runtime."""

    # Application Core
    app_name: str = Field(default="cloud-recommender", description="Application service name")
    # APP_ENV must be provided explicitly (enforced by ``require_explicit_environment``); the
    # default exists only to satisfy typing and is never used to start the application.
    app_env: Literal["development", "testing", "staging", "production"] = Field(
        default="development",
        description="Application runtime environment (must be set explicitly via APP_ENV).",
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    api_host: str = Field(default="0.0.0.0", description="API server bind host")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API server bind port")
    api_v1_str: str = Field(default="/api/v1", description="Prefix for version 1 API routes")
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "https://app.fabric.microsoft.com",
            "https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net",
        ],
        description="Allowed CORS origins",
    )
    secret_key: str = Field(
        default="insecure-default-development-secret-key-change-in-production",
        description="Application secret key",
    )

    # Microsoft Entra ID Authentication & Authorization
    entra_auth_enabled: bool = Field(
        default=False,
        description="Enable cryptographic Microsoft Entra ID JWT verification for protected API routes.",
    )
    entra_tenant_id: str | None = Field(
        default=None,
        description="Target Microsoft Entra ID tenant GUID (no default; must be configured).",
    )
    entra_audience: str | None = Field(
        default=None,
        description="Expected audience (client ID or API URI) for incoming Entra ID JWTs.",
    )
    entra_required_scopes: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["access_as_user"],
        description=(
            "Delegated scopes (`scp`) accepted for API access; a token needs at least one. "
            "Tokens without `scp` (application tokens) need an application role instead."
        ),
    )
    entra_allowed_client_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Approved calling applications (`azp`/`appid` claim GUIDs). Mandatory in production; "
            "when non-empty, tokens from any other client are rejected with 403."
        ),
    )
    entra_jwks_cache_ttl_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Cache time-to-live for Microsoft published JWKS public keys in hours.",
    )

    dev_auth_enabled: bool = Field(
        default=False,
        description=(
            "Explicit opt-in local-development identity used ONLY when Entra auth is disabled "
            "and a request carries no bearer token. Rejected when APP_ENV=production/staging."
        ),
    )
    dev_auth_roles: list[str] = Field(
        default_factory=list,
        description=(
            "Application roles granted to the development identity (none by default; add "
            "FinOpsAdmin locally to exercise restricted operations)."
        ),
    )

    # Relational Database (PostgreSQL with asyncpg)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/cloud_recommender",
        description="PostgreSQL async connection URI",
    )
    db_pool_size: int = Field(default=10, ge=1, le=50, description="DB connection pool size")
    db_max_overflow: int = Field(
        default=20, ge=0, le=50, description="DB connection pool max overflow"
    )
    db_echo: bool = Field(default=False, description="Echo SQL statements to logs")
    db_pool_pre_ping: bool = Field(
        default=True, description="Enable connection health check pre-ping"
    )
    db_pool_timeout: int = Field(
        default=30, ge=5, le=120, description="Database connection pool checkout timeout in seconds"
    )
    db_pool_recycle: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description="Recycle database connections after N seconds (prevents firewall drops)",
    )
    db_ssl_mode: Literal["disable", "prefer", "require", "verify-ca", "verify-full"] = Field(
        default="prefer",
        description="TLS/SSL mode for PostgreSQL. Set to 'require' for Azure PostgreSQL Flexible Server.",
    )

    # LLM & Agent Orchestration (LangGraph)
    llm_provider: Literal["mock", "azure_openai", "openai", "gemini", "anthropic"] = Field(
        default="mock",
        description="Active LLM provider. Defaults to 'mock' for safe offline execution.",
    )
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=256, le=32768)
    llm_request_timeout_seconds: int = Field(default=45, ge=5, le=300)

    # Azure AI Foundry Configuration (Phase A AI Architect)
    azure_ai_foundry_endpoint: str | None = Field(
        default=None,
        description="Azure AI Foundry / Azure OpenAI inference endpoint URL.",
    )

    # Databricks FinOps & System Tables Ingestion (Milestone 3H / M1 Multi-Workspace)
    databricks_host: str = Field(
        default="https://adb-642006393507276.16.azuredatabricks.net",
        description="Primary Azure Databricks workspace host URL (Dev default)",
    )
    databricks_workspace_id: str = Field(
        default="642006393507276",
        description="Primary Azure Databricks workspace ID (Dev default)",
    )
    databricks_warehouse_id: str = Field(
        default="05ed10a52697a344",
        description="SQL Warehouse ID (Serverless Starter Warehouse)",
    )
    databricks_dev_workspace_id: str = Field(
        default="642006393507276",
        description="Azure Databricks Dev workspace ID",
    )
    databricks_dev_host: str = Field(
        default="https://adb-642006393507276.16.azuredatabricks.net",
        description="Azure Databricks Dev workspace host URL",
    )
    databricks_dev_warehouse_id: str | None = Field(
        default=None,
        description="Optional override SQL Warehouse ID for Dev workspace (falls back to databricks_warehouse_id)",
    )
    databricks_prod_workspace_id: str | None = Field(
        default="7405608085231210",
        description="Azure Databricks Prod workspace ID",
    )
    databricks_prod_host: str = Field(
        default="https://adb-7405608085231210.10.azuredatabricks.net",
        description="Azure Databricks Prod workspace host URL",
    )
    databricks_prod_warehouse_id: str | None = Field(
        default=None,
        description="SQL Warehouse ID for Prod workspace (configured via DATABRICKS_PROD_WAREHOUSE_ID)",
    )
    databricks_prod_profile: str = Field(
        default="azure-prod",
        description="Databricks CLI profile fallback for Prod workspace in local development",
    )
    databricks_workspaces_json: str | None = Field(
        default=None,
        description="Optional JSON array defining additional Databricks workspace registry entries",
    )
    databricks_auth_type: str = Field(
        default="azure-cli",
        description="Databricks authentication type: oauth, azure-cli, profile",
    )
    databricks_client_id: str | None = Field(
        default=None,
        description="OAuth Service Principal client ID",
    )
    databricks_client_secret: str | None = Field(
        default=None,
        description="OAuth Service Principal client secret",
    )
    databricks_profile: str = Field(
        default="azure-dev",
        description="Databricks CLI profile fallback for local development",
    )
    databricks_query_timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Read-only query timeout limit in seconds",
    )
    finops_signing_secret: str | None = Field(
        default=None,
        description="Explicit HMAC-SHA256 secret for signing live execution approval tokens",
    )
    databricks_inventory_refresh_seconds: int = Field(
        default=60,
        ge=0,
        description="Background refresh interval for workspace inventory/health (0 disables)",
    )
    databricks_metadata_refresh_seconds: int = Field(
        default=600,
        ge=0,
        description="Background refresh interval for slower Unity Catalog / system-table metadata",
    )
    finops_monthly_budget_usd: float | None = Field(
        default=None,
        ge=0,
        description="Configured monthly Databricks budget in USD; budgets are never invented.",
    )
    finops_signing_kid: str = Field(
        default="k1-2026",
        description="Key identifier for the active token signing secret",
    )
    finops_verification_keys: str | None = Field(
        default=None,
        description="JSON dictionary mapping kid to secret key for verification key ring and rotation",
    )
    azure_ai_foundry_api_key: str | None = Field(
        default=None,
        description="API key for authenticating with Azure AI Foundry model deployment.",
    )
    azure_ai_foundry_deployment_name: str | None = Field(
        default=None,
        description="Model deployment name in Azure AI Foundry (e.g. 'gpt-4o' or 'gpt-4o-mini').",
    )
    azure_ai_foundry_api_version: str = Field(
        default="2024-05-01-preview",
        description="API version for Azure AI Foundry model inference.",
    )
    azure_ai_foundry_auth_type: Literal["api_key", "bearer_token"] = Field(
        default="api_key",
        description="Authentication method for Azure AI Foundry.",
    )
    azure_retail_prices_api_url: str = Field(
        default="https://prices.azure.com/api/retail/prices",
        description="Official public Azure Retail Prices API endpoint.",
    )

    # Azure Integration (Phase B - Strictly Read-Only)
    azure_auth_method: Literal["service_principal", "default_azure_credential", "azure_cli"] = (
        Field(default="service_principal")
    )
    azure_tenant_id: str | None = Field(default=None)
    azure_client_id: str | None = Field(default=None)
    azure_client_secret: str | None = Field(default=None)
    azure_subscription_id: str | None = Field(default=None)
    azure_authority_url: str = Field(
        default="https://login.microsoftonline.com",
        description="Microsoft Entra authority used for user-supplied service principal tokens.",
    )
    azure_live_session_ttl_seconds: int = Field(
        default=3300,
        ge=60,
        le=3600,
        description="Maximum lifetime of a live Azure connection session (also bounded by token).",
    )
    azure_live_max_connections_per_user: int = Field(
        default=10, ge=1, le=100, description="Maximum active live Azure connections per user."
    )
    azure_live_connect_attempts_per_minute: int = Field(
        default=5, ge=1, le=100, description="Connect/validate attempts per user per minute."
    )
    azure_live_max_resources: int = Field(
        default=5000, ge=100, le=50000, description="Maximum resources/groups returned per call."
    )
    azure_live_request_timeout_seconds: int = Field(
        default=30, ge=5, le=120, description="Timeout for Entra and Azure calls."
    )
    azure_arm_base_url: str = Field(
        default="https://management.azure.com",
        description="Azure Resource Manager read-only endpoint.",
    )

    # GCP Integration (Public Pricing vs. Read-Only Project/Resource Inventory)
    gcp_cloud_api_key: str | None = Field(
        default=None,
        description="Public Google Cloud Billing Catalog API key (strictly for SKU pricing, never for inventory).",
    )
    gcp_billing_catalog_api_url: str = Field(
        default="https://cloudbilling.googleapis.com/v1",
        description="Official Google Cloud Billing Catalog API v1 endpoint.",
    )
    gcp_project_id: str | None = Field(
        default=None,
        description="Default GCP Project ID for read-only resource discovery.",
    )
    gcp_access_token: str | None = Field(
        default=None,
        description="Optional short-lived OAuth2 access token for read-only GCP inventory discovery.",
    )
    google_application_credentials: str | None = Field(
        default=None,
        description="Path to read-only Google Cloud service account JSON or ADC file.",
    )

    # Microsoft Fabric Analytics (Phase B - Lakehouse)
    fabric_enabled: bool = Field(
        default=False,
        description="Enable live Microsoft Fabric Lakehouse integration. Disabled by default.",
    )
    fabric_tenant_id: str | None = Field(default=None)
    fabric_client_id: str | None = Field(default=None)
    fabric_client_secret: str | None = Field(default=None)
    fabric_workspace_id: str | None = Field(default=None)
    fabric_lakehouse_id: str | None = Field(default=None)

    # Multi-Cloud Pricing Engine & Service Catalog
    offline_pricing_mode: bool = Field(
        default=True,
        description="Use local cached pricing datasets rather than external live APIs.",
    )
    catalog_offline_mode: bool = Field(
        default=False,
        description="Force service catalog into offline fixture mode without database queries.",
    )
    allow_demo_fixtures: bool = Field(
        default=False,
        description=(
            "Opt-in (tests/demos only): when Azure authentication is missing or expired, return "
            "labelled mock_fixture inventory instead of failing closed with HTTP 401."
        ),
    )
    pricing_cache_ttl_hours: int = Field(default=24, ge=1, le=168)
    pricing_refresh_cooldown_seconds: int = Field(
        default=900,
        ge=0,
        le=86400,
        description="Minimum seconds between pricing refreshes per connection/subscription scope.",
    )

    # File Ingestion Limits
    max_document_size_mb: int = Field(default=25, ge=1, le=100)
    max_code_archive_size_mb: int = Field(default=100, ge=1, le=500)

    # Logging & Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")
    log_format: Literal["json", "console"] = Field(default="json")

    @model_validator(mode="before")
    @classmethod
    def require_explicit_environment(cls, data: Any) -> Any:
        """Refuse to start unless APP_ENV is explicitly set to a known environment.

        A missing/invalid value must never silently become "development". Only variable names
        and the allowed set are reported, never other configuration values.
        """
        value = data.get("app_env") if isinstance(data, dict) else None
        if not isinstance(value, str) or value.strip().lower() not in VALID_APP_ENVIRONMENTS:
            raise InsecureConfigurationError(
                "APP_ENV must be set explicitly to one of: "
                + ", ".join(VALID_APP_ENVIRONMENTS)
                + "."
            )
        return data

    @field_validator("entra_required_scopes", "entra_allowed_client_ids", mode="before")
    @classmethod
    def split_entra_lists(cls, v: object) -> list[str]:
        """Accept JSON arrays or comma/space separated strings for Entra list settings."""
        import json

        if isinstance(v, str):
            text = v.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(i).strip() for i in parsed if str(i).strip()]
                except ValueError:
                    pass
            return [i for i in re.split(r"[,\s]+", text) if i]
        if isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: object) -> list[str]:
        """Support JSON arrays, comma-separated strings, or string lists for CORS origins."""
        import json

        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                try:
                    parsed = json.loads(v_str)
                    if isinstance(parsed, list):
                        return [str(origin).strip() for origin in parsed if str(origin).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return []

    @field_validator("debug", mode="before")
    @classmethod
    def validate_debug(cls, v: object) -> bool:
        """Handle boolean conversion robustly, accommodating non-standard values like 'release'."""
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "on", "debug")
        return bool(v)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL specifies an async driver for PostgreSQL."""
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        """Construction-time consistency checks (apply to the API *and* operational scripts).

        - Entra auth requires a tenant GUID and an audience in every environment.
        - Development authentication is allowed only in development/testing and never on a
          managed hosting platform.
        Messages name variables only; values are never echoed.
        """
        problems: list[str] = []

        if self.entra_auth_enabled:
            if not self.entra_tenant_id or not _GUID_PATTERN.match(self.entra_tenant_id.strip()):
                problems.append("ENTRA_TENANT_ID must be set to a valid tenant GUID")
            if not self.entra_audience or not self.entra_audience.strip():
                problems.append("ENTRA_AUDIENCE must be set when ENTRA_AUTH_ENABLED=true")

        if self.dev_auth_enabled:
            if self.app_env not in ("development", "testing"):
                problems.append(
                    "DEV_AUTH_ENABLED is only permitted when APP_ENV is development/testing"
                )
            if is_hosted_runtime():
                problems.append("DEV_AUTH_ENABLED is not permitted on a managed hosting platform")

        if problems:
            raise InsecureConfigurationError(
                "Insecure security configuration: " + "; ".join(problems) + "."
            )
        return self

    def validate_for_serving(self) -> None:
        """Enforce the web-server security requirements (called when the API app is built).

        Operational scripts (migrations, audits) construct ``Settings`` without calling this, so
        they need only their own configuration; the running API can never skip it because
        ``create_app`` and the lifespan both invoke it.
        """
        if self.app_env != "production":
            return
        problems: list[str] = []
        if not self.entra_auth_enabled:
            problems.append("ENTRA_AUTH_ENABLED must be true in production")
        if not self.entra_tenant_id or not _GUID_PATTERN.match(self.entra_tenant_id.strip()):
            problems.append("ENTRA_TENANT_ID must be explicitly set to a valid tenant GUID")
        if not self.entra_audience or not self.entra_audience.strip():
            problems.append("ENTRA_AUDIENCE must be set in production")
        if not self.entra_required_scopes:
            problems.append("ENTRA_REQUIRED_SCOPES must contain at least one scope")
        if not self.entra_allowed_client_ids:
            problems.append("ENTRA_ALLOWED_CLIENT_IDS must list the approved client applications")
        elif any(not _GUID_PATTERN.match(c) for c in self.entra_allowed_client_ids):
            problems.append("ENTRA_ALLOWED_CLIENT_IDS must contain only GUIDs")
        if is_insecure_secret(self.secret_key):
            problems.append(
                f"SECRET_KEY must be a non-default secret of at least "
                f"{MIN_PRODUCTION_SECRET_LENGTH} characters"
            )
        if is_insecure_secret(self.finops_signing_secret):
            problems.append(
                f"FINOPS_SIGNING_SECRET must be a non-default secret of at least "
                f"{MIN_PRODUCTION_SECRET_LENGTH} characters"
            )
        if "cors_origins" not in self.model_fields_set or not self.cors_origins:
            problems.append("CORS_ORIGINS must be set explicitly in production")
        elif any(is_local_origin(o) or o.strip() == "*" for o in self.cors_origins):
            problems.append(
                "CORS_ORIGINS must not contain localhost or wildcard origins in production"
            )
        elif any(not o.strip().lower().startswith("https://") for o in self.cors_origins):
            problems.append("CORS_ORIGINS must use https:// origins in production")
        if self.debug:
            problems.append("DEBUG must be false in production")
        if problems:
            raise InsecureConfigurationError(
                "Insecure security configuration: " + "; ".join(problems) + "."
            )

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_PLACEHOLDER_CREDENTIAL_PATTERNS: tuple[str, ...] = (
    "your_",
    "your-",
    "placeholder",
    "changeme",
    "change_me",
    "change-me",
    "change-in-production",
    "replace_me",
    "replace-me",
    "xxx",
    "{{secrets/",
)


def is_valid_credential_value(value: str | None) -> bool:
    """Return True if a credential value is non-empty, >= 10 chars, and not a placeholder."""
    if not value:
        return False
    cleaned = value.strip()
    if len(cleaned) < 10:
        return False
    if (cleaned.startswith("<") and cleaned.endswith(">")) or (
        cleaned.startswith("${") and cleaned.endswith("}")
    ):
        return False
    lowered = cleaned.lower()
    return not any(pattern in lowered for pattern in _PLACEHOLDER_CREDENTIAL_PATTERNS)


def has_valid_sp_credentials(*values: str | None) -> bool:
    """Return True only when all supplied Service Principal credential fields are valid."""
    return bool(values) and all(is_valid_credential_value(val) for val in values)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


def get_operational_settings() -> Settings:
    """Settings for operational scripts (migrations, audits).

    Same construction-time safety checks (explicit APP_ENV, no dev auth, consistent Entra
    settings) but NOT the web-server serving requirements, and it never alters authentication
    behaviour of any running API. Scripts must not print values from this object.
    """
    return get_settings()


def redact_connection_string(text: str, database_url: str | None = None) -> str:
    """Remove credentials from DSN-like text before printing (``scheme://user:pw@host``)."""
    redacted = re.sub(r"(://[^/\s:@]*):[^@\s/]*@", r"\1:***@", text)
    if database_url:
        from urllib.parse import unquote, urlparse

        password = urlparse(database_url).password
        if password:
            for variant in {password, unquote(password)}:
                redacted = redacted.replace(variant, "***")
    return redacted


def reload_settings() -> Settings:
    """Re-read .env files fresh and return an updated Settings instance without mutating os.environ."""
    env_overrides: dict[str, str] = {}
    for env_path in (Path("backend/.env"), Path(".env")):
        if env_path.is_file():
            for key, val in dotenv_values(env_path).items():
                if key and val is not None:
                    env_overrides[key.lower()] = val
    get_settings.cache_clear()
    valid_fields = set(Settings.model_fields.keys())
    filtered = {k: v for k, v in env_overrides.items() if k in valid_fields}
    return Settings(**filtered)  # type: ignore[arg-type]


def setup_logging(settings: Settings) -> None:
    """Configure structured logging based on application settings."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Quiet external loggers that can be excessively verbose
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
