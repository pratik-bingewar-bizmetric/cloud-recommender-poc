"""FinOps Analytics Service for Azure Databricks.

Aggregates live workspace discovery assets, System Tables metadata and ingested billing
rows for all 15 Command Center modules. Every value is LIVE, CALCULATED, ESTIMATED or an
explicit UNAVAILABLE / BLOCKED state; no mock or modelled values are produced.
"""

import csv
import functools
import inspect
import io
import statistics
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from cloud_recommender.schemas.billing_ingestion import BillingUsageRecord
from cloud_recommender.schemas.databricks import DiscoveredResourceItem
from cloud_recommender.schemas.finops import (
    AiEconomicsResponse,
    AllocationRuleItem,
    AnomalyDetectionResponse,
    AnomalyItem,
    AuditEventItem,
    BudgetControlItem,
    CanonicalKpiResponse,
    ChargebackStatementItem,
    ClusterInventoryItem,
    ComputeWarehousesResponse,
    ConnectedSourceItem,
    CostAllocationResponse,
    CostDriverItem,
    CostExplorerItem,
    CostExplorerResponse,
    DataStorageResponse,
    DecisionItem,
    ExecutiveOverviewResponse,
    FinOpsAiAnalysis,
    FinOpsAiOpportunity,
    ForecastBudgetsResponse,
    GovernancePoliciesResponse,
    JobEfficiencyItem,
    KpiMetric,
    KpiStatus,
    ModelServingEndpointItem,
    NetworkCloudResponse,
    OptimizationAdvisorResponse,
    PipelineHealthMetric,
    PolicyCatalogueItem,
    QueryHistoryRecordItem,
    QueryHistoryResponse,
    RateCardItem,
    ReportPackItem,
    ReportsAuditResponse,
    ScenarioSimulationRequest,
    ScenarioSimulationResponse,
    SectionProvenance,
    SettingsIntegrationsResponse,
    ShowbackChargebackResponse,
    StorageInventoryItem,
    SystemTableProbeItem,
    SystemTablesExplorerResponse,
    TrainingEvaluationItem,
    WarehouseInventoryItem,
    WorkloadEconomicsResponse,
    WorkloadUnitEconomicsItem,
)
from cloud_recommender.services.databricks.billing_sql import (
    ATTRIBUTION_RULES,
    CostBasis,
    MatchStatus,
    matches_resource,
)
from cloud_recommender.services.databricks.workspace_service import DatabricksWorkspaceService


def _unknown_scope_guard[R: BaseModel](fn: Callable[..., R]) -> Callable[..., R]:
    """Force every KPI to a typed NO_DATA metric when the requested resource scope is unknown."""

    @functools.wraps(fn)
    def wrapper(self: "FinOpsAnalyticsService", *args: Any, **kwargs: Any) -> R:
        resp = fn(self, *args, **kwargs)
        bound = inspect.signature(fn).bind(self, *args, **kwargs)
        rid = bound.arguments.get("resource_id")
        rtype = bound.arguments.get("resource_type")
        _, unknown = self._resolve_resource_filter(rid, rtype)
        kpis = getattr(resp, "kpis", None)
        if unknown and isinstance(kpis, dict):
            for key, metric in list(kpis.items()):
                kpis[key] = self._build_empty_kpi(
                    key,
                    metric.unit,
                    metric.currency,
                    metric.source,
                    workspace_id=metric.workspace_id,
                    resource_id=rid,
                    resource_type=rtype,
                )
        return resp

    return wrapper


@dataclass(frozen=True)
class _CurrencyState:
    """Currency of the priced billing rows in the scope most recently read.

    ``code`` is set only when exactly one currency is present. ``mixed`` means several are
    present: no monetary aggregate may then be shown (and nothing is ever converted).
    """

    code: str | None = None
    mixed: bool = False
    codes: tuple[str, ...] = ()


_SCOPE_CURRENCY: ContextVar[_CurrencyState] = ContextVar(
    "finops_scope_currency",
    default=_CurrencyState(),  # noqa: B039 - frozen dataclass, immutable
)

_MIXED_CURRENCY_NOTE = (
    "Ambiguous: priced billing rows use more than one currency ({codes}). "
    "Amounts are never merged or converted, so no monetary total is shown."
)


def format_money(value: float, currency: str, decimals: int = 2) -> str:
    """Render an amount in its own currency; only USD uses a symbol, others carry their code."""
    if currency.upper() == "USD":
        return f"${value:,.{decimals}f}"
    return f"{value:,.{decimals}f} {currency.upper()}"


# Display label of each billing attribution type (keeps analytics aligned with billing_sql).
_ATTRIBUTION_LABELS: dict[str, str] = {
    "SQL_WAREHOUSE": "warehouse",
    "SERVING_ENDPOINT": "serving",
    "APP": "app",
    "JOB": "job",
    "PIPELINE": "pipeline",
    "CLUSTER": "cluster",
    "POOL": "pool",
    "NOTEBOOK": "notebook",
    "SERVERLESS": "serverless",
}


# Derived from billing_sql.ATTRIBUTION_RULES so analytics and ingestion can never drift:
# same keys, same priority order (``app_name`` is not an ingested key).
_RESOURCE_KEYS: tuple[tuple[str, str], ...] = tuple(
    (key, _ATTRIBUTION_LABELS[rtype]) for key, rtype in ATTRIBUTION_RULES
)
_FILTER_KEYS: dict[str, tuple[str, ...]] = {
    label: tuple(k for k, lbl in _RESOURCE_KEYS if lbl == label)
    for label in dict.fromkeys(lbl for _, lbl in _RESOURCE_KEYS)
}


class FinOpsAnalyticsService:
    """Canonical engine computing FinOps KPIs and module datasets for Azure Databricks."""

    def __init__(
        self,
        workspace_service: DatabricksWorkspaceService | None = None,
        billing_service: Any = None,
    ) -> None:
        self.workspace_service = workspace_service or DatabricksWorkspaceService()
        self._billing_service: Any = billing_service
        # In-memory overrides and audit events recorded by this process (no seeded history)
        self._action_overrides: dict[str, dict[str, Any]] = {}
        self._anomaly_overrides: dict[str, str] = {}
        self._audit_events: list[AuditEventItem] = []

    def _get_authorized_workspaces(self) -> set[str]:
        """Authorized scope ids come only from the live workspace registry (plus ``all``)."""
        allowed = {"all"}
        for conn in self.workspace_service.list_connections():
            allowed.add(conn.workspace_id)
            allowed.add(conn.connection_id)
        return allowed

    def validate_scope(self, workspace_id: Any = None) -> list[str]:
        """Enforce server-side workspace authorization. Rejects unconfigured or mismatched scopes.

        Supports single workspace ID, comma-separated workspace IDs, or list of workspace IDs.
        Returns the parsed list of authorized workspace IDs.
        """
        if workspace_id is None:
            return ["642006393507276"]
        if isinstance(workspace_id, str):
            wid_str = workspace_id.strip()
            if not wid_str:
                return ["642006393507276"]
            items = [w.strip() for w in wid_str.split(",") if w.strip()]
        elif isinstance(workspace_id, (list, tuple, set)):
            items = [str(w).strip() for w in workspace_id if str(w).strip()]
        else:
            return ["642006393507276"]

        if not items:
            return ["642006393507276"]

        allowed = self._get_authorized_workspaces()
        for wid in items:
            if wid not in allowed:
                raise ValueError(
                    f"Scope validation failed: Workspace '{wid}' is not authorized or does not match target environment."
                )
        return items

    def _get_workspace_assets(
        self, connection_id: str = "databricks-azure-dev"
    ) -> dict[str, list[DiscoveredResourceItem]]:
        """Fetch discovered workspace inventory grouped by category."""
        discovery = self.workspace_service._discovery_cache.get(connection_id)
        if not discovery or not discovery.resources:
            return {}
        grouped: dict[str, list[DiscoveredResourceItem]] = {}
        for r in discovery.resources:
            rt = r.resource_type.lower()
            if rt not in grouped:
                grouped[rt] = []
            grouped[rt].append(r)
        return grouped

    def _resolve_resource_filter(
        self, resource_id: Any, resource_type: Any
    ) -> tuple[str | None, bool]:
        """Resolve resource scope filter strictly without partial substring matching.

        Enforces:
        1. Exact identifier matching against discovered inventory or verified production registry.
        2. Exact resource type validation when resource_type is provided.
        3. Zero substring, fuzzy, or heuristic matching.
        4. Immediate return of (None, True) [NO_DATA] for any unknown, fake, or mismatched identifier.

        Returns:
            (resolved_category, is_unknown)
            where resolved_category is one of: "warehouse", "cluster", "serving", "app", None
            and is_unknown is True if resource_id/resource_type was specified but invalid/unmatched.
        """
        if not isinstance(resource_id, str):
            resource_id = None
        if not isinstance(resource_type, str):
            resource_type = None

        rid = (resource_id or "").strip()
        rt = (resource_type or "").lower().strip()

        # Both empty -> full workspace scope (valid)
        if not rid and not rt:
            return None, False

        # Map requested resource_type to canonical category
        expected_cat = None
        if rt:
            if rt in ("warehouse", "warehouses", "sql_warehouse", "sql_warehouses"):
                expected_cat = "warehouse"
            elif rt in ("cluster", "clusters", "compute"):
                expected_cat = "cluster"
            elif rt in ("model_serving", "serving_endpoint", "serving_endpoints", "serving"):
                expected_cat = "serving"
            elif rt in ("app", "apps", "databricks_app"):
                expected_cat = "app"
            else:
                # Unsupported resource type (e.g. virtual_machine, quantum, sql_db) -> invalid
                return None, True

        # Helper to look up an exact identifier's actual category
        def find_exact_asset_category(identifier: str) -> str | None:
            # 1. Live discovery cache (any connection): exact provider id, or provider name for
            #    serving endpoints and apps.
            category_of = {
                "warehouse": "warehouse",
                "warehouses": "warehouse",
                "sql_warehouse": "warehouse",
                "cluster": "cluster",
                "clusters": "cluster",
                "compute": "cluster",
                "model_serving": "serving",
                "serving_endpoint": "serving",
                "serving": "serving",
                "app": "app",
                "apps": "app",
            }
            for discovery in self.workspace_service._discovery_cache.values():
                for item in discovery.resources or []:
                    cat = category_of.get(item.resource_type.lower())
                    if cat and (
                        item.id == identifier
                        or (item.name == identifier and cat in ("serving", "app"))
                    ):
                        return cat

            # 2. Ids attributed by ingested billing rows are real source data too.
            billing = self._billing_service
            if billing is not None:
                for rec in billing._usage_store.values():
                    for key, label in _RESOURCE_KEYS:
                        if label in ("warehouse", "cluster", "serving", "app") and (
                            str(rec.usage_metadata.get(key) or "") == identifier
                        ):
                            return label

            return None

        # Case A: resource_id provided
        if rid:
            actual_cat = find_exact_asset_category(rid)
            if not actual_cat:
                # Not a known asset
                return None, True

            # If expected_cat is specified, it MUST match the actual asset category!
            if expected_cat and expected_cat != actual_cat:
                # Mismatch! (e.g. cluster ID with resource_type="warehouse")
                return None, True

            return actual_cat, False

        # Case B: Only resource_type provided (e.g. filter by category across workspace)
        if expected_cat:
            return expected_cat, False

        return None, True

    def _build_empty_kpi(
        self,
        metric_id: str,
        unit: str,
        currency: str | None = None,
        source: str = "Azure Databricks Telemetry",
        formula: str | None = None,
        workspace_id: str = "642006393507276",
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> KpiMetric:
        """Create a typed NO_DATA KPI metric for unknown or unpopulated resource scopes."""
        return KpiMetric(
            value=None,
            formatted_value="-",
            reason="The query succeeded but returned no records for this resource scope.",
            unit=unit,
            currency=currency,
            metric_id=metric_id,
            status=KpiStatus.NO_DATA,
            data_freshness="Not applicable",
            source=source,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
            data_source="Azure Databricks REST API",
            last_refreshed=datetime.now(UTC).isoformat(),
            aggregation_method="NONE",
            formula=formula,
            record_count=0,
            limitations="No telemetry data found for the specified resource scope.",
            caveats="Resource not present in workspace discovery inventory.",
        )

    def update_anomaly_status(
        self, anomaly_id: str, new_status: str, actor: str = "finops.operator"
    ) -> dict[str, Any]:
        """Update lifecycle state of an anomaly with audit tracking."""
        valid_states = {"New", "Investigating", "Acknowledged", "Resolved", "False positive"}
        if new_status not in valid_states:
            raise ValueError(
                f"Invalid anomaly status '{new_status}'. Must be one of: {sorted(valid_states)}"
            )
        self._anomaly_overrides[anomaly_id] = new_status
        self._audit_events.insert(
            0,
            AuditEventItem(
                timestamp=datetime.now(UTC).strftime("%b %d %H:%M"),
                actor=actor,
                event=f"Anomaly {anomaly_id} status changed to {new_status}",
                resource=anomaly_id,
                before="Previous",
                after=new_status,
                approval_ref="ANOM-AUDIT",
            ),
        )
        return {
            "anomaly_id": anomaly_id,
            "status": new_status,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def record_decision_action(
        self, decision_id: str, action: str, notes: str | None = None
    ) -> DecisionItem:
        """Update decision status and record audit entry."""
        self._action_overrides[decision_id] = {"status": action, "notes": notes}
        decisions = {d.id: d for d in self._get_decisions()}
        updated = decisions[decision_id]

        now_str = datetime.now(UTC).strftime("%b %d %H:%M")
        self._audit_events.insert(
            0,
            AuditEventItem(
                timestamp=now_str,
                actor="pratik.bingewar",
                event=f"Recommendation marked {action}",
                resource=updated.title[:30] + "...",
                before="Pending",
                after=action,
                approval_ref=f"ACT-{hash(decision_id) % 9000 + 1000}",
            ),
        )
        return updated

    def get_canonical_kpi(
        self,
        metric_id: str,
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        connection_id: str = "databricks-azure-dev",
    ) -> CanonicalKpiResponse:
        """Fetch a specific certified canonical KPI metric with exact lineage, formula, and caveats."""
        self.validate_scope(workspace_id)
        metric_key = metric_id.lower().strip()

        # Check Executive Overview KPIs first
        overview = self.get_executive_overview(
            connection_id=connection_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
        if metric_key in overview.kpis:
            return CanonicalKpiResponse(metric_id=metric_id, metric=overview.kpis[metric_key])

        # Check Cost Explorer KPIs
        cost_exp = self.get_cost_explorer(
            connection_id=connection_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
        if metric_key in cost_exp.kpis:
            return CanonicalKpiResponse(metric_id=metric_id, metric=cost_exp.kpis[metric_key])

        # Check Compute & Warehouses KPIs
        compute = self.get_compute_warehouses(
            connection_id=connection_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
        if metric_key in compute.kpis:
            return CanonicalKpiResponse(metric_id=metric_id, metric=compute.kpis[metric_key])

        # Check AI Economics KPIs
        ai = self.get_ai_economics(
            connection_id=connection_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
        if metric_key in ai.kpis:
            return CanonicalKpiResponse(metric_id=metric_id, metric=ai.kpis[metric_key])

        # Check Optimization Advisor KPIs
        opt = self.get_optimization_advisor(
            connection_id=connection_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
        if metric_key in opt.kpis:
            return CanonicalKpiResponse(metric_id=metric_id, metric=opt.kpis[metric_key])

        # Unknown metric_id -> return typed NO_DATA metric
        empty_kpi = self._build_empty_kpi(
            metric_id=metric_id,
            unit="unit",
            currency=None,
            source="Canonical KPI Registry",
            workspace_id=workspace_id or "642006393507276",
            resource_id=resource_id,
            resource_type=resource_type,
        )
        return CanonicalKpiResponse(metric_id=metric_id, metric=empty_kpi)

    # ------------------------------------------------------------------
    # Live-data helpers (M2.3): every value is LIVE, CALCULATED, ESTIMATED or
    # explicitly UNAVAILABLE / BLOCKED. Nothing is modelled or invented.
    # ------------------------------------------------------------------

    _COLORS: tuple[str, ...] = (
        "#2563eb",
        "#0284c7",
        "#8b5cf6",
        "#06b6d4",
        "#f59e0b",
        "#10b981",
        "#94a3b8",
    )
    _OWNER_TAG_KEYS: tuple[str, ...] = (
        "owner",
        "team",
        "business_unit",
        "cost_center",
        "costcenter",
        "department",
    )
    _RESOURCE_META_KEYS: tuple[tuple[str, str], ...] = _RESOURCE_KEYS
    _FILTER_META_KEYS: dict[str, tuple[str, ...]] = _FILTER_KEYS
    _MIN_HISTORY_DAYS: int = 14

    @property
    def billing_service(self) -> Any:
        """Lazily bound billing ingestion service (shared with the API layer when injected)."""
        if self._billing_service is None:
            from cloud_recommender.services.databricks.billing_ingestion_service import (
                BillingIngestionService,
            )

            self._billing_service = BillingIngestionService(
                workspace_service=self.workspace_service
            )
        return self._billing_service

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _scope_currency() -> _CurrencyState:
        return _SCOPE_CURRENCY.get()

    def _money(self, value: float, currency: str | None = None, decimals: int = 2) -> str:
        """Format a monetary amount in the confirmed currency of the scope; never assume USD."""
        state = _SCOPE_CURRENCY.get()
        if currency is None and state.mixed:
            return "n/a (mixed currencies)"
        code = currency or state.code
        return format_money(value, code, decimals) if code else "-"

    def _scope_workspace_ids(self, workspace_id: Any) -> set[str]:
        """Resolve validated scope entries (workspace or connection ids) to workspace ids."""
        ids: set[str] = set()
        for wid in self.validate_scope(workspace_id):
            if wid == "all":
                return set()
            conn = self.workspace_service.get_connection(wid)
            ids.add(conn.workspace_id if conn else wid)
        return ids

    def _primary_workspace(self, workspace_id: Any) -> str:
        ids = sorted(self._scope_workspace_ids(workspace_id))
        return ids[0] if ids else "642006393507276"

    def _mk_kpi(
        self,
        metric_id: str,
        unit: str,
        status: KpiStatus,
        *,
        value: float | None = None,
        formatted: str | None = None,
        currency: str | None = None,
        confirmed_currency: str | None = None,
        source: str,
        formula: str | None = None,
        caveats: str | None = None,
        record_count: int | None = None,
        workspace_id: str = "642006393507276",
        resource_id: str | None = None,
        resource_type: str | None = None,
        delta_label: str | None = None,
        aggregation: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        change_percentage: float | None = None,
        coverage: float = 1.0,
    ) -> KpiMetric:
        """Build a KPI whose display text always matches its provenance."""
        resource_id = resource_id if isinstance(resource_id, str) else None
        resource_type = resource_type if isinstance(resource_type, str) else None
        money_unit = unit in ("USD", "USD/DBU")
        mixed_note: str | None = None
        if money_unit:
            # The "USD" unit is only a marker for "a monetary amount": the real currency is the
            # one confirmed by the priced rows (or by an explicit, named setting), never assumed.
            if confirmed_currency:
                currency = confirmed_currency
            else:
                state = _SCOPE_CURRENCY.get()
                currency = state.code
                if state.mixed:
                    mixed_note = _MIXED_CURRENCY_NOTE.format(codes=", ".join(state.codes))
                    value = None
                    status = KpiStatus.UNAVAILABLE
                    caveats = f"{caveats} {mixed_note}" if caveats else mixed_note
            unit = unit.replace("USD", currency or "CURRENCY")
        else:
            currency = None
        reason_prefix = {
            KpiStatus.BLOCKED_PENDING_APPROVAL: "Blocked: requires approved read-only SQL access to system tables.",
            KpiStatus.INSUFFICIENT_HISTORY: "Insufficient history.",
            KpiStatus.UNAVAILABLE: "Not available: no connected source provides this metric.",
            KpiStatus.SOURCE_UNAVAILABLE: "Source unavailable.",
            KpiStatus.NOT_AUTHORIZED: "Permission required.",
            KpiStatus.NO_DATA: "The query succeeded but returned no records for this scope.",
        }
        if value is None:
            # `-` means "could not be established"; a measured zero is a real 0 value.
            text = "-"
            reason: str | None = " ".join(
                x for x in (reason_prefix.get(status, "Value not established."), caveats) if x
            )
            if mixed_note:
                reason = mixed_note
        elif formatted is not None:
            text = formatted
            reason = None
        elif money_unit:
            text = self._money(value, currency, 4 if unit.endswith("/DBU") else 2) + (
                " / DBU" if unit.endswith("/DBU") else ""
            )
            reason = None
        elif unit == "%":
            text = f"{value:,.1f}%"
            reason = None
        else:
            text = f"{value:,.2f}".rstrip("0").rstrip(".") + (f" {unit}" if unit else "")
            reason = None
        return KpiMetric(
            value=value,
            formatted_value=text,
            unit=unit,
            currency=currency,
            metric_id=metric_id,
            status=status,
            source=source,
            data_source=source,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
            last_refreshed=self._now_iso(),
            aggregation_method=aggregation,
            formula=formula,
            record_count=record_count,
            caveats=caveats,
            limitations=caveats,
            delta_label=delta_label,
            period_start=period_start,
            period_end=period_end,
            change_percentage=change_percentage,
            coverage=coverage,
            reason=reason,
            data_freshness="Live" if status == KpiStatus.LIVE else "As of last_refreshed",
        )

    def _inventory(self, connection_id: str) -> dict[str, list[DiscoveredResourceItem]]:
        return self._get_workspace_assets(connection_id)

    def _warehouse_state(self, connection_id: str) -> str:
        wh = self._inventory(connection_id).get("warehouse", [])
        return wh[0].status or "UNKNOWN" if wh else "UNKNOWN"

    def _inventory_provenance(
        self, connection_id: str, resource_types: tuple[str, ...]
    ) -> SectionProvenance:
        grouped = self._inventory(connection_id)
        if not grouped:
            return SectionProvenance(
                classification=KpiStatus.UNAVAILABLE,
                source="Databricks REST/SDK workspace discovery",
                message="Workspace discovery has not completed; no inventory is available.",
                requirement="Valid Databricks authentication for the workspace",
                retrieved_at=self._now_iso(),
            )
        discovery = self.workspace_service._discovery_cache.get(connection_id)
        count = sum(len(grouped.get(t, [])) for t in resource_types)
        return SectionProvenance(
            classification=KpiStatus.LIVE if count else KpiStatus.NO_DATA,
            source="Databricks REST/SDK workspace discovery",
            message=None if count else "Discovery succeeded and returned zero matching resources.",
            retrieved_at=discovery.discovered_at.isoformat() if discovery else self._now_iso(),
            record_count=count,
        )

    # -- billing rows ---------------------------------------------------

    def _billing_rows(
        self,
        workspace_id: Any,
        filter_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[BillingUsageRecord]:
        """Ingested system.billing.usage rows in scope. Empty until an approved ingestion ran."""
        scope = self._scope_workspace_ids(workspace_id)
        rows = [
            r
            for r in self.billing_service._usage_store.values()
            if not scope or r.workspace_id in scope
        ]
        # Currency is judged on the whole workspace scope (before any resource filter) so a
        # per-resource read can never disagree with the scope-level figures around it.
        currencies = sorted({r.currency for r in rows if r.pricing_matched and r.currency})
        _SCOPE_CURRENCY.set(
            _CurrencyState(
                code=currencies[0] if len(currencies) == 1 else None,
                mixed=len(currencies) > 1,
                codes=tuple(currencies),
            )
        )
        if filter_type in self._FILTER_META_KEYS:
            keys = self._FILTER_META_KEYS[filter_type]
            rows = [
                r
                for r in rows
                if any(
                    r.usage_metadata.get(k)
                    and (not resource_id or r.usage_metadata[k] == resource_id)
                    for k in keys
                )
            ]
        elif resource_id:
            rows = [r for r in rows if matches_resource(r.usage_metadata, resource_id)]
        return self._withhold_priced_costs(rows) if _SCOPE_CURRENCY.get().mixed else rows

    @staticmethod
    def _withhold_priced_costs(rows: list[BillingUsageRecord]) -> list[BillingUsageRecord]:
        """Never sum different currencies: drop the costs of priced rows (scope is mixed).

        Usage quantities are untouched. Affected rows read as unpriced (MIXED_CURRENCY) so
        every downstream spend figure is explicitly partial rather than silently merged.
        """
        return [
            r.model_copy(
                update={
                    "effective_cost": None,
                    "pricing_matched": False,
                    "currency": None,
                    "cost_basis": CostBasis.METERED_USAGE,
                    "match_status": MatchStatus.MIXED_CURRENCY,
                }
            )
            if r.pricing_matched
            else r
            for r in rows
        ]

    def _billing_provenance(
        self, rows: list[BillingUsageRecord], connection_id: str = "databricks-azure-dev"
    ) -> SectionProvenance:
        if rows:
            priced = sum(1 for r in rows if r.pricing_matched)
            mixed = any(r.match_status == MatchStatus.MIXED_CURRENCY for r in rows)
            return SectionProvenance(
                classification=KpiStatus.CALCULATED,
                source="system.billing.usage (ingested) x rate card",
                message=(
                    f"{priced}/{len(rows)} usage rows priced with list prices (DBU x list rate). "
                    "Excludes discounts, credits and Azure infrastructure charges."
                    + (
                        " Several currencies are present: costs are withheld, never merged or converted."
                        if mixed
                        else ""
                    )
                ),
                retrieved_at=self._now_iso(),
                record_count=len(rows),
            )
        wh_state = self._warehouse_state(connection_id)
        return SectionProvenance(
            classification=KpiStatus.BLOCKED_PENDING_APPROVAL,
            source="system.billing.usage",
            message=(
                "No billing rows ingested. Spend cannot be derived from Databricks APIs alone; "
                f"it requires a read-only SELECT on system.billing.usage (SQL warehouse state: {wh_state})."
            ),
            requirement=(
                "Explicit human approval to start the SQL warehouse and run the approved ingestion, "
                "plus SELECT on system.billing.usage and system.billing.list_prices."
            ),
            retrieved_at=self._now_iso(),
            record_count=0,
        )

    @staticmethod
    def _owner_of(rec: BillingUsageRecord) -> str | None:
        lowered = {k.lower(): v for k, v in rec.custom_tags.items() if v}
        for key in FinOpsAnalyticsService._OWNER_TAG_KEYS:
            if lowered.get(key):
                return lowered[key]
        return None

    @staticmethod
    def _product_of(rec: BillingUsageRecord) -> str:
        return (rec.billing_origin_product or rec.sku_name.split("_")[0] or "UNKNOWN").upper()

    @staticmethod
    def _is_ai(rec: BillingUsageRecord) -> bool:
        product = (rec.billing_origin_product or "").upper()
        if product:
            return any(t in product for t in ("MODEL_SERVING", "AI_", "FOUNDATION", "VECTOR"))
        sku = rec.sku_name.upper()
        return any(t in sku for t in ("MODEL_SERVING", "INFERENCE", "FOUNDATION"))

    def _resource_of(self, rec: BillingUsageRecord) -> tuple[str, str] | None:
        for key, rtype in self._RESOURCE_META_KEYS:
            val = rec.usage_metadata.get(key)
            if val:
                return rtype, str(val)
        return None

    @staticmethod
    def _cost(rec: BillingUsageRecord) -> float:
        """LIST_PRICE_ESTIMATE of one row as float (display boundary; storage stays Decimal)."""
        return float(rec.effective_cost) if rec.effective_cost is not None else 0.0

    @staticmethod
    def _sum_cost(rows: list[BillingUsageRecord]) -> float:
        total = sum((r.effective_cost for r in rows if r.effective_cost is not None), Decimal("0"))
        return round(float(total), 2)

    @staticmethod
    def _sum_dbu(rows: list[BillingUsageRecord]) -> float:
        total = sum((r.usage_quantity for r in rows if r.usage_unit == "DBU"), Decimal("0"))
        return round(float(total), 4)

    @staticmethod
    def _coverage(rows: list[BillingUsageRecord]) -> float:
        dbu = [r for r in rows if r.usage_unit == "DBU"]
        return round(sum(1 for r in dbu if r.pricing_matched) / len(dbu), 4) if dbu else 1.0

    def _daily_totals(self, rows: list[BillingUsageRecord]) -> dict[str, tuple[float, float]]:
        out: dict[str, list[float]] = {}
        for r in rows:
            d = out.setdefault(r.usage_date, [0.0, 0.0])
            d[0] += self._cost(r)
            d[1] += float(r.usage_quantity) if r.usage_unit == "DBU" else 0.0
        return {k: (round(v[0], 2), round(v[1], 4)) for k, v in sorted(out.items())}

    @staticmethod
    def _label_date(iso_date: str) -> str:
        try:
            return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%b %d")
        except ValueError:
            return iso_date

    def _reference_month(
        self, rows: list[BillingUsageRecord]
    ) -> tuple[str, list[BillingUsageRecord]]:
        """Month of the latest usage row and the rows inside it (period of record)."""
        month = max(r.usage_date for r in rows)[:7]
        return month, [r for r in rows if r.usage_date.startswith(month)]

    def _budget(self) -> float | None:
        from cloud_recommender.core.config import get_settings

        return get_settings().finops_monthly_budget_usd

    def _forecast(self, rows: list[BillingUsageRecord]) -> dict[str, Any] | None:
        """Run-rate forecast; None when there is not enough history (>= 14 usage days)."""
        daily = self._daily_totals(rows)
        if len(daily) < self._MIN_HISTORY_DAYS:
            return None
        month, month_rows = self._reference_month(rows)
        month_daily = self._daily_totals(month_rows)
        days = list(daily.items())
        last7 = [v[0] for _, v in days[-7:]]
        run_rate = sum(last7) / len(last7)
        last_day = datetime.strptime(days[-1][0], "%Y-%m-%d")
        next_month = (last_day.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_len = (next_month - timedelta(days=1)).day
        remaining = max(0, month_len - last_day.day)
        mtd = round(sum(v[0] for v in month_daily.values()), 2)
        return {
            "month": month,
            "mtd": mtd,
            "run_rate": round(run_rate, 2),
            "forecast": round(mtd + run_rate * remaining, 2),
            "remaining_days": remaining,
            "days_observed": len(daily),
        }

    def _detect_anomalies(self, rows: list[BillingUsageRecord]) -> list[AnomalyItem] | None:
        """Trailing-window z-score on daily spend. None when history is insufficient."""
        daily = self._daily_totals(rows)
        if len(daily) < self._MIN_HISTORY_DAYS:
            return None
        days = list(daily.items())
        found: list[AnomalyItem] = []
        for i in range(7, len(days)):
            window = [v[0] for _, v in days[max(0, i - 28) : i]]
            mean = statistics.fmean(window)
            # Floor the deviation at 5% of the baseline so a perfectly flat history
            # (sd == 0) still yields a finite, conservative z-score.
            sd = max(statistics.pstdev(window), 0.05 * mean)
            date, (cost, _dbu) = days[i]
            if sd <= 0:
                continue
            z = (cost - mean) / sd
            if z < 3.0:
                continue
            day_rows = [r for r in rows if r.usage_date == date]
            by_sku: dict[str, float] = {}
            for r in day_rows:
                by_sku[r.sku_name] = by_sku.get(r.sku_name, 0.0) + self._cost(r)
            aid = f"anom-{date}"
            found.append(
                AnomalyItem(
                    id=aid,
                    detected=self._label_date(date),
                    severity="Critical" if z >= 5 else "High" if z >= 4 else "Medium",
                    signal="Daily spend above trailing baseline",
                    resource="Workspace (all billed SKUs)",
                    baseline=f"{self._money(mean)} / day",
                    observed=f"{self._money(cost)} / day",
                    estimated_impact=f"{self._money(cost - mean)} (list-price basis)",
                    likely_cause="Not determined; review SKU contribution and workload attribution.",
                    evidence_detail=f"z={z:.2f} over {len(window)} trailing days from system.billing.usage.",
                    resource_type="workspace",
                    metric="Spend / Day",
                    absolute_deviation=self._money(cost - mean),
                    percentage_deviation=f"{((cost - mean) / mean * 100) if mean else 0:.1f}%",
                    detection_methodology="Z-score >= 3 SD over trailing <=28-day window (SD floored at 5% of mean)",
                    confidence=f"Statistical (n={len(window)} days)",
                    status=self._anomaly_overrides.get(aid, "New"),
                    historical_trend=[
                        {"date": self._label_date(d), "spend": c}
                        for d, (c, _) in days[max(0, i - 13) : i + 1]
                    ],
                    sku_contribution=[
                        {
                            "sku": k,
                            "pct": round(v / cost * 100, 1) if cost else 0.0,
                            "amount": self._money(v),
                        }
                        for k, v in sorted(by_sku.items(), key=lambda kv: -kv[1])[:5]
                    ],
                )
            )
        return found

    def _get_anomalies(
        self, resource_id: str | None = None, resource_type: str | None = None
    ) -> list[AnomalyItem]:
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        if is_unknown:
            return []
        rows = self._billing_rows(None, filter_type, resource_id)
        return self._detect_anomalies(rows) or []

    # -- optimization recommendations (configuration evidence only) -----

    def _get_decisions(
        self, resource_id: str | None = None, resource_type: str | None = None
    ) -> list[DecisionItem]:
        """Recommendations derived from live resource configuration. Savings are never invented."""
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        if is_unknown:
            return []
        grouped = self._inventory("databricks-azure-dev")
        ts = self._now_iso()
        discovery = self.workspace_service._discovery_cache.get("databricks-azure-dev")
        if discovery:
            ts = discovery.discovered_at.isoformat()
        recs: list[DecisionItem] = []

        def add(
            rule: str,
            res: DiscoveredResourceItem,
            category: str,
            title: str,
            finding: str,
            evidence: str,
            action: str,
            confidence: int,
            risk: str,
        ) -> None:
            rid = f"rec-{rule}-{res.id}"
            override = self._action_overrides.get(rid, {})
            recs.append(
                DecisionItem(
                    id=rid,
                    priority=len(recs) + 1,
                    title=title,
                    description=finding,
                    estimated_savings_monthly=None,
                    formatted_savings="Not calculable (requires usage and billing telemetry)",
                    impact="Configuration risk",
                    status=override.get("status", "Approval required"),
                    confidence_pct=confidence,
                    effort="Low",
                    owner=res.creator or "Unassigned",
                    evidence=evidence,
                    category=category,
                    resource_name=res.name,
                    resource_id=res.id,
                    finding=finding,
                    current_cost="-"
                    if not self._billing_rows(None, None, res.id)
                    else self._money(self._sum_cost(self._billing_rows(None, None, res.id))),
                    potential_savings_range="Not calculable",
                    recommended_action=action,
                    calculation_methodology=(
                        "Rule-based check of live configuration; no savings claimed because "
                        "idle time / utilization telemetry is not available."
                    ),
                    validation_method="Re-read the resource configuration and compare post-change billing.",
                    risk=risk,
                    complexity="Low",
                    performance_impact="Depends on workload; validate before applying.",
                    source_timestamp=ts,
                    savings_status=KpiStatus.UNAVAILABLE,
                )
            )

        if filter_type in (None, "warehouse"):
            for w in grouped.get("warehouse", []):
                if resource_id and w.id != resource_id:
                    continue
                stop = w.metadata.get("auto_stop_mins")
                if stop is None or stop == 0 or stop > 10:
                    add(
                        "wh-autostop",
                        w,
                        "Compute",
                        f"Tighten auto-stop on SQL warehouse '{w.name}'",
                        f"Auto-stop is {'disabled' if not stop else f'{stop} min'}; idle warehouses keep billing until stopped.",
                        f"warehouses.list: auto_stop_mins={stop}, size={w.metadata.get('cluster_size')}, state={w.status}",
                        "Set auto-stop to 10 minutes or less (human approval required; not applied by this platform).",
                        70,
                        "Low",
                    )
        if filter_type in (None, "cluster"):
            for c in grouped.get("cluster", []):
                if resource_id and c.id != resource_id:
                    continue
                term = c.metadata.get("autotermination_minutes")
                if not term:
                    add(
                        "cl-noterm",
                        c,
                        "Compute",
                        f"Configure auto-termination on cluster '{c.name}'",
                        "No auto-termination is configured; a running cluster bills DBU and VM cost until stopped manually.",
                        f"clusters.list: autotermination_minutes={term}, node_type={c.metadata.get('node_type_id')}, state={c.status}",
                        "Set auto-termination to 60 minutes or less (human approval required).",
                        90,
                        "Low",
                    )
                elif term > 60:
                    add(
                        "cl-longterm",
                        c,
                        "Compute",
                        f"Shorten auto-termination on cluster '{c.name}'",
                        f"Auto-termination is {term} minutes.",
                        f"clusters.list: autotermination_minutes={term}, state={c.status}",
                        "Reduce auto-termination to 60 minutes or less (human approval required).",
                        75,
                        "Low",
                    )
        if filter_type in (None, "serving"):
            for e in grouped.get("serving_endpoint", []):
                if resource_id and e.id != resource_id:
                    continue
                ents = e.metadata.get("served_entities") or []
                flagged = [
                    x
                    for x in ents
                    if isinstance(x, dict)
                    and x.get("workload_size")
                    and x.get("scale_to_zero_enabled") is False
                ]
                if flagged:
                    add(
                        "srv-s2z",
                        e,
                        "AI",
                        f"Enable scale-to-zero on endpoint '{e.name}'",
                        "Provisioned endpoint keeps capacity allocated while idle.",
                        f"serving-endpoints.list: scale_to_zero_enabled=False, workload_size={flagged[0].get('workload_size')}",
                        "Enable scale-to-zero if cold-start latency is acceptable (human approval required).",
                        65,
                        "Medium",
                    )
        return recs

    def get_decision_savings(self, decisions: list[DecisionItem]) -> float | None:
        values = [
            d.estimated_savings_monthly
            for d in decisions
            if d.estimated_savings_monthly is not None
        ]
        return round(sum(values), 2) if values else None

    # ------------------------------------------------------------------
    # Module 1: Executive overview
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_executive_overview(
        self,
        connection_id: str = "databricks-azure-dev",
        period: str = "month",
        environment: str | None = None,
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> ExecutiveOverviewResponse:
        """Executive KPIs from ingested billing rows; BLOCKED when none exist."""
        ws = self._primary_workspace(workspace_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)
        decisions = [] if is_unknown else self._get_decisions(resource_id, resource_type)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        bill_prov = self._billing_provenance(rows, connection_id)
        blocked = KpiStatus.NO_DATA if is_unknown else KpiStatus.BLOCKED_PENDING_APPROVAL
        grouped = self._inventory(connection_id)
        global_filters: dict[str, Any] = {
            "period": period,
            "environment": environment or "Development",
            "currency": self._scope_currency().code,
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "live_inventory": {
                "clusters": len(grouped.get("cluster", [])),
                "warehouses": len(grouped.get("warehouse", [])),
                "serving_endpoints": len(grouped.get("serving_endpoint", [])),
                "apps": len(grouped.get("app", [])),
                "catalogs": len(grouped.get("catalog", [])),
                "jobs": len(grouped.get("job", [])),
            },
        }
        provenance = {
            "spend": bill_prov,
            "inventory": self._inventory_provenance(
                connection_id, ("cluster", "warehouse", "serving_endpoint", "app")
            ),
        }
        forecast = self._forecast(rows) if rows else None
        anomalies = self._detect_anomalies(rows) if rows else None
        savings = self.get_decision_savings(decisions)

        def anomaly_kpi() -> KpiMetric:
            if anomalies is None:
                return self._mk_kpi(
                    "anomalies",
                    "count",
                    KpiStatus.INSUFFICIENT_HISTORY if rows else blocked,
                    currency=None,
                    source="system.billing.usage",
                    caveats=f"Needs >= {self._MIN_HISTORY_DAYS} days of ingested billing history.",
                    **common,
                )
            return self._mk_kpi(
                "anomalies",
                "count",
                KpiStatus.CALCULATED,
                value=float(len(anomalies)),
                currency=None,
                source="system.billing.usage",
                formula="count(days with z-score >= 3 vs trailing 28d)",
                record_count=len(rows),
                **common,
            )

        if not rows:
            msg: dict[str, Any] = {
                "source": "system.billing.usage",
                "caveats": bill_prov.message,
                **common,
            }
            kpis = {
                "total_spend": self._mk_kpi("total_spend", "USD", blocked, **msg),
                "databricks_spend": self._mk_kpi("databricks_spend", "USD", blocked, **msg),
                "ai_spend": self._mk_kpi("ai_spend", "USD", blocked, **msg),
                "dbu_consumption": self._mk_kpi(
                    "dbu_consumption", "DBU", blocked, **{**msg, "currency": None}
                ),
                "savings_opportunity": self._mk_kpi(
                    "savings_opportunity",
                    "USD",
                    KpiStatus.UNAVAILABLE,
                    source="Optimization Advisor",
                    caveats="Savings require billing and utilization telemetry; none is calculable yet.",
                    **common,
                ),
                "forecast_spend": self._mk_kpi(
                    "forecast_spend",
                    "USD",
                    KpiStatus.INSUFFICIENT_HISTORY if not is_unknown else blocked,
                    **msg,
                ),
                "anomalies": anomaly_kpi(),
            }
            return ExecutiveOverviewResponse(
                kpis=kpis,
                spend_trend=[],
                spend_composition=[],
                top_cost_drivers=[],
                decisions_requiring_attention=decisions,
                global_filters=global_filters,
                provenance=provenance,
            )

        month, month_rows = self._reference_month(rows)
        prev_month_rows = [r for r in rows if r.usage_date[:7] < month]
        total = self._sum_cost(month_rows)
        ai_rows = [r for r in month_rows if self._is_ai(r)]
        period_kwargs: dict[str, Any] = {
            "period_start": min(r.usage_date for r in month_rows),
            "period_end": max(r.usage_date for r in month_rows),
        }
        caveat = "List-price basis (DBU x rate card). Excludes discounts, credits and Azure infrastructure."
        change = None
        if prev_month_rows:
            prev_total = self._sum_cost(prev_month_rows)
            if prev_total:
                change = round((total - prev_total) / prev_total * 100, 1)
        kpis = {
            "total_spend": self._mk_kpi(
                "total_spend",
                "USD",
                KpiStatus.CALCULATED,
                value=total,
                source="system.billing.usage x list prices",
                aggregation="SUM",
                formula="sum(usage_quantity * list_price) for latest usage month",
                caveats=caveat,
                record_count=len(month_rows),
                coverage=self._coverage(month_rows),
                change_percentage=change,
                **period_kwargs,
                **common,
            ),
            "databricks_spend": self._mk_kpi(
                "databricks_spend",
                "USD",
                KpiStatus.CALCULATED,
                value=total,
                source="system.billing.usage x list prices",
                aggregation="SUM",
                formula="sum(DBU usage_quantity * list_price)",
                caveats=caveat,
                record_count=len(month_rows),
                coverage=self._coverage(month_rows),
                **period_kwargs,
                **common,
            ),
            "ai_spend": self._mk_kpi(
                "ai_spend",
                "USD",
                KpiStatus.CALCULATED,
                value=self._sum_cost(ai_rows),
                source="system.billing.usage x list prices",
                aggregation="SUM",
                formula="sum(cost) WHERE billing_origin_product is AI/model serving",
                caveats=caveat,
                record_count=len(ai_rows),
                **period_kwargs,
                **common,
            ),
            "dbu_consumption": self._mk_kpi(
                "dbu_consumption",
                "DBU",
                KpiStatus.LIVE,
                value=self._sum_dbu(month_rows),
                currency=None,
                source="system.billing.usage",
                aggregation="SUM",
                formula="sum(usage_quantity) WHERE usage_unit = 'DBU'",
                record_count=len(month_rows),
                **period_kwargs,
                **common,
            ),
            "savings_opportunity": self._mk_kpi(
                "savings_opportunity",
                "USD",
                KpiStatus.CALCULATED if savings is not None else KpiStatus.UNAVAILABLE,
                value=savings,
                source="Optimization Advisor",
                caveats="Only recommendations with calculable savings contribute.",
                **common,
            ),
            "forecast_spend": self._mk_kpi(
                "forecast_spend",
                "USD",
                KpiStatus.ESTIMATED if forecast else KpiStatus.INSUFFICIENT_HISTORY,
                value=forecast["forecast"] if forecast else None,
                source="Run-rate projection of system.billing.usage",
                formula="MTD actual + trailing-7-day average x remaining days",
                caveats="Projection, not actual spend."
                if forecast
                else f"Needs >= {self._MIN_HISTORY_DAYS} days of history.",
                **common,
            ),
            "anomalies": anomaly_kpi(),
        }

        daily = self._daily_totals(rows)
        by_family: dict[str, float] = {}
        for r in month_rows:
            by_family[self._product_of(r)] = by_family.get(self._product_of(r), 0.0) + self._cost(r)
        composition = [
            {
                "family": fam,
                "amount": round(amt, 2),
                "share": round(amt / total, 4) if total else 0.0,
                "color": self._COLORS[i % len(self._COLORS)],
            }
            for i, (fam, amt) in enumerate(sorted(by_family.items(), key=lambda kv: -kv[1]))
        ]
        by_res: dict[tuple[str, str], float] = {}
        for r in month_rows:
            key = self._resource_of(r) or ("sku", r.sku_name)
            by_res[key] = by_res.get(key, 0.0) + self._cost(r)
        drivers = [
            CostDriverItem(
                driver=f"{rtype}: {rid}",
                workspace_owner=ws,
                spend=round(amt, 2),
                formatted_spend=self._money(amt),
                change="n/a",
                signal="Review" if total and amt / total >= 0.3 else "Stable",
            )
            for (rtype, rid), amt in sorted(by_res.items(), key=lambda kv: -kv[1])[:5]
        ]
        return ExecutiveOverviewResponse(
            kpis=kpis,
            spend_trend=[
                {"day": self._label_date(d), "actual": c, "forecast": None, "budget_pace": None}
                for d, (c, _) in daily.items()
            ],
            spend_composition=composition,
            top_cost_drivers=drivers,
            decisions_requiring_attention=decisions,
            global_filters=global_filters,
            provenance=provenance,
        )

    # ------------------------------------------------------------------
    # Module 2: Cost explorer
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_cost_explorer(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> CostExplorerResponse:
        ws = self._primary_workspace(workspace_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)
        prov = {"ledger": self._billing_provenance(rows, connection_id)}
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        if not rows:
            status = KpiStatus.NO_DATA if is_unknown else KpiStatus.BLOCKED_PENDING_APPROVAL
            kpis = {
                "gross_consumption": self._mk_kpi(
                    "gross_consumption", "USD", status, source="system.billing.usage", **common
                ),
                "effective_rate": self._mk_kpi(
                    "effective_rate", "USD/DBU", status, source="system.billing.usage", **common
                ),
                "unallocated_spend": self._mk_kpi(
                    "unallocated_spend", "USD", status, source="system.billing.usage", **common
                ),
                "credits_discounts": self._mk_kpi(
                    "credits_discounts",
                    "USD",
                    KpiStatus.UNAVAILABLE,
                    source="Azure invoice / contract data",
                    caveats="Discounts and credits are not exposed by system.billing.usage.",
                    **common,
                ),
            }
            return CostExplorerResponse(
                kpis=kpis,
                daily_trend=[],
                cost_by_product_family=[],
                billing_ledger=[],
                provenance=prov,
            )

        total = self._sum_cost(rows)
        dbu = self._sum_dbu(rows)
        unalloc = self._sum_cost([r for r in rows if not self._owner_of(r)])
        by_family: dict[str, float] = {}
        grouped: dict[tuple[str, str, str, str], list[float]] = {}
        for r in rows:
            by_family[self._product_of(r)] = by_family.get(self._product_of(r), 0.0) + self._cost(r)
            owner = self._owner_of(r) or "unallocated"
            g = grouped.setdefault(
                (r.usage_date, self._product_of(r), r.sku_name, owner), [0.0, 0.0]
            )
            g[0] += float(r.usage_quantity)
            g[1] += self._cost(r)
        ledger = [
            CostExplorerItem(
                date=self._label_date(d),
                product=prod,
                sku=sku,
                workspace=f"adb-{ws}",
                usage_qty=round(q, 4),
                unit="DBU",
                list_cost=round(c, 2),
                effective_cost=round(c, 2),
                owner_tag=owner,
                allocation_status="Unallocated" if owner == "unallocated" else "Allocated",
            )
            for (d, prod, sku, owner), (q, c) in sorted(grouped.items(), reverse=True)[:500]
        ]
        caveat = "List-price basis; excludes discounts and Azure infrastructure."
        kpis = {
            "gross_consumption": self._mk_kpi(
                "gross_consumption",
                "USD",
                KpiStatus.CALCULATED,
                value=total,
                source="system.billing.usage x list prices",
                aggregation="SUM",
                formula="sum(usage_quantity * list_price)",
                caveats=caveat,
                record_count=len(rows),
                coverage=self._coverage(rows),
                **common,
            ),
            "effective_rate": self._mk_kpi(
                "effective_rate",
                "USD/DBU",
                KpiStatus.CALCULATED,
                value=round(total / dbu, 4) if dbu else None,
                source="system.billing.usage x list prices",
                formula="total cost / total DBU",
                caveats=caveat,
                record_count=len(rows),
                **common,
            ),
            "unallocated_spend": self._mk_kpi(
                "unallocated_spend",
                "USD",
                KpiStatus.CALCULATED,
                value=unalloc,
                source="system.billing.usage custom_tags",
                formula="sum(cost) WHERE no owner tag",
                record_count=len(rows),
                **common,
            ),
            "credits_discounts": self._mk_kpi(
                "credits_discounts",
                "USD",
                KpiStatus.UNAVAILABLE,
                source="Azure invoice / contract data",
                caveats="Discounts and credits are not exposed by system.billing.usage.",
                **common,
            ),
        }
        return CostExplorerResponse(
            kpis=kpis,
            daily_trend=[
                {"date": self._label_date(d), "cost": c, "dbu": q}
                for d, (c, q) in self._daily_totals(rows).items()
            ],
            cost_by_product_family=[
                {"product": p, "cost": round(c, 2), "share": round(c / total, 4) if total else 0.0}
                for p, c in sorted(by_family.items(), key=lambda kv: -kv[1])
            ],
            billing_ledger=ledger,
            provenance=prov,
        )

    def export_cost_ledger_csv(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> str:
        """CSV of the real ledger (header only when no billing rows are ingested)."""
        data = self.get_cost_explorer(
            connection_id=connection_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
        # Source currency comes from the priced rows read by get_cost_explorer above.
        csv_state = self._scope_currency()
        csv_ccy_known = csv_state.code is not None
        csv_ccy = csv_state.code or ("mixed currencies" if csv_state.mixed else "currency unknown")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Date",
                "Product",
                "SKU",
                "Workspace",
                "Usage Qty",
                "Unit",
                f"List Cost ({csv_ccy})",
                f"Effective Cost ({csv_ccy})",
                "Owner Tag",
                "Allocation Status",
            ]
        )
        for r in data.billing_ledger:
            writer.writerow(
                [
                    r.date,
                    r.product,
                    r.sku,
                    r.workspace,
                    r.usage_qty,
                    r.unit,
                    f"{r.list_cost:.2f}" if csv_ccy_known else "",
                    f"{r.effective_cost:.2f}" if csv_ccy_known else "",
                    r.owner_tag,
                    r.allocation_status,
                ]
            )
        return output.getvalue()

    # ------------------------------------------------------------------
    # Module 3: Cost allocation / showback
    # ------------------------------------------------------------------

    def _allocation(self, rows: list[BillingUsageRecord]) -> dict[str, dict[str, float]]:
        """Spend by real owner tag; untagged spend stays 'Unallocated' (never distributed)."""
        out: dict[str, dict[str, float]] = {}
        for r in rows:
            owner = self._owner_of(r) or "Unallocated"
            b = out.setdefault(owner, {"total": 0.0, "ai": 0.0, "compute": 0.0, "storage": 0.0})
            c = self._cost(r)
            b["total"] += c
            if self._is_ai(r):
                b["ai"] += c
            elif "STORAGE" in self._product_of(r):
                b["storage"] += c
            else:
                b["compute"] += c
        return out

    @_unknown_scope_guard
    def get_cost_allocation(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> CostAllocationResponse:
        ws = self._primary_workspace(workspace_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)
        prov = {"allocation": self._billing_provenance(rows, connection_id)}
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        rulebook = [
            AllocationRuleItem(
                priority=1,
                rule_name="Owner tag attribution",
                match_condition=f"custom_tags has any of: {', '.join(self._OWNER_TAG_KEYS)}",
                allocation_target="Tag value",
                method="Direct (100% to tag value)",
                status="Active",
            ),
            AllocationRuleItem(
                priority=2,
                rule_name="Unallocated fallback",
                match_condition="No owner tag present",
                allocation_target="Unallocated",
                method="Not distributed",
                status="Active",
            ),
        ]
        if not rows:
            status = KpiStatus.NO_DATA if is_unknown else KpiStatus.BLOCKED_PENDING_APPROVAL
            kpis = {
                "allocated_spend": self._mk_kpi(
                    "allocated_spend", "USD", status, source="system.billing.usage", **common
                ),
                "unallocated_spend": self._mk_kpi(
                    "unallocated_spend", "USD", status, source="system.billing.usage", **common
                ),
                "active_rules": self._mk_kpi(
                    "active_rules",
                    "rules",
                    KpiStatus.LIVE,
                    value=float(len(rulebook)),
                    currency=None,
                    source="Allocation engine configuration",
                    **common,
                ),
                "shared_pool": self._mk_kpi(
                    "shared_pool",
                    "USD",
                    KpiStatus.UNAVAILABLE,
                    source="Shared-cost configuration",
                    caveats="No shared-cost pools are configured.",
                    **common,
                ),
            }
            return CostAllocationResponse(
                kpis=kpis,
                spend_by_bu=[],
                allocation_completeness={},
                rulebook=rulebook,
                provenance=prov,
            )
        alloc = self._allocation(rows)
        total = self._sum_cost(rows)
        unalloc = round(alloc.get("Unallocated", {}).get("total", 0.0), 2)
        allocated = round(total - unalloc, 2)
        kpis = {
            "allocated_spend": self._mk_kpi(
                "allocated_spend",
                "USD",
                KpiStatus.CALCULATED,
                value=allocated,
                source="system.billing.usage custom_tags",
                record_count=len(rows),
                **common,
            ),
            "unallocated_spend": self._mk_kpi(
                "unallocated_spend",
                "USD",
                KpiStatus.CALCULATED,
                value=unalloc,
                source="system.billing.usage custom_tags",
                record_count=len(rows),
                **common,
            ),
            "active_rules": self._mk_kpi(
                "active_rules",
                "rules",
                KpiStatus.LIVE,
                value=float(len(rulebook)),
                currency=None,
                source="Allocation engine configuration",
                **common,
            ),
            "shared_pool": self._mk_kpi(
                "shared_pool",
                "USD",
                KpiStatus.UNAVAILABLE,
                source="Shared-cost configuration",
                caveats="No shared-cost pools are configured.",
                **common,
            ),
        }
        tagged = sum(1 for r in rows if self._owner_of(r))
        return CostAllocationResponse(
            kpis=kpis,
            spend_by_bu=[
                {
                    "business_unit": owner,
                    "spend": round(b["total"], 2),
                    "share": round(b["total"] / total, 4) if total else 0.0,
                    "dimension": "custom_tags.owner",
                }
                for owner, b in sorted(alloc.items(), key=lambda kv: -kv[1]["total"])
            ],
            allocation_completeness={
                "tagged_records": tagged,
                "untagged_records": len(rows) - tagged,
                "allocated_pct": round(tagged / len(rows) * 100) if rows else 0,
            },
            rulebook=rulebook,
            provenance=prov,
        )

    @_unknown_scope_guard
    def get_showback_chargeback(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> ShowbackChargebackResponse:
        ws = self._primary_workspace(workspace_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)
        prov = {"statements": self._billing_provenance(rows, connection_id)}
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        unavailable_shared = self._mk_kpi(
            "shared_pool",
            "USD",
            KpiStatus.UNAVAILABLE,
            source="Shared-cost configuration",
            caveats="No shared-cost pools are configured; nothing is distributed artificially.",
            **common,
        )
        disputed = self._mk_kpi(
            "disputed_allocations",
            "count",
            KpiStatus.UNAVAILABLE,
            currency=None,
            source="Dispute workflow",
            caveats="No dispute workflow data source exists.",
            **common,
        )
        if not rows:
            status = KpiStatus.NO_DATA if is_unknown else KpiStatus.BLOCKED_PENDING_APPROVAL
            return ShowbackChargebackResponse(
                kpis={
                    "bu_billed": self._mk_kpi(
                        "bu_billed", "USD", status, source="system.billing.usage", **common
                    ),
                    "shared_pool": unavailable_shared,
                    "disputed_allocations": disputed,
                    "statement_readiness": self._mk_kpi(
                        "statement_readiness",
                        "%",
                        status,
                        currency=None,
                        source="system.billing.usage",
                        **common,
                    ),
                },
                statements=[],
                provenance=prov,
            )
        alloc = self._allocation(rows)
        total = self._sum_cost(rows)
        unalloc = alloc.get("Unallocated", {}).get("total", 0.0)
        statements = [
            ChargebackStatementItem(
                business_unit=owner,
                direct_compute=round(b["compute"], 2),
                ai_tokens=round(b["ai"], 2),
                storage=round(b["storage"], 2) if b["storage"] else None,
                shared_allocation=None,
                total=round(b["total"], 2),
                budget_variance="N/A (no budget configured)",
                trend="N/A",
            )
            for owner, b in sorted(alloc.items(), key=lambda kv: -kv[1]["total"])
        ]
        return ShowbackChargebackResponse(
            kpis={
                "bu_billed": self._mk_kpi(
                    "bu_billed",
                    "USD",
                    KpiStatus.CALCULATED,
                    value=round(total - unalloc, 2),
                    source="system.billing.usage custom_tags",
                    record_count=len(rows),
                    **common,
                ),
                "shared_pool": unavailable_shared,
                "disputed_allocations": disputed,
                "statement_readiness": self._mk_kpi(
                    "statement_readiness",
                    "%",
                    KpiStatus.CALCULATED,
                    value=round((total - unalloc) / total * 100, 1) if total else None,
                    currency=None,
                    source="system.billing.usage custom_tags",
                    formula="attributed spend / total spend",
                    **common,
                ),
            },
            statements=statements,
            provenance=prov,
        )

    # ------------------------------------------------------------------
    # Module 4: Compute & warehouses (live inventory)
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_compute_warehouses(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> ComputeWarehousesResponse:
        ws = self._primary_workspace(workspace_id)
        grouped = self._inventory(connection_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        prov = {
            "inventory": self._inventory_provenance(connection_id, ("cluster", "warehouse", "job")),
            "utilization": SectionProvenance(
                classification=KpiStatus.BLOCKED_PENDING_APPROVAL,
                source="system.compute.node_timeline / warehouse_events",
                message="Utilization and uptime need system.compute tables (SQL on a started warehouse).",
                requirement="Approval to start the SQL warehouse; SELECT on system.compute.*",
                retrieved_at=self._now_iso(),
            ),
        }
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)

        def spend(kind: str, rid: str) -> tuple[float | None, float | None]:
            matched = self._billing_rows(workspace_id, kind, rid) if rows else []
            if not matched:
                return None, None
            return self._sum_cost(matched), self._sum_dbu(matched)

        clusters: list[ClusterInventoryItem] = []
        if not is_unknown and filter_type in (None, "cluster"):
            for c in grouped.get("cluster", []):
                if resource_id and c.id != resource_id:
                    continue
                term = c.metadata.get("autotermination_minutes")
                cost, dbu = spend("cluster", c.id)
                scale = c.metadata.get("autoscale")
                workers = c.metadata.get("num_workers")
                size = (
                    f"autoscale {scale}"
                    if scale
                    else f"{workers} workers"
                    if workers is not None
                    else "workers n/a"
                )
                clusters.append(
                    ClusterInventoryItem(
                        cluster_id=c.id,
                        name=c.name,
                        type=str(c.metadata.get("cluster_source") or "Unknown"),
                        owner=c.creator or "Unknown",
                        node_profile=f"{c.metadata.get('node_type_id') or 'n/a'} - {size}",
                        runtime_hrs=None,
                        cpu_utilization="-",
                        dbu_mtd=dbu,
                        cost_mtd=cost,
                        state=c.status or "UNKNOWN",
                        finding="No auto-termination configured"
                        if not term
                        else f"Auto-termination {term} min",
                    )
                )
        warehouses: list[WarehouseInventoryItem] = []
        if not is_unknown and filter_type in (None, "warehouse"):
            for w in grouped.get("warehouse", []):
                if resource_id and w.id != resource_id:
                    continue
                stop = w.metadata.get("auto_stop_mins")
                cost, _ = spend("warehouse", w.id)
                serverless = w.metadata.get("enable_serverless_compute")
                warehouses.append(
                    WarehouseInventoryItem(
                        warehouse_id=w.id,
                        name=w.name,
                        warehouse_class="Serverless"
                        if serverless
                        else str(w.metadata.get("warehouse_type") or "Classic"),
                        size=str(w.metadata.get("cluster_size") or "n/a"),
                        uptime="-",
                        avg_utilization="-",
                        queue_p95="-",
                        auto_stop_mins=stop,
                        cost_mtd=cost,
                        state=w.status or "UNKNOWN",
                        recommendation="Review auto-stop"
                        if (stop is None or stop > 10)
                        else "No configuration findings",
                    )
                )
        job_runs = grouped.get("job_run", [])
        jobs: list[JobEfficiencyItem] = []
        if not is_unknown and filter_type is None:
            for j in grouped.get("job", []):
                runs = [r for r in job_runs if r.metadata.get("job_id") == j.id]
                finished = [r for r in runs if r.metadata.get("result_state")]
                ok = sum(1 for r in finished if r.metadata.get("result_state") == "SUCCESS")
                durations = [
                    r.metadata["execution_duration_ms"]
                    for r in runs
                    if r.metadata.get("execution_duration_ms")
                ]
                jobs.append(
                    JobEfficiencyItem(
                        job_id=j.id,
                        name=j.name,
                        runs=len(runs),
                        success_rate=f"{ok / len(finished) * 100:.1f}%" if finished else "-",
                        avg_duration=f"{statistics.fmean(durations) / 60000:.1f} min"
                        if durations
                        else "-",
                        signal="Run metrics cover the retrieved run window only",
                    )
                )
        total_units = len(clusters) + len(warehouses)
        running = sum(1 for x in clusters if x.state == "RUNNING") + sum(
            1 for x in warehouses if x.state == "RUNNING"
        )
        comp_rows = [
            r
            for r in rows
            if r.usage_metadata.get("cluster_id") or r.usage_metadata.get("warehouse_id")
        ]
        kpis = {
            "compute_spend": self._mk_kpi(
                "compute_spend",
                "USD",
                KpiStatus.CALCULATED if comp_rows else KpiStatus.BLOCKED_PENDING_APPROVAL,
                value=self._sum_cost(comp_rows) if comp_rows else None,
                source="system.billing.usage x list prices",
                record_count=len(comp_rows),
                caveats=None if comp_rows else "Needs ingested billing rows.",
                **common,
            ),
            "active_compute": self._mk_kpi(
                "active_compute",
                "units",
                KpiStatus.LIVE if grouped else KpiStatus.UNAVAILABLE,
                value=float(running) if grouped else None,
                currency=None,
                formatted=f"{running} of {total_units} running" if grouped else None,
                source="Databricks clusters/warehouses API",
                aggregation="COUNT",
                formula="count(state == RUNNING)",
                record_count=total_units,
                **common,
            ),
            "idle_capacity": self._mk_kpi(
                "idle_capacity",
                "%",
                KpiStatus.BLOCKED_PENDING_APPROVAL,
                currency=None,
                source="system.compute.node_timeline",
                caveats=prov["utilization"].message,
                **common,
            ),
            "potential_savings": self._mk_kpi(
                "potential_savings",
                "USD",
                KpiStatus.UNAVAILABLE,
                source="Optimization Advisor",
                caveats="Savings are not calculable without utilization and billing data.",
                **common,
            ),
        }
        return ComputeWarehousesResponse(
            kpis=kpis,
            clusters=clusters,
            warehouses=warehouses,
            jobs=jobs,
            heatmap_utilization=[],
            provenance=prov,
        )

    # ------------------------------------------------------------------
    # Module 5: AI economics (live endpoint inventory; usage is blocked)
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_ai_economics(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> AiEconomicsResponse:
        ws = self._primary_workspace(workspace_id)
        grouped = self._inventory(connection_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        usage_prov = SectionProvenance(
            classification=KpiStatus.BLOCKED_PENDING_APPROVAL,
            source="system.serving.endpoint_usage / system.ai_gateway.usage",
            message="Token counts, request counts and latency are only exposed through system tables (SQL).",
            requirement="Approval to start the SQL warehouse; SELECT on system.serving / system.ai_gateway tables.",
            retrieved_at=self._now_iso(),
        )
        prov = {
            "endpoints": self._inventory_provenance(connection_id, ("serving_endpoint",)),
            "usage": usage_prov,
        }
        rows = [] if is_unknown else self._billing_rows(workspace_id, "serving", None)
        endpoints: list[ModelServingEndpointItem] = []
        if not is_unknown and filter_type in (None, "serving"):
            for e in grouped.get("serving_endpoint", []):
                if resource_id and e.id != resource_id:
                    continue
                ents = [x for x in (e.metadata.get("served_entities") or []) if isinstance(x, dict)]
                model = (ents[0].get("entity_name") or ents[0].get("name")) if ents else None
                matched = [
                    r
                    for r in rows
                    if e.id
                    in (r.usage_metadata.get("endpoint_id"), r.usage_metadata.get("endpoint_name"))
                ]
                endpoints.append(
                    ModelServingEndpointItem(
                        endpoint_name=e.name,
                        model=str(model or "n/a"),
                        serving_type=str(e.metadata.get("task") or "n/a"),
                        requests_per_day="-",
                        capacity_utilization="-",
                        p95_latency="-",
                        availability=e.status or "UNKNOWN",
                        monthly_cost=self._sum_cost(matched) if matched else None,
                        action="Usage telemetry unavailable",
                    )
                )
        ai_rows = [
            r
            for r in (
                self._billing_rows(workspace_id, filter_type, resource_id) if not is_unknown else []
            )
            if self._is_ai(r)
        ]
        ai_status = KpiStatus.CALCULATED if ai_rows else KpiStatus.BLOCKED_PENDING_APPROVAL

        def blocked(mid: str, unit: str, currency: str | None = None) -> KpiMetric:
            return self._mk_kpi(
                mid,
                unit,
                KpiStatus.BLOCKED_PENDING_APPROVAL,
                currency=currency,
                source=usage_prov.source,
                caveats=usage_prov.message,
                **common,
            )

        training: list[TrainingEvaluationItem] = []
        runs = grouped.get("mlflow_run", [])
        if not is_unknown and filter_type is None:
            for x in grouped.get("mlflow_experiment", []):
                n = sum(1 for r in runs if r.metadata.get("experiment_id") == x.id)
                training.append(
                    TrainingEvaluationItem(
                        experiment_name=x.name,
                        workload="MLflow experiment",
                        compute_hrs="-",
                        runs=n,
                        artifact_storage="-",
                        spend=None,
                        quality_lift="-",
                        decision="Not assessed",
                    )
                )
        kpis = {
            "ai_spend": self._mk_kpi(
                "ai_spend",
                "USD",
                ai_status,
                value=self._sum_cost(ai_rows) if ai_rows else None,
                source="system.billing.usage x list prices",
                record_count=len(ai_rows),
                caveats="DBU compute cost only; token-priced external models are not included.",
                **common,
            ),
            "input_tokens": blocked("input_tokens", "tokens"),
            "output_tokens": blocked("output_tokens", "tokens"),
            "cached_tokens": blocked("cached_tokens", "tokens"),
            "cost_per_1k_tokens": blocked("cost_per_1k_tokens", "USD", "USD"),
            "cost_per_task": self._mk_kpi(
                "cost_per_task",
                "USD",
                KpiStatus.UNAVAILABLE,
                source="Agent evaluation telemetry",
                caveats="No task/outcome telemetry source is connected.",
                **common,
            ),
        }
        return AiEconomicsResponse(
            kpis=kpis,
            token_consumption_by_model=[],
            token_cost_drivers=[],
            model_economics=[],
            serving_endpoints=endpoints,
            genie_scorecard=[],
            agents=[],
            training=training,
            unit_economics=[],
            provenance=prov,
        )

    # ------------------------------------------------------------------
    # Module 6: Data & storage (Unity Catalog metadata only)
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_data_storage(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> DataStorageResponse:
        ws = self._primary_workspace(workspace_id)
        grouped = self._inventory(connection_id)
        _, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        size_prov = SectionProvenance(
            classification=KpiStatus.BLOCKED_PENDING_APPROVAL,
            source="DESCRIBE DETAIL / system.information_schema / Azure Storage metrics",
            message="Unity Catalog REST metadata does not report table size, growth or last access.",
            requirement="Approval to run read-only SQL on a started warehouse, or Azure Monitor Reader on the storage account.",
            retrieved_at=self._now_iso(),
        )
        prov = {
            "catalogs": self._inventory_provenance(connection_id, ("catalog",)),
            "storage_metrics": size_prov,
        }
        tables: list[StorageInventoryItem] = []
        cache = self.workspace_service._uc_cache.get(connection_id)
        if not is_unknown:
            if cache and cache.catalogs:
                for cat in cache.catalogs:
                    for sch in cat.schemas:
                        for t in sch.tables:
                            tables.append(
                                StorageInventoryItem(
                                    catalog_schema_table=t.full_name,
                                    storage_type=f"{t.table_type or 'n/a'} / {t.data_source_format or 'n/a'}",
                                    size="-",
                                    last_read="-",
                                    retention="-",
                                    growth_month="-",
                                    monthly_cost=None,
                                    recommendation="Size telemetry unavailable",
                                )
                            )
                tables = tables[:500]  # response cap; full counts are in provenance
                prov["tables"] = SectionProvenance(
                    classification=KpiStatus.LIVE,
                    source="Unity Catalog REST API",
                    message=f"{cache.total_catalogs} catalogs, {cache.total_schemas} schemas, {cache.total_tables} tables discovered.",
                    retrieved_at=cache.retrieved_at.isoformat(),
                    record_count=cache.total_tables,
                )
            else:
                for cat_res in grouped.get("catalog", []):
                    tables.append(
                        StorageInventoryItem(
                            catalog_schema_table=cat_res.name,
                            storage_type=f"Catalog ({cat_res.metadata.get('catalog_type') or 'n/a'})",
                            size="-",
                            last_read="-",
                            retention="-",
                            growth_month="-",
                            monthly_cost=None,
                            recommendation="Size telemetry unavailable",
                        )
                    )

        def blocked(mid: str, unit: str, currency: str | None = None) -> KpiMetric:
            return self._mk_kpi(
                mid,
                unit,
                KpiStatus.BLOCKED_PENDING_APPROVAL,
                currency=currency,
                source=size_prov.source,
                caveats=size_prov.message,
                **common,
            )

        return DataStorageResponse(
            kpis={
                "storage_spend": self._mk_kpi(
                    "storage_spend",
                    "USD",
                    KpiStatus.UNAVAILABLE,
                    source="Azure Cost Management",
                    caveats="Storage charges are Azure resources, not in system.billing.usage.",
                    **common,
                ),
                "total_stored_data": blocked("total_stored_data", "TB"),
                "cold_data": blocked("cold_data", "%"),
                "ingestion_spend": blocked("ingestion_spend", "USD", "USD"),
            },
            storage_tiers=[],
            lifecycle_opportunities=[],
            tables=tables,
            provenance=prov,
        )

    # ------------------------------------------------------------------
    # Module 7: Network & cloud economics
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_network_cloud(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> NetworkCloudResponse:
        _ = connection_id
        ws = self._primary_workspace(workspace_id)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        reason = SectionProvenance(
            classification=KpiStatus.NOT_AUTHORIZED,
            source="Azure Cost Management / Azure Resource Graph",
            message="Databricks exposes no network cost telemetry; this needs read-only Azure access.",
            requirement="Azure Reader and Cost Management Reader on the workspace subscription / resource group.",
            retrieved_at=self._now_iso(),
        )

        def kpi(mid: str, unit: str, currency: str | None = None) -> KpiMetric:
            # Needs Azure read access (not SQL): report it as a permission requirement.
            return self._mk_kpi(
                mid,
                unit,
                KpiStatus.NOT_AUTHORIZED,
                currency=currency,
                source=reason.source,
                caveats=f"{reason.message} Required: {reason.requirement}",
                **common,
            )

        return NetworkCloudResponse(
            kpis={
                "network_infra_spend": kpi("network_infra_spend", "USD", "USD"),
                "data_egress": kpi("data_egress", "GB"),
                "private_endpoints": kpi("private_endpoints", "count"),
                "unmapped_resources": kpi("unmapped_resources", "count"),
            },
            components=[],
            provenance={"azure": reason},
        )

    # ------------------------------------------------------------------
    # Module 8: Optimization advisor
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_optimization_advisor(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> OptimizationAdvisorResponse:
        ws = self._primary_workspace(workspace_id)
        recs = self._get_decisions(resource_id, resource_type)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        savings = self.get_decision_savings(recs)
        approved = [d for d in recs if d.status == "Approved"]
        approved_savings = self.get_decision_savings(approved)
        savings_status = KpiStatus.CALCULATED if savings is not None else KpiStatus.UNAVAILABLE
        note = "Savings are only reported when calculable from usage and billing telemetry."
        kpis = {
            "potential_savings": self._mk_kpi(
                "potential_savings",
                "USD",
                savings_status,
                value=savings,
                source="Optimization Advisor",
                caveats=note,
                **common,
            ),
            "estimated_savings": self._mk_kpi(
                "estimated_savings",
                "USD",
                savings_status,
                value=savings,
                source="Optimization Advisor",
                caveats=note,
                **common,
            ),
            "approved_savings": self._mk_kpi(
                "approved_savings",
                "USD",
                KpiStatus.CALCULATED if approved_savings is not None else KpiStatus.UNAVAILABLE,
                value=approved_savings,
                source="Optimization Advisor",
                caveats=note,
                **common,
            ),
            "quick_wins": self._mk_kpi(
                "quick_wins",
                "count",
                KpiStatus.CALCULATED,
                value=float(len(recs)),
                currency=None,
                source="Optimization Advisor",
                formula="count(configuration findings)",
                **common,
            ),
            "awaiting_approval": self._mk_kpi(
                "awaiting_approval",
                "count",
                KpiStatus.CALCULATED,
                value=float(sum(1 for d in recs if d.status == "Approval required")),
                currency=None,
                source="Optimization Advisor",
                **common,
            ),
            "implemented_savings": self._mk_kpi(
                "implemented_savings",
                "USD",
                KpiStatus.UNAVAILABLE,
                source="Post-change billing audit",
                caveats="No change has been verified against post-change billing.",
                **common,
            ),
            "realized_savings": self._mk_kpi(
                "realized_savings",
                "USD",
                KpiStatus.UNAVAILABLE,
                source="Post-change billing audit",
                caveats="Realized savings require a verified before/after billing comparison.",
                **common,
            ),
        }
        return OptimizationAdvisorResponse(
            kpis=kpis,
            recommendations=recs,
            provenance={
                "recommendations": self._inventory_provenance(
                    connection_id, ("cluster", "warehouse", "serving_endpoint")
                )
            },
        )

    # ------------------------------------------------------------------
    # Module 9: Forecast & budgets
    # ------------------------------------------------------------------

    def simulate_forecast_scenario(
        self, req: ScenarioSimulationRequest
    ) -> ScenarioSimulationResponse:
        """Scenario on the real run-rate forecast; unavailable without enough history."""
        rows = self._billing_rows(None, None, None)
        fc = self._forecast(rows) if rows else None
        if not fc:
            return ScenarioSimulationResponse(
                formatted_spend="-",
                delta_label=f"Needs >= {self._MIN_HISTORY_DAYS} days of ingested billing history.",
                status=KpiStatus.INSUFFICIENT_HISTORY,
                message="No baseline forecast exists, so no scenario is computed.",
            )
        base = float(fc["forecast"])
        ai = self._sum_cost(
            [r for r in rows if self._is_ai(r) and r.usage_date.startswith(fc["month"])]
        )
        compute = max(0.0, base - ai)
        adjusted = (
            base * (1 + req.growth_pct / 100)
            - compute * req.compute_save_pct / 100
            - ai * req.token_save_pct / 100
        )
        budget = self._budget()
        return ScenarioSimulationResponse(
            baseline_spend=round(base, 2),
            adjusted_spend=round(adjusted, 2),
            formatted_spend=self._money(adjusted),
            savings_vs_baseline=round(base - adjusted, 2),
            delta_label=f"{(adjusted - base) / base * 100:+.1f}% vs baseline forecast"
            if base
            else "n/a",
            is_favorable=adjusted <= base,
            budget_variance=round(budget - adjusted, 2) if budget is not None else None,
            status=KpiStatus.ESTIMATED,
            message="Scenario assumptions applied to a run-rate projection; not actual spend.",
        )

    @_unknown_scope_guard
    def get_forecast_budgets(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> ForecastBudgetsResponse:
        ws = self._primary_workspace(workspace_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        fc = self._forecast(rows) if rows else None
        budget = self._budget()
        prov = {"history": self._billing_provenance(rows, connection_id)}
        hist_status = KpiStatus.INSUFFICIENT_HISTORY if rows else KpiStatus.BLOCKED_PENDING_APPROVAL
        no_hist = f"Needs >= {self._MIN_HISTORY_DAYS} days of ingested billing history."
        mtd = (
            fc["mtd"] if fc else (self._sum_cost(self._reference_month(rows)[1]) if rows else None)
        )
        # The budget setting is USD: it is only comparable with USD-confirmed actuals.
        scope_ccy = self._scope_currency()
        budget_comparable = (not rows) or scope_ccy.code == "USD"
        util = (
            round(mtd / budget * 100, 1)
            if (mtd is not None and budget and budget_comparable)
            else None
        )
        overrun = (
            round(max(0.0, fc["forecast"] - budget), 2)
            if (fc and budget is not None and budget_comparable)
            else None
        )
        kpis = {
            "approved_budget": self._mk_kpi(
                "approved_budget",
                "USD",
                KpiStatus.LIVE if budget is not None else KpiStatus.UNAVAILABLE,
                value=budget,
                formatted=None if budget is not None else "No budget configured",
                source="FINOPS_MONTHLY_BUDGET_USD setting",
                confirmed_currency="USD",  # the setting is explicitly denominated in USD
                caveats=None
                if budget is not None
                else "Set finops_monthly_budget_usd to enable budget tracking.",
                **common,
            ),
            "actual_mtd": self._mk_kpi(
                "actual_mtd",
                "USD",
                KpiStatus.CALCULATED if mtd is not None else hist_status,
                value=mtd,
                source="system.billing.usage x list prices",
                caveats="Actual (list-price basis).",
                **common,
            ),
            "forecast_month_end": self._mk_kpi(
                "forecast_month_end",
                "USD",
                KpiStatus.ESTIMATED if fc else hist_status,
                value=fc["forecast"] if fc else None,
                source="Run-rate projection",
                formula="MTD + trailing-7-day average x remaining days",
                caveats="Forecast, not actual." if fc else no_hist,
                **common,
            ),
            "forecast_confidence": self._mk_kpi(
                "forecast_confidence",
                "%",
                KpiStatus.UNAVAILABLE,
                currency=None,
                source="Forecast backtest",
                caveats="No confidence interval is computed for the run-rate method.",
                **common,
            ),
            "forecast_accuracy": self._mk_kpi(
                "forecast_accuracy",
                "%",
                KpiStatus.INSUFFICIENT_HISTORY,
                currency=None,
                source="Forecast backtest",
                caveats="Requires >= 3 completed forecast cycles.",
                **common,
            ),
            "budget_utilization": self._mk_kpi(
                "budget_utilization",
                "%",
                KpiStatus.CALCULATED if util is not None else KpiStatus.UNAVAILABLE,
                value=util,
                currency=None,
                source="Budget vs actual",
                caveats=None if budget else "No budget configured.",
                **common,
            ),
            "projected_overrun": self._mk_kpi(
                "projected_overrun",
                "USD",
                KpiStatus.ESTIMATED if overrun is not None else KpiStatus.UNAVAILABLE,
                value=overrun,
                source="Forecast vs budget",
                caveats="Requires both a forecast and a configured budget.",
                **common,
            ),
        }
        controls: list[BudgetControlItem] = []
        burn: list[dict[str, Any]] = []
        if budget is not None and not is_unknown and budget_comparable:
            controls.append(
                BudgetControlItem(
                    budget_scope="Databricks workspace (monthly)",
                    owner="Configured",
                    budget=budget,
                    actual=mtd,
                    forecast=fc["forecast"] if fc else None,
                    threshold="n/a",
                    burn_pct=int(util) if util is not None else None,
                    status="Forecast breach"
                    if (overrun or 0) > 0
                    else "On track"
                    if mtd is not None
                    else "No actuals",
                )
            )
            if rows:
                cum = 0.0
                for d, (c, _q) in self._daily_totals(self._reference_month(rows)[1]).items():
                    cum += c
                    burn.append(
                        {"day": self._label_date(d), "actual": round(cum, 2), "budget": budget}
                    )
        return ForecastBudgetsResponse(
            kpis=kpis,
            budget_burn=burn,
            budget_controls=controls,
            default_scenario=self.simulate_forecast_scenario(ScenarioSimulationRequest()),
            provenance=prov,
        )

    # ------------------------------------------------------------------
    # Module 10: Anomaly detection
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_anomaly_detection(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> AnomalyDetectionResponse:
        ws = self._primary_workspace(workspace_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        found = self._detect_anomalies(rows) if rows else None
        prov = {"history": self._billing_provenance(rows, connection_id)}
        if found is None:
            status = KpiStatus.INSUFFICIENT_HISTORY if rows else KpiStatus.BLOCKED_PENDING_APPROVAL
            prov["detection"] = SectionProvenance(
                classification=status,
                source="system.billing.usage",
                message=f"Anomaly detection needs >= {self._MIN_HISTORY_DAYS} days of ingested billing history.",
                retrieved_at=self._now_iso(),
            )
            kpi_open = self._mk_kpi(
                "open_anomalies",
                "count",
                status,
                currency=None,
                source="system.billing.usage",
                **common,
            )
            kpi_exp = self._mk_kpi(
                "potential_exposure", "USD", status, source="system.billing.usage", **common
            )
            found = []
        else:
            open_items = [a for a in found if a.status not in ("Resolved", "False positive")]
            exposure = sum(
                float(a.estimated_impact.split()[0].replace("$", "").replace(",", ""))
                for a in open_items
            )
            kpi_open = self._mk_kpi(
                "open_anomalies",
                "count",
                KpiStatus.CALCULATED,
                value=float(len(open_items)),
                currency=None,
                source="system.billing.usage",
                **common,
            )
            kpi_exp = self._mk_kpi(
                "potential_exposure",
                "USD",
                KpiStatus.CALCULATED,
                value=round(exposure, 2),
                source="system.billing.usage x list prices",
                **common,
            )
        return AnomalyDetectionResponse(
            kpis={
                "open_anomalies": kpi_open,
                "potential_exposure": kpi_exp,
                "mean_time_to_detect": self._mk_kpi(
                    "mean_time_to_detect",
                    "hours",
                    KpiStatus.UNAVAILABLE,
                    currency=None,
                    source="Detection latency telemetry",
                    caveats="Not measured.",
                    **common,
                ),
                "auto_triaged": self._mk_kpi(
                    "auto_triaged",
                    "%",
                    KpiStatus.UNAVAILABLE,
                    currency=None,
                    source="Triage workflow",
                    caveats="No automated triage exists.",
                    **common,
                ),
            },
            anomalies=found,
            provenance=prov,
        )

    # ------------------------------------------------------------------
    # Module 13: Workload economics
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_workload_economics(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> WorkloadEconomicsResponse:
        ws = self._primary_workspace(workspace_id)
        grouped = self._inventory(connection_id)
        filter_type, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        rows = [] if is_unknown else self._billing_rows(workspace_id, filter_type, resource_id)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        names: dict[str, str] = {
            r.id: r.name
            for t in ("job", "warehouse", "cluster", "serving_endpoint", "app", "pipeline")
            for r in grouped.get(t, [])
        }
        spend: dict[tuple[str, str], list[BillingUsageRecord]] = {}
        for r in rows:
            key = self._resource_of(r)
            if key:
                spend.setdefault(key, []).append(r)
        workloads: list[WorkloadUnitEconomicsItem] = []
        seen: set[str] = set()
        for (rtype, rid), recs in sorted(spend.items(), key=lambda kv: -self._sum_cost(kv[1])):
            seen.add(rid)
            workloads.append(
                WorkloadUnitEconomicsItem(
                    workload=names.get(rid, rid),
                    workload_type=rtype,
                    owner=next((o for o in (self._owner_of(r) for r in recs) if o), "Unassigned"),
                    monthly_spend=self._sum_cost(recs),
                    volume="-",
                    unit_cost="-",
                    sla_quality="-",
                    business_outcome="-",
                    efficiency_trend="-",
                )
            )
        if not is_unknown and filter_type is None:
            for t, label in (("job", "job"), ("pipeline", "pipeline")):
                for item in grouped.get(t, []):
                    if item.id not in seen:
                        workloads.append(
                            WorkloadUnitEconomicsItem(
                                workload=item.name,
                                workload_type=label,
                                owner=item.creator or "Unassigned",
                                monthly_spend=None,
                                volume="-",
                                unit_cost="-",
                                sla_quality="-",
                                business_outcome="-",
                                efficiency_trend="-",
                            )
                        )
        costed = [w for w in workloads if w.monthly_spend is not None]
        status = (
            KpiStatus.CALCULATED
            if costed
            else (KpiStatus.NO_DATA if is_unknown else KpiStatus.BLOCKED_PENDING_APPROVAL)
        )
        avg = round(sum(w.monthly_spend or 0 for w in costed) / len(costed), 2) if costed else None
        return WorkloadEconomicsResponse(
            kpis={
                "tracked_workloads": self._mk_kpi(
                    "tracked_workloads",
                    "count",
                    KpiStatus.LIVE if grouped else KpiStatus.UNAVAILABLE,
                    value=float(len(workloads)) if grouped or workloads else None,
                    currency=None,
                    source="Jobs / pipelines API + system.billing.usage",
                    **common,
                ),
                "unit_metrics_coverage": self._mk_kpi(
                    "unit_metrics_coverage",
                    "%",
                    KpiStatus.UNAVAILABLE,
                    currency=None,
                    source="Business volume metrics",
                    caveats="No business volume metric source is connected.",
                    **common,
                ),
                "avg_cost_workload": self._mk_kpi(
                    "avg_cost_workload",
                    "USD",
                    status,
                    value=avg,
                    source="system.billing.usage x list prices",
                    **common,
                ),
                "value_positive": self._mk_kpi(
                    "value_positive",
                    "count",
                    KpiStatus.UNAVAILABLE,
                    currency=None,
                    source="Business outcome metrics",
                    caveats="No outcome/value data is connected.",
                    **common,
                ),
            },
            workloads=workloads,
            provenance={"spend": self._billing_provenance(rows, connection_id)},
        )

    # ------------------------------------------------------------------
    # Module 11: Governance (from live cluster policies and configuration)
    # ------------------------------------------------------------------

    @_unknown_scope_guard
    def get_governance_policies(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> GovernancePoliciesResponse:
        ws = self._primary_workspace(workspace_id)
        grouped = self._inventory(connection_id)
        _, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        common: dict[str, Any] = {
            "workspace_id": ws,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        policies = [
            PolicyCatalogueItem(
                policy_name=p.name,
                scope="Compute (cluster policy)",
                control="Cluster policy definition",
                enforcement="Cluster policy",
                owner=p.creator or "Unknown",
                exceptions=None,
                status="Active",
            )
            for p in ([] if is_unknown else grouped.get("cluster_policy", []))
        ]
        owned = [
            r
            for t in ("cluster", "warehouse", "serving_endpoint", "app")
            for r in grouped.get(t, [])
        ]
        no_owner = sum(1 for r in owned if not r.creator)
        clusters = grouped.get("cluster", [])
        warehouses = grouped.get("warehouse", [])
        checklist = [
            {
                "label": "Cluster policies are defined",
                "checked": bool(grouped.get("cluster_policy")),
            },
            {
                "label": "All clusters have auto-termination configured",
                "checked": bool(clusters)
                and all(c.metadata.get("autotermination_minutes") for c in clusters),
            },
            {
                "label": "All SQL warehouses auto-stop within 10 minutes",
                "checked": bool(warehouses)
                and all(0 < (w.metadata.get("auto_stop_mins") or 0) <= 10 for w in warehouses),
            },
            {
                "label": "All discovered resources have a creator/owner",
                "checked": bool(owned) and no_owner == 0,
            },
        ]
        live = KpiStatus.LIVE if grouped else KpiStatus.UNAVAILABLE
        return GovernancePoliciesResponse(
            kpis={
                "policy_compliance": self._mk_kpi(
                    "policy_compliance",
                    "%",
                    KpiStatus.UNAVAILABLE,
                    currency=None,
                    source="Policy compliance scanner",
                    caveats="No compliance scanner data source exists.",
                    **common,
                ),
                "policy_violations": self._mk_kpi(
                    "policy_violations",
                    "violations",
                    KpiStatus.UNAVAILABLE,
                    currency=None,
                    source="Policy compliance scanner",
                    caveats="No violation data source exists.",
                    **common,
                ),
                "resources_without_owner": self._mk_kpi(
                    "resources_without_owner",
                    "resources",
                    live,
                    value=float(no_owner) if grouped else None,
                    currency=None,
                    source="Databricks resource APIs (creator field)",
                    formula="count(resources WHERE creator IS NULL)",
                    record_count=len(owned),
                    **common,
                ),
                "expiring_exceptions": self._mk_kpi(
                    "expiring_exceptions",
                    "exceptions",
                    KpiStatus.UNAVAILABLE,
                    currency=None,
                    source="Exception registry",
                    caveats="No exception registry exists.",
                    **common,
                ),
            },
            policies=policies,
            checklist=checklist,
            workflow_steps=[
                "1. Recommendation generated with evidence and estimated savings.",
                "2. Technical owner validates performance, reliability and security impact.",
                "3. Budget owner approves financial impact and implementation window.",
                "4. Change is executed through an approved deployment mechanism (outside this platform).",
                "5. Actual savings and service-level impact are measured and audited.",
            ],
            provenance={"policies": self._inventory_provenance(connection_id, ("cluster_policy",))},
        )

    # ------------------------------------------------------------------
    # Module 14: Reports & audit
    # ------------------------------------------------------------------

    def get_reports_audit(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> ReportsAuditResponse:
        """Report catalogue plus audit events recorded by this process (no seeded history)."""
        self.validate_scope(workspace_id)
        _ = connection_id
        _, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        if is_unknown:
            return ReportsAuditResponse(report_packs=[], audit_events=[])
        packs = [
            ReportPackItem(
                report_id="rep-exec",
                title="Executive FinOps Pack",
                subtitle="Spend, forecast, savings and decisions (needs billing ingestion).",
                format="CSV",
            ),
            ReportPackItem(
                report_id="rep-opt",
                title="Optimization Findings",
                subtitle="Configuration findings with evidence and approval state.",
                format="CSV",
            ),
            ReportPackItem(
                report_id="rep-alloc",
                title="Allocation & Chargeback",
                subtitle="Tag-based attribution with explicit unallocated spend.",
                format="CSV",
            ),
            ReportPackItem(
                report_id="rep-gov",
                title="Policy Compliance",
                subtitle="Cluster policies and configuration checks.",
                format="CSV",
            ),
        ]
        return ReportsAuditResponse(report_packs=packs, audit_events=self._audit_events)

    # ------------------------------------------------------------------
    # Module 15: Settings & integrations
    # ------------------------------------------------------------------

    def get_settings_integrations(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> SettingsIntegrationsResponse:
        self.validate_scope(workspace_id)
        _, is_unknown = self._resolve_resource_filter(resource_id, resource_type)
        if is_unknown:
            return SettingsIntegrationsResponse(
                connected_sources=[], pipeline_health=[], rate_cards=[], system_tables_readiness={}
            )
        discovery = self.workspace_service._discovery_cache.get(connection_id)
        usage = self.billing_service._usage_store
        wh_state = self._warehouse_state(connection_id)
        sources = [
            ConnectedSourceItem(
                source_name="Databricks Workspace APIs",
                status="Connected" if discovery else "Needs validation",
                last_verified=discovery.discovered_at.isoformat() if discovery else "Never",
                details=f"{discovery.total_resources_count} resources discovered."
                if discovery
                else "Discovery has not run.",
            ),
            ConnectedSourceItem(
                source_name="Databricks System Tables (SQL)",
                status="Connected" if usage else "Blocked - approval required",
                last_verified="Never",
                details=f"{len(usage)} usage rows ingested; SQL warehouse state: {wh_state}.",
            ),
            ConnectedSourceItem(
                source_name="Azure Cost Management",
                status="Unconfigured",
                last_verified="Never",
                details="Requires Cost Management Reader on the subscription.",
            ),
            ConnectedSourceItem(
                source_name="Identity & Cost-Center Map",
                status="Unconfigured",
                last_verified="Never",
                details="No mapping source is configured; spend is attributed from billing tags only.",
            ),
        ]
        last_run = (
            self.billing_service._runs_store[-1] if self.billing_service._runs_store else None
        )
        unmatched = sum(
            1 for r in usage.values() if r.usage_unit == "DBU" and not r.pricing_matched
        )
        untagged = sum(1 for r in usage.values() if not self._owner_of(r))
        pipeline_health = [
            PipelineHealthMetric(metric_name="Billing Rows Ingested", metric_value=str(len(usage))),
            PipelineHealthMetric(
                metric_name="Last Ingestion Run",
                metric_value=f"{last_run.status} at {last_run.completed_at}"
                if last_run
                else "No run yet",
            ),
            PipelineHealthMetric(
                metric_name="Unmatched SKU Records",
                metric_value=str(unmatched) if usage else "-",
            ),
            PipelineHealthMetric(
                metric_name="Missing Owner Tag Ratio",
                metric_value=f"{untagged / len(usage) * 100:.1f}%" if usage else "-",
            ),
        ]
        rate_cards = [
            RateCardItem(
                provider="Databricks",
                sku_family=p.sku_name,
                region=p.cloud,
                list_rate=(
                    "-"
                    if p.price_per_unit is None
                    else f"{format_money(p.price_per_unit, p.currency_code, 5)} / {p.usage_unit}"
                ),
                contract_rate="Not configured",
                discount="N/A",
                effective_date=p.price_start_time[:10],
                source="Built-in rate card (replaced by system.billing.list_prices on ingestion)",
            )
            for p in self.billing_service._price_store
        ]
        st = self.workspace_service._system_tables_cache.get(connection_id)
        readiness: dict[str, Any] = {
            "catalog": "system",
            "schemas_verified": st.discovered_schemas if st else [],
            "key_tables": [
                {
                    "name": t.full_name,
                    "columns_count": t.columns_count,
                    "status": t.metadata_status.value,
                    "select_grant_verified": t.select_grant_verified,
                }
                for t in (st.tables if st else [])
                if t.full_name
                in (
                    "system.billing.usage",
                    "system.billing.list_prices",
                    "system.compute.clusters",
                    "system.compute.warehouses",
                    "system.query.history",
                )
            ],
            "sql_execution_state": wh_state,
            "sql_execution_note": "No SQL is executed without explicit approval; the warehouse is never auto-started.",
        }
        return SettingsIntegrationsResponse(
            connected_sources=sources,
            pipeline_health=pipeline_health,
            rate_cards=rate_cards,
            system_tables_readiness=readiness,
        )

    # ------------------------------------------------------------------
    # Module 12: Query history (Databricks Query History REST API)
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_state(state: Any) -> KpiStatus:
        name = str(getattr(state, "value", state))
        return {
            "LIVE": KpiStatus.LIVE,
            "NO_DATA": KpiStatus.NO_DATA,
            "ACCESS_DENIED": KpiStatus.NOT_AUTHORIZED,
            "AUTH_FAILED": KpiStatus.NOT_AUTHORIZED,
            "PARTIAL": KpiStatus.PARTIAL,
        }.get(name, KpiStatus.UNAVAILABLE)

    async def get_query_history(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
        warehouse_id: str | None = None,
        user: str | None = None,
        status: str | None = None,
        limit: int = 50,
        page_token: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> QueryHistoryResponse:
        """Live, paginated query history. No SQL is executed and no compute is started."""
        self.validate_scope(workspace_id)
        live = await self.workspace_service.get_query_history(
            connection_id=connection_id,
            warehouse_id=warehouse_id,
            status_filter=status,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            max_results=limit,
            page_token=page_token,
        )
        wh_names = {w.id: w.name for w in self._inventory(connection_id).get("warehouse", [])}
        records: list[QueryHistoryRecordItem] = []
        for q in live.records:
            if user and user.lower() not in (q.executed_by_masked or "").lower():
                continue
            records.append(
                QueryHistoryRecordItem(
                    query_id=q.query_id,
                    start_time=q.start_time or "",
                    end_time=q.end_time,
                    duration_ms=q.duration_ms or 0.0,
                    duration_formatted=(
                        f"{q.duration_ms / 1000:.2f}s"
                        if q.duration_ms and q.duration_ms >= 1000
                        else f"{q.duration_ms:.0f}ms"
                        if q.duration_ms is not None
                        else "n/a"
                    ),
                    status=q.status,
                    warehouse_id=q.warehouse_id or "",
                    warehouse_name=wh_names.get(q.warehouse_id or "", ""),
                    rows_produced=q.rows_produced,
                    bytes_read=q.read_bytes,
                    bytes_written=None,
                    user=q.executed_by_masked or "unknown",
                    sql_statement=q.sql_summary,
                    query_type=q.statement_type or "UNKNOWN",
                    error_message=q.error_message,
                )
            )
        buckets = [
            ("< 1s", 0, 1000),
            ("1s - 5s", 1000, 5000),
            ("5s - 15s", 5000, 15000),
            ("15s - 60s", 15000, 60000),
            ("> 60s", 60000, float("inf")),
        ]
        n = len(records)
        histogram = []
        for label, lo, hi in buckets:
            c = sum(1 for r in records if lo <= r.duration_ms < hi)
            histogram.append(
                {"bucket": label, "count": c, "percentage": round(c / n * 100, 1) if n else 0.0}
            )
        palette = {
            "FINISHED": "#10b981",
            "FAILED": "#ef4444",
            "CANCELED": "#f59e0b",
            "CANCELLED": "#f59e0b",
        }
        statuses: dict[str, int] = {}
        for r in records:
            statuses[r.status] = statuses.get(r.status, 0) + 1
        distribution = [
            {
                "status": s,
                "count": c,
                "percentage": round(c / n * 100, 1),
                "color": palette.get(s, "#94a3b8"),
            }
            for s, c in sorted(statuses.items(), key=lambda kv: -kv[1])
        ]
        per_day: dict[str, list[float]] = {}
        for r in records:
            per_day.setdefault(r.start_time[:10], []).append(r.duration_ms)
        daily = [
            {"date": d, "queries": len(v), "avg_duration_ms": round(statistics.fmean(v), 1)}
            for d, v in sorted(per_day.items())
        ]
        state_cls = self._classify_state(live.discovery_state)
        return QueryHistoryResponse(
            records=records,
            total_count=len(records),
            duration_histogram=histogram,
            status_distribution=distribution,
            daily_volume=daily,
            active_filters={
                "warehouse_id": warehouse_id,
                "user": user,
                "status": status,
                "limit": limit,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
            },
            has_next_page=live.has_next_page,
            next_page_token=live.next_page_token,
            provenance=SectionProvenance(
                classification=state_cls,
                source=live.source_api,
                message=live.error_message
                or "Aggregates cover the returned page only. Users are masked by the source layer.",
                retrieved_at=live.retrieved_at.isoformat(),
                record_count=len(records),
            ),
        )

    # ------------------------------------------------------------------
    # System tables explorer (metadata only; no rows are read)
    # ------------------------------------------------------------------

    def get_system_tables(
        self,
        connection_id: str = "databricks-azure-dev",
        workspace_id: str | None = None,
    ) -> SystemTablesExplorerResponse:
        """System table metadata from the live Unity Catalog API. Row access is a separate state."""
        self.validate_scope(workspace_id)
        wh_state = self._warehouse_state(connection_id)
        st = self.workspace_service._system_tables_cache.get(connection_id)
        if st is None:
            return SystemTablesExplorerResponse(
                tables=[],
                catalog_status="UNAVAILABLE",
                warehouse_state=wh_state,
                governance_model="Unity Catalog System Schema (metadata not yet discovered)",
            )
        tables: list[SystemTableProbeItem] = []
        for t in st.tables:
            if t.select_grant_verified is False:
                status = "PERMISSION_DENIED"
            elif wh_state != "RUNNING":
                status = "STOPPED_WAREHOUSE" if t.table_discovered else "SCHEMA_VERIFIED"
            else:
                status = "QUERY_ACCESSIBLE"
            tables.append(
                SystemTableProbeItem(
                    table_name=t.full_name,
                    catalog="system",
                    schema_name=t.schema_name,
                    description=t.comment or t.domain or "",
                    status=status,
                    columns_count=t.columns_count,
                    columns=[
                        {"name": c.name, "type": c.type_text or "", "comment": c.comment or ""}
                        for c in t.columns
                    ],
                    row_count=None,
                    latest_record_time=None,
                    query_duration_ms=None,
                    notes=(
                        f"Metadata discovered via Unity Catalog API; SELECT grant verified: {t.select_grant_verified}. "
                        "Row-level access has not been exercised (no SQL executed)."
                    ),
                    sample_records=[],
                )
            )
        return SystemTablesExplorerResponse(
            tables=tables,
            catalog_status="METADATA_DISCOVERED",
            warehouse_state=wh_state,
            governance_model="Unity Catalog System Schema",
        )

    def get_module_ai_analysis(
        self,
        module_id: str,
        workspace_id: str = "642006393507276",
        resource_id: str | None = None,
        resource_type: str | None = None,
        connection_id: str = "databricks-azure-dev",
    ) -> FinOpsAiAnalysis:
        """Deterministic, evidence-grounded summary built only from the module's own live response.

        No numbers are authored here: every statement is derived from KPI values, statuses
        and provenance returned by the module getter.
        """
        self.validate_scope(workspace_id)
        mod = module_id.lower().strip()
        aliases = {
            "overview": "get_executive_overview",
            "cost_explorer": "get_cost_explorer",
            "cost_allocation": "get_cost_allocation",
            "compute_warehouses": "get_compute_warehouses",
            "compute": "get_compute_warehouses",
            "ai_economics": "get_ai_economics",
            "ai": "get_ai_economics",
            "data_storage": "get_data_storage",
            "network_cloud": "get_network_cloud",
            "optimization_advisor": "get_optimization_advisor",
            "optimization": "get_optimization_advisor",
            "forecast_budgets": "get_forecast_budgets",
            "anomaly_detection": "get_anomaly_detection",
            "anomalies": "get_anomaly_detection",
            "governance_policies": "get_governance_policies",
            "showback_chargeback": "get_showback_chargeback",
            "workload_economics": "get_workload_economics",
        }
        findings: list[str] = []
        warnings: list[str] = []
        opportunities: list[FinOpsAiOpportunity] = []
        refs: list[str] = []
        getter = aliases.get(mod)
        if getter:
            resp = getattr(self, getter)(
                connection_id=connection_id,
                workspace_id=workspace_id,
                resource_id=resource_id,
                resource_type=resource_type,
            )
            for kpi in getattr(resp, "kpis", {}).values():
                findings.append(f"{kpi.metric_id}: {kpi.formatted_value} [{kpi.status.value}]")
                if kpi.source and kpi.source not in refs:
                    refs.append(kpi.source)
            for name, sec in getattr(resp, "provenance", {}).items():
                if sec.classification not in (KpiStatus.LIVE, KpiStatus.CALCULATED):
                    warnings.append(
                        f"{name}: {sec.classification.value} - {sec.message or ''}".strip(" -")
                    )
            for rec in getattr(resp, "recommendations", []):
                opportunities.append(
                    FinOpsAiOpportunity(
                        title=rec.title,
                        description=rec.finding,
                        resource_id=rec.resource_id,
                        estimated_savings=rec.formatted_savings,
                        effort=rec.effort,
                        risk=rec.risk,
                        confidence_pct=rec.confidence_pct,
                    )
                )
        else:
            warnings.append(f"No analysis is defined for module '{mod}'.")
        confirmed = [f for f in findings if "[LIVE]" in f or "[CALCULATED]" in f]
        return FinOpsAiAnalysis(
            module_id=mod,
            workspace_id=workspace_id,
            executive_summary=(
                f"{len(confirmed)} of {len(findings)} metrics are backed by live or calculated data; "
                "the rest are explicitly unavailable or blocked."
                if findings
                else "No metrics are available for this module."
            ),
            important_findings=findings,
            cost_drivers=[],
            unusual_changes=[],
            optimization_opportunities=opportunities,
            expected_savings="Not calculable"
            if not opportunities
            else "See per-recommendation status",
            risk_assessment="Configuration findings only; validate against workload requirements before any change.",
            data_quality_warnings=warnings,
            suggested_investigations=[
                "Approve read-only billing ingestion to unlock spend, forecast and anomaly analysis."
            ]
            if any("BLOCKED" in w for w in warnings)
            else [],
            confidence_score=round(len(confirmed) / len(findings), 2) if findings else 0.0,
            source_references=refs,
            analysis_timestamp=self._now_iso(),
            is_ai_live=False,
        )
