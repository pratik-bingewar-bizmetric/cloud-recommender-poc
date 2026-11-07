# Milestone 3F — FinOps Defect Register & Remediation Roadmap

**Date:** November 7, 2026  
**Repository:** `cloud-recommender-poc`  
**Active Branch:** `feature/databricks-apps-integration`  
**Target Workspace:** Azure Databricks Dev (`642006393507276`)  
**Status:** AUDITED — SUBMITTED FOR USER APPROVAL PRIOR TO REMEDIATION  

---

## 1. Prioritized Defect Summary

| Defect ID | Severity | Title | Affected Modules | Root Cause Category |
| :--- | :--- | :--- | :--- | :--- |
| **DEFECT-3F-01** | `CRITICAL` | DBU Rate & Databricks Spend Mathematical Mismatch | Mod 1 (Overview), Mod 2 (Cost) | Mathematical Inconsistency |
| **DEFECT-3F-02** | `CRITICAL` | Billing Ledger Sum vs Gross Consumption Variance | Mod 2 (Cost Explorer) | Data Reconciliation Failure |
| **DEFECT-3F-03** | `HIGH` | Unknown Child Resource ID Silently Returns Workspace Totals | Mod 1, Mod 2, Scope Engine | Scope Enforcement Flaw |
| **DEFECT-3F-04** | `HIGH` | False Child Resource Attribution via Substring Matching | Backend Scope Filter | Pattern Matching Bug |
| **DEFECT-3F-05** | `HIGH` | Cross-Module AI Spend Inconsistency ($38.4K vs $59.7K vs $4.2K) | Mod 1, Mod 5, Workspace View | Cross-Component Divergence |
| **DEFECT-3F-06** | `HIGH` | AI Token Volume Discrepancy (10.28 Billion vs 42.8 Million) | Mod 5 (AI), Workspace Mod 11 | Backend / Frontend Divergence |
| **DEFECT-3F-07** | `MEDIUM` | Savings Opportunity KPI vs Sum of Recommendations ($31.2K vs $24.5K) | Mod 1, Mod 8 (Advisor) | Aggregation Inconsistency |
| **DEFECT-3F-08** | `MEDIUM` | Anomaly KPI Count (7) vs Anomaly Queue Items (3) | Mod 1, Mod 10 (Anomaly) | List / KPI Desynchronization |
| **DEFECT-3F-09** | `MEDIUM` | Child Resource Scope Not Propagated to Modules 3–15 | Mod 3 through Mod 15 | Scope Hook Missing |
| **DEFECT-3F-10** | `MEDIUM` | Compute Spend Mismatch Between Overview and Compute View | Mod 1 ($108K), Mod 4 ($91K / $36K) | Family Mapping Variance |

---

## 2. Detailed Forensic Analysis of Identified Defects

---

### DEFECT-3F-01: DBU Rate & Databricks Spend Mathematical Mismatch
- **Severity:** `CRITICAL`
- **Category:** `MATHEMATICAL_RECONCILIATION`
- **Observed Behavior:**
  - Executive Overview reports `databricks_spend = $176,840` and `dbu_consumption = 88,420 DBU`.
  - Cost Explorer reports `effective_rate = $0.148 / DBU`.
  - Mathematical calculation: `88,420 DBU * $0.148/DBU = $13,086.16`.
  - **Variance:** **`$163,753.84`** (13.5x discrepancy).
- **Root Cause:**
  - `effective_rate` was copied from an enterprise discounted rate card fixture ($0.148/DBU), while `databricks_spend` was anchored to a high-volume monthly commitment ($176,840).
  - To reconcile, either `effective_rate` is `$2.00 / DBU` (`$176,840 / 88,420`), or `databricks_spend` should be `$13,086.16`.
- **Recommended Remediation:**
  - Establish a single source of truth for DBU rate calculation:
    `databricks_spend = round(dbu_consumption * blended_rate, 2)`.
  - Update `effective_rate` to reflect actual blended SKU rates (e.g. $2.00/DBU for serverless SQL, $0.40/DBU for standard compute).

---

### DEFECT-3F-02: Billing Ledger Sum vs Gross Consumption Variance
- **Severity:** `CRITICAL`
- **Category:** `DATA_RECONCILIATION`
- **Observed Behavior:**
  - In Cost Explorer (`get_cost_explorer()`), the `billing_ledger` table displays 8 line-item records.
  - Summing `effective_cost` across all 8 rows yields:
    `$16,578 + $6,840 + $8,865 + $2,280 + $1,640 + $1,767 + $4,140 + $1,240 = $43,350.00`.
  - However, the `gross_consumption` KPI card directly above the table displays **`$176,840.00`**.
  - **Variance:** **`$133,490.00`**.
- **Root Cause:**
  - In `finops_analytics_service.py` line 1027:
    `value = total_effective if resource_id else 176840.0`.
    When no resource filter is active, it bypasses the ledger calculation and injects `$176,840.0`.
- **Recommended Remediation:**
  - Generate a full, complete 30-day ledger whose line-item sum mathematically matches `gross_consumption`, or set `gross_consumption = sum(item.effective_cost for item in billing_ledger)`.

---

### DEFECT-3F-03: Unknown Child Resource ID Silently Returns Workspace Totals
- **Severity:** `HIGH`
- **Category:** `SCOPE_FILTERING`
- **Observed Behavior:**
  - When a user filters by an unrecognized child resource ID (e.g. `resource_id="my-custom-pipeline-9999"`, `resource_type=None`), the backend silently returns the **entire workspace spend ($284,620)**.
  - The UI Active Filter banner states: *"Filtered to Child Resource: my-custom-pipeline-9999"*, but every KPI card and chart shows the full organization totals.
- **Root Cause:**
  - In `finops_analytics_service.py`, `is_warehouse_filter`, `is_cluster_filter`, `is_serving_filter`, and `is_app_filter` evaluate to `False`. The logic falls into the generic `else:` branch which renders the full workspace response.
- **Recommended Remediation:**
  - Check if `resource_id` exists in discovered assets. If not found, return an explicit empty state:
    `total_spend = 0.0, status = KpiStatus.NO_DATA, limitations = "No telemetry records found for resource ID."`.

---

### DEFECT-3F-04: False Child Resource Attribution via Substring Matching
- **Severity:** `HIGH`
- **Category:** `SCOPE_FILTERING`
- **Observed Behavior:**
  - A request with `resource_id="fake-cluster-1234"` matches `is_cluster_filter` because `"cluster" in resource_id.lower()`.
  - The API responds with the spend of `adf-deaccelator-compute` ($24,600).
- **Root Cause:**
  - Keyword substring searches (`"cluster" in resource_id.lower()`, `"warehouse" in resource_id.lower()`, `"app" in resource_id.lower()`) rather than exact resource ID matching.
- **Recommended Remediation:**
  - Replace substring checks with exact equality checks against discovered resource IDs.

---

### DEFECT-3F-05: Cross-Module AI Spend Inconsistency
- **Severity:** `HIGH`
- **Category:** `UI_DISCREPANCY`
- **Observed Behavior:**
  - Executive Overview KPI card: **`$38,460`**
  - Spend Composition chart (Module 1): **`$59,770`**
  - Model Serving Endpoint filter: **`$26,740`**
  - Databricks Workspace Detail View (Module 11): **`$4,280 / mo`**
- **Root Cause:**
  - Disparate mock constants were defined in different parts of `finops_analytics_service.py` and hardcoded in JSX inside `DatabricksWorkspaceDetailView.tsx`.
- **Recommended Remediation:**
  - Align all AI spend representations to a single canonical figure (e.g. $38,460) and make `DatabricksWorkspaceDetailView.tsx` consume the backend API rather than hardcoded JSX constants.

---

### DEFECT-3F-06: AI Token Economics Volume Discrepancy
- **Severity:** `HIGH`
- **Category:** `UI_DISCREPANCY`
- **Observed Behavior:**
  - Backend `get_ai_economics()` returns:
    - `input_tokens = 8,420,000,000` (8.42 Billion)
    - `output_tokens = 1,860,000,000` (1.86 Billion)
    - Total = **10.28 Billion tokens**.
  - Frontend `DatabricksWorkspaceDetailView.tsx` renders:
    - Monthly Token Volume = **42.8 Million tokens** (Prompt: 28.4M, Completion: 14.4M).
  - **Variance:** **`10.237 Billion tokens`**.
- **Root Cause:**
  - The 14-module detail view used a prototype mock from Milestone 3B (42.8M tokens), while the FinOps Command Center used a high-volume enterprise fixture (10.28B tokens).
- **Recommended Remediation:**
  - Unify token metrics across both views by binding `DatabricksWorkspaceDetailView.tsx` Module 11 to `getFinOpsAiEconomics()`.

---

### DEFECT-3F-07: Savings Opportunity KPI vs Sum of Recommendations
- **Severity:** `MEDIUM`
- **Category:** `MATHEMATICAL_RECONCILIATION`
- **Observed Behavior:**
  - Executive Overview Savings Opportunity KPI = **`$31,280`**.
  - Sum of all 5 recommendations in `_get_decisions()`:
    - `dec-01`: $8,400
    - `dec-02`: $6,100
    - `dec-03`: $2,750
    - `dec-04`: $3,460
    - `dec-05`: $3,820
    - **Total Sum:** **`$24,530.00`**.
  - **Unreconciled Difference:** **`$6,750.00`**.
- **Root Cause:**
  - KPI was hardcoded to $31,280 instead of dynamically evaluating `sum(d.estimated_savings_monthly for d in decisions)`.
- **Recommended Remediation:**
  - Dynamically compute: `savings_opportunity = sum(d.estimated_savings_monthly for d in self._get_decisions())`.

---

### DEFECT-3F-08: Anomaly KPI Count (7) vs Anomaly Queue Items (3)
- **Severity:** `MEDIUM`
- **Category:** `MATHEMATICAL_RECONCILIATION`
- **Observed Behavior:**
  - KPI reports `7` open anomalies.
  - Anomaly Detection queue in Module 10 only contains 3 items (`anom-01`, `anom-02`, `anom-03`).
- **Root Cause:**
  - Static KPI value (`7.0`) out of sync with fixture list length.
- **Recommended Remediation:**
  - Set `anomalies_count = len(self._get_anomalies())`.

---

### DEFECT-3F-09: Child Resource Scope Not Propagated to Modules 3–15
- **Severity:** `MEDIUM`
- **Category:** `SCOPE_FILTERING`
- **Observed Behavior:**
  - In `FinOpsCommandCenterView.tsx`, only `getFinOpsOverview` and `getFinOpsCostExplorer` pass `resource_id` and `resource_type`.
  - Modules 3 through 15 do not accept or forward child scope parameters.
- **Root Cause:**
  - API endpoint contracts and frontend hooks were only extended for Modules 1 & 2 in Milestone 3E.
- **Recommended Remediation:**
  - Add optional `resource_id` and `resource_type` query parameters to remaining FinOps endpoints.

---

### DEFECT-3F-10: Compute Spend Mismatch Between Overview and Compute View
- **Severity:** `MEDIUM`
- **Category:** `MATHEMATICAL_RECONCILIATION`
- **Observed Behavior:**
  - Overview Spend Composition: Compute = **`$108,155`**.
  - Module 4 (Compute & Warehouses) KPI: `compute_spend = $91,420`.
  - Discovered Cluster (`$18,420`) + Warehouse (`$18,400`) = **`$36,820`**.
- **Root Cause:**
  - Different mock figures used across modules.
- **Recommended Remediation:**
  - Reconcile compute categorization so that `Compute Spend` in Module 4 matches the Spend Composition figure in Module 1.

---

## 3. Prioritized Remediation Roadmap

```
[ Phase 1: High-Priority Mathematical Reconciliations ]
  ├── 1. Reconcile DBU Effective Rate: databricks_spend = dbu_consumption * blended_rate
  ├── 2. Reconcile Cost Explorer Ledger so sum(items) equals gross_consumption
  └── 3. Reconcile Savings Opportunity KPI = sum(decisions)

[ Phase 2: Scope Enforcement & Attribution Integrity ]
  ├── 4. Replace substring matching with exact asset ID matching
  ├── 5. Add explicit NO_DATA empty state for unknown resource IDs
  └── 6. Propagate child scope filters to Modules 3–15

[ Phase 3: Cross-Module UI & Data Unification ]
  ├── 7. Unify AI Spend ($38,460 canonical across all components)
  ├── 8. Unify Token Volumes across Backend and Workspace Detail View
  └── 9. Reconcile Anomaly KPI count with queue length
```

*Note: In accordance with Milestone 3F operational instructions, these defects are documented for human review and approval prior to modifying application logic.*

