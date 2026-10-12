"""PostgreSQL integration tests against a live, isolated database.

Executes real database migrations, ORM persistence, JSONB/UUID types,
catalog seeding, and verified record protection against PostgreSQL.
Enforces strict database isolation guards to prevent destructive actions
against production or development databases.
"""

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal

import asyncpg  # type: ignore[import-untyped]
import pytest
from alembic.config import Config
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from cloud_recommender.catalog.seeds import seed_catalog
from cloud_recommender.core.config import get_settings
from cloud_recommender.db.repositories.catalog_repo import CatalogRepository
from cloud_recommender.db.repositories.workload_repo import WorkloadRepository
from cloud_recommender.schemas.catalog import CatalogServiceFilter
from cloud_recommender.schemas.common import (
    CatalogRecordStatus,
    CloudProvider,
    ServiceCategory,
    WorkloadCategory,
)
from cloud_recommender.schemas.workload import WorkloadProfileCreate

PROTECTED_DB_NAMES = frozenset(
    {
        "postgres",
        "template0",
        "template1",
        "public",
        "cloud_recommender",
        "master",
        "model",
        "msdb",
    }
)


def validate_test_database_target(test_db_url: str) -> str:
    """Validate that test_db_url points to a dedicated, safe, isolated test database.

    Raises ValueError if:
    - URL is empty or lacks a database name.
    - Target database name matches any protected database name.
    - Target database name matches application dev/prod database in Settings.
    - Target database name does not contain an explicit test isolation marker.
    """
    if not test_db_url or not test_db_url.strip():
        raise ValueError("TEST_DATABASE_URL is empty or not configured.")

    parsed = make_url(test_db_url)
    db_name = parsed.database
    if not db_name or not db_name.strip():
        raise ValueError(f"TEST_DATABASE_URL has no database name: '{test_db_url}'")

    db_lower = db_name.lower().strip()

    if db_lower in PROTECTED_DB_NAMES:
        raise ValueError(
            f"Safety check failed: TEST_DATABASE_URL targets protected database '{db_name}'. "
            "Destructive operations are strictly prohibited."
        )

    # Check against configured application database from settings
    app_settings = get_settings()
    if app_settings.database_url:
        app_db_name = make_url(app_settings.database_url).database
        if app_db_name and db_lower == app_db_name.lower().strip():
            raise ValueError(
                f"Safety check failed: TEST_DATABASE_URL targets application database "
                f"'{app_db_name}'. Destructive operations are strictly prohibited."
            )

    # Require an explicit test isolation marker in the database name
    valid_markers = ("test", "_it_", "tmp")
    if not any(marker in db_lower for marker in valid_markers):
        raise ValueError(
            f"Safety check failed: TEST_DATABASE_URL database name '{db_name}' must contain "
            "an explicit test isolation marker ('test', '_it_', or 'tmp')."
        )

    return db_name


def get_admin_url(test_db_url: str) -> str:
    """Derive admin PostgreSQL connection URL for database creation/teardown."""
    admin_override = os.getenv("TEST_PG_ADMIN_URL")
    if admin_override and admin_override.strip():
        return admin_override.strip()

    parsed = make_url(test_db_url)
    # asyncpg connect requires postgresql:// driver and postgres database
    return parsed.set(database="postgres", drivername="postgresql").render_as_string(
        hide_password=False
    )


async def is_postgres_available(admin_url: str) -> bool:
    """Check if PostgreSQL admin endpoint is reachable."""
    try:
        conn = await asyncpg.connect(admin_url, timeout=2.0)
        await conn.close()
        return True
    except Exception:
        return False


# -------------------------------------------------------------------------
# Isolation Guard Unit Tests (Run unconditionally, offline-safe)
# -------------------------------------------------------------------------


def test_isolation_guard_rejects_empty_url() -> None:
    with pytest.raises(ValueError, match="TEST_DATABASE_URL is empty"):
        validate_test_database_target("")


def test_isolation_guard_rejects_protected_postgres_database() -> None:
    with pytest.raises(ValueError, match="targets protected database 'postgres'"):
        validate_test_database_target("postgresql+asyncpg://user:pass@localhost:5432/postgres")


def test_isolation_guard_rejects_protected_cloud_recommender_database() -> None:
    with pytest.raises(ValueError, match="targets protected database 'cloud_recommender'"):
        validate_test_database_target(
            "postgresql+asyncpg://user:pass@localhost:5432/cloud_recommender"
        )


def test_isolation_guard_rejects_database_without_test_marker() -> None:
    with pytest.raises(ValueError, match="must contain an explicit test isolation marker"):
        validate_test_database_target(
            "postgresql+asyncpg://user:pass@localhost:5432/production_analytics"
        )


def test_isolation_guard_accepts_valid_isolated_test_database() -> None:
    db_name = validate_test_database_target(
        "postgresql+asyncpg://user:pass@localhost:5432/cloud_recommender_it_db"
    )
    assert db_name == "cloud_recommender_it_db"

    db_name2 = validate_test_database_target(
        "postgresql+asyncpg://user:pass@localhost:5432/recommender_unit_test"
    )
    assert db_name2 == "recommender_unit_test"


# -------------------------------------------------------------------------
# Integration Fixture & Tests (Require explicit TEST_DATABASE_URL)
# -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def isolated_pg_db() -> Generator[str, None, None]:
    """Create a temporary isolated test database, run migrations, and teardown."""
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url or not test_db_url.strip():
        pytest.skip("PostgreSQL integration tests skipped: TEST_DATABASE_URL is not set.")

    # Validate isolation guard before doing anything
    test_db_name = validate_test_database_target(test_db_url)
    admin_url = get_admin_url(test_db_url)

    # Check PostgreSQL connectivity
    try:
        available = asyncio.run(is_postgres_available(admin_url))
    except Exception:
        available = False

    if not available:
        pytest.skip(
            f"PostgreSQL integration tests skipped: PostgreSQL server not reachable at {admin_url}."
        )

    async def _setup() -> None:
        conn = await asyncpg.connect(admin_url)
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", test_db_name)
        if exists:
            await conn.execute(f'DROP DATABASE "{test_db_name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{test_db_name}"')
        await conn.close()

    async def _teardown() -> None:
        # Re-validate isolation guard before teardown
        validate_test_database_target(test_db_url)
        conn = await asyncpg.connect(admin_url)
        await conn.execute(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)')
        await conn.close()

    asyncio.run(_setup())

    # Run Alembic upgrade head
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url.replace("%", "%%"))
    command.upgrade(alembic_cfg, "head")

    yield test_db_url

    # Run Alembic downgrade base and teardown DB
    command.downgrade(alembic_cfg, "base")
    asyncio.run(_teardown())


@pytest.mark.asyncio
async def test_postgres_workload_persistence_and_query(isolated_pg_db: str) -> None:
    """Test full WorkloadProfileModel persistence with native UUID, JSONB, and Decimal types."""
    engine = create_async_engine(isolated_pg_db, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        repo = WorkloadRepository(session)
        dto = WorkloadProfileCreate(
            name="Live PG Integration Test Workload",
            category=WorkloadCategory.MICROSERVICES,
            target_traffic_rps=1500,
            peak_multiplier=Decimal("3.50"),
            target_sla_percentage=Decimal("99.950"),
            max_monthly_budget=Decimal("4500.00"),
            cost_buffer_percentage=Decimal("15.00"),
            estimation_assumptions={"compute_mode": "serverless_first"},
        )
        saved = await repo.create(dto)
        assert saved.id is not None
        saved_id = saved.id

    # Retrieve in fresh session
    async with session_factory() as session:
        repo = WorkloadRepository(session)
        loaded = await repo.get_by_id(saved_id)
        assert loaded is not None
        assert loaded.name == "Live PG Integration Test Workload"
        assert loaded.peak_multiplier == Decimal("3.50")
        assert loaded.max_monthly_budget == Decimal("4500.00")
        assert loaded.estimation_assumptions == {"compute_mode": "serverless_first"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_catalog_seeding_and_verified_protection(isolated_pg_db: str) -> None:
    """Test catalog fixture seeding and verified status protection on real PostgreSQL."""
    engine = create_async_engine(isolated_pg_db, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Seed all 18 fixtures
    async with session_factory() as session:
        count = await seed_catalog(session)
        assert count == 18

    # 2. Verify seeded data and query with filter
    async with session_factory() as session:
        repo = CatalogRepository(session)
        items, total = await repo.list_services(
            CatalogServiceFilter(provider=CloudProvider.AZURE, category=ServiceCategory.COMPUTE)
        )
        assert total >= 2
        assert all(i.provider == "azure" for i in items)

        # 3. Mark one service as 'verified'
        aca = await repo.get_by_provider_and_id(CloudProvider.AZURE, "azure-container-apps")
        assert aca is not None
        aca.status = CatalogRecordStatus.VERIFIED.value
        aca.description = "Protected verified custom description"
        await session.commit()

    # 4. Re-run seeding with force=False: verify protected record was NOT overwritten
    async with session_factory() as session:
        await seed_catalog(session, force=False)
        repo = CatalogRepository(session)
        aca_after_seed = await repo.get_by_provider_and_id(
            CloudProvider.AZURE, "azure-container-apps"
        )
        assert aca_after_seed is not None
        assert aca_after_seed.status == CatalogRecordStatus.VERIFIED.value
        assert aca_after_seed.description == "Protected verified custom description"

    # 5. Re-run seeding with force=True: verify protected record IS updated
    async with session_factory() as session:
        await seed_catalog(session, force=True)
        repo = CatalogRepository(session)
        aca_forced = await repo.get_by_provider_and_id(CloudProvider.AZURE, "azure-container-apps")
        assert aca_forced is not None
        assert aca_forced.status == CatalogRecordStatus.FIXTURE.value
        assert "Kubernetes and KEDA" in aca_forced.description

    await engine.dispose()
