# FinOps KPI Inventory

> **Application:** Bizmetric FinOps & Infrastructure Intelligence Platform  
> **Repository:** `cloud-recommender-poc`  
> **Status:** Production Reference & Authoritative Forensic Inventory  
> **Verification Date:** 2026-11-10  
> **Scope:** Azure Databricks Workspace `642006393507276` (`databricks-azure-dev`) / Subscription `sub-finops-enterprise-01`

---

## 1. Overview & Verification Standard

This document catalogs every actual KPI card and important summary metric rendered across all 21 modules of the unified Bizmetric platform.

### Standard of Evidence
1. **Source Code Parity:** Every documented value, formula, and unit matches `backend/src/cloud_recommender/services/databricks/finops_analytics_service.py` and `frontend/src/components/FinOpsCommandCenterView.tsx`.
2. **Explicit Absence Declaration:** Where an operational or analytical module has no dedicated KPI cards, it is explicitly marked as `No dedicated KPI cards currently implemented.` rather than inventing synthetic cards.
3. **Unit Separation:** DBU consumption (`88,420 DBU`) is strictly separated from GenAI token metrics (`10.28B tokens`).
4. **Zero-Execution Realization:** Implemented and realized savings are verified at `$0.00` under the platform's non-mutation security policy.

---

## 2. Master KPI Inventory Table

| # | Module | Section | KPI Name | Metric ID | Default Value | Unit | Calculation Formula | Authoritative Source | Status | Drill-Down Target |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Executive Overview | FinOps & Cost Intelligence | Total Spend | `total_spend` | \$284,620 | USD | `databricks_spend + azure_storage_spend + azure_network_spend` | Azure Cost Management & Databricks Ingestion | BASELINE | `FinancialKpiDrawer` (Total Spend Breakdown) |
| 2 | Executive Overview | FinOps & Cost Intelligence | Databricks Spend | `databricks_spend` | \$176,840 | USD | `dbu_consumption * blended_rate` (across 24 ledger items) | Azure Databricks DBU Metering | BASELINE | `FinancialKpiDrawer` (Databricks Platform Ledger) |
| 3 | Executive Overview | FinOps & Cost Intelligence | AI & GenAI Spend | `ai_spend` | \$38,460 | USD | `model_serving_dbu ($26,740) + ai_gateway_tokens ($11,296) + vector_search ($424)` | Model Serving & AI Gateway | BASELINE | `FinancialKpiDrawer` / AI Economics module |
| 4 | Executive Overview | FinOps & Cost Intelligence | DBU Consumption | `dbu_consumption` | 88,420 DBU | DBU | `sum(system.billing.usage.usage_quantity)` (24 ledger records) | `system.billing.usage` | BASELINE | `FinancialKpiDrawer` (DBU Breakdown by SKU) |
| 5 | Executive Overview | FinOps & Cost Intelligence | Identified Savings | `savings_opportunity` | \$24,530 | USD | `sum(decisions.estimated_savings_monthly)` (Approved initiatives) | FinOps Optimization Advisor | BASELINE | Optimization Advisor module |
| 6 | Executive Overview | FinOps & Cost Intelligence | Forecast Month-End | `forecast_spend` | \$319,500 | USD | `round(mtd_spend * (30.0 / 26.7236), -2)` (+$19,500 vs \$300K budget) | Linear Regression & Run-Rate Engine | ESTIMATED | Forecast & Budgets module |
| 7 | Executive Overview | FinOps & Cost Intelligence | Cost Anomalies | `anomalies` | 3 | count | `count(open_anomalies)` | Databricks Usage Anomaly Detector | BASELINE | Anomaly Detection module |
| 8 | Cost Explorer | FinOps & Cost Intelligence | Gross Consumption | `gross_consumption` | \$176,840 | USD | `sum(billing_ledger.effective_cost)` | `system.billing.usage` | BASELINE | Granular Billing Ledger |
| 9 | Cost Explorer | FinOps & Cost Intelligence | Effective Rate | `effective_rate` | \$2.000 | USD/DBU | `total_effective_cost / total_dbu_consumption` | Contract Rate Card & Consumption Ledger | BASELINE | Rate card breakdown drawer |
| 10 | Cost Explorer | FinOps & Cost Intelligence | Unallocated Spend | `unallocated_spend` | \$1,240 | USD | `sum(billing_ledger WHERE allocation_status = 'Unallocated')` | Tag Completeness Analyzer | BASELINE | Cost Allocation module |
| 11 | Cost Explorer | FinOps & Cost Intelligence | Credits & Discounts | `credits_discounts` | \$8,260 | USD | `sum(azure_credits + committed_use_discounts)` | Azure Commercial Billing | BASELINE | Commercial adjustments ledger |
| 12 | Cost Allocation | FinOps & Cost Intelligence | Allocated Spend | `allocated_spend` | \$164,360 | USD | `total_spend - unallocated_spend` (92.9% allocated) | Tag & Workspace Rules Engine | BASELINE | Spend by Business Unit table |
| 13 | Cost Allocation | FinOps & Cost Intelligence | Unallocated Spend | `unallocated_spend` | \$12,480 | USD | `sum(unattributed_usage_records)` | Tag Completeness Analyzer | BASELINE | Unattributed Records list |
| 14 | Cost Allocation | FinOps & Cost Intelligence | Active Rules | `active_rules` | 28 | rules | `count(active_allocation_rules)` | FinOps Rule Engine | BASELINE | Allocation Rulebook table |
| 15 | Cost Allocation | FinOps & Cost Intelligence | Shared Pool | `shared_pool` | \$21,600 | USD | `sum(shared_platform_costs)` | Shared Cost Allocation Model | BASELINE | Shared pool distribution breakdown |
| 16 | Cost & Billing | FinOps & Cost Intelligence | BUs Billed | `bu_billed` | 12 | BUs | `count(distinct business_units)` | HR Cost Center Map | BASELINE | Chargeback Statement table |
| 17 | Cost & Billing | FinOps & Cost Intelligence | Shared Pool | `shared_pool` | \$21,600 | USD | `sum(shared_infrastructure_costs)` | Shared Pool Model | BASELINE | Shared pool statement lines |
| 18 | Cost & Billing | FinOps & Cost Intelligence | Disputed Allocations | `disputed_allocations` | 3 | disputes | `count(open_chargeback_disputes)` | Dispute Workflow | BASELINE | Dispute investigation queue |
| 19 | Cost & Billing | FinOps & Cost Intelligence | Statement Readiness | `statement_readiness` | 96% | % | `reconciled_statement_lines / total_statement_lines` | Financial Close Validation | BASELINE | Statement validation audit |
| 20 | Forecast & Budgets | FinOps & Cost Intelligence | Approved Budget | `approved_budget` | \$300,000 | USD | `allocated_monthly_budget` | Finance Budget Registry | BASELINE | Budget Controls table |
| 21 | Forecast & Budgets | FinOps & Cost Intelligence | Actual MTD | `actual_mtd` | \$284,620 | USD | `sum(mtd_consumption_cost)` (94.9% consumed) | Azure Databricks Billing | BASELINE | Spend Trend chart |
| 22 | Forecast & Budgets | FinOps & Cost Intelligence | Forecast Month-End | `forecast_month_end` | \$319,500 | USD | `round(mtd_actual * (30.0 / 26.7236), -2)` | Forecasting Model | ESTIMATED | Scenario Simulator |
| 23 | Forecast & Budgets | FinOps & Cost Intelligence | Forecast Confidence | `forecast_confidence` | 87% | % | `r_squared_fit_score` (Confidence interval: ±3.4%) | Statistical Fit Engine | BASELINE | Model fit diagnostics |
| 24 | Forecast & Budgets | FinOps & Cost Intelligence | Forecast Accuracy | `forecast_accuracy` | NOT AVAILABLE | MAPE | `mean_absolute_percentage_error` (min. 3 completed cycles req.) | Forecasting Model Benchmark | UNAVAILABLE | Accuracy benchmark audit |
| 25 | Forecast & Budgets | FinOps & Cost Intelligence | Budget Utilization | `budget_utilization` | 94.9% | % | `(actual_mtd / approved_budget) * 100` | Finance Budget Registry | BASELINE | Budget Burn curve |
| 26 | Forecast & Budgets | FinOps & Cost Intelligence | Projected Overrun | `projected_overrun` | +\$19,500 | USD | `forecast_month_end - approved_budget` (+6.5%) | Forecasting Model | ESTIMATED | Scenario Simulator |
| 27 | Anomaly Detection | FinOps & Cost Intelligence | Open Anomalies | `open_anomalies` | 3 | items | `count(open_anomalies)` | Databricks Anomaly Engine | BASELINE | Detected Anomalies queue |
| 28 | Anomaly Detection | FinOps & Cost Intelligence | Potential Exposure | `potential_exposure` | \$9,840 | USD | `sum(anomaly.estimated_daily_impact * 30)` | Exposure Calculator | BASELINE | Anomaly impact detail |
| 29 | Anomaly Detection | FinOps & Cost Intelligence | Mean Time to Detect | `mean_time_to_detect` | 18 min | min | `avg(detection_time - event_time)` | Telemetry Latency Monitor | BASELINE | Telemetry latency graph |
| 30 | Anomaly Detection | FinOps & Cost Intelligence | Auto-Triaged | `auto_triaged` | 86% | % | `triaged_anomalies / total_detected_anomalies` | Triage Engine | BASELINE | Auto-triage audit trail |
| 31 | Optimization Advisor | FinOps & Cost Intelligence | Potential Savings | `potential_savings` | \$31,340 | USD | `sum(all_detected_anomalies_and_waste_candidates)` | FinOps Advisor Heuristics | BASELINE | Recommendations inventory |
| 32 | Optimization Advisor | FinOps & Cost Intelligence | Estimated Savings | `estimated_savings` | \$31,280 | USD | `sum(actionable_heuristic_opportunities)` | FinOps Advisor Heuristics | ESTIMATED | Recommendations inventory |
| 33 | Optimization Advisor | FinOps & Cost Intelligence | Approved Savings | `approved_savings` | \$24,530 | USD | `sum(staged_recommendations.estimated_savings_monthly)` | FinOps Advisor Decisions | BASELINE | Staged Initiatives drawer |
| 34 | Optimization Advisor | FinOps & Cost Intelligence | Quick Wins | `quick_wins` | 5 | items | `count(recommendations WHERE effort = 'Low')` | FinOps Advisor | BASELINE | Quick Win filter view |
| 35 | Optimization Advisor | FinOps & Cost Intelligence | Awaiting Approval | `awaiting_approval` | 5 | items | `count(recommendations WHERE status = 'Approval required')` | FinOps Advisor | BASELINE | Approval workflow drawer |
| 36 | Optimization Advisor | FinOps & Cost Intelligence | Implemented Savings | `implemented_savings` | \$0.00 | USD | `sum(implemented_recommendations.actual_savings) [strictly $0.00]` | FinOps Governance Engine | BASELINE | Zero-Execution status banner |
| 37 | Optimization Advisor | FinOps & Cost Intelligence | Realized Savings | `realized_savings` | \$0.00 | USD | `sum(verified_post_audit_savings) [strictly $0.00]` | FinOps Billing Audit | BASELINE | Post-implementation audit log |
| 38 | AI Economics | FinOps & Cost Intelligence | AI Spend | `ai_spend` | \$38,460 | USD | `model_serving_spend ($26,740) + ai_gateway_spend ($11,296) + vector_search ($424)` | Model Serving & AI Gateway | BASELINE | Model Economics table |
| 39 | AI Economics | FinOps & Cost Intelligence | Input Tokens | `input_tokens` | 8.42B | tokens | `sum(system.ai_gateway.usage.prompt_tokens)` | AI Gateway Telemetry | BASELINE | Token Consumption by Model chart |
| 40 | AI Economics | FinOps & Cost Intelligence | Output Tokens | `output_tokens` | 1.86B | tokens | `sum(system.ai_gateway.usage.completion_tokens)` | AI Gateway Telemetry | BASELINE | Token Consumption by Model chart |
| 41 | AI Economics | FinOps & Cost Intelligence | Cached Tokens | `cached_tokens` | 2.10B | tokens | `sum(cached_prompt_tokens)` (25% of input volume) | Provider Context Caching | BASELINE | Context Caching breakdown |
| 42 | AI Economics | FinOps & Cost Intelligence | Cost per 1K Tokens | `cost_per_1k_tokens` | \$0.0037 | USD/1K | `ai_spend / (total_tokens / 1000)` | Model Rate Card & Usage | BASELINE | Rate card breakdown drawer |
| 43 | AI Economics | FinOps & Cost Intelligence | Cost per Task | `cost_per_task` | \$0.084 | USD/task | `ai_task_spend / completed_tasks` (↓ 6.2% vs prior month) | Task Economics Monitor | BASELINE | Agent Task scorecard |
| 44 | Governance & Policies | FinOps & Cost Intelligence | Policy Compliance | `policy_compliance` | 94.2% | % | `compliant_resources / total_evaluated_resources` | Policy Audit Engine | BASELINE | Policy Matrix table |
| 45 | Governance & Policies | FinOps & Cost Intelligence | Policy Violations | `policy_violations` | 18 | violations | `count(active_policy_violations)` (6 unresolved) | Compliance Scanner | BASELINE | Violations queue |
| 46 | Governance & Policies | FinOps & Cost Intelligence | Resources Without Owner | `resources_without_owner` | 16 | resources | `count(resources WHERE owner_tag IS NULL)` | Tag Completeness Analyzer | BASELINE | Tag Remediation queue |
| 47 | Governance & Policies | FinOps & Cost Intelligence | Expiring Exceptions | `expiring_exceptions` | 5 | exceptions | `count(exceptions WHERE expiry_date <= now() + 14_days)` | Exception Registry | BASELINE | Exception renewal workflow |
| 48 | Query History | Workspace & Operations | Total Query Executions | `total_query_count` | 7 | queries | `count(system.query.history)` | `system.query.history` | BASELINE | Query Duration Histogram |
| 49 | Query History | Workspace & Operations | Finished (Success) | `finished_query_count` | 5 | queries | `count(records WHERE status = 'FINISHED')` (71.4%) | `system.query.history` | BASELINE | Filter by FINISHED queries |
| 50 | Query History | Workspace & Operations | Failed Executions | `failed_query_count` | 1 | queries | `count(records WHERE status = 'FAILED')` | `system.query.history` | BASELINE | Filter by FAILED queries |
| 51 | Query History | Workspace & Operations | Average Duration | `avg_query_duration` | 1,432 ms | ms | `avg(execution_duration_ms)` | `system.query.history` | BASELINE | Duration Histogram buckets |

---

## 3. Modules Without Dedicated KPI Cards

In strict accordance with forensic truthfulness, the following modules do not have dedicated KPI cards in the active production codebase. Their operational telemetry is rendered as interactive inventories, data tables, or diagnostic trees:

| Module Name | Module Section | Current Presentation Architecture | Interactive Drill-Down / Navigation |
|---|---|---|---|
| **Clusters** | Workspace & Operations | Table with search, status filter (`RUNNING`, `TERMINATED`, `PENDING`), cluster ID, autoscale, creator, and total count badge. | Clicking any row opens `ResourceDetailDrawer` with configuration and DBU consumption. |
| **Warehouses** | Workspace & Operations | Table with search, state filter (`STOPPED`, `RUNNING`), sizing, and zero-execution banner for `05ed10a52697a344`. | Clicking row opens `ResourceDetailDrawer` with query history and sizing recommendations. |
| **Jobs & Workflows** | Workspace & Operations | Table with search, status filter (`SUCCESS`, `FAILED`, `RUNNING`), schedule, creator, and discovered count badge. | Clicking row opens `ResourceDetailDrawer` with DAG tasks and run history. |
| **Pipelines (DLT)** | Workspace & Operations | Table with search, state filter (`ACTIVE`, `IDLE`, `FAILED`), target schema, and discovered count badge. | Clicking row opens `ResourceDetailDrawer` with data quality expectations and update history. |
| **Model Serving** | Workspace & Operations | Table with search, status filter (`READY`, `UPDATING`), compute scale, and endpoint count badge (`27 Discovered Models`). | Clicking row opens `ResourceDetailDrawer` with token metrics and latency SLA. |
| **Unity Catalog** | Workspace & Operations | Dual-pane explorer with 3-level namespace tree (Metastore &rarr; Catalog &rarr; Schema &rarr; Table) and column schema matrix. | Interactive selection navigates catalogs and displays column schemas. |
| **Databricks Apps** | Workspace & Operations | App cards grid with search, status filter (`DEPLOYED`, `STOPPED`), and Unattributed Cost Bucket callout banner. | Clicking card opens `ResourceDetailDrawer` with runtime parameters. |
| **System Tables** | Workspace & Operations | Diagnostic table with 10 core verified schemas, column counts, query state (`REST API Verified / SQL Gated`), and expandable column schemas. | Expanding rows displays column name, type, nullability, and description. |
| **Audit & Governance** | Workspace & Operations | Compliance status banner (`Read-Only RBAC Enforced`) and role verification summary (`Reader`, `Account User`, zero-mutation block). | Displays verified permissions and exclusion of mutating roles. |
| **Reports & Audit** | FinOps & Cost Intelligence | 6 downloadable Report Pack cards (Executive, AI, Optimization, Cloud, Allocation, Governance) and chronological Audit Event log table. | Action buttons trigger spec-compliant CSV / PDF export downloads. |

---

## 4. Auxiliary FinOps Subviews Inventory

| Subview | Internal Key | Implemented KPIs | Display Values | Data Sources |
|---|---|---|---|---|
| **Compute & Warehouses** | `compute` | Compute Spend, Active Compute, Idle Capacity, Potential Savings | \$108,960, 14 units, 22% idle, \$11,860 | `system.billing.usage` + Cluster API |
| **Data & Storage** | `data` / `storage` | Storage Spend, Total Stored Data, Cold Data, Ingestion Spend | \$18,950, 482 TB, 142 TB cold, \$3,410 | ADLS Gen2 Telemetry + Unity Catalog |
| **Network & Cloud** | `network` | Network & Cloud Spend, Data Egress, Private Endpoints, Unmapped Resources | \$28,420, 42.8 TB, 38 endpoints, 3 unmapped | Azure Network Watcher & Cost Management |
| **Workload Economics** | `workloads` | Tracked Workloads, Unit Metrics Coverage, Avg Cost / Workload, Value Positive | 84 workloads, 62 covered, \$2,105/workload, 78 positive | Workload Profiler & Tag Engine |

