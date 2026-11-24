# Databricks Billing Ingestion Fix & Operational Remediation Report

**Repository:** `cloud-recommender-poc`  
**Target Environment:** Azure Databricks Dev (`adb-deaccelerator-dev`)  
**Workspace ID:** `642006393507276`  
**Workspace URL:** `https://adb-642006393507276.16.azuredatabricks.net`  
**SQL Warehouse ID:** `05ed10a52697a344` (`Serverless Starter Warehouse`)  
**Azure CLI Identity:** `pratik.bingewar@bizmetric.com`  
**Date:** November 23, 2026  
**Status:** Fixes Implemented & Validated  

---

## 1. Executive Summary

To resolve the discrepancy between the workspace reporting `CONNECTED` and billing data appearing empty (`"—"`), we implemented critical UX transparency, dynamic schema bindings, and operational runbooks while **strictly preserving the zero-execution and human-approval safety guardrails**.

The platform now:
1. Clearly displays a **governance banner** informing operators that live System Tables are verified and ready, but warehouse compute is currently suspended (`STOPPED`).
2. Explains the exact reason why KPIs show `"—"` (awaiting authorized ingestion rather than a broken connection).
3. Replaces static mock values in Cost Allocation and Cost Explorer with dynamic bindings to real API state.
4. Provides full operational commands for authorized administrators to safely resume compute and execute approved ingestion runs.

---

## 2. Implemented Codebase Enhancements

### 2.1 Governance & Operational Transparency Alert Banners
In `fabric-integration/finops-app/packages/frontend/src/components/FinOpsCommandCenterView.tsx`:
- Added prominent status alerts to **Executive Cost Overview**, **Cost Explorer**, and **Cost Allocation** when `status === "BLOCKED_PENDING_APPROVAL"`.
- The banner explicitly informs the operator:
  - Workspace is **Connected** (`pratik.bingewar@bizmetric.com`).
  - Unity Catalog schemas `system.billing.usage` and `system.billing.list_prices` are verified present.
  - Target SQL Warehouse `Serverless Starter Warehouse` (`05ed10a52697a344`) is **STOPPED**.
  - Compute auto-resume is prohibited by FinOps safety policies.
  - Directs the user to request an approval token and authorize compute startup.

### 2.2 Replaced Static Mock Cards with Live Dynamic Bindings
In `fabric-integration/finops-app/packages/frontend/src/components/FinOpsCommandCenterView.tsx`:
- **Cost Allocation:** Replaced hardcoded `$164,360` and `$12,480` with:
  - `allocData?.kpis.allocated_spend?.formatted_value ?? (isLoading ? "..." : "—")`
  - `allocData?.kpis.unallocated_spend?.formatted_value ?? (isLoading ? "..." : "—")`
  - `allocData?.kpis.active_rules?.formatted_value ?? (isLoading ? "..." : "—")`
  - `allocData?.kpis.shared_pool?.formatted_value ?? (isLoading ? "..." : "—")`
- **Cost Explorer:** Replaced hardcoded `$176,840` and `$0.148` with:
  - `costData?.kpis.gross_consumption?.formatted_value ?? (isLoading ? "..." : "—")`
  - `costData?.kpis.effective_rate?.formatted_value ?? (isLoading ? "..." : "—")`
  - `costData?.kpis.unallocated_spend?.formatted_value ?? (isLoading ? "..." : "—")`
  - `costData?.kpis.credits_discounts?.formatted_value ?? (isLoading ? "..." : "—")`

### 2.3 Strict Adherence to Zero-Mutation Guardrails
- Under no circumstances will the backend auto-start the warehouse during regular browsing or status polling.
- Warehouse compute is started only when an authorized operator explicitly authorizes it.

---

## 3. Operational Runbook: How to Retrieve Live Billing Data

When an authorized administrator decides to execute live billing ingestion, follow this 4-step procedure:

### Step 1: Verify Azure CLI Session & Warehouse State
Ensure Azure CLI is logged in as `pratik.bingewar@bizmetric.com`:
```bash
az account show
```
Inspect the current warehouse state (read-only):
```bash
backend/.venv/Scripts/python.exe -c "
from cloud_recommender.services.databricks.sql_client import DatabricksSqlService
svc = DatabricksSqlService()
print(svc.check_warehouse_status())
"
```

### Step 2: Resume SQL Warehouse Compute (Operator Action)
Because the platform complies with zero-execution guardrails, warehouse startup must be explicitly executed:
```bash
# Via Databricks CLI or Databricks SDK
databricks warehouses start 05ed10a52697a344
```
Wait approximately 45-60 seconds until the warehouse enters `RUNNING` state.

### Step 3: Request Cryptographic Approval Token
Request a single-use authorization token for the ingestion query via the FinOps API:
```bash
curl -X POST http://localhost:8000/api/v1/finops/ingestion/approval-token \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <USER_SESSION_TOKEN>" \
  -d '{
    "workspace_id": "642006393507276",
    "warehouse_id": "05ed10a52697a344",
    "query": "SELECT record_id, account_id, workspace_id, sku_name, cloud, usage_start_time, usage_end_time, usage_date, usage_unit, usage_quantity, record_type, ingestion_date, billing_origin_product, product_features, usage_metadata, custom_tags FROM system.billing.usage WHERE workspace_id = '\''642006393507276'\'' AND usage_date >= '\''2026-11-01'\'' AND usage_date <= '\''2026-11-23'\'' ORDER BY usage_start_time DESC LIMIT 100",
    "start_date": "2026-11-01",
    "end_date": "2026-11-23",
    "max_rows": 100,
    "ttl_seconds": 600,
    "approval_purpose": "Operator approved live ingestion of Databricks billing events"
  }'
```

### Step 4: Execute Approved Ingestion Run
Submit the approved token to execute the read-only extract:
```bash
curl -X POST http://localhost:8000/api/v1/finops/ingestion/run \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "642006393507276",
    "start_date": "2026-11-01",
    "end_date": "2026-11-23",
    "limit": 100,
    "is_approved": true,
    "approval_token": "<TOKEN_FROM_STEP_3>",
    "source_table": "system.billing.usage"
  }'
```

Once completed:
1. `_usage_store` in `BillingIngestionService` contains the extracted records.
2. Ingest `system.billing.list_prices` similarly to populate `_price_store` for deterministic pricing joins.
3. Refreshing the FinOps Command Center instantly populates Executive Overview, Cost Explorer, Cost Allocation, and Showback/Chargeback with live calculated spend metrics!

---

## 4. Verification & Automated Test Results

The following test suites were executed and verified clean:

### 4.1 Backend Pytest Suites
Executed command:
```bash
$env:PYTHONPATH="backend"; backend/.venv/Scripts/pytest.exe \
  backend/tests/test_databricks_workspace.py \
  backend/tests/test_databricks_phase4_e2e.py \
  backend/tests/test_finops_analytics.py \
  backend/tests/test_live_finops_integration.py \
  backend/tests/test_m7_1_billing_hardening.py
```
**Result:** **149 passed in 17.32s** (0 errors, 0 failures, 0 warnings).

### 4.2 Frontend Vitest Suites
Executed command:
```bash
npm --prefix fabric-integration/finops-app/packages/frontend test
```
**Result:** **20 test files passed, 193 tests passed in 31.31s** (0 errors, 0 failures).

### 4.3 Frontend Production Build
Executed command:
```bash
npm --prefix fabric-integration/finops-app/packages/frontend run build
```
**Result:** **Vite production build succeeded in 11.02s** with 3,989 modules transformed and 0 compilation errors.

---
*Verified on 2026-11-23.*

