"""Application configuration management using Pydantic Settings."""

import logging
import sys
from functools import lru_cache
from typing import Literal

import structlog
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings validated at runtime."""

    # Application Core
    app_name: str = Field(default="cloud-recommender", description="Application service name")
    app_env: Literal["development", "testing", "staging", "production"] = Field(
        default="development", description="Application runtime environment"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    api_host: str = Field(default="0.0.0.0", description="API server bind host")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API server bind port")
    api_v1_str: str = Field(default="/api/v1", description="Prefix for version 1 API routes")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins",
    )
    secret_key: str = Field(
        default="insecure-default-development-secret-key-change-in-production",
        description="Application secret key",
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
    azure_auth_method: Literal["service_principal", "default_azure_credential"] = Field(
        default="service_principal"
    )
    azure_tenant_id: str | None = Field(default=None)
    azure_client_id: str | None = Field(default=None)
    azure_client_secret: str | None = Field(default=None)
    azure_subscription_id: str | None = Field(default=None)

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
    pricing_cache_ttl_hours: int = Field(default=24, ge=1, le=168)

    # File Ingestion Limits
    max_document_size_mb: int = Field(default=25, ge=1, le=100)
    max_code_archive_size_mb: int = Field(default=100, ge=1, le=500)

    # Logging & Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")
    log_format: Literal["json", "console"] = Field(default="json")

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


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
