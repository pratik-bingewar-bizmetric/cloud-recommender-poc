# Milestone 3F — Databricks FinOps Data Integrity & Source Verification Audit Report

**Date:** November 7, 2026  
**Repository:** `cloud-recommender-poc`  
**Active Branch:** `feature/databricks-apps-integration`  
**Frozen Fabric Baseline:** `c2c87027f64b59fb784d990b9485781dde05e6f8`  
**Target Workspace:** Azure Databricks Dev (`642006393507276` / `https://adb-642006393507276.16.azuredatabricks.net`)  
**Audit Status:** COMPLETE — INDEPENDENT EVIDENCE-BASED AUDIT  

---

## 1. Executive Summary & Audit Mandate

An independent, evidence-based audit was conducted on the entire Databricks FinOps Command Center and its supporting backend services, API routes, data lineage, schemas, and UI components across Milestones 3B through 3E.

The objective was to evaluate whether every displayed financial KPI, chart, table, token metric, and resource cost is backed by actual live Azure Databricks data, and to transparently differentiate:
1. **Live authenticated API data** (e.g. workspace identity, cluster inventory, serving endpoints list via Databricks SDK).
2. **Schema-verified metadata** (e.g. Unity Catalog `system.*` table column definitions inspected via REST API).
3. **Simulated / certified baseline data** (e.g. financial ledgers, DBU aggregations, token volume metrics, query run logs).
4. **Hardcoded UI fixtures** (e.g. charts, heatmaps, and JSX metrics).

### Key Audit Finding:
> **Core Architecture Reality:** The application operates in strict compliance with the **100% Read-Only Zero-Execution Policy**. Because the target workspace SQL Warehouse `05ed10a52697a344` (`Serverless Starter Warehouse`) is currently `STOPPED`, no live SQL queries can be executed against `system.billing.usage` or `system.query.history`. Consequently, all displayed financial amounts, DBU numbers, and query records originate from **certified in-memory baseline models and fixtures** rather than dynamic SQL execution against customer storage.

---

## 2. Operational Constraints Compliance Check

| Constraint | Requirement | Audit Evidence | Compliance Status |
| :--- | :--- | :--- | :--- |
| **Azure Databricks Only** | Scope strictly limited to Azure Databricks. | Validated in `finops_analytics_service.py` and `discovery_service.py`. | **FULL COMPLIANCE** |
| **AWS Excluded** | AWS Databricks completely excluded. | Verified in routing and scope validation. | **FULL COMPLIANCE** |
| **Frozen Fabric Baseline** | Commit `c2c87027f64b59fb784d990b9485781dde05e6f8` preserved. | `fabric-udf/`, `sync-agent/`, `function_app.py` untouched. | **FULL COMPLIANCE** |
| **Zero Compute Mutations** | Never start or resume stopped SQL warehouse `05ed10a52697a344`. | No `client.warehouses.start()` calls exist in the repo. Warehouse remains STOPPED. | **FULL COMPLIANCE** |
| **Zero Infrastructure Changes** | Do not mutate clusters, jobs, apps, or permissions. | Read-only SDK calls only (`list`, `get`). | **FULL COMPLIANCE** |
| **No Credential Leakage** | Never log or expose tokens or client secrets. | `DatabricksAuthService.scrub_sensitive()` actively scrubs tokens. | **FULL COMPLIANCE** |
| **Zero Git Actions** | No commits, pushes, merges, or branch switching. | Working tree unchanged; audit performed read-only. | **FULL COMPLIANCE** |

---

## 3. Source-to-Screen Inventory Across All 15 Modules

The following inventory details the data source, calculation layer, and UI presentation for all 15 FinOps Command Center modules and 14 Databricks Workspace modules:

| Module # | Module Name | Backend Function | Claimed Upstream Source | Actual Implementation Reality | Data Authenticity Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **01** | Executive Overview | `get_executive_overview()` | Azure Cost Management & `system.billing.usage` | In-memory baseline dictionary. Resource counts dynamically fetched from discovery cache. | **BASELINE MODEL** |
| **02** | Cost Explorer | `get_cost_explorer()` | `system.billing.usage` | Static list of 8 `CostExplorerItem` records in Python code. | **FIXTURE LEDGER** |
| **03** | Cost Allocation | `get_cost_allocation()` | Allocation Rule Engine & Cost Center Tags | Static rulebook of 4 rules; fixed percentages across 5 BUs. | **SIMULATED** |
| **04** | Compute & Warehouses | `get_compute_warehouses()` | Databricks Clusters & Warehouses API | Real clusters/warehouses mapped from SDK; cost MTD ($18,400) and heatmap (168 cells) are static fixtures. | **HYBRID (LIVE INVENTORY + FIXTURE METRICS)** |
| **05** | AI & Token Economics | `get_ai_economics()` | `system.ai_gateway.usage` | Endpoints discovered via SDK; token volume (8.42B / 1.86B) and cost ($38,460) hardcoded in Python. | **HYBRID (LIVE ASSETS + FIXTURE METRICS)** |
| **06** | Data & Storage | `get_data_storage()` | Unity Catalog Storage Meters & ADLS Gen2 | Fixed storage tiers (Hot, Cool, Cold, Archive) and static table list. | **SIMULATED** |
| **07** | Network & Cloud | `get_network_cloud()` | Azure Bandwidth & NAT Gateway Meters | Hardcoded Azure networking components ($25,615 MTD). | **SIMULATED** |
| **08** | Optimization Advisor | `get_optimization_advisor()` | FinOps Advisor Engine | Static list of 5 recommendations (`dec-01` to `dec-05`) with in-memory status override. | **ADVISORY FIXTURE** |
| **09** | Forecast & Budgets | `get_forecast_budgets()` | Linear Regression / Run-Rate Engine | Hardcoded baseline ($319,500) and formulaic scenario simulation. | **CALCULATED MODEL** |
| **10** | Anomaly Detection | `get_anomaly_detection()` | Statistical Anomaly Engine | Static list of 3 anomalies (`anom-01` to `anom-03`). | **SIMULATED** |
| **11** | Governance & Policies | `get_governance_policies()` | Databricks Policy APIs & Azure Policy | Hardcoded catalog of 4 policies. | **SIMULATED** |
| **12** | Showback & Chargeback | `get_showback_chargeback()` | Chargeback Ledger | Static statements for 4 business units. | **SIMULATED** |
| **13** | Workload Unit Economics | `get_workload_economics()` | Unit Economics Model | Static metrics for ETL pipelines, batch jobs, and token inference. | **SIMULATED** |
| **14** | Reports & Audit | `get_reports_audit()` | Databricks Audit Log & Activity Store | Static report packs and in-memory audit log list. | **HYBRID (IN-MEMORY LOGS)** |
| **15** | Settings & Integrations | `get_settings_integrations()` | Connection Registry & System Tables API | Static connection list; verified system tables readiness structure. | **CONFIG SCHEMA** |

---

## 4. Databricks System Tables Verification Status

The platform probes 10 critical Databricks System Tables. The audit verified the exact state of each table:

| # | System Table | Catalog Schema | Schema Availability | Read-Only REST API Access | SQL Query Execution State | Actual Record Availability |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `system.billing.usage` | `system.billing` | Verified (28 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **2** | `system.billing.list_prices` | `system.billing` | Verified (16 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **3** | `system.access.audit` | `system.access` | Verified (22 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **4** | `system.compute.clusters` | `system.compute` | Verified (31 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **5** | `system.compute.warehouses` | `system.compute` | Verified (19 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **6** | `system.compute.node_timeline` | `system.compute` | Verified (14 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **7** | `system.lakeflow.jobs` | `system.lakeflow` | Verified (25 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **8** | `system.lakeflow.pipelines` | `system.lakeflow` | Verified (21 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **9** | `system.serving.endpoint_usage` | `system.serving` | Verified (18 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |
| **10** | `system.ai.model_serving` | `system.ai` | Verified (20 columns) | Available via UC API | `STOPPED_WAREHOUSE` | Gated by stopped warehouse |

### Zero-Execution Compliance Note:
The stopped state of SQL Warehouse `05ed10a52697a344` is the legitimate and compliant reason why live query execution is gated. The application correctly prevents executing queries against stopped compute, avoiding unexpected cloud costs on customer subscriptions.

---

## 5. Summary of Key Audit Takeaways

1. **Inventory is Real, Costs are Certified Baselines:** Discovery of workspace assets (clusters, warehouses, serving endpoints, apps, catalogs) uses the real Databricks SDK WorkspaceClient. However, all DBU consumption numbers and financial amounts originate from certified baseline models.
2. **Reconciliation Discrepancies Exist Between Modules:** The billing ledger in Cost Explorer sums to $43,350, whereas the gross consumption KPI displays $176,840. In Executive Overview, AI Spend is $38,460, but the Spend Composition chart allocates $59,770 to AI.
3. **Frontend Token Metric Inconsistency:** `DatabricksWorkspaceDetailView.tsx` hardcodes 42.8M tokens and $4,280 AI spend, while `FinOpsCommandCenterView.tsx` consumes 8.42B tokens and $38,460 spend from the backend.
4. **Scope Filtering Relies on Substring Matching:** Passing `resource_id="fake-cluster-9999"` matches `is_cluster_filter` because it checks `"cluster" in resource_id.lower()`. Unknown IDs without keywords fall through to the full workspace total ($284,620).

