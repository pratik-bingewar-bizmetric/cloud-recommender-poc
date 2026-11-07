"""AWS provider ingestion contract.

Honest status: AWS live integration is not configured in this deployment.
Does NOT fabricate or claim live telemetry.
"""

import structlog

from cloud_recommender.schemas.ingestion import IngestionScope, ResourceIngestionStatus
from cloud_recommender.services.ingestion.providers.base import (
    BaseProviderIngestor,
    ResourceExtractionResult,
)

logger = structlog.get_logger(__name__)


class AwsProviderIngestor(BaseProviderIngestor):
    """Honest unconfigured ingestor for AWS."""

    async def ingest_scope(self, scope: IngestionScope) -> list[ResourceExtractionResult]:
        """Return clear unconfigured status for any scoped AWS resources."""
        logger.warning("aws_ingestion_attempted_unsupported", connection_id=scope.connection_id)
        results: list[ResourceExtractionResult] = []
        for res_id in scope.effective_resource_ids:
            results.append(
                ResourceExtractionResult(
                    resource_id=res_id,
                    status=ResourceIngestionStatus.SKIPPED,
                    error_message="AWS provider is not configured. AWS multi-cloud ingestion will be supported in a future release.",
                    inventory_extracted=False,
                    cost_extracted=False,
                    metrics_extracted=False,
                )
            )
        return results
