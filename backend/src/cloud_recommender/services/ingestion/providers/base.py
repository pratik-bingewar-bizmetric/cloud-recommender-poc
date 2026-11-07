"""Base provider ingestion contract."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from cloud_recommender.schemas.ingestion import IngestionScope, ResourceIngestionStatus


class ResourceExtractionResult(BaseModel):
    """Extraction outcome and telemetry payloads for a single scoped resource."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    resource_id: str
    resource_type: str | None = None
    region: str | None = None
    status: ResourceIngestionStatus = ResourceIngestionStatus.SUCCESS
    inventory_extracted: bool = False
    cost_extracted: bool = False
    metrics_extracted: bool = False
    extracted_records_count: int = 0
    error_message: str | None = None
    inventory_payload: dict[str, Any] | None = None
    cost_records: list[dict[str, Any]] = []
    metric_records: list[dict[str, Any]] = []


class BaseProviderIngestor(ABC):
    """Abstract contract for cloud provider scope-aware data extraction."""

    @abstractmethod
    async def ingest_scope(self, scope: IngestionScope) -> list[ResourceExtractionResult]:
        """Extract inventory, cost, and metrics for all resources admitted in effective scope."""
        raise NotImplementedError
