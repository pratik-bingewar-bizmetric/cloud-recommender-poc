"""Microsoft Fabric FinOps Sync Agent - Configuration Management.

Loads lakehouse identifiers, Azure subscription details, and runtime parameters
from lakehouse_config.json, with support for environment variable overrides.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_LAKEHOUSE_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "lakehouse" / "lakehouse_config.json"
)

DEFAULT_SUBSCRIPTION_ID = "9636348b-8445-4441-94d2-f6191f131721"
DEFAULT_TENANT_ID = "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"
DEFAULT_CONNECTION_ID = "conn_azure_sub1"
DEFAULT_WORKSPACE_ID = "672a6995-4190-4000-befd-5cc6479c3f74"
DEFAULT_LAKEHOUSE_ID = "4bba3647-0112-4adc-8b18-f7a422461404"
DEFAULT_ONELAKE_DFS_ENDPOINT = "https://onelake.dfs.fabric.microsoft.com"


@dataclass
class SyncAgentConfig:
    """Runtime configuration for Azure Data Extraction and OneLake Ingestion."""

    # Azure Environment
    subscription_id: str = DEFAULT_SUBSCRIPTION_ID
    tenant_id: str = DEFAULT_TENANT_ID
    connection_id: str = DEFAULT_CONNECTION_ID
    cloud_provider: str = "azure"

    # Microsoft Fabric & OneLake
    workspace_id: str = DEFAULT_WORKSPACE_ID
    lakehouse_id: str = DEFAULT_LAKEHOUSE_ID
    lakehouse_name: str = "finops_lakehouse"
    onelake_dfs_endpoint: str = DEFAULT_ONELAKE_DFS_ENDPOINT

    # Azure Cost Management Extraction Parameters
    cost_timeframe: str = "MonthToDate"  # Options: MonthToDate, TheLastBillingMonth, Custom
    cost_custom_start: str | None = None  # YYYY-MM-DD
    cost_custom_end: str | None = None  # YYYY-MM-DD
    fallback_to_historical_cost: bool = True  # If current month has 0 rows, check prior month

    # Azure Monitor Metrics Extraction Parameters
    metrics_timespan: str = "P7D"  # Past 7 days
    metrics_interval: str = "PT1H"  # 1 hour granularity
    metrics_max_resources: int = 50  # Cap number of resources queried per run

    # Network, Retries and Resilience
    max_retries: int = 4
    initial_backoff_sec: float = 3.0
    max_backoff_sec: float = 60.0
    request_timeout_sec: float = 45.0
    verify_ssl: bool = False  # Set to False to handle corporate proxy TLS interception

    @property
    def onelake_table_root_uri(self) -> str:
        """ABFSS URI pointing to the Lakehouse Tables directory."""
        return (
            f"abfss://{self.workspace_id}@onelake.dfs.fabric.microsoft.com/"
            f"{self.lakehouse_id}/Tables"
        )

    def get_table_uri(self, table_name: str) -> str:
        """Return the ABFSS URI for a specific Delta table."""
        return f"{self.onelake_table_root_uri}/{table_name}"

    @classmethod
    def load(cls, config_path: Path | None = None) -> "SyncAgentConfig":
        """Load configuration from lakehouse_config.json with env variable overrides."""
        cfg_path = config_path or Path(
            os.getenv("LAKEHOUSE_CONFIG_PATH", str(DEFAULT_LAKEHOUSE_CONFIG_PATH))
        )
        data: dict[str, Any] = {}

        if cfg_path.exists():
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        workspace_id = (
            os.getenv("FABRIC_WORKSPACE_ID") or data.get("workspaceId") or DEFAULT_WORKSPACE_ID
        )
        lakehouse_id = (
            os.getenv("FABRIC_LAKEHOUSE_ID") or data.get("lakehouseId") or DEFAULT_LAKEHOUSE_ID
        )
        lakehouse_name = data.get("displayName") or "finops_lakehouse"

        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID") or DEFAULT_SUBSCRIPTION_ID
        tenant_id = os.getenv("AZURE_TENANT_ID") or DEFAULT_TENANT_ID
        connection_id = os.getenv("AZURE_CONNECTION_ID") or DEFAULT_CONNECTION_ID

        return cls(
            subscription_id=subscription_id,
            tenant_id=tenant_id,
            connection_id=connection_id,
            workspace_id=workspace_id,
            lakehouse_id=lakehouse_id,
            lakehouse_name=lakehouse_name,
            cost_timeframe=os.getenv("AZURE_COST_TIMEFRAME", "MonthToDate"),
            cost_custom_start=os.getenv("AZURE_COST_START_DATE"),
            cost_custom_end=os.getenv("AZURE_COST_END_DATE"),
        )
