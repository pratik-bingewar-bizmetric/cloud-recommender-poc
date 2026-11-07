"""Health check and connectivity inspection for Microsoft Fabric Lakehouse.

Evaluates authentication readiness, OneLake DFS connectivity, and Delta table states,
reporting honest statuses (READY, DEGRADED, or UNAVAILABLE).
"""

import logging
from datetime import UTC, datetime

from .auth import LakehouseAuthError, OneLakeAuthManager
from .config import LakehouseReaderConfig
from .delta_reader import OneLakeDeltaReader
from .models import LakehouseHealthStatus, TableHealthStatus

logger = logging.getLogger("finops_udf.lakehouse.health")

ANALYTICAL_TABLES = [
    "resource_inventory",
    "cost_details",
    "resource_metrics",
    "token_telemetry",
    "sync_history",
]


class LakehouseHealthChecker:
    """Probes Lakehouse storage and returns structured readiness diagnostic."""

    def __init__(
        self,
        reader: OneLakeDeltaReader | None = None,
        auth_manager: OneLakeAuthManager | None = None,
        config: LakehouseReaderConfig | None = None,
    ) -> None:
        self.config = config or LakehouseReaderConfig.load()
        self.auth_manager = auth_manager or OneLakeAuthManager(self.config)
        self.reader = reader or OneLakeDeltaReader(self.auth_manager, self.config)

    def check_health(self) -> LakehouseHealthStatus:
        """Execute non-destructive health probe across all 5 analytical Delta tables."""
        now_iso = datetime.now(UTC).isoformat()
        table_statuses: dict[str, TableHealthStatus] = {}

        # 1. Probe Authentication
        try:
            _, auth_method = self.auth_manager.get_token()
            auth_status = "AUTHENTICATED"
        except LakehouseAuthError as auth_err:
            return LakehouseHealthStatus(
                overall_status="UNAVAILABLE",
                auth_status="UNAUTHENTICATED",
                auth_method="none",
                workspace_id=self.config.workspace_id,
                lakehouse_id=self.config.lakehouse_id,
                diagnostic_details=f"OneLake token acquisition failed: {auth_err}",
                timestamp=now_iso,
            )
        except Exception as exc:
            return LakehouseHealthStatus(
                overall_status="UNAVAILABLE",
                auth_status="ERROR",
                auth_method="unknown",
                workspace_id=self.config.workspace_id,
                lakehouse_id=self.config.lakehouse_id,
                diagnostic_details=f"Unexpected authentication failure: {exc}",
                timestamp=now_iso,
            )

        # 2. Probe Individual Delta Tables
        accessible_tables = 0
        for table_name in ANALYTICAL_TABLES:
            meta = self.reader.get_table_metadata(table_name)
            if meta.get("accessible"):
                accessible_tables += 1
                table_statuses[table_name] = TableHealthStatus(
                    name=table_name,
                    accessible=True,
                    version=meta.get("version"),
                    file_count=meta.get("file_count"),
                )
            else:
                table_statuses[table_name] = TableHealthStatus(
                    name=table_name,
                    accessible=False,
                    error=meta.get("error"),
                )

        # 3. Determine Overall System Status
        if accessible_tables == len(ANALYTICAL_TABLES):
            overall_status = "READY"
            diagnostic_msg = f"All {len(ANALYTICAL_TABLES)} OneLake Delta tables verified and accessible."
        elif accessible_tables > 0:
            overall_status = "DEGRADED"
            diagnostic_msg = f"{accessible_tables}/{len(ANALYTICAL_TABLES)} tables accessible. Some tables unpopulated."
        else:
            overall_status = "UNAVAILABLE"
            diagnostic_msg = "No analytical Delta tables accessible on OneLake."

        return LakehouseHealthStatus(
            overall_status=overall_status,
            auth_status=auth_status,
            auth_method=auth_method,
            workspace_id=self.config.workspace_id,
            lakehouse_id=self.config.lakehouse_id,
            tables=table_statuses,
            diagnostic_details=diagnostic_msg,
            timestamp=now_iso,
        )
