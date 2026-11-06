"""Unit tests for Azure Cost Management Extractor."""

import hashlib
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from auth import AzureCliAuthManager
from config import SyncAgentConfig
from cost_client import AzureCostExtractor


def test_build_query_payload():
    extractor = AzureCostExtractor(MagicMock(), SyncAgentConfig())
    payload_mtd = extractor._build_query_payload("MonthToDate")
    assert payload_mtd["timeframe"] == "MonthToDate"
    assert payload_mtd["dataset"]["granularity"] == "Daily"

    payload_custom = extractor._build_query_payload("Custom", "2026-10-01", "2026-10-31")
    assert payload_custom["timeframe"] == "Custom"
    assert payload_custom["timePeriod"]["from"] == "2026-10-01"


def test_parse_usage_date():
    extractor = AzureCostExtractor(MagicMock(), SyncAgentConfig())
    # Integer format YYYYMMDD
    d1 = extractor._parse_usage_date(20261019)
    assert d1 == date(2026, 10, 19)

    # String format ISO
    d2 = extractor._parse_usage_date("2026-10-19T00:00:00Z")
    assert d2 == date(2026, 10, 19)


def test_rate_limiting_and_cost_extraction():
    mock_auth = MagicMock(spec=AzureCliAuthManager)
    mock_auth.get_token.return_value = "mock-token"

    config = SyncAgentConfig(subscription_id="sub-abc", fallback_to_historical_cost=False)
    extractor = AzureCostExtractor(mock_auth, config)

    # Mock response 1: 429 rate limited with retry-after header
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after": "0.1"}

    # Mock response 2: 200 OK with data rows
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "properties": {
            "columns": [
                {"name": "Cost", "type": "Number"},
                {"name": "UsageDate", "type": "Number"},
                {"name": "ResourceId", "type": "String"},
                {"name": "ServiceName", "type": "String"},
                {"name": "MeterCategory", "type": "String"},
                {"name": "Meter", "type": "String"},
                {"name": "ChargeType", "type": "String"},
                {"name": "Currency", "type": "String"},
            ],
            "rows": [
                [
                    15.2500,
                    20261025,
                    "/subscriptions/sub-abc/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/flexibleServers/db1",
                    "Azure Database for PostgreSQL",
                    "Azure Database for PostgreSQL",
                    "Compute",
                    "Usage",
                    "USD",
                ]
            ],
        }
    }

    with (
        patch("httpx.Client.post", side_effect=[resp_429, resp_200]),
        patch("time.sleep", return_value=None),
    ):
        records = extractor.extract_costs()
        assert len(records) == 1
        r = records[0]
        assert r.service_name == "Azure Database for PostgreSQL"
        assert r.cost_in_billing_currency == Decimal("15.2500")
        assert r.billing_year_month == "2026-10"
        assert r.usage_date == date(2026, 10, 25)

        # Verify deterministic hash
        expected_raw = "sub-abc:2026-10-25:/subscriptions/sub-abc/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/flexibleServers/db1:Azure Database for PostgreSQL:Azure Database for PostgreSQL:Compute:Usage"
        expected_hash = hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()
        assert r.cost_record_id == expected_hash
