"""Microsoft Fabric FinOps Sync Agent - Azure Resource Graph Inventory Extractor.

Extracts real Azure cloud resource inventory using the Azure Resource Graph REST API.
Handles pagination ($skipToken), extracts resource metadata, tags, and power states,
and maps the items into ResourceInventoryRecord instances matching the Delta schema.
"""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from auth import AUDIENCE_ARM, AzureCliAuthManager
from config import SyncAgentConfig
from models import ResourceInventoryRecord

logger = logging.getLogger("azure_sync_agent.inventory")

ARG_ENDPOINT = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2021-03-01"


class AzureInventoryExtractor:
    """Extracts live resource inventory from Azure subscriptions using Resource Graph."""

    def __init__(self, auth_manager: AzureCliAuthManager, config: SyncAgentConfig) -> None:
        self.auth_manager = auth_manager
        self.config = config

    def _extract_power_state(self, properties: dict[str, Any] | None) -> str | None:
        """Derive resource power or provisioning state from Azure properties payload."""
        if not properties or not isinstance(properties, dict):
            return None

        # Virtual machine power state
        extended = properties.get("extended", {})
        if isinstance(extended, dict):
            instance_view = extended.get("instanceView", {})
            if isinstance(instance_view, dict):
                p_state = instance_view.get("powerState", {})
                if isinstance(p_state, dict) and p_state.get("code"):
                    return str(p_state["code"])

        # Service / DB status or state
        for key in ["status", "state", "userVisibleState", "provisioningState"]:
            val = properties.get(key)
            if val and isinstance(val, str):
                return val

        return None

    def _extract_sku_name(self, sku_obj: Any) -> str | None:
        """Extract SKU name string from sku object."""
        if not sku_obj:
            return None
        if isinstance(sku_obj, dict):
            return str(sku_obj.get("name") or sku_obj.get("tier") or "") or None
        if isinstance(sku_obj, str):
            return sku_obj
        return str(sku_obj)

    def extract_inventory(
        self, snapshot_timestamp: datetime | None = None
    ) -> list[ResourceInventoryRecord]:
        """Query Azure Resource Graph and return strongly-typed ResourceInventoryRecord items."""
        snapshot_dt = snapshot_timestamp or datetime.now(UTC)
        ingestion_dt = datetime.now(UTC)

        token = self.auth_manager.get_token(AUDIENCE_ARM)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        query = (
            "Resources "
            "| project id, name, type, location, resourceGroup, subscriptionId, sku, tags, properties"
        )

        all_rows: list[dict[str, Any]] = []
        skip_token: str | None = None
        page = 1

        logger.info(
            "Initiating Azure Resource Graph query for subscription '%s'...",
            self.config.subscription_id,
        )

        with httpx.Client(
            verify=self.config.verify_ssl, timeout=self.config.request_timeout_sec
        ) as client:
            while True:
                payload: dict[str, Any] = {
                    "subscriptions": [self.config.subscription_id],
                    "query": query,
                    "options": {
                        "$top": 500,
                    },
                }
                if skip_token:
                    payload["options"]["$skipToken"] = skip_token

                resp: httpx.Response | None = None
                for attempt in range(1, self.config.max_retries + 1):
                    try:
                        logger.debug("Executing ARG query page %d (attempt %d)...", page, attempt)
                        resp = client.post(ARG_ENDPOINT, headers=headers, json=payload)
                        if resp.status_code == 200:
                            break
                        if resp.status_code == 429:
                            retry_after = float(
                                resp.headers.get(
                                    "Retry-After", self.config.initial_backoff_sec * attempt
                                )
                            )
                            logger.warning(
                                "ARG rate limited (429). Retrying after %.1f seconds...",
                                retry_after,
                            )
                            time.sleep(retry_after)
                        else:
                            logger.warning(
                                "ARG returned status %d on attempt %d: %s",
                                resp.status_code,
                                attempt,
                                resp.text[:200],
                            )
                            time.sleep(self.config.initial_backoff_sec * attempt)
                    except Exception as ex:
                        logger.warning("ARG request error on attempt %d: %s", attempt, ex)
                        time.sleep(self.config.initial_backoff_sec * attempt)

                if resp is None or resp.status_code != 200:
                    err_msg = resp.text if resp else "No response received"
                    raise RuntimeError(f"Failed to query Azure Resource Graph: {err_msg}")

                data = resp.json()
                data_rows = data.get("data", [])
                if isinstance(data_rows, dict) and "rows" in data_rows:
                    # In some API versions, data is a dictionary with 'rows' and 'columns'
                    columns = [col["name"] for col in data_rows.get("columns", [])]
                    for row_values in data_rows.get("rows", []):
                        row_dict = dict(zip(columns, row_values, strict=False))
                        all_rows.append(row_dict)
                elif isinstance(data_rows, list):
                    all_rows.extend(data_rows)

                skip_token = data.get("$skipToken")
                if not skip_token:
                    break
                page += 1

        logger.info("Retrieved %d raw resource records from Azure Resource Graph.", len(all_rows))

        records: list[ResourceInventoryRecord] = []
        for row in all_rows:
            raw_id = row.get("id")
            if not raw_id:
                continue

            name = row.get("name") or raw_id.split("/")[-1]
            resource_type = row.get("type", "unknown")
            location = row.get("location") or "global"
            resource_group = row.get("resourceGroup")
            sub_id = row.get("subscriptionId") or self.config.subscription_id
            sku_name = self._extract_sku_name(row.get("sku"))
            power_state = self._extract_power_state(row.get("properties"))

            tags_dict = row.get("tags")
            tags_json = json.dumps(tags_dict) if tags_dict and isinstance(tags_dict, dict) else None

            rec = ResourceInventoryRecord(
                resource_id=raw_id,
                connection_id=self.config.connection_id,
                subscription_id=sub_id,
                tenant_id=self.config.tenant_id,
                provider="azure",
                name=name,
                resource_type=resource_type,
                resource_group=resource_group,
                location=location,
                sku_name=sku_name,
                power_state=power_state,
                tags=tags_json,
                monthly_retail_cost=None,
                source_api="Azure Resource Graph",
                snapshot_timestamp=snapshot_dt,
                ingestion_timestamp=ingestion_dt,
            )
            records.append(rec)

        return records
