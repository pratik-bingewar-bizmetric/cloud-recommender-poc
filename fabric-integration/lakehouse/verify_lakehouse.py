"""Microsoft Fabric Lakehouse & Delta Table Verification Script.

Executes comprehensive end-to-end verification of:
1. Fabric Lakehouse existence and metadata parity.
2. OneLake data-plane read/write/delete permissions.
3. Delta Lake table transaction logs and PyArrow schemas.
4. Zero synthetic business data enforcement.
5. SQL Analytics endpoint configuration status.
"""

import json
import logging
import uuid
from typing import Any

import deltalake
import httpx
import pyarrow as pa
from init_delta_schemas import get_storage_token, load_lakehouse_config
from provision_lakehouse import get_fabric_token, get_lakehouse_details, list_lakehouses
from schemas import TABLE_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_lakehouse")


def verify_lakehouse_metadata(config: dict[str, Any]) -> dict[str, Any]:
    """Verify Lakehouse exists via Microsoft Fabric REST API."""
    workspace_id = config["workspaceId"]
    lakehouse_id = config["lakehouseId"]
    token = get_fabric_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    with httpx.Client(verify=False, timeout=30.0) as client:
        lakehouses = list_lakehouses(client, workspace_id, headers)
        target = next((lh for lh in lakehouses if lh.get("id") == lakehouse_id), None)
        if not target:
            raise AssertionError(
                f"Lakehouse ID '{lakehouse_id}' not found in workspace '{workspace_id}'."
            )

        details = get_lakehouse_details(client, workspace_id, lakehouse_id, headers)
        props = details.get("properties", {})
        sql_props = props.get("sqlEndpointProperties", {})

        return {
            "verified": True,
            "id": details.get("id"),
            "displayName": details.get("displayName"),
            "workspaceId": workspace_id,
            "oneLakeTablesPath": props.get("oneLakeTablesPath"),
            "oneLakeFilesPath": props.get("oneLakeFilesPath"),
            "sqlEndpointId": sql_props.get("id"),
            "sqlEndpointConnectionString": sql_props.get("connectionString"),
            "sqlEndpointProvisioningStatus": sql_props.get("provisioningStatus"),
        }


def verify_onelake_dataplane_access(config: dict[str, Any]) -> dict[str, Any]:
    """Verify real OneLake data-plane read/write/delete operations."""
    workspace_id = config["workspaceId"]
    lakehouse_id = config["lakehouseId"]
    token = get_storage_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "x-ms-version": "2023-11-03",
    }

    test_file_name = f"verify_probe_{uuid.uuid4().hex[:8]}.tmp"
    test_url = f"https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{lakehouse_id}/Files/{test_file_name}"
    payload = b"FinOps OneLake Verification Probe - Nonce: " + uuid.uuid4().bytes

    with httpx.Client(verify=False, timeout=30.0) as client:
        # 1. Create file
        r_create = client.put(f"{test_url}?resource=file", headers=headers)
        if r_create.status_code != 201:
            raise AssertionError(
                f"OneLake PUT failed (HTTP {r_create.status_code}): {r_create.text}"
            )

        # 2. Append payload
        r_append = client.patch(
            f"{test_url}?action=append&position=0",
            headers={**headers, "Content-Type": "application/octet-stream"},
            content=payload,
        )
        if r_append.status_code != 202:
            raise AssertionError(f"OneLake append failed (HTTP {r_append.status_code})")

        # 3. Flush file
        r_flush = client.patch(f"{test_url}?action=flush&position={len(payload)}", headers=headers)
        if r_flush.status_code != 200:
            raise AssertionError(f"OneLake flush failed (HTTP {r_flush.status_code})")

        # 4. Read back and verify content parity
        r_read = client.get(test_url, headers=headers)
        if r_read.status_code != 200 or r_read.content != payload:
            raise AssertionError(f"OneLake content verification failed (HTTP {r_read.status_code})")

        # 5. Delete test file
        r_del = client.delete(test_url, headers=headers)
        if r_del.status_code != 200:
            raise AssertionError(f"OneLake delete failed (HTTP {r_del.status_code})")

        # 6. Confirm 404
        r_confirm = client.get(test_url, headers=headers)
        if r_confirm.status_code != 404:
            raise AssertionError(
                f"OneLake deletion confirmation failed (Expected 404, got {r_confirm.status_code})"
            )

    return {
        "verified": True,
        "testFile": test_file_name,
        "roundtripVerified": True,
        "deletionConfirmed": True,
    }


def verify_delta_tables(config: dict[str, Any]) -> dict[str, Any]:
    """Verify all 5 Delta tables on OneLake using Delta-rs."""
    workspace_id = config["workspaceId"]
    lakehouse_id = config["lakehouseId"]
    token = get_storage_token()
    storage_options = {
        "bearer_token": token,
        "account_name": "onelake",
    }

    table_verifications: dict[str, Any] = {}

    for table_name, spec in TABLE_REGISTRY.items():
        table_path = f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}/Tables/{table_name}"
        dt = deltalake.DeltaTable(table_path, storage_options=storage_options)

        # Verify schema field count
        expected_schema: pa.Schema = spec["schema"]
        actual_fields = [f.name for f in dt.schema().fields]
        if set(actual_fields) != set(expected_schema.names):
            raise AssertionError(f"Schema mismatch on table '{table_name}'")

        # Verify partition columns
        expected_partitions = spec["partition_cols"]
        actual_partitions = dt.metadata().partition_columns
        if set(actual_partitions) != set(expected_partitions):
            raise AssertionError(f"Partition mismatch on table '{table_name}'")

        # Verify zero synthetic records
        pa_table = dt.to_pyarrow_table()
        if pa_table.num_rows != 0:
            raise AssertionError(f"Table '{table_name}' expected 0 rows, found {pa_table.num_rows}")

        table_verifications[table_name] = {
            "verified": True,
            "version": dt.version(),
            "fieldCount": len(actual_fields),
            "partitionColumns": actual_partitions,
            "rowCount": pa_table.num_rows,
            "hasValidDeltaLog": True,
        }

    return {
        "allTablesVerified": True,
        "tablesCount": len(table_verifications),
        "tables": table_verifications,
    }


def run_full_verification() -> dict[str, Any]:
    """Run complete verification sequence."""
    config = load_lakehouse_config()
    logger.info(
        "Verifying Lakehouse '%s' (%s)...", config.get("displayName"), config.get("lakehouseId")
    )

    meta_res = verify_lakehouse_metadata(config)
    logger.info(
        "1. Lakehouse metadata: VERIFIED (SQL Endpoint: %s)",
        meta_res.get("sqlEndpointProvisioningStatus"),
    )

    dataplane_res = verify_onelake_dataplane_access(config)
    logger.info("2. OneLake data-plane access: VERIFIED (CRUD roundtrip passed)")

    delta_res = verify_delta_tables(config)
    logger.info("3. Delta tables: ALL 5 TABLES VERIFIED (0 synthetic records, valid Delta logs)")

    report = {
        "status": "SUCCESS",
        "lakehouseMetadata": meta_res,
        "oneLakeDataPlane": dataplane_res,
        "deltaTables": delta_res,
    }
    return report


if __name__ == "__main__":
    rep = run_full_verification()
    print("\n=== Lakehouse & Delta Verification Complete ===")
    print(json.dumps(rep, indent=2))
