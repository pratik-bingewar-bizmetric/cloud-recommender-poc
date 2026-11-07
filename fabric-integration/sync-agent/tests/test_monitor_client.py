"""Unit tests for Azure Monitor Metrics Extractor."""

import hashlib
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from auth import AzureCliAuthManager
from config import SyncAgentConfig
from monitor_client import AzureMonitorMetricsExtractor


def test_is_metric_eligible():
    extractor = AzureMonitorMetricsExtractor(MagicMock(), SyncAgentConfig())
    assert extractor._is_metric_eligible("Microsoft.Compute/virtualMachines") is True
    assert extractor._is_metric_eligible("Microsoft.DBforPostgreSQL/flexibleServers") is True
    assert extractor._is_metric_eligible("Microsoft.Network/networkSecurityGroups") is False


def test_extract_metrics_for_resources():
    mock_auth = MagicMock(spec=AzureCliAuthManager)
    mock_auth.get_token.return_value = "mock-token"

    config = SyncAgentConfig(subscription_id="sub-abc")
    extractor = AzureMonitorMetricsExtractor(mock_auth, config)

    res_id = "/subscriptions/sub-abc/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/flexibleServers/db1"
    resources = [{"id": res_id, "type": "Microsoft.DBforPostgreSQL/flexibleServers"}]

    # 1. Mock metric definitions
    resp_defs = MagicMock()
    resp_defs.status_code = 200
    resp_defs.json.return_value = {
        "value": [
            {"name": {"value": "cpu_percent"}},
            {"name": {"value": "memory_percent"}},
        ]
    }

    # 2. Mock metrics time-series response
    resp_metrics = MagicMock()
    resp_metrics.status_code = 200
    resp_metrics.json.return_value = {
        "value": [
            {
                "name": {"value": "cpu_percent"},
                "unit": "Percent",
                "timeseries": [
                    {
                        "data": [
                            {
                                "timeStamp": "2026-11-01T10:00:00Z",
                                "average": 4.5,
                                "maximum": 12.0,
                                "minimum": 1.0,
                            },
                            {
                                "timeStamp": "2026-11-01T11:00:00Z",
                                "average": None,
                                "maximum": None,
                                "minimum": None,  # Should be skipped
                            },
                        ]
                    }
                ],
            }
        ]
    }

    with patch("httpx.Client.get", side_effect=[resp_defs, resp_metrics]):
        records = extractor.extract_metrics_for_resources(resources)
        assert len(records) == 1
        r = records[0]
        assert r.resource_id == res_id
        assert r.metric_name == "cpu_percent"
        assert r.average == 4.5
        assert r.maximum == 12.0
        assert r.unit == "Percent"
        assert r.timestamp == datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC)

        # Verify deterministic hash
        expected_raw = f"{res_id}:cpu_percent:2026-11-01T10:00:00+00:00"
        expected_hash = hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()
        assert r.metric_record_id == expected_hash
