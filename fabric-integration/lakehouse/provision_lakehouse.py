"""Microsoft Fabric Lakehouse Provisioning Script.

Idempotently provisions or retrieves 'finops_lakehouse' in workspace '672a6995-4190-4000-befd-5cc6479c3f74'
using the official Microsoft Fabric REST API:
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/lakehouses

Records:
- Lakehouse ID
- OneLake Tables Path
- OneLake Files Path
- SQL Analytics Endpoint Connection String & ID
- Provisioning Status
"""

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("provision_lakehouse")

DEFAULT_WORKSPACE_ID = "672a6995-4190-4000-befd-5cc6479c3f74"
DEFAULT_LAKEHOUSE_NAME = "finops_lakehouse"
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
CONFIG_PATH = Path(__file__).resolve().parent / "lakehouse_config.json"


def get_fabric_token() -> str:
    """Acquire Microsoft Fabric access token using local Azure CLI session."""
    az_cmd = shutil.which("az.cmd") or shutil.which("az") or "az"
    cmd = [
        az_cmd,
        "account",
        "get-access-token",
        "--resource",
        "https://api.fabric.microsoft.com",
        "--output",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Azure CLI failed to obtain Fabric access token: {proc.stderr}")
    data = json.loads(proc.stdout)
    token = data.get("accessToken")
    if not token:
        raise RuntimeError("Empty access token returned by Azure CLI.")
    return token


def list_lakehouses(
    client: httpx.Client, workspace_id: str, headers: dict[str, str]
) -> list[dict[str, Any]]:
    """List all Lakehouses in target workspace."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses"
    resp = client.get(url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list Lakehouses (HTTP {resp.status_code}): {resp.text}")
    return resp.json().get("value", [])


def get_lakehouse_details(
    client: httpx.Client, workspace_id: str, lakehouse_id: str, headers: dict[str, str]
) -> dict[str, Any]:
    """Retrieve complete metadata for a specific Lakehouse."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
    resp = client.get(url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to get Lakehouse details (HTTP {resp.status_code}): {resp.text}"
        )
    return resp.json()


def poll_fabric_operation(
    client: httpx.Client, op_url: str, headers: dict[str, str], timeout_sec: int = 180
) -> dict[str, Any]:
    """Poll an asynchronous Fabric LRO (Long Running Operation) until completion."""
    start_time = time.time()
    logger.info("Polling asynchronous Fabric operation: %s", op_url)
    while time.time() - start_time < timeout_sec:
        resp = client.get(op_url, headers=headers)
        if resp.status_code not in (200, 202):
            raise RuntimeError(
                f"Operation polling failed with HTTP {resp.status_code}: {resp.text}"
            )
        data = resp.json()
        status = data.get("status")
        logger.info("Operation status: %s (elapsed: %.1fs)", status, time.time() - start_time)
        if status in ("Succeeded", "Completed"):
            return data
        if status in ("Failed", "Canceled"):
            raise RuntimeError(f"Fabric LRO ended with status '{status}': {data.get('error')}")
        retry_after = int(resp.headers.get("Retry-After", "3"))
        time.sleep(max(retry_after, 2))
    raise TimeoutError(f"Fabric operation timed out after {timeout_sec} seconds: {op_url}")


def provision_or_get_lakehouse(
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    display_name: str = DEFAULT_LAKEHOUSE_NAME,
) -> dict[str, Any]:
    """Idempotently create or retrieve finops_lakehouse and return connection metadata."""
    token = get_fabric_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    with httpx.Client(verify=False, timeout=60.0) as client:
        # Step 1: Check if already exists
        existing = list_lakehouses(client, workspace_id, headers)
        for lh in existing:
            if lh.get("displayName") == display_name:
                logger.info(
                    "Existing Lakehouse '%s' found (ID: %s). Reusing.", display_name, lh.get("id")
                )
                details = get_lakehouse_details(client, workspace_id, lh.get("id"), headers)
                return _format_and_save_metadata(workspace_id, details)

        # Step 2: Create new Lakehouse
        create_url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses"
        payload = {
            "displayName": display_name,
            "description": "Cloud FinOps persistent analytical Lakehouse",
        }
        logger.info("Provisioning Lakehouse '%s' in workspace %s...", display_name, workspace_id)
        resp = client.post(create_url, json=payload, headers=headers)

        if resp.status_code == 201:
            details = resp.json()
            logger.info("Lakehouse provisioned synchronously (HTTP 201). ID: %s", details.get("id"))
        elif resp.status_code == 202:
            op_loc = resp.headers.get("Location") or resp.headers.get("operation-location")
            if not op_loc:
                raise RuntimeError(f"HTTP 202 received without Location header: {resp.headers}")
            poll_fabric_operation(client, op_loc, headers)
            # Retrieve created Lakehouse
            time.sleep(2)
            lakehouses = list_lakehouses(client, workspace_id, headers)
            target = next((lh for lh in lakehouses if lh.get("displayName") == display_name), None)
            if not target:
                raise RuntimeError(f"Lakehouse '{display_name}' not found after successful LRO.")
            details = get_lakehouse_details(client, workspace_id, target.get("id"), headers)
        else:
            raise RuntimeError(f"Failed to create Lakehouse (HTTP {resp.status_code}): {resp.text}")

        # Step 3: Wait for SQL Analytics endpoint provisioning if in progress
        lakehouse_id = details.get("id")
        sql_props = details.get("properties", {}).get("sqlEndpointProperties", {})
        poll_count = 0
        while sql_props.get("provisioningStatus") == "InProgress" and poll_count < 15:
            logger.info(
                "SQL analytics endpoint provisioning in progress... waiting 3s (poll %d/15)",
                poll_count + 1,
            )
            time.sleep(3)
            details = get_lakehouse_details(client, workspace_id, lakehouse_id, headers)
            sql_props = details.get("properties", {}).get("sqlEndpointProperties", {})
            poll_count += 1

        return _format_and_save_metadata(workspace_id, details)


def _format_and_save_metadata(workspace_id: str, details: dict[str, Any]) -> dict[str, Any]:
    props = details.get("properties", {})
    sql_props = props.get("sqlEndpointProperties", {})

    metadata = {
        "lakehouseId": details.get("id"),
        "displayName": details.get("displayName"),
        "description": details.get("description", ""),
        "workspaceId": workspace_id,
        "oneLakeTablesPath": props.get("oneLakeTablesPath"),
        "oneLakeFilesPath": props.get("oneLakeFilesPath"),
        "sqlEndpointId": sql_props.get("id"),
        "sqlEndpointConnectionString": sql_props.get("connectionString"),
        "sqlEndpointProvisioningStatus": sql_props.get("provisioningStatus"),
    }

    # Persist config file
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Lakehouse metadata saved to %s", CONFIG_PATH)
    return metadata


if __name__ == "__main__":
    meta = provision_or_get_lakehouse()
    print("\n=== Lakehouse Provisioning Completed Successfully ===")
    print(json.dumps(meta, indent=2))
