"""Modular provider ingestion interface implementations."""

from cloud_recommender.services.ingestion.providers.aws import AwsProviderIngestor
from cloud_recommender.services.ingestion.providers.azure import AzureProviderIngestor
from cloud_recommender.services.ingestion.providers.base import (
    BaseProviderIngestor,
    ResourceExtractionResult,
)
from cloud_recommender.services.ingestion.providers.databricks import (
    DatabricksWorkspaceIngestor,
)
from cloud_recommender.services.ingestion.providers.gcp import GcpProviderIngestor

__all__ = [
    "BaseProviderIngestor",
    "ResourceExtractionResult",
    "AzureProviderIngestor",
    "DatabricksWorkspaceIngestor",
    "GcpProviderIngestor",
    "AwsProviderIngestor",
]
