"""Configuration management for Microsoft Fabric Lakehouse Delta Reader.

Provides environment variable resolution, workspace/lakehouse validation,
and ABFSS storage endpoint mapping for OneLake Delta analytical storage.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("finops_udf.lakehouse.config")

DEFAULT_WORKSPACE_ID = "672a6995-4190-4000-befd-5cc6479c3f74"
DEFAULT_LAKEHOUSE_ID = "4bba3647-0112-4adc-8b18-f7a422461404"
DEFAULT_LAKEHOUSE_NAME = "finops_lakehouse"
DEFAULT_ONELAKE_DFS_ENDPOINT = "https://onelake.dfs.fabric.microsoft.com"
DEFAULT_SQL_ENDPOINT = "pstif7vh7kne3o72pus3obd3ie-svusuz4qieaebpx5ltdephb7oq.datawarehouse.fabric.microsoft.com"

# Relative path to lakehouse_config.json if available
CONFIG_FILE_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent
    / "lakehouse"
    / "lakehouse_config.json",
    Path(__file__).resolve().parent / "lakehouse_config.json",
]


@dataclass
class LakehouseReaderConfig:
    """Runtime parameters governing OneLake analytical Delta reading."""

    workspace_id: str = DEFAULT_WORKSPACE_ID
    lakehouse_id: str = DEFAULT_LAKEHOUSE_ID
    lakehouse_name: str = DEFAULT_LAKEHOUSE_NAME
    onelake_dfs_endpoint: str = DEFAULT_ONELAKE_DFS_ENDPOINT
    sql_endpoint_connection_string: str = DEFAULT_SQL_ENDPOINT

    # Analytics Routing: 'onelake' (Production) or 'local' (Development fallback)
    analytics_source: str = "onelake"

    # Query Performance & Caching
    read_timeout_sec: float = 30.0
    cache_ttl_sec: float = 60.0
    max_cache_entries: int = 128
    verify_ssl: bool = False  # Allows proxy traversal in enterprise environments

    # Service Principal overrides (if running as a dedicated SP in container)
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None

    @property
    def onelake_table_root_uri(self) -> str:
        """ABFSS root URI pointing to the Lakehouse Tables directory."""
        return (
            f"abfss://{self.workspace_id}@onelake.dfs.fabric.microsoft.com/"
            f"{self.lakehouse_id}/Tables"
        )

    def get_table_uri(self, table_name: str) -> str:
        """Resolve full ABFSS URI for an analytical Delta table."""
        return f"{self.onelake_table_root_uri}/{table_name}"

    def validate(self) -> None:
        """Validate presence of critical IDs."""
        if not self.workspace_id or not self.lakehouse_id:
            raise ValueError(
                "LakehouseReaderConfig requires valid workspace_id and lakehouse_id."
            )

    @classmethod
    def load(cls) -> "LakehouseReaderConfig":
        """Load configuration from environment variables and lakehouse_config.json."""
        file_data: dict[str, Any] = {}
        for candidate in CONFIG_FILE_CANDIDATES:
            if candidate.exists():
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        file_data = json.load(f)
                    break
                except Exception as exc:
                    logger.debug(
                        "Failed reading config candidate %s: %s", candidate, exc
                    )

        workspace_id = (
            os.getenv("FABRIC_WORKSPACE_ID")
            or file_data.get("workspaceId")
            or DEFAULT_WORKSPACE_ID
        )
        lakehouse_id = (
            os.getenv("FABRIC_LAKEHOUSE_ID")
            or file_data.get("lakehouseId")
            or DEFAULT_LAKEHOUSE_ID
        )
        lakehouse_name = (
            file_data.get("displayName")
            or os.getenv("FABRIC_LAKEHOUSE_NAME")
            or DEFAULT_LAKEHOUSE_NAME
        )
        analytics_source = os.getenv("FINOPS_ANALYTICS_SOURCE", "onelake").lower()

        cfg = cls(
            workspace_id=workspace_id,
            lakehouse_id=lakehouse_id,
            lakehouse_name=lakehouse_name,
            analytics_source=analytics_source,
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            client_id=os.getenv("AZURE_CLIENT_ID"),
            client_secret=os.getenv("AZURE_CLIENT_SECRET"),
        )
        cfg.validate()
        return cfg
