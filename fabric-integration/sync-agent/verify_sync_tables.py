# ruff: noqa: E402
"""Inspect and print detailed summaries and samples from OneLake Delta tables."""

import json
import sys
from pathlib import Path

import pyarrow as pa
from deltalake import DeltaTable

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from auth import AUDIENCE_STORAGE, AzureCliAuthManager
from config import SyncAgentConfig

config = SyncAgentConfig.load()
auth_mgr = AzureCliAuthManager()
storage_options = {
    "bearer_token": auth_mgr.get_token(AUDIENCE_STORAGE),
    "account_name": "onelake",
}

tables = ["resource_inventory", "cost_details", "resource_metrics", "sync_history"]

print("=" * 80)
print(f"LAKEHOUSE: {config.lakehouse_name} ({config.lakehouse_id})")
print(f"WORKSPACE: {config.workspace_id}")
print("=" * 80)

for t_name in tables:
    uri = config.get_table_uri(t_name)
    try:
        dt = DeltaTable(uri, storage_options=storage_options)
        version = dt.version()
        arrow_tbl = dt.to_pyarrow_table()
        num_rows = arrow_tbl.num_rows
        files = len(dt.file_uris())
        print(f"\nTABLE: {t_name}")
        print(f"  URI: {uri}")
        print(f"  Delta Version: {version} | Total Files: {files} | Row Count: {num_rows}")
        if num_rows > 0:
            print("  Columns:", arrow_tbl.column_names)
            print(f"  Sample Records (first {min(3, num_rows)}):")
            # Cast all columns to string via pyarrow compute to avoid tzdata dependency
            string_cols = {}
            for col in arrow_tbl.column_names:
                import pyarrow.compute as pc

                string_cols[col] = pc.cast(arrow_tbl.column(col), pa.string())
            for i in range(min(3, num_rows)):
                row_dict = {col: str(string_cols[col][i]) for col in arrow_tbl.column_names}
                print(f"    [{i + 1}] {json.dumps(row_dict, indent=2)}")
    except Exception as ex:
        print(f"\nTABLE: {t_name} ERROR: {ex}")

print("\n" + "=" * 80)
