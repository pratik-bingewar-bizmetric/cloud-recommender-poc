"""Background refresh of live Databricks metadata (REST only; never SQL, never compute).

Keeps the process-shared discovery / Unity Catalog / system-table-metadata caches fresh for
every connection that has been requested recently, so dashboard requests are served from
cache instead of blocking on a full discovery. A failed refresh keeps the last good cache and
records the error (the health endpoint then reports ``discovery_stale``).
"""

import asyncio
import time

import structlog

from cloud_recommender.services.databricks.workspace_service import DatabricksWorkspaceService

logger = structlog.get_logger(__name__)

_REFRESH_TIMEOUT_SECONDS = 180
_ACTIVE_WINDOW_SECONDS = 15 * 60


class MetadataRefresher:
    """Polls active connections: inventory every N seconds, slow metadata every M seconds."""

    def __init__(
        self,
        workspace_service: DatabricksWorkspaceService,
        inventory_interval: int,
        metadata_interval: int,
    ) -> None:
        self.workspace_service = workspace_service
        self.inventory_interval = inventory_interval
        self.metadata_interval = metadata_interval
        self._touched: dict[str, float] = {}
        self._last_inventory: dict[str, float] = {}
        self._last_metadata: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._task: asyncio.Task[None] | None = None

    # -- activation -----------------------------------------------------

    def touch(self, connection_id: str) -> None:
        """Mark a connection as in use so the loop keeps it fresh."""
        self._touched[connection_id] = time.monotonic()

    def active_connections(self) -> list[str]:
        cutoff = time.monotonic() - _ACTIVE_WINDOW_SECONDS
        return [cid for cid, ts in self._touched.items() if ts >= cutoff]

    # -- one refresh step (also used directly by tests) -----------------

    async def refresh_once(self, connection_id: str, force: bool = False) -> None:
        """Refresh a connection if due. Overlapping refreshes for one connection are skipped."""
        if connection_id in self._inflight:
            return
        now = time.monotonic()
        inventory_due = force or now - self._last_inventory.get(connection_id, -1e12) >= (
            self.inventory_interval
        )
        metadata_due = force or now - self._last_metadata.get(connection_id, -1e12) >= (
            self.metadata_interval
        )
        if not inventory_due and not metadata_due:
            return
        self._inflight.add(connection_id)
        try:
            ws = self.workspace_service
            if inventory_due:
                await asyncio.wait_for(
                    ws.get_or_discover_workspace(
                        connection_id, force_refresh=True, keep_metadata=True
                    ),
                    timeout=_REFRESH_TIMEOUT_SECONDS,
                )
                self._last_inventory[connection_id] = time.monotonic()
            if metadata_due:
                await asyncio.wait_for(
                    ws.get_unity_catalog_metadata(
                        connection_id, include_permissions=False, force_refresh=True
                    ),
                    timeout=_REFRESH_TIMEOUT_SECONDS,
                )
                await asyncio.wait_for(
                    ws.get_system_tables_metadata(connection_id, force_refresh=True),
                    timeout=_REFRESH_TIMEOUT_SECONDS,
                )
                self._last_metadata[connection_id] = time.monotonic()
        except Exception as exc:  # noqa: BLE001 - a failed refresh must never crash the loop
            logger.warning(
                "databricks_refresh_failed", connection_id=connection_id, error=type(exc).__name__
            )
        finally:
            self._inflight.discard(connection_id)

    # -- lifecycle ------------------------------------------------------

    async def _run(self) -> None:
        tick = max(1, min(self.inventory_interval, 15))
        while True:
            for cid in self.active_connections():
                await self.refresh_once(cid)
            await asyncio.sleep(tick)

    def start(self) -> None:
        if self._task is None and self.inventory_interval > 0:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


_refresher: MetadataRefresher | None = None


def get_refresher(
    workspace_service: DatabricksWorkspaceService | None = None,
) -> MetadataRefresher:
    """Process-wide refresher bound to the (cache-sharing) workspace service."""
    global _refresher
    if _refresher is None:
        service = workspace_service or DatabricksWorkspaceService()
        _refresher = MetadataRefresher(
            service,
            service.settings.databricks_inventory_refresh_seconds,
            service.settings.databricks_metadata_refresh_seconds,
        )
    return _refresher
