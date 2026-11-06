"""Analytical repository for Microsoft Fabric OneLake Delta Lake.

Provides application-facing data access methods for the FinOps platform:
- Resource Inventory (filtered to latest snapshot)
- Cost Analytics (strictly currency-separated)
- Resource Metrics (deduplicated across overlapping time windows)
- Token Economics (honest empty-table handling)
- Sync History & Freshness Auditing

Enforces in-memory TTL caching, query timing, and zero-write safety.
"""

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .config import LakehouseReaderConfig
from .delta_reader import OneLakeDeltaReader
from .models import (
    AnalyticalResponseEnvelope,
    CurrencyCostTotal,
    DailyCostTrendPoint,
    LakehouseCostAnalytics,
    LakehouseInventorySummary,
    LakehouseMetricsSummary,
    LakehouseResourceItem,
    LakehouseSyncOverview,
    LakehouseTokenSummary,
    MetricSeriesPoint,
    ResourceMetricSeries,
    ServiceCostItem,
    SyncHistoryEntry,
)

logger = logging.getLogger("finops_udf.lakehouse.repository")


class AnalyticalRepository:
    """High-level repository serving analytical FinOps queries from OneLake Delta tables."""

    def __init__(
        self,
        reader: OneLakeDeltaReader | None = None,
        config: LakehouseReaderConfig | None = None,
    ) -> None:
        self.config = config or LakehouseReaderConfig.load()
        self.reader = reader or OneLakeDeltaReader(config=self.config)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()

    def _get_from_cache(self, cache_key: str) -> Any | None:
        """Retrieve valid cached result if within TTL window."""
        now = time.time()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached:
                insert_time, val = cached
                if now - insert_time <= self.config.cache_ttl_sec:
                    return val
                # Expired
                del self._cache[cache_key]
        return None

    def _put_in_cache(self, cache_key: str, value: Any) -> None:
        """Store result in cache with timestamp, evicting oldest if capacity exceeded."""
        now = time.time()
        with self._cache_lock:
            if len(self._cache) >= self.config.max_cache_entries:
                # Evict oldest entry
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[cache_key] = (now, value)

    def get_inventory_summary(
        self,
        connection_id: str,
        subscription_id: str | None = None,
        resource_type_filter: str | None = None,
    ) -> AnalyticalResponseEnvelope[LakehouseInventorySummary]:
        """Fetch discovered cloud resources from the latest Lakehouse snapshot.

        Enforces snapshot deduplication: filters down to the maximum snapshot_timestamp
        so historical snapshots do not inflate current resource counts.
        """
        start_time = time.time()
        cache_key = f"inv::{connection_id}::{subscription_id}::{resource_type_filter}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return AnalyticalResponseEnvelope[LakehouseInventorySummary](
                status="success",
                data=cached,
                data_source="onelake_delta",
                is_live=True,
                records_count=cached.total_resources,
                query_duration_ms=int((time.time() - start_time) * 1000),
                cache_hit=True,
            )

        try:
            records = self.reader.read_records_as_dicts(
                "resource_inventory",
                columns=[
                    "resource_id",
                    "connection_id",
                    "name",
                    "provider",
                    "resource_type",
                    "resource_group",
                    "location",
                    "sku_name",
                    "power_state",
                    "tags",
                    "monthly_retail_cost",
                    "snapshot_timestamp",
                    "subscription_id",
                ],
            )
        except Exception as exc:
            return AnalyticalResponseEnvelope[LakehouseInventorySummary](
                status="error",
                data_source="onelake_delta",
                error_code="LAKEHOUSE_READ_ERROR",
                error_message=f"Failed to read resource_inventory: {exc}",
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        # Filter by connection_id or subscription_id
        matching_records = []
        if connection_id:
            matching_records = [
                r for r in records if r.get("connection_id") == connection_id
            ]
        if not matching_records and subscription_id:
            matching_records = [
                r for r in records if r.get("subscription_id") == subscription_id
            ]
        if not matching_records and not connection_id and not subscription_id:
            matching_records = records

        if not matching_records:
            empty_summary = LakehouseInventorySummary(
                connection_id=connection_id,
                subscription_id=subscription_id or "unknown",
                snapshot_timestamp=datetime.now(UTC).isoformat(),
                total_resources=0,
            )
            return AnalyticalResponseEnvelope[LakehouseInventorySummary](
                status="success",
                data=empty_summary,
                data_source="onelake_delta",
                records_count=0,
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        # 1. Identify Latest Snapshot Timestamp
        latest_ts = max(r.get("snapshot_timestamp", "") for r in matching_records)

        # 2. Filter to records belonging strictly to the latest snapshot
        latest_records = [
            r for r in matching_records if r.get("snapshot_timestamp") == latest_ts
        ]

        # 3. Apply optional resource_type filter
        if resource_type_filter:
            flt_lower = resource_type_filter.lower()
            latest_records = [
                r
                for r in latest_records
                if flt_lower in r.get("resource_type", "").lower()
            ]

        # 4. Compute distributions
        by_prov = defaultdict(int)
        by_type = defaultdict(int)
        by_reg = defaultdict(int)
        by_power = defaultdict(int)
        items: list[LakehouseResourceItem] = []

        sub_id = subscription_id or (
            latest_records[0].get("subscription_id") or "unknown"
            if latest_records
            else "unknown"
        )

        for r in latest_records:
            prov = r.get("provider") or "azure"
            rtype = r.get("resource_type") or "unknown"
            loc = r.get("location") or "global"
            pstate = r.get("power_state") or "Unknown"

            by_prov[prov] += 1
            by_type[rtype] += 1
            by_reg[loc] += 1
            by_power[pstate] += 1

            tags_raw = r.get("tags")
            tags_dict = None
            if tags_raw and isinstance(tags_raw, str) and tags_raw != "None":
                try:
                    tags_dict = json.loads(tags_raw)
                except Exception:
                    tags_dict = None

            items.append(
                LakehouseResourceItem(
                    resource_id=r["resource_id"],
                    name=r["name"],
                    provider=prov,
                    resource_type=rtype,
                    resource_group=r.get("resource_group"),
                    location=loc,
                    sku_name=r.get("sku_name"),
                    power_state=pstate,
                    tags=tags_dict,
                    monthly_retail_cost=r.get("monthly_retail_cost"),
                    snapshot_timestamp=latest_ts,
                )
            )

        summary = LakehouseInventorySummary(
            connection_id=connection_id,
            subscription_id=sub_id,
            snapshot_timestamp=latest_ts,
            total_resources=len(latest_records),
            by_provider=dict(by_prov),
            by_resource_type=dict(by_type),
            by_region=dict(by_reg),
            by_power_state=dict(by_power),
            resources=items,
        )

        self._put_in_cache(cache_key, summary)
        duration_ms = int((time.time() - start_time) * 1000)

        return AnalyticalResponseEnvelope[LakehouseInventorySummary](
            status="success",
            data=summary,
            data_source="onelake_delta",
            is_live=True,
            last_sync_at=latest_ts,
            records_count=len(latest_records),
            query_duration_ms=duration_ms,
        )

    def get_cost_analytics(
        self,
        connection_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> AnalyticalResponseEnvelope[LakehouseCostAnalytics]:
        """Aggregate authentic Cost Management consumption data strictly by currency."""
        start_time = time.time()
        cache_key = f"cost::{connection_id}::{start_date}::{end_date}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return AnalyticalResponseEnvelope[LakehouseCostAnalytics](
                status="success",
                data=cached,
                data_source="onelake_delta",
                is_live=True,
                records_count=cached.total_records,
                query_duration_ms=int((time.time() - start_time) * 1000),
                cache_hit=True,
            )

        try:
            records = self.reader.read_records_as_dicts(
                "cost_details",
                columns=[
                    "usage_date",
                    "billing_year_month",
                    "resource_id",
                    "service_name",
                    "meter_category",
                    "meter_name",
                    "cost_in_billing_currency",
                    "currency",
                    "charge_type",
                    "subscription_id",
                    "ingestion_timestamp",
                ],
            )
        except Exception as exc:
            return AnalyticalResponseEnvelope[LakehouseCostAnalytics](
                status="error",
                data_source="onelake_delta",
                error_code="LAKEHOUSE_READ_ERROR",
                error_message=f"Failed to read cost_details: {exc}",
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        if not records:
            empty_analytics = LakehouseCostAnalytics(
                connection_id=connection_id,
                subscription_id="unknown",
                date_range_start=start_date or "",
                date_range_end=end_date or "",
                total_records=0,
            )
            return AnalyticalResponseEnvelope[LakehouseCostAnalytics](
                status="success",
                data=empty_analytics,
                data_source="onelake_delta",
                records_count=0,
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        # Apply date filters
        filtered: list[dict[str, Any]] = []
        for r in records:
            u_date = r.get("usage_date", "")
            if start_date and u_date < start_date:
                continue
            if end_date and u_date > end_date:
                continue
            filtered.append(r)

        actual_start = min(
            (r.get("usage_date", "") for r in filtered), default=start_date or ""
        )
        actual_end = max(
            (r.get("usage_date", "") for r in filtered), default=end_date or ""
        )
        sub_id = (
            (filtered[0].get("subscription_id") or "unknown") if filtered else "unknown"
        )

        # 1. Total cost by currency (Strict separation)
        totals_by_curr: dict[str, Decimal] = defaultdict(Decimal)
        count_by_curr: dict[str, int] = defaultdict(int)

        # 2. Daily trend by (date, currency)
        daily_by_curr: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        daily_counts: dict[tuple[str, str], int] = defaultdict(int)

        # 3. Service cost by (service_name, currency)
        service_by_curr: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        service_counts: dict[tuple[str, str], int] = defaultdict(int)

        # 4. Charge type cost by (charge_type, currency)
        charge_type_map: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(Decimal)
        )

        for r in filtered:
            curr = str(r.get("currency") or "USD")
            cost_val = r.get("cost_in_billing_currency")
            cost_dec = (
                Decimal(str(cost_val)) if cost_val is not None else Decimal("0.0000")
            )

            totals_by_curr[curr] += cost_dec
            count_by_curr[curr] += 1

            u_date = r.get("usage_date", "")
            daily_by_curr[(u_date, curr)] += cost_dec
            daily_counts[(u_date, curr)] += 1

            s_name = str(r.get("service_name") or "Unknown")
            service_by_curr[(s_name, curr)] += cost_dec
            service_counts[(s_name, curr)] += 1

            ctype = str(r.get("charge_type") or "Usage")
            charge_type_map[ctype][curr] += cost_dec

        currency_totals = [
            CurrencyCostTotal(currency=c, total_cost=tot, record_count=count_by_curr[c])
            for c, tot in totals_by_curr.items()
        ]

        daily_trend = [
            DailyCostTrendPoint(
                usage_date=k[0],
                currency=k[1],
                daily_cost=val,
                record_count=daily_counts[k],
            )
            for k, val in sorted(daily_by_curr.items(), key=lambda x: x[0][0])
        ]

        service_breakdown = []
        for (s_name, curr), val in sorted(
            service_by_curr.items(), key=lambda x: x[1], reverse=True
        ):
            tot_for_curr = totals_by_curr[curr]
            pct = float((val / tot_for_curr) * 100) if tot_for_curr > 0 else 0.0
            service_breakdown.append(
                ServiceCostItem(
                    service_name=s_name,
                    currency=curr,
                    total_cost=val,
                    percentage=round(pct, 2),
                    record_count=service_counts[(s_name, curr)],
                )
            )

        analytics = LakehouseCostAnalytics(
            connection_id=connection_id,
            subscription_id=sub_id,
            date_range_start=actual_start,
            date_range_end=actual_end,
            total_by_currency=currency_totals,
            daily_trend=daily_trend,
            by_service=service_breakdown,
            by_charge_type={ct: dict(currs) for ct, currs in charge_type_map.items()},
            total_records=len(filtered),
        )

        self._put_in_cache(cache_key, analytics)
        duration_ms = int((time.time() - start_time) * 1000)

        return AnalyticalResponseEnvelope[LakehouseCostAnalytics](
            status="success",
            data=analytics,
            data_source="onelake_delta",
            is_live=True,
            records_count=len(filtered),
            query_duration_ms=duration_ms,
        )

    def get_metrics_summary(
        self,
        connection_id: str,
        resource_id: str,
        metric_names: list[str] | None = None,
        days: int = 7,
    ) -> AnalyticalResponseEnvelope[LakehouseMetricsSummary]:
        """Retrieve performance telemetry deduplicated across overlapping hourly sync windows.

        Uses deterministic hourly window grouping: for duplicate hourly intervals, selects
        the metric value associated with the most recent ingestion_timestamp.
        """
        start_time = time.time()
        m_names_str = ",".join(sorted(metric_names)) if metric_names else "all"
        cache_key = f"metric::{connection_id}::{resource_id}::{m_names_str}::{days}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return AnalyticalResponseEnvelope[LakehouseMetricsSummary](
                status="success",
                data=cached,
                data_source="onelake_delta",
                is_live=True,
                records_count=cached.total_points_evaluated,
                query_duration_ms=int((time.time() - start_time) * 1000),
                cache_hit=True,
            )

        try:
            records = self.reader.read_records_as_dicts(
                "resource_metrics",
                columns=[
                    "resource_id",
                    "metric_name",
                    "timestamp",
                    "average",
                    "maximum",
                    "minimum",
                    "unit",
                    "subscription_id",
                    "ingestion_timestamp",
                ],
            )
        except Exception as exc:
            return AnalyticalResponseEnvelope[LakehouseMetricsSummary](
                status="error",
                data_source="onelake_delta",
                error_code="LAKEHOUSE_READ_ERROR",
                error_message=f"Failed to read resource_metrics: {exc}",
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        if not records:
            empty_summary = LakehouseMetricsSummary(
                connection_id=connection_id,
                subscription_id="unknown",
                series=[],
                total_points_evaluated=0,
                distinct_time_buckets=0,
            )
            return AnalyticalResponseEnvelope[LakehouseMetricsSummary](
                status="success",
                data=empty_summary,
                data_source="onelake_delta",
                records_count=0,
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        # Filter to matching resource_id
        matched = [
            r
            for r in records
            if r.get("resource_id", "").lower() == resource_id.lower()
        ]
        if metric_names:
            names_lower = {m.lower() for m in metric_names}
            matched = [
                r for r in matched if r.get("metric_name", "").lower() in names_lower
            ]

        sub_id = (
            (matched[0].get("subscription_id") or "unknown") if matched else "unknown"
        )

        # ---------------------------------------------------------------------
        # Deduplication Strategy: Group by (metric_name, hourly_bucket)
        # Select record with latest ingestion_timestamp
        # ---------------------------------------------------------------------
        deduped_by_hour: dict[tuple[str, str], dict[str, Any]] = {}
        for r in matched:
            m_name = r.get("metric_name", "unknown")
            raw_ts = r.get("timestamp", "")
            hour_bucket = raw_ts[:13] if len(raw_ts) >= 13 else raw_ts
            pair_key = (m_name, hour_bucket)

            existing = deduped_by_hour.get(pair_key)
            if not existing:
                deduped_by_hour[pair_key] = r
            else:
                # Compare ingestion_timestamp
                cur_ing = r.get("ingestion_timestamp", "")
                prev_ing = existing.get("ingestion_timestamp", "")
                if cur_ing > prev_ing:
                    deduped_by_hour[pair_key] = r

        # Group clean points by metric_name
        series_by_name: dict[str, list[MetricSeriesPoint]] = defaultdict(list)
        unit_by_name: dict[str, str] = {}

        for (m_name, _), r in sorted(
            deduped_by_hour.items(), key=lambda x: x[1].get("timestamp", "")
        ):
            series_by_name[m_name].append(
                MetricSeriesPoint(
                    timestamp=r["timestamp"],
                    average=r.get("average"),
                    maximum=r.get("maximum"),
                    minimum=r.get("minimum"),
                )
            )
            unit_by_name[m_name] = r.get("unit") or "Count"

        result_series = []
        for m_name, points in series_by_name.items():
            valid_avgs = [p.average for p in points if p.average is not None]
            valid_maxs = [p.maximum for p in points if p.maximum is not None]
            valid_mins = [p.minimum for p in points if p.minimum is not None]

            avg_util = sum(valid_avgs) / len(valid_avgs) if valid_avgs else None
            peak_util = max(valid_maxs) if valid_maxs else None
            min_util = min(valid_mins) if valid_mins else None

            result_series.append(
                ResourceMetricSeries(
                    resource_id=resource_id,
                    metric_name=m_name,
                    unit=unit_by_name.get(m_name, "Count"),
                    average_utilization=round(avg_util, 2)
                    if avg_util is not None
                    else None,
                    peak_utilization=round(peak_util, 2)
                    if peak_util is not None
                    else None,
                    minimum_utilization=round(min_util, 2)
                    if min_util is not None
                    else None,
                    points_count=len(points),
                    points=points,
                )
            )

        summary = LakehouseMetricsSummary(
            connection_id=connection_id,
            subscription_id=sub_id,
            series=result_series,
            total_points_evaluated=len(matched),
            distinct_time_buckets=len(deduped_by_hour),
            coverage_percentage=100.0,
        )

        self._put_in_cache(cache_key, summary)
        duration_ms = int((time.time() - start_time) * 1000)

        return AnalyticalResponseEnvelope[LakehouseMetricsSummary](
            status="success",
            data=summary,
            data_source="onelake_delta",
            is_live=True,
            records_count=len(matched),
            query_duration_ms=duration_ms,
        )

    def get_token_telemetry_summary(
        self,
        connection_id: str,
        days: int = 30,
    ) -> AnalyticalResponseEnvelope[LakehouseTokenSummary]:
        """Query token_telemetry table with honest empty-table handling."""
        start_time = time.time()
        try:
            records = self.reader.read_records_as_dicts(
                "token_telemetry",
                columns=[
                    "event_id",
                    "model_name",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "estimated_cost_usd",
                    "timestamp",
                ],
            )
        except Exception as exc:
            return AnalyticalResponseEnvelope[LakehouseTokenSummary](
                status="error",
                data_source="onelake_delta",
                error_code="LAKEHOUSE_READ_ERROR",
                error_message=f"Failed to read token_telemetry: {exc}",
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        if not records:
            empty_token = LakehouseTokenSummary(
                connection_id=connection_id,
                has_data=False,
                total_events=0,
                message="No GenAI token telemetry has been ingested into Lakehouse.",
            )
            return AnalyticalResponseEnvelope[LakehouseTokenSummary](
                status="success",
                data=empty_token,
                data_source="onelake_delta",
                records_count=0,
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        total_p = sum(int(r.get("prompt_tokens", 0)) for r in records)
        total_c = sum(int(r.get("completion_tokens", 0)) for r in records)
        total_t = sum(int(r.get("total_tokens", 0)) for r in records)
        total_cost = sum(
            Decimal(str(r.get("estimated_cost_usd", "0.0"))) for r in records
        )

        summary = LakehouseTokenSummary(
            connection_id=connection_id,
            has_data=True,
            total_events=len(records),
            total_prompt_tokens=total_p,
            total_completion_tokens=total_c,
            total_tokens=total_t,
            total_cost_usd=total_cost,
            message="Token telemetry retrieved successfully from Lakehouse.",
        )
        return AnalyticalResponseEnvelope[LakehouseTokenSummary](
            status="success",
            data=summary,
            data_source="onelake_delta",
            is_live=True,
            records_count=len(records),
            query_duration_ms=int((time.time() - start_time) * 1000),
        )

    def get_sync_overview(
        self,
        connection_id: str,
        limit: int = 10,
    ) -> AnalyticalResponseEnvelope[LakehouseSyncOverview]:
        """Query sync_history table to determine data freshness and execution status."""
        start_time = time.time()
        try:
            records = self.reader.read_records_as_dicts(
                "sync_history",
                columns=[
                    "sync_id",
                    "connection_id",
                    "sync_type",
                    "status",
                    "records_extracted",
                    "records_written",
                    "duration_ms",
                    "started_at",
                    "completed_at",
                    "error_details",
                ],
            )
        except Exception as exc:
            return AnalyticalResponseEnvelope[LakehouseSyncOverview](
                status="error",
                data_source="onelake_delta",
                error_code="LAKEHOUSE_READ_ERROR",
                error_message=f"Failed to read sync_history: {exc}",
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        if not records:
            empty_overview = LakehouseSyncOverview(connection_id=connection_id)
            return AnalyticalResponseEnvelope[LakehouseSyncOverview](
                status="success",
                data=empty_overview,
                data_source="onelake_delta",
                records_count=0,
                query_duration_ms=int((time.time() - start_time) * 1000),
            )

        # Sort descending by started_at
        sorted_records = sorted(
            records, key=lambda x: x.get("started_at", ""), reverse=True
        )
        latest = sorted_records[0]

        successful_runs = [r for r in sorted_records if r.get("status") == "SUCCESS"]
        last_success_ts = (
            successful_runs[0].get("completed_at") if successful_runs else None
        )

        freshness_sec = None
        if last_success_ts:
            try:
                # ISO parsing
                clean_ts = last_success_ts.replace("Z", "+00:00")
                success_dt = datetime.fromisoformat(clean_ts)
                freshness_sec = int((datetime.now(UTC) - success_dt).total_seconds())
            except Exception:
                freshness_sec = None

        recent_entries = [
            SyncHistoryEntry(
                sync_id=r["sync_id"],
                connection_id=r["connection_id"],
                sync_type=r["sync_type"],
                status=r["status"],
                records_extracted=int(r.get("records_extracted", 0)),
                records_written=int(r.get("records_written", 0)),
                duration_ms=int(r.get("duration_ms", 0)),
                started_at=r["started_at"],
                completed_at=r.get("completed_at"),
                error_details=r.get("error_details"),
            )
            for r in sorted_records[:limit]
        ]

        overview = LakehouseSyncOverview(
            connection_id=connection_id,
            latest_status=latest.get("status"),
            last_successful_sync=last_success_ts,
            data_freshness_seconds=freshness_sec,
            total_sync_runs=len(sorted_records),
            success_runs=len(successful_runs),
            failed_runs=len(sorted_records) - len(successful_runs),
            recent_history=recent_entries,
        )

        return AnalyticalResponseEnvelope[LakehouseSyncOverview](
            status="success",
            data=overview,
            data_source="onelake_delta",
            is_live=True,
            last_sync_at=last_success_ts,
            data_freshness_seconds=freshness_sec,
            records_count=len(sorted_records),
            query_duration_ms=int((time.time() - start_time) * 1000),
        )
