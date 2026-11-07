"""Read-only diagnostics and data quality verification for OneLake Delta tables.

Implements the Section 3 Metrics Data Quality Gate and provides table-level
integrity checks for production operations.
"""

import logging
from collections import Counter, defaultdict
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .config import LakehouseReaderConfig
from .delta_reader import OneLakeDeltaReader

logger = logging.getLogger("finops_udf.lakehouse.diagnostics")


class LakehouseDiagnostics:
    """Performs deep analytical audits on OneLake Delta tables without modifying state."""

    def __init__(
        self,
        reader: OneLakeDeltaReader | None = None,
        config: LakehouseReaderConfig | None = None,
    ) -> None:
        self.config = config or LakehouseReaderConfig.load()
        self.reader = reader or OneLakeDeltaReader(config=self.config)

    def diagnose_metrics_quality(self) -> dict[str, Any]:
        """Perform comprehensive data quality audit on resource_metrics Delta table.

        Investigates duplicate metric_record_id occurrences, timestamp shifting,
        hourly bucket overlap, and value consistency.
        """
        table_name = "resource_metrics"
        arrow_tbl = self.reader.read_table(
            table_name,
            columns=[
                "metric_record_id",
                "resource_id",
                "metric_name",
                "timestamp",
                "average",
                "maximum",
                "minimum",
                "unit",
                "ingestion_timestamp",
            ],
        )

        total_rows = arrow_tbl.num_rows
        if total_rows == 0:
            return {
                "status": "empty",
                "total_rows": 0,
                "distinct_record_ids": 0,
                "duplicate_record_ids": 0,
                "duplicate_percentage": 0.0,
                "message": "resource_metrics table is empty or unpopulated.",
            }

        # Convert columns cleanly without tzdata dependency
        metric_ids = pc.cast(
            arrow_tbl.column("metric_record_id"), pa.string()
        ).to_pylist()
        res_ids = pc.cast(arrow_tbl.column("resource_id"), pa.string()).to_pylist()
        m_names = pc.cast(arrow_tbl.column("metric_name"), pa.string()).to_pylist()
        timestamps = pc.cast(arrow_tbl.column("timestamp"), pa.string()).to_pylist()
        averages = arrow_tbl.column("average").to_pylist()
        maximums = arrow_tbl.column("maximum").to_pylist()
        minimums = arrow_tbl.column("minimum").to_pylist()
        units = pc.cast(arrow_tbl.column("unit"), pa.string()).to_pylist()
        ingestion_ts = pc.cast(
            arrow_tbl.column("ingestion_timestamp"), pa.string()
        ).to_pylist()

        # 1. Exact metric_record_id duplicate analysis
        id_counts = Counter(metric_ids)
        distinct_ids = len(id_counts)
        exact_duplicate_ids = {k: v for k, v in id_counts.items() if v > 1}
        exact_excess_dups = sum(v - 1 for v in exact_duplicate_ids.values())
        exact_dup_pct = (
            (exact_excess_dups / total_rows) * 100.0 if total_rows > 0 else 0.0
        )

        # 2. Hourly Bucket Temporal Overlap Analysis
        # When Azure Monitor timespan shifts by minutes between sync cycles, timestamps differ by minutes
        # but represent the same hourly interval.
        hourly_buckets = Counter()
        hourly_records = defaultdict(list)
        for idx in range(total_rows):
            ts_str = timestamps[idx]  # e.g. "2026-10-29 13:52:00.000000Z"
            hour_key = ts_str[:13] if len(ts_str) >= 13 else ts_str  # "2026-10-29 13"
            composite_key = f"{res_ids[idx]}::{m_names[idx]}::{hour_key}"
            hourly_buckets[composite_key] += 1
            hourly_records[composite_key].append(
                {
                    "metric_record_id": metric_ids[idx],
                    "timestamp": ts_str,
                    "average": averages[idx],
                    "maximum": maximums[idx],
                    "minimum": minimums[idx],
                    "unit": units[idx],
                    "ingestion_timestamp": ingestion_ts[idx],
                }
            )

        distinct_hourly_buckets = len(hourly_buckets)
        overlapping_hourly_buckets = {k: v for k, v in hourly_buckets.items() if v > 1}
        excess_temporal_dups = sum(v - 1 for v in overlapping_hourly_buckets.values())
        temporal_dup_pct = (
            (excess_temporal_dups / total_rows) * 100.0 if total_rows > 0 else 0.0
        )

        # 3. Check for conflicting vs identical metric values across overlapping hourly buckets
        conflicting_buckets = 0
        identical_buckets = 0
        for comp_key, points in hourly_records.items():
            if len(points) <= 1:
                continue
            first = points[0]
            conflict = False
            for p in points[1:]:
                if (
                    p["average"] != first["average"]
                    or p["maximum"] != first["maximum"]
                    or p["minimum"] != first["minimum"]
                ):
                    conflict = True
                    break
            if conflict:
                conflicting_buckets += 1
            else:
                identical_buckets += 1

        # 4. Distribution by resource and metric name
        dist_by_resource_metric = Counter()
        for comp_key in overlapping_hourly_buckets:
            parts = comp_key.split("::")
            dist_key = f"{parts[0].split('/')[-1]} | {parts[1]}"
            dist_by_resource_metric[dist_key] += 1

        return {
            "status": "success",
            "total_rows": total_rows,
            "distinct_metric_record_ids": distinct_ids,
            "exact_duplicate_ids_count": len(exact_duplicate_ids),
            "exact_duplicate_percentage": round(exact_dup_pct, 2),
            "distinct_hourly_buckets": distinct_hourly_buckets,
            "overlapping_hourly_buckets_count": len(overlapping_hourly_buckets),
            "temporal_duplicate_percentage": round(temporal_dup_pct, 2),
            "identical_value_buckets": identical_buckets,
            "conflicting_value_buckets": conflicting_buckets,
            "distribution_sample": dict(dist_by_resource_metric.most_common(10)),
            "deduplication_recommendation": (
                "Analytical aggregations should group by (resource_id, metric_name, date_trunc_hour) "
                "and select the row with the most recent ingestion_timestamp to prevent double counting."
            ),
        }
