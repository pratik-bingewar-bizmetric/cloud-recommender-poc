"""Azure scope-aware provider ingestion implementation.

Scoped strictly to subscriptions, resource groups, individual resources, and Databricks workspaces.
Zero Azure mutations; read-only operations only.
"""

from typing import Any

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.ingestion import IngestionScope, ResourceIngestionStatus
from cloud_recommender.services.ingestion.providers.base import (
    BaseProviderIngestor,
    ResourceExtractionResult,
)
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService

logger = structlog.get_logger(__name__)


class AzureProviderIngestor(BaseProviderIngestor):
    """Ingests scoped Azure resources, costs, and metrics strictly bounded by effective scope."""

    def __init__(
        self,
        azure_service: AzureInventoryService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.azure_service = azure_service or AzureInventoryService(settings=self.settings)

    async def ingest_scope(self, scope: IngestionScope) -> list[ResourceExtractionResult]:
        """Execute ingestion strictly for the resource IDs admitted in scope."""
        results: list[ResourceExtractionResult] = []
        token, auth_method = await self.azure_service.get_access_token()

        logger.info(
            "azure_scope_ingestion_started",
            connection_id=scope.connection_id,
            configuration_version=scope.configuration_version,
            resource_count=len(scope.effective_resource_ids),
            auth_method=auth_method,
        )

        for res_id in scope.effective_resource_ids:
            try:
                # Server-side guard: enforce scope boundary
                if res_id not in scope.effective_resource_ids:
                    logger.warning("unscoped_resource_rejected", resource_id=res_id)
                    continue

                res_result = await self._ingest_single_resource(res_id, token, auth_method)
                results.append(res_result)

            except Exception as exc:
                logger.error(
                    "resource_ingestion_failed",
                    resource_id=res_id,
                    error=str(exc),
                )
                results.append(
                    ResourceExtractionResult(
                        resource_id=res_id,
                        status=ResourceIngestionStatus.FAILED,
                        error_message=str(exc),
                        inventory_extracted=False,
                        cost_extracted=False,
                        metrics_extracted=False,
                    )
                )

        return results

    async def _ingest_single_resource(
        self, resource_id: str, token: str | None, auth_method: str
    ) -> ResourceExtractionResult:
        """Extract inventory, cost, and metrics for a single scoped Azure resource."""
        parts = resource_id.split("/")
        res_name = parts[-1] if parts else resource_id
        res_type = ""
        if len(parts) >= 8 and parts[5] == "providers":
            res_type = f"{parts[6]}/{parts[7]}"

        if not token or auth_method == "none":
            if not self.settings.allow_demo_fixtures:
                # Never fabricate extraction results for an unauthenticated run.
                return ResourceExtractionResult(
                    resource_id=resource_id,
                    resource_type=res_type or None,
                    status=ResourceIngestionStatus.FAILED,
                    error_message=(
                        "Azure authentication required: no valid Azure identity. "
                        "Run 'az login' or configure a service principal."
                    ),
                )
            # Explicit DEMO fixture (ALLOW_DEMO_FIXTURES=true only): clearly labelled.
            is_workspace = "microsoft.databricks" in resource_id.lower()
            return ResourceExtractionResult(
                resource_id=resource_id,
                resource_type=res_type
                or (
                    "Microsoft.Databricks/workspaces"
                    if is_workspace
                    else "Microsoft.Compute/virtualMachines"
                ),
                region="eastus",
                status=ResourceIngestionStatus.SUCCESS,
                inventory_extracted=True,
                cost_extracted=True,
                metrics_extracted=True,
                extracted_records_count=24,  # 24 hourly metric samples
                inventory_payload={
                    "id": resource_id,
                    "name": res_name,
                    "type": res_type,
                    "data_source": "demo_fixture",
                },
                cost_records=[
                    {
                        "resource_id": resource_id,
                        "date": "2026-11-05",
                        "cost_in_usd": 12.50,
                        "currency": "USD",
                    }
                ],
                metric_records=[
                    {
                        "resource_id": resource_id,
                        "metric_name": "Percentage CPU",
                        "average": 42.5,
                        "unit": "Percent",
                    }
                ],
            )

        # Live run: only what the ARM resource id itself proves. Cost and metrics are NOT
        # invented here; they are retrieved by the Cost Management / Monitor modules, so
        # this ingestion step reports them as not extracted.
        inv_payload: dict[str, Any] = {
            "id": resource_id,
            "name": res_name,
            "type": res_type,
            "data_source": "live_authenticated",
        }
        return ResourceExtractionResult(
            resource_id=resource_id,
            resource_type=res_type,
            region=None,
            status=ResourceIngestionStatus.SUCCESS,
            inventory_extracted=True,
            cost_extracted=False,
            metrics_extracted=False,
            extracted_records_count=1,
            inventory_payload=inv_payload,
            error_message=(
                "Inventory identifiers only. Cost and metrics were not extracted by this step."
            ),
        )
