"""GCP scope-aware provider ingestion implementation.

Scoped to organizations, projects, and assets.
Preserves existing partial benchmark fixture implementation status.
"""

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.ingestion import IngestionScope, ResourceIngestionStatus
from cloud_recommender.services.ingestion.providers.base import (
    BaseProviderIngestor,
    ResourceExtractionResult,
)
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService

logger = structlog.get_logger(__name__)


class GcpProviderIngestor(BaseProviderIngestor):
    """Ingests scoped GCP project resources, costs, and metrics."""

    def __init__(
        self,
        gcp_service: GcpInventoryService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.gcp_service = gcp_service or GcpInventoryService(settings=self.settings)

    async def ingest_scope(self, scope: IngestionScope) -> list[ResourceExtractionResult]:
        """Extract inventory and telemetry strictly for scoped GCP resources."""
        results: list[ResourceExtractionResult] = []

        logger.info(
            "gcp_scope_ingestion_started",
            connection_id=scope.connection_id,
            resource_count=len(scope.effective_resource_ids),
        )

        if not self.settings.allow_demo_fixtures:
            # Live GCP extraction is not implemented here; never fabricate results.
            for res_id in scope.effective_resource_ids:
                results.append(
                    ResourceExtractionResult(
                        resource_id=res_id,
                        status=ResourceIngestionStatus.SKIPPED,
                        error_message=(
                            "Live GCP ingestion is not available; no data was fabricated. "
                            "(Demo fixtures are disabled.)"
                        ),
                    )
                )
            return results

        for res_id in scope.effective_resource_ids:
            try:
                res_name = res_id.split("/")[-1] if "/" in res_id else res_id
                results.append(
                    ResourceExtractionResult(
                        resource_id=res_id,
                        resource_type="compute.googleapis.com/Instance"
                        if "vm" in res_name
                        else "storage.googleapis.com/Bucket",
                        region="us-central1",
                        status=ResourceIngestionStatus.SUCCESS,
                        inventory_extracted=True,
                        cost_extracted=True,
                        metrics_extracted=True,
                        extracted_records_count=10,
                        inventory_payload={
                            "asset_name": res_id,
                            "display_name": res_name,
                            "state": "RUNNING",
                        },
                        cost_records=[
                            {
                                "resource_id": res_id,
                                "date": "2026-11-05",
                                "cost_in_usd": 8.75,
                                "currency": "USD",
                            }
                        ],
                        metric_records=[
                            {
                                "resource_id": res_id,
                                "metric_name": "compute.googleapis.com/instance/cpu/utilization",
                                "value": 0.38,
                            }
                        ],
                    )
                )
            except Exception as exc:
                results.append(
                    ResourceExtractionResult(
                        resource_id=res_id,
                        status=ResourceIngestionStatus.FAILED,
                        error_message=str(exc),
                    )
                )

        return results
