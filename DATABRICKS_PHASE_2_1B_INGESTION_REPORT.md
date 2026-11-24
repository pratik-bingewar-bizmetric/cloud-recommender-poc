# Phase 2.1B: Databricks Billing Ingestion Audit & Runtime Execution Report

> **Document Status:** Active Engineering Record  
> **Phase:** 2.1B — Live Databricks Ingestion & Auto-Reconciliation  
> **Date:** 2026-11-23  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/gcp-service-account-integration`  
> **Execution Status:** **BLOCKED (Zero-Execution Guardrail Enforced)**

---

## 1. Executive Summary & Status

Phase 2.1B preflight and live verification were executed against Azure Databricks workspace `642006393507276`.
All preflight prerequisites (Azure CLI delegated authentication, PostgreSQL schema and tables, cryptographic approval engine, and Statement Execution chunk parser) are fully verified and operational.

Execution is **BLOCKED** by the live state of the target SQL Warehouse:
- **Target Warehouse:** `Serverless Starter Warehouse` (`05ed10a52697a344`)
- **Observed State:** **`STOPPED`** (`WAREHOUSE_STOPPED`)
- **Zero-Execution Guardrail:** In accordance with repository principles and user instructions, the application strictly refuses to automatically resume, start, or modify customer cloud compute resources.

| Capability / Check | Target Environment | Verified Result | Status |
| :--- | :--- | :--- | :--- |
| **Workspace Authentication** | `adb-642006393507276.16.azuredatabricks.net` | Azure CLI (`pratik.bingewar@bizmetric.com`) | **OPERATIONAL** |
| **SQL Warehouse State** | `05ed10a52697a344` (2X-Small) | `STOPPED` (Auto-stop: 5 mins) | **BLOCKED (Awaiting Operator)** |
| **PostgreSQL Connectivity** | Local / Docker PostgreSQL | Connected (`SELECT 1` succeeded) | **OPERATIONAL** |
| **Database Schema Tables** | `billing_usage_records`, `billing_price_records`, `billing_ingestion_runs` | Verified present, clean schema | **OPERATIONAL** |
| **Application Approval API** | `POST /api/v1/finops/ingestion/approve-and-run` | Auditable token generated, secret redacted | **OPERATIONAL** |
| **Result Chunk Pagination** | `DatabricksSqlService._collect_complete_result` | Follows `next_chunk_index` until exhausted | **OPERATIONAL** |

---

## 2. Preflight Audit & Live Telemetry

### 2.1 Databricks Workspace & Authentication Verification
- **Host URL:** `https://adb-642006393507276.16.azuredatabricks.net`
- **Authentication Method:** Azure CLI Delegated Token (`az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d`)
- **Authenticated Identity:** `pratik.bingewar@bizmetric.com` (Tenant ID: `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`)
- **Workspace Connectivity:** Verified via Databricks SDK `current_user.me()`.

### 2.2 SQL Warehouse Status Probe
- **Warehouse ID:** `05ed10a52697a344`
- **Name:** `Serverless Starter Warehouse`
- **Size / Cluster Size:** `2X-Small`
- **Auto-stop Configured:** 5 minutes
- **Num Active Clusters:** `0`
- **State Observed:** `STOPPED`
- **Diagnostic Message:** `Warehouse 'Serverless Starter Warehouse' (05ed10a52697a344) is STOPPED. Approval required before resuming compute for live ingestion.`

### 2.3 PostgreSQL Schema & Table Readiness
The following target PostgreSQL tables were checked via SQLAlchemy session factory:
1. `billing_usage_records`: Present, row count = 0
2. `billing_price_records`: Present, row count = 0
3. `billing_ingestion_runs`: Present, row count = 0
4. `billing_approval_tokens`: Present, row count = 1 (audit token `tok-k1-2026` from approval pre-check)

---

## 3. Ingestion Architecture & Chunk Pagination Design

The application ingestion pipeline is designed to extract, transform, and persist live Databricks billing data without loss or truncation:

### 3.1 Multi-Chunk Pagination Handling
Databricks Statement Execution API limits individual response sizes and splits large datasets into numbered result chunks:
```python
# Verified in backend/src/cloud_recommender/services/databricks/sql_client.py
while True:
    for row_vals in result.data_array or []:
        rows.append(dict(zip(columns, row_vals, strict=False)))
    chunks_read += 1
    next_index = result.next_chunk_index
    if next_index is None:
        break
    result = api.get_statement_result_chunk_n(statement_id, next_index)
```
- Rejects truncated manifests (`manifest.truncated == True`).
- Validates extracted row count against `manifest.total_row_count`.
- Bounded by query timeout (`databricks_query_timeout_seconds`), failing safely on timeouts.

### 3.2 Idempotency & Record Lineage
- **Idempotent Upsert Key:** `record_id` + `source_row_hash` (SHA-256 hash of provisional row identity: workspace, record_id, sku, record_type, time window, unit, quantity).
- **Record Types Supported:** `original`, `retraction`, `correction`.
- **Exact Precision:** Metered usage quantity stored in `Numeric(38, 18)` without float rounding.

---

## 4. Operational Runbook to Resume Live Extraction

When an authorized human operator decides to run live billing extraction:

1. **Start SQL Warehouse in Databricks Console:**
   - Navigate to: `https://adb-642006393507276.16.azuredatabricks.net/sql/warehouses`
   - Select `Serverless Starter Warehouse` (`05ed10a52697a344`).
   - Click **Start**. Wait until state changes from `STOPPED` to `RUNNING` (typically 10-15 seconds for Serverless).

2. **Trigger Ingestion from FinOps Command Center UI:**
   - In the FinOps application Executive Overview banner, click **Approve & Start Ingestion (Usage)**.
   - Alternatively, trigger via API:
     ```bash
     curl -X POST "http://localhost:8000/api/v1/finops/ingestion/approve-and-run" \
       -H "Content-Type: application/json" \
       -H "Authorization: Bearer <operator-token>" \
       -d '{
         "workspace_id": "642006393507276",
         "source_table": "system.billing.usage",
         "start_date": "2026-11-01",
         "end_date": "2026-11-23"
       }'
     ```

3. **Verify Automatic Pipeline:**
   - Backend checks `check_warehouse_status() -> RUNNING`.
   - Generates internal cryptographic approval token.
   - Executes bounded read-only SQL via Statement Execution API.
   - Iterates all result chunks until `next_chunk_index` is exhausted.
   - Persists records into PostgreSQL `billing_usage_records`.
   - Reconciles against `billing_price_records`.
   - Returns full counts to UI without exposing token secrets.

