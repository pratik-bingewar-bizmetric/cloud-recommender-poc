"""Regression tests: list-valued settings parse consistently from every source.

Bug: ``DEV_AUTH_ROLES=["FinOpsAdmin"]`` in ``.env`` made ``reload_settings()`` fail with
"dev_auth_roles: Input should be a valid list", because ``reload_settings`` passes raw ``.env``
strings as init arguments (no JSON decoding) and the field had no string-splitting validator.
"""

from pathlib import Path

import pytest

from cloud_recommender.core.config import (
    InsecureConfigurationError,
    Settings,
    reload_settings,
)

GUID = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DEV_AUTH_ROLES",
        "DEV_AUTH_ENABLED",
        "ENTRA_REQUIRED_SCOPES",
        "ENTRA_ALLOWED_CLIENT_IDS",
    ):
        monkeypatch.delenv(name, raising=False)


CASES = [
    ('["FinOpsAdmin"]', ["FinOpsAdmin"]),  # documented list format
    ('["FinOpsAdmin", "Other"]', ["FinOpsAdmin", "Other"]),
    ("FinOpsAdmin", ["FinOpsAdmin"]),  # plain value
    ("FinOpsAdmin,Other", ["FinOpsAdmin", "Other"]),  # comma separated
    ("FinOpsAdmin Other", ["FinOpsAdmin", "Other"]),  # space separated
    ("[]", []),
    ("", []),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_dev_auth_roles_parse_from_the_process_environment(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("DEV_AUTH_ROLES", raw)
    assert Settings(_env_file=None, app_env="development").dev_auth_roles == expected  # type: ignore[call-arg]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_dev_auth_roles_parse_through_reload_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    """The exact failing path: reload_settings() feeds raw .env strings to Settings."""
    (tmp_path / ".env").write_text(
        f"APP_ENV=development\nDEV_AUTH_ENABLED=true\nDEV_AUTH_ROLES={raw}\n", encoding="utf-8"
    )
    monkeypatch.setattr("cloud_recommender.core.config._REPO_ROOT", tmp_path)
    monkeypatch.delenv("APP_ENV", raising=False)
    settings = reload_settings()
    assert settings.dev_auth_roles == expected
    assert settings.dev_auth_enabled is True


def test_default_is_no_roles_and_dev_auth_off() -> None:
    settings = Settings(_env_file=None, app_env="development", dev_auth_enabled=False)  # type: ignore[call-arg]
    assert settings.dev_auth_roles == []
    assert settings.dev_auth_enabled is False


def test_roles_given_as_a_list_argument_are_preserved() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, app_env="development", dev_auth_enabled=True, dev_auth_roles=["FinOpsAdmin"]
    )
    assert settings.dev_auth_roles == ["FinOpsAdmin"]


def test_other_list_settings_parse_the_same_way_through_reload_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        f'APP_ENV=development\nENTRA_ALLOWED_CLIENT_IDS=["{GUID}"]\nENTRA_REQUIRED_SCOPES=access_as_user\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("cloud_recommender.core.config._REPO_ROOT", tmp_path)
    monkeypatch.delenv("APP_ENV", raising=False)
    settings = reload_settings()
    assert settings.entra_allowed_client_ids == [GUID]
    assert settings.entra_required_scopes == ["access_as_user"]


@pytest.mark.parametrize("env", ["production", "staging"])
def test_dev_auth_remains_restricted_to_local_development(env: str) -> None:
    with pytest.raises(InsecureConfigurationError, match="DEV_AUTH_ENABLED"):
        Settings(  # type: ignore[call-arg]
            _env_file=None, app_env=env, dev_auth_enabled=True, dev_auth_roles=["FinOpsAdmin"]
        )


def test_roles_without_the_flag_grant_nothing_in_production() -> None:
    """Setting DEV_AUTH_ROLES alone never enables a dev identity (the flag stays off)."""
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="development",
        dev_auth_enabled=False,
        dev_auth_roles=["FinOpsAdmin"],
    )
    assert settings.dev_auth_enabled is False
