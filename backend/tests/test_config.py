"""Unit tests for configuration loading and validation."""

import pytest
from pydantic import ValidationError

from cloud_recommender.core.config import Settings, get_settings


def test_default_settings_values() -> None:
    """Verify safe default settings."""
    settings = Settings()
    assert settings.app_name == "cloud-recommender"
    assert settings.app_env in ["development", "testing"]
    assert settings.llm_provider == "mock"
    assert settings.fabric_enabled is False
    assert settings.offline_pricing_mode is True
    assert settings.azure_subscription_id is None
    assert settings.api_port == 8000
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_custom_settings_override() -> None:
    """Verify settings can be overridden with valid inputs."""
    custom = Settings(
        app_name="custom-recommender",
        app_env="production",
        api_port=9000,
        debug=True,
        llm_provider="openai",
        fabric_enabled=True,
    )
    assert custom.app_name == "custom-recommender"
    assert custom.app_env == "production"
    assert custom.api_port == 9000
    assert custom.debug is True
    assert custom.llm_provider == "openai"
    assert custom.fabric_enabled is True


def test_database_url_normalization() -> None:
    """Verify database URL normalizes standard postgresql scheme to asyncpg driver."""
    settings = Settings(database_url="postgresql://user:pass@localhost:5432/db")
    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost:5432/db"

    settings_alt = Settings(database_url="postgres://user:pass@localhost:5432/db")
    assert settings_alt.database_url == "postgresql+asyncpg://user:pass@localhost:5432/db"


def test_invalid_port_validation() -> None:
    """Verify validation fails on out-of-range port numbers."""
    with pytest.raises(ValidationError):
        Settings(api_port=99999)

    with pytest.raises(ValidationError):
        Settings(api_port=0)


def test_invalid_environment_validation() -> None:
    """Verify validation fails on unknown environment strings."""
    with pytest.raises(ValidationError):
        Settings(app_env="invalid_env")  # type: ignore[arg-type]


def test_get_settings_cached() -> None:
    """Verify get_settings returns consistent cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_setup_logging_configurations() -> None:
    """Verify setup_logging configures structured logger without error."""
    from cloud_recommender.core.config import setup_logging

    json_settings = Settings(log_format="json", log_level="DEBUG")
    setup_logging(json_settings)

    console_settings = Settings(log_format="console", log_level="INFO")
    setup_logging(console_settings)
