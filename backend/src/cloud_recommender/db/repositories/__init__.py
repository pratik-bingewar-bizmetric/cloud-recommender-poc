"""Database repository access layer."""

from cloud_recommender.db.repositories.catalog_repo import CatalogRepository
from cloud_recommender.db.repositories.configuration_repo import (
    ResourceConfigurationRepository,
)
from cloud_recommender.db.repositories.ingestion_repo import IngestionRepository
from cloud_recommender.db.repositories.workload_repo import WorkloadRepository

__all__ = [
    "WorkloadRepository",
    "CatalogRepository",
    "ResourceConfigurationRepository",
    "IngestionRepository",
]
