# Databricks Live Billing Data Root Cause Analysis & Diagnostic Report

**Repository:** `cloud-recommender-poc`  
**Target Environment:** Azure Databricks Dev (`adb-deaccelerator-dev`)  
**Workspace ID:** `642006393507276`  
**Workspace Host:** `https://adb-642006393507276.16.azuredatabricks.net`  
**Target SQL Warehouse:** `Serverless Starter Warehouse` (`05ed10a52697a344`)  
**Active Azure CLI Identity:** `pratik.bingewar@bizmetric.com` (Tenant ID: `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`)  
**Date:** November 23, 2026  
**Status:** Root Cause Identified & Documented  

---

## 1. Executive Summary

In the FinOps application, the Databricks workspace connection displays **`CONNECTED`**, yet pages across the platform (Executive Cost Overview, Cost Explorer, Cost Allocation, and Showback & Chargeback) render empty spend metrics or **`"—"`** for critical KPIs (Total spend, Databricks spend, AI spend, DBU consumption).

A live end-to-end diagnosis of all 12 architectural layers revealed that **the core authentication, token acquisition, workspace REST APIs, and Unity Catalog metadata inspection are 100% operational**. The absence of live billing data is **NOT an authentication failure or bug in workspace communication**, but the intended result of strict FinOps security guardrails coupled with suspended warehouse compute and empty in-memory ingestion stores:

1. **SQL Warehouse is `STOPPED`:** The designated target warehouse (`Serverless Starter Warehouse`, ID: `05ed10a52697a344`) is in state `State.STOPPED`.
2. **Zero-Execution / Human Approval Policy Enforced:** In compliance with repository guardrails (`AGENTS.md`), the application strictly prohibits automatic warehouse resume or compute mutations without explicit human approval. Resuming compute incurs live Databricks/Azure charges.
3. **Approval Gate Active:** Ingestion queries against `system.billing.usage` and `system.billing.list_prices` are gated behind cryptographically signed, single-use approval tokens issued to operators with the `FinOpsAdmin` role.
4. **Zero Billing Rows Ingested (`_usage_store = {}`):** Because no approved ingestion run has executed against running compute, the repository's billing store contains 0 records.
5. **Frontend Rendering Mapping:** When `_usage_store` contains 0 records, the backend returns KPI metrics with `value: null` and `status: "BLOCKED_PENDING_APPROVAL"`. The frontend renders `value === null` as `"—"`.

---

## 2. Comprehensive 12-Layer Architecture Status Table

The following status matrix documents the live runtime verification conducted against the actual cloud environment:

| Layer # | Architecture Layer | Status | Live Evidence & Diagnostics |
| :---: | :--- | :---: | :--- |
| **1** | **Azure CLI Authentication** | **OPERATIONAL** | `az account show` verified user `pratik.bingewar@bizmetric.com` on tenant `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` (subscription: `Microsoft Azure India`). CLI binary: `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.CMD`. |
| **2** | **Databricks Token Acquisition** | **OPERATIONAL** | `AzureCliCredentialProvider.get_access_token()` acquired a valid delegated JWT bearer token for resource `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d` (Databricks Azure App ID) of length 2,623 characters. |
| **3** | **Workspace Client API** | **OPERATIONAL** | `WorkspaceClient(host="https://adb-642006393507276.16.azuredatabricks.net", auth_type="azure-cli")` authenticated successfully. Calling `client.current_user.me()` returned: ID `146809578344068`, user `pratik.bingewar@bizmetric.com`, name `Pratik Bingewar`. Connection status: `CONNECTED`. |
| **4** | **Warehouse Access & Permissions** | **METADATA ACCESSIBLE / COMPUTE STOPPED** | `client.warehouses.get("05ed10a52697a344")` returned `Serverless Starter Warehouse` in `State.STOPPED`. User possesses verified `CAN_USE` permissions on the warehouse. |
| **5** | **SQL Statement Execution** | **BLOCKED BY DESIGN** | `DatabricksSqlService.execute_read_only_statement` enforces AST read-only validation, single-use HMAC token verification, and checks warehouse state. Because the warehouse is `STOPPED`, execution raises `WarehouseStoppedError` to prevent unapproved billable auto-startup. |
| **6** | **`system.billing.usage` Schema** | **VERIFIED ACCESSIBLE (METADATA)** | Read-only SDK catalog probe (`client.tables.list("system", "billing")`) confirmed `system.billing.usage` exists in Unity Catalog metadata without waking up compute. Table has not been queried via SQL due to stopped compute. |
| **7** | **`system.billing.list_prices` Schema** | **VERIFIED ACCESSIBLE (METADATA)** | Verified present in Unity Catalog `system.billing` alongside `attributed_usage`. Unqueried due to stopped compute. |
| **8** | **Billing Ingestion Service** | **APPROVAL REQUIRED / ZERO ROWS** | `BillingIngestionService` repository `_usage_store` contains 0 rows and `_price_store` contains 0 rows. Ingestion status reports `system_tables_status="APPROVAL_REQUIRED"` and `total_usage_records_ingested=0`. |
| **9** | **Database Persistence Layer** | **READY / 0 ROWS STORED** | PostgreSQL database (`localhost:5432/cloud_recommender`) has migrated tables: `billing_usage_records`, `billing_price_records`, `billing_ingestion_runs`, `billing_approval_tokens`. All contain 0 rows because live ingestion has not yet occurred. |
| **10** | **Executive Cost Overview** | **BLOCKED_PENDING_APPROVAL** | Endpoint `/api/v1/finops/overview` receives 0 billing rows, returning all spend KPIs with `status: "BLOCKED_PENDING_APPROVAL"` and `value: null`. UI renders `"—"`. |
| **11** | **Cost Allocation** | **BLOCKED_PENDING_APPROVAL** | Endpoint `/api/v1/finops/cost-allocation` receives 0 billing rows; returns empty allocation structures and `BLOCKED_PENDING_APPROVAL` status. |
| **12** | **Showback & Chargeback** | **BLOCKED_PENDING_APPROVAL** | Endpoint `/api/v1/finops/showback-chargeback` receives 0 billing rows; returns empty department statements. |

---

## 3. Detailed Root Cause Analysis

### 3.1 Why Workspace Shows `CONNECTED` While Billing Data Is Missing

The workspace connection status and the billing data pipeline are decoupled by design:
- **Workspace Connectivity (Control Plane):** The workspace connection is validated via the Databricks Workspace REST API (`current_user.me()` and `clusters.list()`), which does not require a running SQL warehouse. Azure CLI delegated authentication succeeds, so the connection state is accurately reported as `CONNECTED`.
- **Billing Data Pipeline (Data Plane):** Databricks System Tables (`system.billing.usage`, `system.billing.list_prices`) cannot be retrieved via standard REST endpoints; they must be queried via Databricks SQL execution on an active SQL warehouse.

### 3.2 Why the SQL Warehouse Is `STOPPED`

The configured warehouse `05ed10a52697a344` (`Serverless Starter Warehouse`) auto-stopped after its configured idle period (`auto_stop_mins: 15`). This is standard cloud FinOps behavior to avoid unnecessary compute charges.

### 3.3 Strict Enforcement of Zero Compute Mutation Policy

Under `AGENTS.md` (Principle 1 & Protected Boundaries):
> *"The POC must NEVER execute infrastructure changes automatically against customer subscriptions... Zero-execution decoupling: never auto-starts or resumes stopped warehouse compute."*

In `backend/src/cloud_recommender/services/databricks/sql_client.py`:
```python
wh_health = self.check_warehouse_status()
if wh_health.warehouse_state == "STOPPED":
    raise WarehouseStoppedError(wh_health.warehouse_id, wh_health.warehouse_name)
```
When `execute_read_only_statement` detects `State.STOPPED`, it halts immediately with `WarehouseStoppedError`. It deliberately **does not call** `client.warehouses.start(id=...)`.

### 3.4 Cryptographic Human Approval Gate

Even if compute were active, querying live System Tables requires a role-authorized, HMAC-signed approval token issued via:
`POST /api/v1/finops/ingestion/approval-token`
- Requires caller role `FinOpsAdmin`.
- Enforces an exact query hash, workspace ID, warehouse ID, max row limit, and TTL.
- Enforces single-use consumption in database ledger (`billing_approval_tokens`).

### 3.5 In-Memory Store Initialization

In `backend/src/cloud_recommender/services/databricks/billing_ingestion_service.py`:
```python
self._usage_store: dict[str, BillingUsageRecord] = {}
self._price_store: list[BillingPriceRecord] = []
self._runs_store: list[BillingIngestionRunResponse] = []
```
The ingestion service holds records in memory. Because no live ingestion has run against running compute, `_usage_store` is empty.

### 3.6 Frontend KPI Display Behavior

In `backend/src/cloud_recommender/services/databricks/finops_analytics_service.py`:
```python
if not rows:
    msg = {"source": "system.billing.usage", "caveats": bill_prov.message, ...}
    kpis = {
        "total_spend": self._mk_kpi("total_spend", "USD", blocked, **msg),
        "databricks_spend": self._mk_kpi("databricks_spend", "USD", blocked, **msg), ...
    }
```
When `rows` is empty, `self._mk_kpi` sets `value=None` and `text="-"`.
In `fabric-integration/finops-app/packages/frontend/src/components/FinOpsCommandCenterView.tsx`:
```tsx
val: overviewData?.kpis.total_spend?.formatted_value ?? (isLoading ? "..." : "—")
```
When `formatted_value` is `"-"` (or `null`), the UI displays `"—"` with subtitle `Status: BLOCKED_PENDING_APPROVAL`.

Furthermore, prior to our updates, Cost Explorer and Cost Allocation cards had static fallback numbers (`$176,840` and `$164,360`) rather than reflecting the real blocked API state.

---

## 4. Summary of Root Cause

The lack of Databricks live billing data is caused by:
1. **Target SQL Warehouse compute is STOPPED (`State.STOPPED`).**
2. **Strict Zero-Execution guardrail prohibits auto-starting compute.**
3. **No approved ingestion run has been triggered with a valid `FinOpsAdmin` authorization token.**
4. **The in-memory billing repository starts empty upon service initialization.**
5. **The frontend did not previously display an explicit governance banner explaining that compute is suspended and awaiting human approval.**

---
*Report verified against live Azure Databricks workspace `642006393507276` on 2026-11-23.*

