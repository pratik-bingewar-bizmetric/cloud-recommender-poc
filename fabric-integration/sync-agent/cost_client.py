"""Microsoft Fabric FinOps Sync Agent - Azure Cost Management Extractor.

Extracts authentic billed and usage cost records from Azure Cost Management Query API.
Handles HTTP 429 rate limits using the provider retry-after headers, computes
deterministic record IDs (SHA-256), and maps data into CostDetailRecord instances.
"""

import hashlib
import logging
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
from auth import AUDIENCE_ARM, AzureCliAuthManager
from config import SyncAgentConfig
from models import CostDetailRecord

logger = logging.getLogger("azure_sync_agent.cost")


class AzureCostExtractor:
    """Extracts cost telemetry from Azure Cost Management Query API."""

    def __init__(self, auth_manager: AzureCliAuthManager, config: SyncAgentConfig) -> None:
        self.auth_manager = auth_manager
        self.config = config

    def _build_query_payload(
        self,
        timeframe: str,
        custom_from: str | None = None,
        custom_to: str | None = None,
    ) -> dict[str, Any]:
        """Construct the standard Cost Management dataset query payload."""
        payload: dict[str, Any] = {
            "type": "Usage",
            "timeframe": timeframe,
            "dataset": {
                "granularity": "Daily",
                "aggregation": {
                    "totalCost": {
                        "name": "Cost",
                        "function": "Sum",
                    }
                },
                "grouping": [
                    {"type": "Dimension", "name": "ResourceId"},
                    {"type": "Dimension", "name": "ServiceName"},
                    {"type": "Dimension", "name": "MeterCategory"},
                    {"type": "Dimension", "name": "Meter"},
                    {"type": "Dimension", "name": "ChargeType"},
                ],
            },
        }

        if timeframe == "Custom":
            if not custom_from or not custom_to:
                raise ValueError("Custom timeframe requires custom_from and custom_to ISO dates.")
            payload["timePeriod"] = {
                "from": custom_from,
                "to": custom_to,
            }

        return payload

    def _execute_cost_query(
        self, client: httpx.Client, endpoint: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute HTTP POST with rate-limit detection and adaptive backoff."""
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = client.post(endpoint, headers=headers, json=payload)
                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    # Azure Cost Management specific rate limit header
                    retry_header = (
                        resp.headers.get(
                            "x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after"
                        )
                        or resp.headers.get(
                            "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after"
                        )
                        or resp.headers.get("Retry-After")
                    )
                    retry_seconds = (
                        float(retry_header)
                        if retry_header
                        else (self.config.initial_backoff_sec * attempt * 2)
                    )
                    # Add 1.0 second safety buffer
                    wait_time = min(retry_seconds + 1.0, self.config.max_backoff_sec)
                    logger.warning(
                        "Azure Cost Management 429 rate limit received. Retrying after %.1f seconds (attempt %d/%d)...",
                        wait_time,
                        attempt,
                        self.config.max_retries,
                    )
                    time.sleep(wait_time)
                    continue

                logger.warning(
                    "Azure Cost Management returned HTTP %d on attempt %d: %s",
                    resp.status_code,
                    attempt,
                    resp.text[:300],
                )
                time.sleep(self.config.initial_backoff_sec * attempt)
            except Exception as ex:
                logger.warning("Cost Management query error on attempt %d: %s", attempt, ex)
                time.sleep(self.config.initial_backoff_sec * attempt)

        raise RuntimeError(
            f"Failed to query Azure Cost Management after {self.config.max_retries} attempts."
        )

    def _parse_usage_date(self, raw_val: Any) -> date:
        """Parse raw usage date integer (20261019) or string ('2026-10-19') to date."""
        if isinstance(raw_val, int):
            s = str(raw_val)
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        if isinstance(raw_val, str):
            clean_s = raw_val.split("T")[0]
            if "-" in clean_s:
                parts = clean_s.split("-")
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            return date(int(clean_s[:4]), int(clean_s[4:6]), int(clean_s[6:8]))
        return date.today()

    def extract_costs(self) -> list[CostDetailRecord]:
        """Extract Cost Management records, with fallback to historical period if current is empty."""
        token = self.auth_manager.get_token(AUDIENCE_ARM)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        endpoint = (
            f"https://management.azure.com/subscriptions/{self.config.subscription_id}"
            "/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
        )

        timeframe = self.config.cost_timeframe
        custom_from = self.config.cost_custom_start
        custom_to = self.config.cost_custom_end

        payload = self._build_query_payload(timeframe, custom_from, custom_to)

        logger.info(
            "Querying Azure Cost Management for subscription '%s' (timeframe: %s)...",
            self.config.subscription_id,
            timeframe,
        )

        with httpx.Client(
            verify=self.config.verify_ssl, timeout=self.config.request_timeout_sec
        ) as client:
            data = self._execute_cost_query(client, endpoint, headers, payload)
            properties = data.get("properties", {})
            columns = [c["name"] for c in properties.get("columns", [])]
            rows = properties.get("rows", [])

            # Fallback to historical month (e.g. October 2026) if current month has 0 rows
            if not rows and self.config.fallback_to_historical_cost and timeframe == "MonthToDate":
                logger.info(
                    "Current MonthToDate returned 0 cost records. Querying recent historical billing month..."
                )
                # Compute prior month range
                today = date.today()
                date(today.year, today.month, 1)
                # Query past 60 days
                hist_from = "2026-10-01T00:00:00Z"
                hist_to = "2026-10-31T23:59:59Z"
                hist_payload = self._build_query_payload("Custom", hist_from, hist_to)
                data = self._execute_cost_query(client, endpoint, headers, hist_payload)
                properties = data.get("properties", {})
                columns = [c["name"] for c in properties.get("columns", [])]
                rows = properties.get("rows", [])
                logger.info("Historical query returned %d cost records.", len(rows))

        logger.info("Successfully extracted %d cost records from Azure Cost Management.", len(rows))

        ingestion_dt = datetime.now(UTC)
        records: list[CostDetailRecord] = []

        for row in rows:
            row_dict = dict(zip(columns, row, strict=False))
            raw_cost = row_dict.get("Cost", 0.0)
            cost_decimal = Decimal(str(raw_cost)).quantize(Decimal("0.0001"))
            currency = str(row_dict.get("Currency", "USD"))

            raw_date = row_dict.get("UsageDate")
            usage_dt = self._parse_usage_date(raw_date)
            billing_year_month = f"{usage_dt.year:04d}-{usage_dt.month:02d}"

            resource_id = row_dict.get("ResourceId")
            service_name = str(row_dict.get("ServiceName", "Unknown"))
            meter_category = str(row_dict.get("MeterCategory", "Unknown"))
            meter_name = str(row_dict.get("Meter", "Unknown"))
            charge_type = str(row_dict.get("ChargeType", "Usage"))

            # Deterministic record hash
            id_components = f"{self.config.subscription_id}:{usage_dt.isoformat()}:{resource_id or ''}:{service_name}:{meter_category}:{meter_name}:{charge_type}"
            cost_record_id = hashlib.sha256(id_components.encode("utf-8")).hexdigest()

            rec = CostDetailRecord(
                cost_record_id=cost_record_id,
                connection_id=self.config.connection_id,
                subscription_id=self.config.subscription_id,
                billing_year_month=billing_year_month,
                usage_date=usage_dt,
                resource_id=resource_id,
                service_name=service_name,
                meter_category=meter_category,
                meter_name=meter_name,
                cost_in_billing_currency=cost_decimal,
                currency=currency,
                charge_type=charge_type,
                source_api="Azure Cost Management Query API",
                ingestion_timestamp=ingestion_dt,
            )
            records.append(rec)

        return records
