"""Databricks Live Financial & Billing Ingestion Service.

Implements Milestone 3H Phases C, D, E and the M7.1 hardening:
1. Extraction & Ingestion Engine for system.billing.usage and system.billing.list_prices.
2. Idempotent ingestion keyed on full row identity (PROVISIONAL, see ``_row_identity_hash``);
   a correction row that shares a ``record_id`` is never discarded as a "duplicate".
3. Full Retraction & Restatement Preservation (negative usage quantities).
4. Strict Unit Separation: DBU, BYTE_HOURS, and TOKEN units are never conflated.
5. Deterministic pricing join against the *ingested* rate card only (no hardcoded prices):
   SKU, cloud, usage unit and validity interval (``usage_start_time`` in [start, end)).
6. Exact Resource Scope Attribution (no substring, no partial match, unknown IDs return NO_DATA).
7. Human Approval Gate: POST /ingestion/run returns APPROVAL_REQUIRED without live compute mutation.
8. Validated SQL construction (``billing_sql``) with minimal projections (no identity columns).
9. Money figures are LIST_PRICE_ESTIMATE only; nothing here can produce AZURE_INVOICED.
"""

import hashlib
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.billing_ingestion import (
    BillingIngestionRunResponse,
    BillingIngestionStatusResponse,
    BillingPriceRecord,
    BillingReconciliationResponse,
    BillingSummaryResponse,
    BillingUsageRecord,
    IngestionPreviewResponse,
    IngestionRunCreateRequest,
    IngestionValidateResponse,
)
from cloud_recommender.services.databricks.billing_sql import (
    ATTRIBUTION_KEYS,
    PRICE_ROW_LIMIT,
    BillingQueryValidationError,
    CostBasis,
    MatchStatus,
    build_list_prices_query,
    build_usage_query,
    canonical_timestamp,
    matches_resource,
    parse_map,
    parse_timestamp,
    resolve_resource,
    to_decimal,
    to_decimal_or_none,
)
from cloud_recommender.services.databricks.sql_client import (
    ApprovalLedgerError,
    ApprovalRequiredError,
    DatabricksSqlService,
    StatementIncompleteError,
    WarehouseStoppedError,
)
from cloud_recommender.services.databricks.workspace_service import (
    DatabricksWorkspaceService,
)

logger = structlog.get_logger(__name__)

_CENT = Decimal("0.01")


def _cents(value: Decimal) -> Decimal:
    """Round a Decimal to cents for presentation only (never used inside accumulation)."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _qty_text(value: Decimal) -> str:
    """Canonical text of a quantity (trailing zeros removed) for hashing."""
    return format(value.normalize(), "f")


class BillingIngestionService:
    """Service managing Databricks billing ingestion, pricing joins, and canonical DBU aggregation."""

    def __init__(
        self,
        settings: Settings | None = None,
        sql_service: DatabricksSqlService | None = None,
        workspace_service: DatabricksWorkspaceService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._explicit_sql_service = sql_service is not None
        self.sql_service = sql_service or DatabricksSqlService(settings=self.settings)
        self.workspace_service = workspace_service or DatabricksWorkspaceService(
            settings=self.settings
        )

        # In-memory storage for repository caching. Both start EMPTY: usage rows and the rate
        # card enter only through an approved ingestion run (or the explicit ingest_* methods).
        self._usage_store: dict[str, BillingUsageRecord] = {}
        self._price_store: list[BillingPriceRecord] = []
        self._runs_store: list[BillingIngestionRunResponse] = []
        # None = no rate-card run yet; False = last rate-card extract was not provably whole.
        self._price_card_complete: bool | None = None

    def _get_sql_service_for_workspace(self, workspace_id: str) -> DatabricksSqlService:
        """Resolve DatabricksSqlService configured for the requested workspace's warehouse_id and host."""
        conn = self.workspace_service.get_connection(workspace_id)
        if self._explicit_sql_service and (
            self.sql_service.auth_type == "mock"
            or self.sql_service._client is not None
            or not conn
            or conn.workspace_id == self.sql_service.workspace_id
        ):
            return self.sql_service

        if not conn or conn.workspace_id == self.sql_service.workspace_id:
            return self.sql_service

        return DatabricksSqlService(
            settings=self.settings,
            host=conn.workspace_url,
            warehouse_id=conn.warehouse_id or "",
            workspace_id=conn.workspace_id,
            profile=conn.profile_name,
        )

    # ------------------------------------------------------------------ pricing

    def _apply_price_matching(self, record: BillingUsageRecord) -> None:
        """Deterministic join against the ingested rate card.

        Match on SKU, cloud, usage unit and ``usage_start_time`` in ``[price_start, price_end)``.
        Cost is the full-precision product ``usage_quantity x selected list rate``; rounding is a
        presentation concern. With no ingested price the cost stays ``None`` (never zero).
        """
        record.pricing_matched = False
        record.effective_cost = None
        record.currency = None
        record.price_tier = None
        record.cost_basis = CostBasis.METERED_USAGE
        record.match_status = MatchStatus.NO_PRICE

        if record.usage_unit.upper() != "DBU":
            # Strict unit separation: never apply a DBU rate to non-DBU units
            record.match_status = MatchStatus.UNIT_MISMATCH
            return

        ts = parse_timestamp(record.usage_start_time) or parse_timestamp(record.usage_date)
        if ts is None:
            return

        sku_matches = [
            p
            for p in self._price_store
            if p.sku_name.upper() == record.sku_name.upper()
            and p.cloud.lower() == record.cloud.lower()
        ]
        unit_matches = [p for p in sku_matches if p.usage_unit.upper() == record.usage_unit.upper()]
        if sku_matches and not unit_matches:
            record.match_status = MatchStatus.UNIT_MISMATCH
            return

        candidates: list[tuple[datetime, BillingPriceRecord]] = []
        for price in unit_matches:
            start = parse_timestamp(price.price_start_time)
            end = parse_timestamp(price.price_end_time) if price.price_end_time else None
            if start is None or price.selected_price() is None:
                continue
            if ts < start or (end is not None and ts >= end):
                continue
            candidates.append((start, price))
        if not candidates:
            return

        latest_start = max(start for start, _ in candidates)
        latest = [p for start, p in candidates if start == latest_start]
        # Currency is part of the rate: equal numbers in different currencies are NOT the same
        # price, and are never merged or converted.
        rates = {(p.selected_price(), p.currency_code.strip().upper()) for p in latest}
        if len(rates) != 1:
            record.match_status = MatchStatus.AMBIGUOUS
            return

        chosen = latest[0]
        rate = chosen.selected_price()
        assert rate is not None
        record.effective_cost = record.usage_quantity * rate
        record.pricing_matched = True
        record.currency = chosen.currency_code
        record.price_tier = chosen.price_tier
        record.cost_basis = CostBasis.LIST_PRICE_ESTIMATE
        record.match_status = MatchStatus.MATCHED

    def reprice_all(self) -> None:
        """Re-run the price join over every stored usage row (after a rate-card change)."""
        for rec in self._usage_store.values():
            self._apply_price_matching(rec)

    # ------------------------------------------------------------------ status

    def get_ingestion_status(
        self, workspace_id: str = "642006393507276"
    ) -> BillingIngestionStatusResponse:
        """Report live warehouse, auth, and System Tables status."""
        sql_svc = self._get_sql_service_for_workspace(workspace_id)
        wh_health = sql_svc.check_warehouse_status()

        ws_rows = [
            rec
            for rec in self._usage_store.values()
            if rec.workspace_id == workspace_id and rec.usage_unit == "DBU"
        ]
        total_dbu = sum((rec.usage_quantity for rec in ws_rows), Decimal("0"))
        last_run = self._runs_store[-1].completed_at if self._runs_store else None

        if wh_health.status == "AUTH_ERROR":
            conn_status = "AUTH_FAILED"
            sys_status = "AUTH_ERROR"
            next_step = wh_health.message
        elif wh_health.status == "PERMISSION_DENIED":
            conn_status = "PERMISSION_DENIED"
            sys_status = "PERMISSION_DENIED"
            next_step = wh_health.message
        elif wh_health.status == "CONNECTION_ERROR":
            conn_status = "UNAVAILABLE"
            sys_status = "UNAVAILABLE"
            next_step = wh_health.message
        elif wh_health.status == "WAREHOUSE_STOPPED":
            conn_status = "CONNECTED" if wh_health.authenticated_user else "READY_TO_CONNECT"
            next_step = (
                f"SQL Warehouse '{wh_health.warehouse_name}' ({wh_health.warehouse_id}) is STOPPED. "
                "Explicit approval is required before resuming compute to query live System Tables."
            )
            sys_status = "APPROVAL_REQUIRED"
        elif wh_health.status == "AVAILABLE":
            conn_status = "CONNECTED" if wh_health.authenticated_user else "READY_TO_CONNECT"
            next_step = "Warehouse is active. Ready to execute approved ingestion runs."
            sys_status = "AVAILABLE"
        else:
            conn_status = "UNAVAILABLE"
            next_step = wh_health.message
            sys_status = "APPROVAL_REQUIRED"

        return BillingIngestionStatusResponse(
            connection_status=conn_status,
            warehouse_status=wh_health.status,
            warehouse_id=wh_health.warehouse_id,
            warehouse_name=wh_health.warehouse_name,
            system_tables_status=sys_status,
            last_successful_ingestion=last_run,
            total_usage_records_ingested=len(self._usage_store),
            total_dbu_consumed=float(round(total_dbu, 2)) if ws_rows else None,
            active_configuration_version=1,
            next_action=next_step,
        )

    def get_ingestion_runs(
        self, workspace_id: str = "642006393507276"
    ) -> list[BillingIngestionRunResponse]:
        """Fetch audit history of ingestion runs for the workspace."""
        return [r for r in self._runs_store if r.workspace_id == workspace_id]

    def validate_ingestion(
        self, workspace_id: str = "642006393507276"
    ) -> IngestionValidateResponse:
        """Validate warehouse readiness and parameters without executing compute."""
        sql_svc = self._get_sql_service_for_workspace(workspace_id)
        wh_health = sql_svc.check_warehouse_status()
        diagnostics = [
            f"Workspace '{workspace_id}' target confirmed.",
            f"Warehouse ID '{wh_health.warehouse_id}' ({wh_health.warehouse_name}) inspected.",
            f"Observed warehouse state is '{wh_health.warehouse_state}' (status: {wh_health.status}).",
        ]
        if wh_health.auto_stop_mins is not None:
            diagnostics.append(f"Observed warehouse auto-stop: {wh_health.auto_stop_mins} minutes.")
        if wh_health.status in ("AUTH_ERROR", "PERMISSION_DENIED", "CONNECTION_ERROR"):
            diagnostics.append(wh_health.message)
        elif wh_health.warehouse_state == "STOPPED":
            diagnostics.append(
                "Warehouse is currently STOPPED. Queries cannot be executed without separate explicit human approval."
            )
        diagnostics.append(
            "Read-only access: only SELECT queries against allowlisted system tables permitted."
        )
        diagnostics.append("Zero-Execution policy enforced: Run button is locked.")

        window_start = (datetime.now(UTC).date().replace(day=1)).isoformat()
        window_end = datetime.now(UTC).date().isoformat()
        try:
            query_preview = build_usage_query(workspace_id, window_start, window_end, 100)
        except BillingQueryValidationError as exc:
            query_preview = ""
            diagnostics.append(f"Invalid workspace_id for query construction: {exc}")

        is_valid = bool(query_preview) and (
            wh_health.status not in ("AUTH_ERROR", "PERMISSION_DENIED", "CONNECTION_ERROR")
            and (wh_health.authenticated_user is not None or sql_svc.auth_type == "mock")
        )

        return IngestionValidateResponse(
            valid=is_valid,
            workspace_id=workspace_id,
            warehouse_id=wh_health.warehouse_id,
            warehouse_name=wh_health.warehouse_name,
            warehouse_state=wh_health.warehouse_state,
            system_tables_ready=wh_health.status == "AVAILABLE",
            allowed_tables=sorted(sql_svc.ALLOWED_SYSTEM_TABLES),
            query_plan_preview=query_preview,
            expected_result_size="Not estimated (bounded by the requested row limit)",
            expected_operational_cost="Not estimated (depends on warehouse size and runtime)",
            approval_status=wh_health.status if not is_valid else "APPROVAL_REQUIRED",
            duplicate_handling=(
                "Idempotent on full row identity (PROVISIONAL): identical re-extracted rows are "
                "skipped; correction rows sharing a record_id are preserved"
            ),
            can_run=False,
            diagnostic_messages=diagnostics,
        )

    def preview_ingestion(
        self,
        workspace_id: str = "642006393507276",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
    ) -> IngestionPreviewResponse:
        """Provide preview records from the ingested store without live compute execution."""
        today = datetime.now(UTC).date()
        start = start_date or today.replace(day=1).isoformat()
        end = end_date or today.isoformat()
        matching_records = [
            rec
            for rec in self._usage_store.values()
            if rec.workspace_id == workspace_id and start <= rec.usage_date <= end
        ]
        return IngestionPreviewResponse(
            workspace_id=workspace_id,
            period_start=start,
            period_end=end,
            source="Ingested usage store (no SQL executed; empty until an approved ingestion run)",
            preview_records=matching_records[:limit],
            total_available_in_preview=len(matching_records),
            status="PREVIEW_READY",
        )

    # ------------------------------------------------------------------ run

    def _build_statement(self, request: IngestionRunCreateRequest) -> tuple[str, str]:
        """Return (sql, source_table) built only from validated values."""
        if request.source_table == "system.billing.list_prices":
            return build_list_prices_query(limit=PRICE_ROW_LIMIT), "system.billing.list_prices"
        return (
            build_usage_query(
                request.workspace_id, request.start_date, request.end_date, request.limit
            ),
            "system.billing.usage",
        )

    def run_ingestion(
        self, request: IngestionRunCreateRequest, ledger: Any | None = None
    ) -> BillingIngestionRunResponse:
        """Execute ingestion run under strict Human Approval Gate.

        If is_approved is False, halts execution and returns APPROVAL_REQUIRED payload.
        ``ledger`` is the durable approval-token ledger handle (sync Session or LedgerHandle).
        """
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        sql_svc = self._get_sql_service_for_workspace(request.workspace_id)

        def _run(status: str, **kw: Any) -> BillingIngestionRunResponse:
            res = BillingIngestionRunResponse(
                run_id=run_id,
                workspace_id=request.workspace_id,
                source_table=source_table,
                requested_period_start=request.start_date,
                requested_period_end=request.end_date,
                started_at=datetime.now(UTC).isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
                status=status,
                **kw,
            )
            self._runs_store.append(res)
            return res

        sql_stmt, source_table = self._build_statement(request)
        tables = [source_table]

        # Gate Check: Explicit Human Approval
        if not request.is_approved:
            approval_payload = sql_svc.generate_approval_request(
                sql_statement=sql_stmt,
                system_tables=tables,
                execution_purpose="Live ingestion of Databricks billing events into FinOps Command Center",
                estimated_scope=(
                    f"Workspace {request.workspace_id}, {request.start_date} to {request.end_date}"
                    if source_table == "system.billing.usage"
                    else "Published list prices (rate card)"
                ),
            )
            return _run(
                "approval_required",
                error_message="Live SQL execution requires explicit human approval before compute resume.",
                approval_request=approval_payload,
            )

        # If approved, attempt execution via DatabricksSqlService with server token verification
        is_prices = source_table == "system.billing.list_prices"
        row_bound = PRICE_ROW_LIMIT if is_prices else request.limit
        try:
            raw_rows = sql_svc.execute_read_only_statement(
                sql_statement=sql_stmt,
                system_tables=tables,
                is_approved=True,
                approval_token=request.approval_token,
                session=ledger,
                date_start=None if is_prices else request.start_date,
                date_end=None if is_prices else request.end_date,
            )
            # Reaching the bound means the source may hold more rows: never report success.
            limit_reached = len(raw_rows) >= row_bound
            run_status = "incomplete" if limit_reached else "completed"
            completeness: dict[str, Any] = {
                "result_complete": not limit_reached,
                "error_code": "ROW_LIMIT_REACHED" if limit_reached else None,
                "error_message": (
                    f"The extract reached its row bound ({row_bound}); more rows may exist. "
                    "Results are partial - narrow the window or raise the (approved) limit."
                    if limit_reached
                    else None
                ),
            }
            if is_prices:
                self._price_card_complete = not limit_reached
            if source_table == "system.billing.list_prices":
                prices: list[BillingPriceRecord] = []
                malformed = 0
                for raw in raw_rows:
                    price = self._row_to_price_record(raw)
                    if price is None:
                        malformed += 1
                    else:
                        prices.append(price)
                price_stats = self.ingest_price_records(prices)
                return _run(
                    run_status,
                    extracted_count=len(raw_rows),
                    inserted_count=price_stats["inserted_count"],
                    duplicate_count=price_stats["duplicate_count"],
                    error_count=malformed,
                    **completeness,
                )

            parsed: list[BillingUsageRecord] = []
            malformed = 0
            for raw in raw_rows:
                rec = self._row_to_usage_record(raw)
                if rec is None or rec.workspace_id != request.workspace_id:
                    malformed += 1  # unparsable or outside the requested workspace
                else:
                    parsed.append(rec)
            stats = self.ingest_records(parsed)
            return _run(
                run_status,
                extracted_count=len(raw_rows),
                inserted_count=stats["inserted_count"],
                duplicate_count=stats["duplicate_count"],
                retraction_count=stats["retraction_count"],
                shared_record_id_count=stats["shared_record_id_count"],
                error_count=malformed,
                **completeness,
            )

        except ApprovalRequiredError as are:
            return _run(
                "approval_required",
                error_message="Live SQL execution blocked by approval gate. Valid server authorization token required.",
                approval_request=are.approval_request,
            )

        except WarehouseStoppedError as wse:
            return _run(
                "failed",
                error_message=(
                    f"Execution blocked: Target SQL Warehouse {wse.warehouse_id} is STOPPED. "
                    "Automatic startup is disabled. Compute startup must be performed as an "
                    f"explicit, separately authorized operator action ({wse}). "
                    "The approval token was NOT consumed."
                ),
            )

        except ApprovalLedgerError:
            return _run(
                "failed",
                error_message="Durable approval-token ledger unavailable; execution refused.",
            )

        except StatementIncompleteError as sie:
            # Nothing from an unfinished/truncated/failed statement is ingested.
            if is_prices:
                self._price_card_complete = False
            return _run(
                "failed",
                error_code=sie.code,
                result_complete=False,
                error_message=f"{sie.reason} No rows were ingested from this run.",
            )

        except Exception as exc:
            scrubbed = self.sql_service.auth_service.scrub_sensitive(str(exc))
            return _run("failed", error_message=scrubbed)

    # ------------------------------------------------------------------ mapping

    @staticmethod
    def _parse_map(value: Any) -> dict[str, Any]:
        """Normalize a system-table MAP/STRUCT column that may arrive as dict or JSON text."""
        return parse_map(value)

    @classmethod
    def _row_to_usage_record(cls, row: dict[str, Any]) -> BillingUsageRecord | None:
        """Map a system.billing.usage result row to a BillingUsageRecord; None if malformed.

        Only allow-listed ID keys of ``usage_metadata`` are kept (flat projected columns, or the
        nested struct for backward compatibility). ``identity_metadata`` is never read.
        """
        try:
            tags = {str(k): str(v) for k, v in cls._parse_map(row.get("custom_tags")).items()}
            nested = cls._parse_map(row.get("usage_metadata"))
            usage_metadata = {
                k: str(v)
                for k in ATTRIBUTION_KEYS
                if (v := row.get(k, nested.get(k))) not in (None, "")
            }
            rec = BillingUsageRecord(
                record_id=str(row["record_id"]),
                workspace_id=str(row["workspace_id"]),
                account_id=str(row["account_id"]) if row.get("account_id") else None,
                sku_name=str(row["sku_name"]),
                cloud=str(row.get("cloud") or "azure").lower(),
                usage_start_time=str(row["usage_start_time"]),
                usage_end_time=str(row["usage_end_time"]),
                usage_date=str(row["usage_date"])[:10],
                usage_unit=str(row["usage_unit"]),
                usage_quantity=to_decimal(row["usage_quantity"]),
                record_type=str(row.get("record_type") or "original").lower(),
                ingestion_date=str(row["ingestion_date"]) if row.get("ingestion_date") else None,
                billing_origin_product=(
                    str(row["billing_origin_product"])
                    if row.get("billing_origin_product")
                    else None
                ),
                product_features=cls._parse_map(row.get("product_features")),
                usage_metadata=usage_metadata,
                custom_tags=tags,
            )
        except (KeyError, TypeError, ValueError):
            return None
        cls._annotate(rec)
        return rec

    @classmethod
    def _row_to_price_record(cls, row: dict[str, Any]) -> BillingPriceRecord | None:
        """Map a system.billing.list_prices row (nested ``pricing`` struct) to a price record."""
        try:
            pricing = cls._parse_map(row.get("pricing"))
            promo = pricing.get("promotional")
            promo_map = promo if isinstance(promo, dict) else cls._parse_map(promo)
            eff = pricing.get("effective_list")
            eff_map = eff if isinstance(eff, dict) else cls._parse_map(eff)
            price_default = to_decimal_or_none(pricing.get("default"))
            price_effective = to_decimal_or_none(eff_map.get("default"))
            if price_default is None and price_effective is None:
                return None  # a price row with no usable rate is malformed, not "free"
            return BillingPriceRecord(
                account_id=str(row["account_id"]) if row.get("account_id") else None,
                sku_name=str(row["sku_name"]),
                cloud=str(row.get("cloud") or "azure").lower(),
                currency_code=str(row.get("currency_code") or "USD"),
                usage_unit=str(row.get("usage_unit") or "DBU"),
                price_default=price_default,
                price_promotional=to_decimal_or_none(promo_map.get("default")),
                price_effective_list=price_effective,
                price_start_time=str(row["price_start_time"]),
                price_end_time=str(row["price_end_time"]) if row.get("price_end_time") else None,
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _annotate(rec: BillingUsageRecord) -> None:
        """Fill attribution fields and the identity hash (idempotent)."""
        resolved = resolve_resource(rec.usage_metadata)
        if resolved:
            rec.resource_type, rec.resource_id = resolved
        rec.source_row_hash = BillingIngestionService._row_identity_hash(rec)

    @staticmethod
    def _row_identity_hash(rec: BillingUsageRecord) -> str:
        """Hash of the fields that identify a source row.

        PROVISIONAL dedup identity. Evidence available offline (Unity Catalog column comments)
        does not state whether a retraction/restatement reuses the original ``record_id``, so the
        key deliberately includes ``record_type``, the metering window and the exact quantity:
        it removes only genuine re-extracts of an identical row and can never discard a
        correction row (``ingestion_date`` is stored but excluded, as a re-extract of the same
        row may be observed on different days). Timestamps are canonicalised to parsed UTC
        ISO text first, so ``...00Z`` and ``...00.000+00:00`` are the same instant and a
        re-extract formatted differently is still recognised. Finalise after the first approved
        extract (see ``shared_record_id_count``).
        """
        parts = (
            rec.workspace_id,
            rec.record_id,
            rec.sku_name.strip(),
            rec.record_type,
            canonical_timestamp(rec.usage_start_time),
            canonical_timestamp(rec.usage_end_time),
            rec.usage_unit,
            _qty_text(rec.usage_quantity),
        )
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ ingest

    def ingest_records(self, records: list[BillingUsageRecord]) -> dict[str, int]:
        """Ingest usage records idempotently; retractions/restatements are preserved."""
        inserted = 0
        duplicates = 0
        retractions = 0

        ids_in_batch: dict[str, int] = {}
        for rec in records:
            ids_in_batch[rec.record_id] = ids_in_batch.get(rec.record_id, 0) + 1
        shared_batch = sum(n for n in ids_in_batch.values() if n > 1)
        cross_run_ids: set[str] = set()

        for rec in records:
            if rec.source_row_hash is None:
                self._annotate(rec)
            row_hash = rec.source_row_hash or ""
            existing = self._usage_store.get(rec.record_id)
            if existing is None:
                key = rec.record_id
            elif existing.source_row_hash == row_hash:
                duplicates += 1
                continue
            else:
                if ids_in_batch[rec.record_id] == 1:
                    cross_run_ids.add(rec.record_id)  # correction landing in a later run
                key = f"{rec.record_id}#{row_hash[:12]}"
                if key in self._usage_store:
                    duplicates += 1
                    continue

            self._apply_price_matching(rec)
            self._usage_store[key] = rec
            inserted += 1

            if rec.record_type == "retraction" or rec.usage_quantity < 0:
                retractions += 1

        return {
            "extracted_count": len(records),
            "inserted_count": inserted,
            "duplicate_count": duplicates,
            "retraction_count": retractions,
            "shared_record_id_count": shared_batch + len(cross_run_ids),
            "inserted": inserted,
            "duplicates": duplicates,
            "retractions": retractions,
            "total_stored": len(self._usage_store),
        }

    def ingest_price_records(self, prices: list[BillingPriceRecord]) -> dict[str, int]:
        """Ingest the rate card (idempotent) and re-price stored usage."""
        inserted = 0
        duplicates = 0
        existing = {
            (
                p.account_id,
                p.sku_name.upper(),
                p.cloud,
                p.currency_code,
                p.usage_unit,
                p.price_start_time,
            )
            for p in self._price_store
        }
        for price in prices:
            key = (
                price.account_id,
                price.sku_name.upper(),
                price.cloud,
                price.currency_code,
                price.usage_unit,
                price.price_start_time,
            )
            if key in existing:
                duplicates += 1
                continue
            existing.add(key)
            self._price_store.append(price)
            inserted += 1
        if inserted:
            self.reprice_all()
        return {
            "extracted_count": len(prices),
            "inserted_count": inserted,
            "duplicate_count": duplicates,
        }

    # ------------------------------------------------------------------ summary

    def get_billing_summary(
        self,
        workspace_id: str = "642006393507276",
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> BillingSummaryResponse:
        """Produce canonical DBU summary and spend breakdown with exact scope filtering."""
        _ = resource_type
        # Gather matching workspace records
        workspace_records = [
            rec
            for rec in self._usage_store.values()
            if rec.workspace_id == workspace_id and rec.usage_unit == "DBU"
        ]

        # Exact resource scope filtering
        if resource_id:
            filtered_records = [
                rec
                for rec in workspace_records
                if matches_resource(rec.usage_metadata, resource_id)
            ]
            if not filtered_records:
                # No ingested rows for this resource scope -> unknown, never zero
                return BillingSummaryResponse(
                    workspace_id=workspace_id,
                    resource_id=resource_id,
                    data_status="NO_DATA",
                    price_card_complete=self._price_card_complete,
                )
            target_records = filtered_records
        else:
            target_records = workspace_records
            if not target_records:
                return BillingSummaryResponse(
                    workspace_id=workspace_id,
                    data_status="NO_BILLING_ROWS",
                    price_card_complete=self._price_card_complete,
                )

        zero = Decimal("0")
        gross_dbu = sum((r.usage_quantity for r in target_records if r.usage_quantity > 0), zero)
        retraction_dbu = abs(
            sum((r.usage_quantity for r in target_records if r.usage_quantity < 0), zero)
        )
        net_dbu = gross_dbu - retraction_dbu

        # List-price estimate over priced rows only; completeness is reported explicitly.
        priced_records = [
            rec for rec in target_records if rec.pricing_matched and rec.effective_cost is not None
        ]
        total_spend: Decimal | None = (
            sum(
                (rec.effective_cost for rec in priced_records if rec.effective_cost is not None),
                zero,
            )
            if priced_records
            else None
        )
        spend_by_currency: dict[str, Decimal] = {}
        for rec in priced_records:
            if rec.currency and rec.effective_cost is not None:
                spend_by_currency[rec.currency] = (
                    spend_by_currency.get(rec.currency, zero) + rec.effective_cost
                )
        mixed = len(spend_by_currency) > 1
        if mixed:
            total_spend = None  # currencies are never merged or converted

        # Breakdowns (net quantity, DBU only)
        product_map: dict[str, Decimal] = {}
        sku_map: dict[str, Decimal] = {}
        day_map: dict[str, Decimal] = {}
        for rec in target_records:
            prod = rec.billing_origin_product or "OTHER"
            product_map[prod] = product_map.get(prod, zero) + rec.usage_quantity
            sku_map[rec.sku_name] = sku_map.get(rec.sku_name, zero) + rec.usage_quantity
            day_map[rec.usage_date] = day_map.get(rec.usage_date, zero) + rec.usage_quantity

        return BillingSummaryResponse(
            workspace_id=workspace_id,
            resource_id=resource_id,
            total_dbu=float(round(gross_dbu, 2)),
            net_dbu=float(round(net_dbu, 2)),
            retraction_dbu=float(round(retraction_dbu, 2)),
            total_spend_verified=float(_cents(total_spend)) if total_spend is not None else None,
            spend_complete=len(priced_records) == len(target_records) and not mixed,
            pricing_coverage_pct=round(100.0 * len(priced_records) / len(target_records), 2),
            cost_basis=(
                CostBasis.LIST_PRICE_ESTIMATE
                if total_spend is not None
                else CostBasis.METERED_USAGE
            ),
            currency=next(iter(spend_by_currency)) if len(spend_by_currency) == 1 else None,
            spend_by_currency=[
                {"currency": c, "spend": float(_cents(v))}
                for c, v in sorted(spend_by_currency.items())
            ],
            price_card_complete=self._price_card_complete,
            dbu_by_product=[
                {"product": k, "dbu": float(round(v, 2))} for k, v in sorted(product_map.items())
            ],
            dbu_by_sku=[{"sku": k, "dbu": float(round(v, 2))} for k, v in sorted(sku_map.items())],
            daily_trend=[
                {"date": k, "dbu": float(round(v, 2))} for k, v in sorted(day_map.items())
            ],
            matched_pricing_count=len(priced_records),
            unmatched_pricing_count=len(target_records) - len(priced_records),
            data_status="INGESTED",
        )

    def get_billing_reconciliation(
        self, workspace_id: str = "642006393507276"
    ) -> BillingReconciliationResponse:
        """Internal reconciliation. Every check is evaluated; failures are reported, not hidden."""
        recs = [rec for rec in self._usage_store.values() if rec.workspace_id == workspace_id]
        if not recs:
            return BillingReconciliationResponse(
                workspace_id=workspace_id,
                price_record_count=len(self._price_store),
                reconciliation_status="NO_DATA",
                audit_notes=[
                    "No billing usage rows are ingested, so nothing can be reconciled.",
                    "Rows enter only through an approved read-only system.billing.usage ingestion.",
                ],
            )

        zero = Decimal("0")
        dbu_rows = [r for r in recs if r.usage_unit == "DBU"]
        gross_dbu = sum((r.usage_quantity for r in dbu_rows if r.usage_quantity > 0), zero)
        retraction_dbu = abs(
            sum((r.usage_quantity for r in dbu_rows if r.usage_quantity < 0), zero)
        )
        net_dbu = gross_dbu - retraction_dbu
        signed_dbu = sum((r.usage_quantity for r in dbu_rows), zero)

        costed = [r for r in recs if r.effective_cost is not None]
        gross_cost = sum(
            (r.effective_cost for r in costed if r.effective_cost and r.effective_cost > 0), zero
        )
        retraction_cost = abs(
            sum(
                (r.effective_cost for r in costed if r.effective_cost and r.effective_cost < 0),
                zero,
            )
        )
        net_cost = gross_cost - retraction_cost
        signed_cost = sum((r.effective_cost for r in costed if r.effective_cost is not None), zero)
        cost_by_cur: dict[str, list[Decimal]] = {}
        for r in costed:
            if r.currency and r.effective_cost is not None:
                g, t = cost_by_cur.setdefault(r.currency, [zero, zero])
                cost_by_cur[r.currency] = [
                    g + (r.effective_cost if r.effective_cost > 0 else zero),
                    t + (-r.effective_cost if r.effective_cost < 0 else zero),
                ]

        matched = [r for r in recs if r.pricing_matched]
        unmatched = [r for r in recs if not r.pricing_matched]
        unmatched_dbu = [r for r in dbu_rows if not r.pricing_matched]
        retractions = [r for r in recs if r.record_type == "retraction" or r.usage_quantity < 0]
        currencies = {r.currency for r in matched if r.currency}

        checks: list[dict[str, Any]] = [
            {
                "name": "net_dbu_identity",
                "passed": net_dbu == signed_dbu,
                "detail": "gross - retractions equals the signed sum of DBU quantities",
            },
            {
                "name": "pricing_partition",
                "passed": len(matched) + len(unmatched) == len(recs),
                "detail": "matched + unmatched equals total records",
            },
            {
                "name": "cost_identity",
                "passed": net_cost == signed_cost,
                "detail": "gross - retraction cost equals the signed sum of row costs",
            },
            {
                "name": "unit_separation",
                "passed": all(r.effective_cost is None for r in recs if r.usage_unit != "DBU"),
                "detail": "no non-DBU row carries a DBU-derived cost",
            },
            {
                "name": "retraction_sign",
                "passed": all(r.usage_quantity <= 0 for r in recs if r.record_type == "retraction"),
                "detail": "retraction records carry non-positive quantities",
            },
            {
                "name": "single_currency",
                "passed": len(currencies) <= 1,
                "detail": "priced rows use one currency (currencies are never merged or converted)",
            },
        ]
        failed = [c["name"] for c in checks if not c["passed"]]
        if failed:
            status = "DISCREPANCY_DETECTED"
        elif unmatched_dbu:
            status = "PARTIAL_PRICING"
        else:
            status = "RECONCILED"

        notes = [
            f"Evaluated {len(recs)} total billing usage records for workspace {workspace_id}.",
            f"{len(matched)} records matched against {len(self._price_store)} ingested list prices.",
            f"{len(unmatched)} records unmatched or unpriced ({len(unmatched_dbu)} DBU rows).",
            f"Preserved {len(retractions)} retractions with exact negative quantity accounting.",
            "Strict unit separation enforced: non-DBU units (BYTE_HOURS, TOKEN) isolated.",
            "Exact Decimal arithmetic; rounding applied only to the presented totals.",
            "Costs are LIST_PRICE_ESTIMATE (DBU x published list rate), not invoiced amounts.",
        ]
        if failed:
            notes.append(f"Failed checks: {', '.join(failed)}.")

        return BillingReconciliationResponse(
            workspace_id=workspace_id,
            usage_record_count=len(recs),
            price_record_count=len(self._price_store),
            matched_records_count=len(matched),
            unmatched_records_count=len(unmatched),
            retraction_records_count=len(retractions),
            gross_dbu=float(round(gross_dbu, 2)),
            retraction_dbu=float(round(retraction_dbu, 2)),
            net_dbu=float(round(net_dbu, 2)),
            gross_cost=float(_cents(gross_cost)) if costed and len(currencies) <= 1 else None,
            net_cost=float(_cents(net_cost)) if costed and len(currencies) <= 1 else None,
            currency=next(iter(currencies)) if len(currencies) == 1 else None,
            cost_by_currency=[
                {"currency": c, "gross_cost": float(_cents(g)), "net_cost": float(_cents(g - t))}
                for c, (g, t) in sorted(cost_by_cur.items())
            ],
            cost_basis=CostBasis.LIST_PRICE_ESTIMATE if costed else CostBasis.METERED_USAGE,
            reconciliation_status=status,
            checks=checks,
            audit_notes=notes,
        )

    def list_usage_records(
        self,
        workspace_id: str = "642006393507276",
        sku_name: str | None = None,
        product: str | None = None,
        resource_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[BillingUsageRecord]:
        """Query stored billing records with parameter filtering."""
        results: list[BillingUsageRecord] = []
        for rec in self._usage_store.values():
            if rec.workspace_id != workspace_id:
                continue
            if sku_name and rec.sku_name.upper() != sku_name.upper():
                continue
            if product and (rec.billing_origin_product or "").upper() != product.upper():
                continue
            if start_date and rec.usage_date < start_date:
                continue
            if end_date and rec.usage_date > end_date:
                continue
            if resource_id and not matches_resource(rec.usage_metadata, resource_id):
                continue
            results.append(rec)

        if offset > 0:
            results = results[offset:]
        if limit is not None:
            results = results[:limit]

        return results

    def list_price_records(self) -> list[BillingPriceRecord]:
        """Return the ingested rate card (empty until an approved list_prices ingestion)."""
        return list(self._price_store)
