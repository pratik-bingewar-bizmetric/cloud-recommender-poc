"""AWS provider ingestion contract.

Honest status:
- Phase 1 AWS discovery and read-only resource inventory is active.
- Live billing ingestion (Cost Explorer / CUR ingestion) remains DEFERRED per zero-mutation & non-billable policy.
- Does NOT fabricate or claim live cost telemetry.
"""

from __future__ import annotations

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.ingestion import IngestionScope, ResourceIngestionStatus
from cloud_recommender.services.ingestion.providers.base import (
    BaseProviderIngestor,
    ResourceExtractionResult,
)

logger = structlog.get_logger(__name__)


class AwsProviderIngestor(BaseProviderIngestor):
    """Honest read-only ingestor for AWS."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def ingest_scope(self, scope: IngestionScope) -> list[ResourceExtractionResult]:
        """Extract inventory strictly for scoped AWS resources; billing ingestion is deferred."""
        logger.info("aws_ingestion_scope_evaluated", connection_id=scope.connection_id)
        results: list[ResourceExtractionResult] = []

        for res_id in scope.effective_resource_ids:
            results.append(
                ResourceExtractionResult(
                    resource_id=res_id,
                    status=ResourceIngestionStatus.SKIPPED,
                    error_message=(
                        "AWS Phase 1 resource discovery is active, but live billing ingestion (CUR/Cost Explorer) "
                        "is DEFERRED in this phase. Zero billing modifications were performed."
                    ),
                    inventory_extracted=True,
                    cost_extracted=False,
                    metrics_extracted=False,
                )
            )
        return results
