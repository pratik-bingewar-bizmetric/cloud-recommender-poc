"""Unit tests for FinOps Sync Agent Configuration."""

import json

from config import DEFAULT_SUBSCRIPTION_ID, DEFAULT_WORKSPACE_ID, SyncAgentConfig


def test_default_config():
    cfg = SyncAgentConfig()
    assert cfg.subscription_id == DEFAULT_SUBSCRIPTION_ID
    assert cfg.workspace_id == DEFAULT_WORKSPACE_ID
    assert "abfss://" in cfg.onelake_table_root_uri
    assert cfg.get_table_uri("cost_details").endswith("/Tables/cost_details")


def test_load_from_json(tmp_path):
    config_file = tmp_path / "lakehouse_config.json"
    data = {
        "workspaceId": "ws-12345",
        "lakehouseId": "lh-67890",
        "displayName": "custom_lakehouse",
    }
    config_file.write_text(json.dumps(data), encoding="utf-8")

    cfg = SyncAgentConfig.load(config_file)
    assert cfg.workspace_id == "ws-12345"
    assert cfg.lakehouse_id == "lh-67890"
    assert cfg.lakehouse_name == "custom_lakehouse"


def test_env_var_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "sub-override-999")
    monkeypatch.setenv("FABRIC_WORKSPACE_ID", "ws-override-888")
    monkeypatch.setenv("AZURE_COST_TIMEFRAME", "TheLastBillingMonth")

    non_existent = tmp_path / "absent.json"
    cfg = SyncAgentConfig.load(non_existent)
    assert cfg.subscription_id == "sub-override-999"
    assert cfg.workspace_id == "ws-override-888"
    assert cfg.cost_timeframe == "TheLastBillingMonth"
