# ruff: noqa: E402
"""Diagnostic inspection of resource_metrics Delta table for duplicate records.

Reads resource_metrics from OneLake in read-only mode and performs an in-depth
analysis of duplicate metric_record_id occurrences, value consistency, and distribution.
"""

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from deltalake import DeltaTable
import pyarrow as pa
import pyarrow.compute as pc

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from auth import AUDIENCE_STORAGE, AzureCliAuthManager
from config import SyncAgentConfig


def run_metrics_diagnostics() -> dict:
    config = SyncAgentConfig.load()
    auth_mgr = AzureCliAuthManager()
    storage_options = {
        "bearer_token": auth_mgr.get_token(AUDIENCE_STORAGE),
        "account_name": "onelake",
    }

    table_uri = config.get_table_uri("resource_metrics")
    print(f"Opening Delta Table at: {table_uri}")

    dt = DeltaTable(table_uri, storage_options=storage_options)
    version = dt.version()
    print(f"Delta Table Version: {version}")

    arrow_tbl = dt.to_pyarrow_table()
    total_rows = arrow_tbl.num_rows
    print(f"Total Rows in Table: {total_rows}")

    if total_rows == 0:
        return {"total_rows": 0, "status": "empty"}

    # Extract columns without relying on local timezone packages
    metric_ids = pc.cast(arrow_tbl.column("metric_record_id"), pa.string()).to_pylist()
    res_ids = pc.cast(arrow_tbl.column("resource_id"), pa.string()).to_pylist()
    m_names = pc.cast(arrow_tbl.column("metric_name"), pa.string()).to_pylist()
    timestamps = pc.cast(arrow_tbl.column("timestamp"), pa.string()).to_pylist()
    averages = arrow_tbl.column("average").to_pylist()
    maximums = arrow_tbl.column("maximum").to_pylist()
    minimums = arrow_tbl.column("minimum").to_pylist()
    units = pc.cast(arrow_tbl.column("unit"), pa.string()).to_pylist()
    ingestion_ts = pc.cast(arrow_tbl.column("ingestion_timestamp"), pa.string()).to_pylist()

    # Count occurrences of each metric_record_id
    id_counts = Counter(metric_ids)
    distinct_ids = len(id_counts)
    duplicate_ids = {k: v for k, v in id_counts.items() if v > 1}
    duplicate_rows_count = sum(v - 1 for v in duplicate_ids.values())
    total_duplicate_rows = sum(v for v in duplicate_ids.values())
    dup_percentage = (duplicate_rows_count / total_rows) * 100 if total_rows > 0 else 0.0

    print("=" * 80)
    print("METRICS DATA QUALITY GATE - DIAGNOSTIC SUMMARY")
    print("=" * 80)
    print(f"Total metric rows:                 {total_rows}")
    print(f"Distinct metric_record_id count:   {distinct_ids}")
    print(f"Unique IDs with duplicates:        {len(duplicate_ids)}")
    print(f"Excess duplicate rows:             {duplicate_rows_count}")
    print(f"Total rows involved in duplicates: {total_duplicate_rows}")
    print(f"Duplicate percentage:              {dup_percentage:.2f}%")

    # Check value consistency across duplicates
    # Group rows by metric_record_id
    rows_by_id = defaultdict(list)
    for idx in range(total_rows):
        m_id = metric_ids[idx]
        if m_id in duplicate_ids:
            rows_by_id[m_id].append({
                "resource_id": res_ids[idx],
                "metric_name": m_names[idx],
                "timestamp": timestamps[idx],
                "average": averages[idx],
                "maximum": maximums[idx],
                "minimum": minimums[idx],
                "unit": units[idx],
                "ingestion_timestamp": ingestion_ts[idx],
            })

    conflicting_ids = []
    identical_ids = []
    for m_id, row_list in rows_by_id.items():
        first = row_list[0]
        is_conflict = False
        for other in row_list[1:]:
            if (
                other["average"] != first["average"]
                or other["maximum"] != first["maximum"]
                or other["minimum"] != first["minimum"]
            ):
                is_conflict = True
                break
        if is_conflict:
            conflicting_ids.append(m_id)
        else:
            identical_ids.append(m_id)

    print(f"Duplicates with IDENTICAL metric values:   {len(identical_ids)} ({len(identical_ids) / len(duplicate_ids) * 100:.1f}%)" if duplicate_ids else "0")
    print(f"Duplicates with CONFLICTING metric values: {len(conflicting_ids)}")

    # Distribution by resource_id and metric_name
    dup_dist = Counter()
    for m_id, row_list in rows_by_id.items():
        sample = row_list[0]
        key = f"{sample['resource_id']} | {sample['metric_name']}"
        dup_dist[key] += 1

    print("\nTop Duplicate Distributions (Resource ID | Metric Name):")
    for key, count in dup_dist.most_common(10):
        print(f"  - {key}: {count} duplicate metric series points")

    # Sample duplicate records
    sample_dups = []
    for m_id in list(duplicate_ids.keys())[:3]:
        sample_dups.append({
            "metric_record_id": m_id,
            "occurrences": len(rows_by_id[m_id]),
            "records": rows_by_id[m_id],
        })

    print("\nSample Duplicate ID Analysis:")
    for s in sample_dups:
        print(f"\nID: {s['metric_record_id']} (Occurrences: {s['occurrences']})")
        for i, rec in enumerate(s["records"], 1):
            print(f"  [{i}] Timestamp: {rec['timestamp']} | Avg: {rec['average']} | Max: {rec['maximum']} | Min: {rec['minimum']} | Ingested: {rec['ingestion_timestamp']}")

    print("=" * 80)

    return {
        "total_rows": total_rows,
        "distinct_ids": distinct_ids,
        "duplicate_id_count": len(duplicate_ids),
        "excess_duplicate_rows": duplicate_rows_count,
        "duplicate_percentage": round(dup_percentage, 2),
        "identical_value_count": len(identical_ids),
        "conflicting_value_count": len(conflicting_ids),
        "distribution": dict(dup_dist.most_common(15)),
        "samples": sample_dups,
    }


if __name__ == "__main__":
    run_metrics_diagnostics()
