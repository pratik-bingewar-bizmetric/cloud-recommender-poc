"""Microsoft Fabric FinOps Sync Agent - Azure Monitor Metrics Extractor.

Extracts performance telemetry (CPU, memory, disk, IOPS, storage) from Azure Monitor.
Discovers metric definitions for discovered infrastructure resources, queries
time-series telemetry, generates deterministic record IDs, and maps to ResourceMetricRecord.
"""

import hashlib
import logging
from datetime import UTC, datetime

import httpx
from auth import AUDIENCE_ARM, AzureCliAuthManager
from config import SyncAgentConfig
from models import ResourceMetricRecord

logger = logging.getLogger("azure_sync_agent.monitor")

# Resource types that routinely expose Azure Monitor metrics
METRIC_ELIGIBLE_PREFIXES = (
    "microsoft.compute/virtualmachines",
    "microsoft.web/sites",
    "microsoft.web/serverfarms",
    "microsoft.dbforpostgresql/flexibleservers",
    "microsoft.sql/servers/databases",
    "microsoft.documentdb/databaseaccounts",
    "microsoft.storage/storageaccounts",
    "microsoft.search/searchservices",
    "microsoft.cognitiveservices/accounts",
)

PRIMARY_METRIC_CANDIDATES = [
    "cpu_percent",
    "Percentage CPU",
    "memory_percent",
    "MemoryPercentage",
    "disk_bytes_read",
    "disk_bytes_written",
    "storage_percent",
    "StorageUsed",
    "Http2xx",
    "Http5xx",
    "AverageResponseTime",
    "Transactions",
]


class AzureMonitorMetricsExtractor:
    """Extracts operational time-series metrics from Azure Monitor for provisioned resources."""

    def __init__(self, auth_manager: AzureCliAuthManager, config: SyncAgentConfig) -> None:
        self.auth_manager = auth_manager
        self.config = config

    def _is_metric_eligible(self, resource_type: str) -> bool:
        """Filter resources down to types that emit Azure Monitor metrics."""
        lower_type = resource_type.lower()
        return any(lower_type.startswith(prefix) for prefix in METRIC_ELIGIBLE_PREFIXES)

    def _get_metric_definitions(
        self, client: httpx.Client, headers: dict[str, str], resource_id: str
    ) -> list[str]:
        """Discover active metric names supported by the resource."""
        endpoint = (
            f"https://management.azure.com{resource_id}"
            "/providers/microsoft.insights/metricDefinitions?api-version=2018-01-01"
        )
        try:
            resp = client.get(endpoint, headers=headers)
            if resp.status_code != 200:
                logger.debug(
                    "Metric definitions not available for %s: HTTP %d",
                    resource_id,
                    resp.status_code,
                )
                return []

            data = resp.json()
            metric_defs = data.get("value", [])
            avail_names = [
                m["name"]["value"] for m in metric_defs if "name" in m and "value" in m["name"]
            ]

            # Prioritize candidates from PRIMARY_METRIC_CANDIDATES
            matched = [name for name in avail_names if name in PRIMARY_METRIC_CANDIDATES]
            if matched:
                return matched[:3]  # Query up to 3 metrics per resource to minimize call overhead
            return avail_names[:2]  # Fallback to first 2 metrics
        except Exception as ex:
            logger.debug("Failed to query metric definitions for %s: %s", resource_id, ex)
            return []

    def extract_metrics_for_resources(
        self, resource_items: list[dict[str, str]]
    ) -> list[ResourceMetricRecord]:
        """Extract Azure Monitor metrics for a list of resources [{'id': ..., 'type': ...}]."""
        token = self.auth_manager.get_token(AUDIENCE_ARM)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Filter candidate resources
        candidates = [
            item for item in resource_items if self._is_metric_eligible(item.get("type", ""))
        ][: self.config.metrics_max_resources]

        logger.info(
            "Found %d metric-eligible resources (capped at %d).",
            len(candidates),
            self.config.metrics_max_resources,
        )

        all_records: list[ResourceMetricRecord] = []
        ingestion_dt = datetime.now(UTC)

        with httpx.Client(
            verify=self.config.verify_ssl, timeout=self.config.request_timeout_sec
        ) as client:
            for item in candidates:
                res_id = item.get("id")
                if not res_id:
                    continue

                metric_names = self._get_metric_definitions(client, headers, res_id)
                if not metric_names:
                    continue

                metric_param = ",".join(metric_names)
                endpoint = (
                    f"https://management.azure.com{res_id}"
                    "/providers/microsoft.insights/metrics?api-version=2018-01-01"
                    f"&metricnames={metric_param}&timespan={self.config.metrics_timespan}"
                    f"&interval={self.config.metrics_interval}&aggregation=Average,Maximum,Minimum"
                )

                try:
                    resp = client.get(endpoint, headers=headers)
                    if resp.status_code != 200:
                        logger.debug(
                            "Metrics query failed for %s: HTTP %d", res_id, resp.status_code
                        )
                        continue

                    data = resp.json()
                    for m_val in data.get("value", []):
                        m_name = m_val.get("name", {}).get("value", "unknown")
                        unit = m_val.get("unit", "Count")
                        timeseries_list = m_val.get("timeseries", [])

                        for ts in timeseries_list:
                            for dp in ts.get("data", []):
                                avg = dp.get("average")
                                max_val = dp.get("maximum")
                                min_val = dp.get("minimum")

                                # Skip purely empty intervals where no telemetry occurred
                                if avg is None and max_val is None and min_val is None:
                                    continue

                                ts_raw = dp.get("timeStamp")
                                if not ts_raw:
                                    continue

                                ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))

                                # Deterministic record ID
                                raw_key = f"{res_id}:{m_name}:{ts_dt.isoformat()}"
                                metric_record_id = hashlib.sha256(
                                    raw_key.encode("utf-8")
                                ).hexdigest()

                                rec = ResourceMetricRecord(
                                    metric_record_id=metric_record_id,
                                    resource_id=res_id,
                                    subscription_id=self.config.subscription_id,
                                    metric_name=m_name,
                                    timestamp=ts_dt,
                                    average=float(avg) if avg is not None else None,
                                    maximum=float(max_val) if max_val is not None else None,
                                    minimum=float(min_val) if min_val is not None else None,
                                    unit=unit,
                                    source_api="Azure Monitor Metrics API",
                                    ingestion_timestamp=ingestion_dt,
                                )
                                all_records.append(rec)
                except Exception as ex:
                    logger.warning("Error querying metrics for %s: %s", res_id, ex)

        logger.info(
            "Extracted %d valid metric data points across %d resources.",
            len(all_records),
            len(candidates),
        )
        return all_records
