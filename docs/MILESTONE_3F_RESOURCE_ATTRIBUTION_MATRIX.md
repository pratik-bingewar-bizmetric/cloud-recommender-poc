# Milestone 3F — Resource Cost Attribution & Scope Isolation Matrix

**Date:** November 7, 2026  
**Repository:** `cloud-recommender-poc`  
**Active Branch:** `feature/databricks-apps-integration`  
**Target Workspace:** Azure Databricks Dev (`642006393507276`)  

---

## 1. Resource Cost Attribution Matrix

The table below outlines the attribution mechanism, billing source, attribution keys, verification status, and limitations for each Databricks resource type:

| Resource Type | Intended Billing Source | Attribution Key | Verification Status | Current Limitations & Fallback Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Compute Clusters** | `system.billing.usage` where `sku_name LIKE '%ALL_PURPOSE%'` | `custom_tags.cluster_id` or `identity_metadata.run_as` | **PARTIALLY VERIFIED** | Live cluster inventory extracted via `client.clusters.list()`. Financial DBU attribution ($24,600 / 11,180 DBU) uses static cluster model because SQL warehouse is stopped. |
| **SQL Warehouses** | `system.billing.usage` where `sku_name LIKE '%SQL%'` | `custom_tags.warehouse_id` or `warehouse_name` | **VERIFIED (STOPPED)** | Real warehouse `05ed10a52697a344` discovered. Reported as `STOPPED`. Cost ($42,180 / 19,172 DBU) is an in-memory baseline. Zero-execution prevents live querying. |
| **Jobs & Workflows** | `system.billing.usage` where `sku_name LIKE '%JOBS%'` | `custom_tags.job_id` or `run_id` | **SIMULATED** | Workflows discovered via `client.jobs.list()`. Individual run DBUs and cost per run ($21.00 / run) are mock metrics in `get_compute_warehouses()`. |
| **Lakeflow / DLT Pipelines** | `system.billing.usage` where `sku_name LIKE '%DLT%'` | `custom_tags.pipeline_id` | **SIMULATED** | Pipeline discovery extracted via SDK. Telemetry records ($4,140 in Cost Explorer) originate from fixture ledger. |
| **Model Serving Endpoints** | `system.ai.model_serving` & `system.billing.usage` (GPU Serving SKUs) | `endpoint_name` or `served_model_name` | **PARTIALLY VERIFIED** | 27 serving endpoints discovered via SDK. Incurred spend ($26,740 / $38,460) and token counts (8.42B) are simulated models. |
| **Databricks Apps** | `system.billing.usage` where `sku_name LIKE '%APPS%'` or serverless | `custom_tags.app_name` or isolated unattributed bucket | **VERIFIED ISOLATION** | 3 apps discovered. Lacking direct billing tags, app spend ($1,240) is strictly isolated in an `Unattributed` bucket rather than being distributed across compute. |
| **Unity Catalog Storage** | Azure Storage / ADLS Gen2 Billing Meter | `storage_account_name` or catalog namespace | **SIMULATED** | Storage tier breakdown (Hot, Cool, Cold, Archive) and ADLS Gen2 charges ($18,950 MTD) are static models. |

---

## 2. Metadata Fields in Official Databricks Billing Records

The official schema for `system.billing.usage` contains the following attribution fields:

| Field Name | Data Type | Description | FinOps Attribution Value |
| :--- | :--- | :--- | :--- |
| `record_id` | `STRING` | Unique billing UUID | Primary key for ledger deduplication |
| `workspace_id` | `STRING` | Databricks workspace ID | Primary tenant isolation boundary |
| `sku_name` | `STRING` | Product SKU code | Classifies workload (SQL, Jobs, Compute, Serving) |
| `usage_quantity` | `DECIMAL(18,4)`| Metered consumption | Volume basis (always DBU for compute) |
| `usage_unit` | `STRING` | Measurement unit | `DBU` or `BYTE_HOURS` (never tokens) |
| `usage_start_time` | `TIMESTAMP` | Interval start | Timezone-normalized metering interval |
| `usage_end_time` | `TIMESTAMP` | Interval end | Duration boundary |
| `identity_metadata` | `STRUCT` | Calling principal | User or service principal attribution |
| `custom_tags` | `MAP<STRING,STRING>`| User-defined tags | Essential for cost center, project, and app attribution |

---

## 3. Dedicated Unattributed Cost Bucket Evaluation

### Architectural Principle
In enterprise FinOps, unmapped or shared infrastructure must **never be arbitrarily distributed** across compute clusters or forced into fictitious user mappings. Doing so distorts chargeback accuracy and produces false optimization recommendations.

### Implementation Audit
- In `finops_analytics_service.py` (lines 482-591):
  - When filtering by `resource_type="app"` or `resource_id="databricks-cost-monitor"`, `total_spend` returns `$0.00`.
  - The formatted value explicitly shows `"$0 (Unattributed)"`.
  - The delta label clearly informs the user: `"$1,240 in Unattributed pool"`.
  - The Spend Composition returns a dedicated family: `{"family": "Unattributed Compute", "share": 1.0, "amount": 1240, "color": "#94a3b8"}`.
  - The Top Cost Driver displays: `spend=1240.0, formatted_spend="$1,240 (Unattributed)"`.
- **Audit Conclusion:** The Unattributed cost bucket is **fully compliant and correctly implemented**.

---

## 4. Substring-Matching Defect in Child Scope Filtering

### Root Cause Analysis
In `backend/src/cloud_recommender/services/databricks/finops_analytics_service.py`, child resource filtering in `get_executive_overview()` (lines 134-161) and `get_cost_explorer()` (lines 978-1022) is implemented using keyword substring matching on `resource_id`:

```python
is_warehouse_filter = resource_type == "warehouse" or (
    resource_id and ("05ed10a52697a344" in resource_id or "warehouse" in resource_id.lower() or "starter" in resource_id.lower())
)
is_cluster_filter = resource_type == "cluster" or (
    resource_id and ("deaccelator" in resource_id.lower() or "cluster" in resource_id.lower())
)
is_serving_filter = resource_type in ("serving_endpoint", "model_serving") or (
    resource_id and ("serving" in resource_id.lower() or "endpoint" in resource_id.lower() or "dbrx" in resource_id.lower())
)
is_app_filter = resource_type == "app" or (
    resource_id and ("app" in resource_id.lower() or "monitor" in resource_id.lower() or "optimizer" in resource_id.lower())
)
```

### Manifested Vulnerabilities & Inaccuracies

1. **False Positive Attribution via Substrings:**
   - If a caller passes `resource_id="fake-cluster-9999"`, it matches `is_cluster_filter` because the string contains `"cluster"`. It falsely returns `$24,600` spend for `adf-deaccelator-compute`.
   - If a caller passes `resource_id="temporary-test-warehouse"`, it falsely returns `$42,180` spend for `Serverless Starter Warehouse`.

2. **Silent Fallthrough to Entire Workspace Totals:**
   - If a caller passes a valid UUID or resource name that contains none of the keywords (e.g. `resource_id="pipeline-exec-3b8c4d5e"`, `resource_type=None`), it matches none of the branches and enters the `else:` clause.
   - The `else:` clause returns the **full workspace total ($284,620)**!
   - The user believes they are inspecting `pipeline-exec-3b8c4d5e`, but the UI renders the entire workspace spend ($284,620) without any warning.

3. **Modules 3 through 15 Lack Scope Parameter Binding:**
   - In `FinOpsCommandCenterView.tsx`, only Module 1 (`overview`) and Module 2 (`cost`) pass `resource_id` and `resource_type` to backend API endpoints.
   - Modules 3 through 15 (`allocation`, `compute`, `ai`, `data`, `network`, `recommend`, `forecast`, `anomaly`, `governance`, `chargeback`, `workloads`, `reports`, `settings`) ignore the child scope and render un-scoped workspace-level totals.

---

## 5. Remediation Plan for Resource Attribution

1. **Exact-ID Matching:** Replace substring checks with exact equality checks against discovered asset inventories:
   ```python
   # Match against discovered assets
   matched_cluster = next((c for c in discovered_clusters if c.id == resource_id), None)
   matched_warehouse = next((w for w in discovered_warehouses if w.id == resource_id), None)
   ```
2. **Explicit Empty State on Unknown Resource:** If `resource_id` is specified but does not match any discovered asset, return an explicit empty response (`total_spend = 0.0`, `status = KpiStatus.NO_DATA`) rather than falling through to the full workspace total.
3. **Propagate Child Filters to Modules 3-15:** Update API endpoint handlers in `finops.py` and frontend query hooks in `FinOpsCommandCenterView.tsx` to accept and respect `resource_id` and `resource_type` across all modules.

