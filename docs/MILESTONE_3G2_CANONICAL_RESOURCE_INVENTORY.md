# Milestone 3G.2 — Canonical Resource Inventory Closure Report

**Repository:** `cloud-recommender-poc`  
**Branch:** `feature/databricks-apps-integration`  
**Workspace:** Azure Databricks `642006393507276` (`Azure Databricks Dev`)  
**Status:** Certified & Inventory-Locked  

---

## 1. Executive Summary

This report certifies the closure of the Databricks resource inventory. All provider-issued identifiers are established as authoritative primary keys, the legacy mock cluster identifier `1105-132712-k0qfl59u` has been permanently purged from the application, cluster names are restricted to display metadata, and historical endpoint fixtures have been isolated from live inventory.

---

## 2. Authoritative Identity Rules (Section 3.1)

In compliance with enterprise FinOps data standards, the platform enforces strict separation between **Authoritative Primary Keys** and **Display Metadata**:

| Resource Category | Authoritative Primary Key | Permitted Key Format | Display Metadata (Name) | Independent Authorization Permitted? |
| :--- | :--- | :--- | :--- | :---: |
| **Compute Clusters** | `1102-081455-7t3bqp3v` | Databricks Cluster UUID | `adf-deaccelator-compute` | **NO** (ID strictly required) |
| **SQL Warehouses** | `05ed10a52697a344` | Databricks Warehouse Hex ID | `Serverless Starter Warehouse` | **NO** (ID strictly required) |
| **Model Serving Endpoints** | `databricks-claude-fable-5` | Provider Endpoint Name | Configured Endpoint Slug | **YES** (Endpoint slug is REST PK) |
| **Databricks Apps** | `cement-demand-forecasting` | Provider App Name | App Registration Name | **YES** (App slug is REST PK) |

---

## 3. Resolution of the Cluster ID Discrepancy (Section 3.2)

### 3.1 Audit of the Legacy Mock Cluster ID
- **Investigated Identifier:** `1105-132712-k0qfl59u`
- **Audit Findings:** This identifier did **not** exist in the authenticated live discovery response from Azure Databricks workspace `642006393507276`. It was introduced during early Milestone 3C UI scaffolding as a fallback fixture in `DatabricksWorkspaceDetailView.tsx`.
- **Actions Taken:**
  1. **Backend Registry:** Permanently removed `1105-132712-k0qfl59u` from `KNOWN_CLUSTERS` in `finops_analytics_service.py`.
  2. **Frontend Fallback:** Replaced `1105-132712-k0qfl59u` with canonical `1102-081455-7t3bqp3v` in `frontend/src/components/DatabricksWorkspaceDetailView.tsx`.
  3. **Cluster Name Restriction:** Excised cluster name `adf-deaccelator-compute` from `KNOWN_CLUSTERS`. When a request supplies `resource_id="adf-deaccelator-compute"`, the engine rejects it as an unverified identifier and returns `NO_DATA`.
  4. **Adversarial Verification:** Added automated regression tests proving that `1105-132712-k0qfl59u` and `adf-deaccelator-compute` return `NO_DATA` across all 15 modules.

---

## 4. Serving Endpoint Inventory Separation (Section 3.3)

### 4.1 Live Discovered Endpoints
The live authenticated workspace discovery identified 27 provisioned and serverless model serving endpoints. The canonical production registry `KNOWN_SERVING_ENDPOINTS` contains verified endpoints:
- `databricks-claude-fable-5`
- `databricks-claude-fable-5-1`
- `databricks-meta-llama-3-1-405b-instruct`
- `databricks-bge-large-en`
- `databricks-dbrx-instruct`
- `databricks-mixtral-8x7b-instruct`
- `dbrx-instruct-endpoint`
- `mpt-30b-instruct`
- `bge-large-en-v1.5`
- `llama-3-70b-instruct`
- `mistral-large`

### 4.2 Isolation of Historical Fixtures
Historical fixtures used during early mock testing have been explicitly removed from `KNOWN_SERVING_ENDPOINTS` and quarantined into `HISTORICAL_FIXTURE_ENDPOINTS`:

```python
HISTORICAL_FIXTURE_ENDPOINTS: dict[str, dict[str, Any]] = {
    "deepseek-r1-endpoint": {
        "model_name": "DeepSeek R1",
        "provenance": "Historical Test Fixture (Offline Prototype)",
        "status": "HISTORICAL_FIXTURE",
        "is_live_asset": False,
    },
    "mistral-large-endpoint": {
        "model_name": "Mistral Large 2407",
        "provenance": "Historical Test Fixture (Offline Prototype)",
        "status": "HISTORICAL_FIXTURE",
        "is_live_asset": False,
    },
}
```

**Guardrail:** `_resolve_resource_filter()` immediately rejects any identifier present in `HISTORICAL_FIXTURE_ENDPOINTS`, returning `NO_DATA`.

---

## 5. Databricks App Inventory & Unattributed Pool (Section 3.4)

### 5.1 Discovered Application Inventory
The authenticated workspace discovery identified three active applications on workspace `642006393507276`:
1. `cement-demand-forecasting`
2. `mcp-generate-ppt`
3. `wonder-cement-app`

### 5.2 Unattributed Shared Compute Enforcement
Because Databricks Serverless App runtime does not attach direct resource tags to child workloads in the current Azure billing export:
- All Databricks Apps compute spend is classified as **Unattributed Shared Compute**.
- The 2 ledger items totaling **$1,240.00** (310 DBU) have `owner_tag="unassigned"` and `allocation_status="Unallocated"`.
- When filtering by any individual application (e.g. `cement-demand-forecasting`), the Executive Overview displays:
  - `total_spend`: `$0 (Unattributed)`
  - `delta_label`: `"$1,240 in Unattributed pool"`
  - `status`: `AVAILABLE`
- The platform never fabricates direct compute spend for an application when only an unattributed shared pool is supported by the telemetry.

