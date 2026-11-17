"""Regression: CORS_ORIGINS must parse from App Service style (comma separated) settings.

Before the fix a comma separated value crashed startup with a JSON decode error, because the
field lacked ``NoDecode`` (pydantic-settings JSON-decodes complex env values before validators run).
"""

import pytest

from cloud_recommender.core.config import Settings

FABRIC = "https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net"
PORTAL = "https://app.fabric.microsoft.com"


@pytest.mark.parametrize(
    "raw",
    [
        f"{FABRIC},{PORTAL}",
        f"{FABRIC}, {PORTAL}",
        f'["{FABRIC}","{PORTAL}"]',
    ],
)
def test_cors_origins_parse_from_environment(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", raw)
    settings = Settings()
    assert settings.cors_origins == [FABRIC, PORTAL]
    assert "cors_origins" in settings.model_fields_set


def test_unset_cors_origins_is_not_treated_as_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert "cors_origins" not in Settings().model_fields_set
