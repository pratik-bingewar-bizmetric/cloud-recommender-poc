# Milestone 3G.2 — Remaining Defects & Architectural Constraints Register

**Repository:** `cloud-recommender-poc`  
**Branch:** `feature/databricks-apps-integration`  
**Workspace:** Azure Databricks `642006393507276` (`Azure Databricks Dev`)  
**Status:** Canonical & Audited  

---

## 1. Defect Resolution Summary

All primary financial, mathematical, and resource-identity defects identified across Milestones 3F, 3G, and 3G.1 have been resolved in Milestone 3G.2.

| Defect ID | Title / Finding | Resolution Status | Verified In Milestone 3G.2 |
| :---: | :--- | :---: | :--- |
| **DEFECT-3G2-01** | **Total Spend vs AI Spend ($11,720 delta)** | **RESOLVED** | Proven lineage: $26,740 Model Serving DBU compute (in $176,840 consumption ledger) + $11,296 External AI Gateway Pay-per-Token Model APIs + $424 Vector Search = $38,460 Total AI Spend. Zero double counting. |
| **DEFECT-3G2-02** | **DBU Consumption Discrepancy (7.28 DBU)** | **RESOLVED** | Traced to authoring approximation in 3G.1 report. Canonical 24-record ledger sums to exactly 88,420.0 DBU and $176,840.00 with zero variance. |
| **DEFECT-3G2-03** | **Effective Rate Misclassification ($2.00/DBU)** | **RESOLVED** | Classified strictly as blended baseline quotient ($176,840 / 88,420 DBU). Explicitly not labeled as retail list price. |
| **DEFECT-3G2-04** | **Forecast Spend Rounding ($319,500 vs $319,486)** | **RESOLVED** | Documented exact 26.72-day run-rate pace multiplier (1.122542) and executive milestone rounding rule `round(spend, -2)`. |
| **DEFECT-3G2-05** | **UI Mock Cluster ID (`1105-132712-k0qfl59u`)** | **RESOLVED** | Permanently purged from backend registries, frontend mocks, and aliases. Tested to return `NO_DATA`. |
| **DEFECT-3G2-06** | **Cluster Name Authorizing Attribution** | **RESOLVED** | Cluster name `adf-deaccelator-compute` restricted to display metadata only. ID `1102-081455-7t3bqp3v` is strictly required. |
| **DEFECT-3G2-07** | **Historical Fixtures in Live Inventory** | **RESOLVED** | `deepseek-r1-endpoint` and `mistral-large-endpoint` quarantined into `HISTORICAL_FIXTURE_ENDPOINTS`. Rejected in live scope. |
| **DEFECT-3G2-08** | **Databricks Apps Direct Attribution** | **RESOLVED** | Compute isolated in unattributed shared pool ($1,240, 310 DBU). UI truthfully renders `$0 (Unattributed)`. |

---

## 2. Documented Operational Constraints (Non-Defects)

The following items are governed by strict non-negotiable operational rules and architectural boundaries. They represent intentional guardrails, not application defects:

### 2.1 Live SQL Execution Gated by Stopped SQL Warehouse
- **Observation:** Live Databricks System Tables (`system.billing.usage`, `system.access.audit`, `system.query.history`) cannot be queried dynamically without starting or resuming SQL Warehouse `05ed10a52697a344`.
- **Operating Guardrail:** Rule 1 & Rule 2 strictly prohibit starting, resuming, or modifying customer cloud compute.
- **Handling:** The System Tables Explorer and Query History modules truthfully report the warehouse status as `STOPPED` and utilize the certified offline baseline without fabricating synthetic live telemetry.
- **Customer Action for Live Streaming:** If the customer desires real-time continuous ingestion, they must explicitly authorize starting the warehouse or configure an automated scheduled job.

### 2.2 Databricks Apps Serverless Runtime Tagging
- **Observation:** Individual app runtimes (`cement-demand-forecasting`, `mcp-generate-ppt`, `wonder-cement-app`) do not currently have custom Azure Cost Management billing tags attached at the container pod level.
- **Handling:** The application transparently isolates app compute in the unattributed shared compute pool ($1,240 / 310 DBU) and renders `"Unattributed"` in the UI.

### 2.3 Frozen Fabric Baseline
- **Protected Components:** `fabric-udf/`, `sync-agent/`, `function_app.py`, commit `c2c87027f64b59fb784d990b9485781dde05e6f8`.
- **Status:** 100% frozen and unmodified.

---

## 3. Acceptance Recommendation

Based on the complete mathematical reconciliation, purge of legacy mock fixtures, and passing of all 81 automated tests, the FinOps Command Center qualifies for:

**ACCEPTED**
- Financial components reconcile with zero unexplained variance.
- Resource registries contain only canonical verified identifiers.
- All 15 modules strictly enforce canonical scoping.
- UI status rendering is truthful across all states.
- 100% of test suites pass with Exit Code 0.

