"""Seed loader for curated multi-cloud service catalog fixtures."""

import json
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.db.repositories.catalog_repo import CatalogRepository
from cloud_recommender.schemas.catalog import CatalogServiceBase

logger = structlog.get_logger(__name__)

CURATED_DATA_PATH = Path(__file__).parent / "data" / "curated_services.json"


def load_curated_catalog() -> list[CatalogServiceBase]:
    """Load and validate the curated catalog fixtures from JSON file."""
    if not CURATED_DATA_PATH.exists():
        raise FileNotFoundError(f"Curated catalog fixtures not found at {CURATED_DATA_PATH}")

    with open(CURATED_DATA_PATH, encoding="utf-8") as f:
        raw_data = json.load(f)

    services: list[CatalogServiceBase] = []
    for item in raw_data:
        service = CatalogServiceBase.model_validate(item)
        services.append(service)

    return services


async def seed_catalog(session: AsyncSession) -> int:
    """Idempotently seed curated catalog fixtures into the operational database.

    Returns the count of catalog services seeded or updated.
    """
    services = load_curated_catalog()
    repo = CatalogRepository(session)
    count = await repo.seed_services(services)
    logger.info("catalog_seeding_complete", seeded_count=count)
    return count
