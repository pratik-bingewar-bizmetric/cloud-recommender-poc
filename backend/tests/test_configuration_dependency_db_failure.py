"""Regression: a database error inside a configuration route must not become a generic HTTP 500.

``get_configuration_service`` used to ``yield`` a second time from ``except Exception``. A route
error thrown back into the generator then raised ``RuntimeError: generator didn't stop after
athrow()``, so an unreachable database produced HTTP 500 instead of the 503 DATABASE_UNAVAILABLE
handler. The memory fallback must apply only when the session factory cannot be built.
"""

import pytest
from sqlalchemy.exc import OperationalError

from cloud_recommender.api.routes import configuration as routes
from cloud_recommender.core.config import Settings


class _Session:
    def __init__(self) -> None:
        self.rolled_back = False
        self.closed = False
        self.fail_rollback = False

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def rollback(self) -> None:
        if self.fail_rollback:
            raise ConnectionError("connection already lost")
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


def _settings() -> Settings:
    return Settings(app_env="testing", catalog_offline_mode=False)


def _db_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, ConnectionRefusedError("refused"))


async def test_database_error_from_the_route_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    monkeypatch.setattr(routes, "get_session_factory", lambda: lambda: session)
    gen = routes.get_configuration_service(_settings())
    service = await gen.__anext__()
    assert service.repository is not None
    error = _db_error()
    with pytest.raises(OperationalError) as caught:
        await gen.athrow(error)
    assert caught.value is error  # not RuntimeError("generator didn't stop after athrow()")
    assert session.rolled_back and session.closed


async def test_failed_rollback_does_not_mask_the_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    session.fail_rollback = True
    monkeypatch.setattr(routes, "get_session_factory", lambda: lambda: session)
    gen = routes.get_configuration_service(_settings())
    await gen.__anext__()
    with pytest.raises(OperationalError):
        await gen.athrow(_db_error())
    assert session.closed


async def test_memory_fallback_only_when_the_session_factory_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> object:
        raise RuntimeError("engine could not be created")

    monkeypatch.setattr(routes, "get_session_factory", broken)
    gen = routes.get_configuration_service(_settings())
    service = await gen.__anext__()
    assert service.repository is None
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


async def test_offline_catalog_mode_still_uses_memory() -> None:
    gen = routes.get_configuration_service(Settings(app_env="testing", catalog_offline_mode=True))
    service = await gen.__anext__()
    assert service.repository is None
