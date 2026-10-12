"""PostgreSQL integration tests against a live, isolated database.

Executes real database migrations, ORM persistence, JSONB/UUID types,
catalog seeding, and verified record protection against PostgreSQL.
Automatically skipped if PostgreSQL is unavailable.
"""

import os
from collections.abc import Generator
from decimal import Decimal

import asyncpg  # type: ignore[import-untyped]
import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from cloud_recommender.catalog.seeds import seed_catalog
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

# Determine PostgreSQL test connection URL
DEFAULT_PG_ADMIN_URL = os.getenv(
    "TEST_PG_ADMIN_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)
TEST_DB_NAME = "cloud_recommender_it_db"
ASYNC_TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://postgres:postgres@localhost:5432/{TEST_DB_NAME}",
)


async def is_postgres_available() -> bool:
    """Check if PostgreSQL admin endpoint is reachable."""
    try:
        conn = await asyncpg.connect(DEFAULT_PG_ADMIN_URL, timeout=2.0)
        await conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def postgres_available() -> bool:
    import asyncio

    try:
        return asyncio.run(is_postgres_available())
    except Exception:
        return False


@pytest.fixture(scope="module")
def isolated_pg_db(postgres_available: bool) -> Generator[str, None, None]:
    """Create a temporary isolated test database, run migrations, and teardown."""

    if not postgres_available:
        pytest.skip(
            "PostgreSQL integration tests skipped: PostgreSQL server not reachable at "
            f"{DEFAULT_PG_ADMIN_URL}. Set TEST_DATABASE_URL to enable."
        )

    import asyncio

    async def _setup() -> None:
        conn = await asyncpg.connect(DEFAULT_PG_ADMIN_URL)
        exists = await conn.fetchval(f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DB_NAME}'")
        if exists:
            await conn.execute(f"DROP DATABASE {TEST_DB_NAME} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {TEST_DB_NAME}")
        await conn.close()

    async def _teardown() -> None:
        conn = await asyncpg.connect(DEFAULT_PG_ADMIN_URL)
        await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")
        await conn.close()

    asyncio.run(_setup())

    # Run Alembic upgrade head
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", ASYNC_TEST_DB_URL)
    command.upgrade(alembic_cfg, "head")

    yield ASYNC_TEST_DB_URL

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
