"""Microsoft Fabric Lakehouse Delta Reader Package for User Data Functions.

Provides persistent analytical data access from OneLake Delta tables while
preserving operational connection state in SQLite.
"""

from .auth import LakehouseAuthError, LakehousePermissionError, OneLakeAuthManager
from .config import LakehouseReaderConfig
from .delta_reader import OneLakeDeltaReader
from .diagnostics import LakehouseDiagnostics
from .health import LakehouseHealthChecker
from .models import (
    AnalyticalResponseEnvelope,
    CurrencyCostTotal,
    DailyCostTrendPoint,
    LakehouseCostAnalytics,
    LakehouseHealthStatus,
    LakehouseInventorySummary,
    LakehouseMetricsSummary,
    LakehouseResourceItem,
    LakehouseSyncOverview,
    LakehouseTokenSummary,
    MetricSeriesPoint,
    ResourceMetricSeries,
    ServiceCostItem,
    SyncHistoryEntry,
    TableHealthStatus,
)
from .repository import AnalyticalRepository

__all__ = [
    "AnalyticalRepository",
    "AnalyticalResponseEnvelope",
    "CurrencyCostTotal",
    "DailyCostTrendPoint",
    "LakehouseAuthError",
    "LakehouseCostAnalytics",
    "LakehouseDiagnostics",
    "LakehouseHealthChecker",
    "LakehouseHealthStatus",
    "LakehouseInventorySummary",
    "LakehouseMetricsSummary",
    "LakehousePermissionError",
    "LakehouseReaderConfig",
    "LakehouseResourceItem",
    "LakehouseSyncOverview",
    "LakehouseTokenSummary",
    "MetricSeriesPoint",
    "OneLakeAuthManager",
    "OneLakeDeltaReader",
    "ResourceMetricSeries",
    "ServiceCostItem",
    "SyncHistoryEntry",
    "TableHealthStatus",
]
