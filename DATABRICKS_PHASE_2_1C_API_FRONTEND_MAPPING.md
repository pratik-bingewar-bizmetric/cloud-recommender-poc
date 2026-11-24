# Phase 2.1C: Databricks API & Frontend Mapping Matrix

> **Document Status:** Active Engineering Record  
> **Phase:** 2.1C — Databricks Integration Completion (Warehouse-Independent)  
> **Date:** 2026-11-23  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/gcp-service-account-integration`

---

## 1. Overview & Data Integrity Rules

This matrix verifies the explicit mapping between the frontend FinOps Command Center modules and backend REST APIs for Azure Databricks workspace `642006393507276`.

### Core Data Integrity Rules Enforced:
1. **Zero Silent Fallback:** If live System Tables data has not been ingested, the UI renders explicit honest status banners (`WAREHOUSE_STOPPED`, `APPROVAL_REQUIRED`, `NO_DATA`) rather than silently synthesizing mock numbers.
2. **Dynamic Workspace Scoping:** Every query, filter, and KPI is strictly bound to `workspace_id = '642006393507276'`.
3. **Database Re-hydration:** If backend processes restart, `_ensure_loaded` retrieves persisted records from PostgreSQL without losing historical state.

---

## 2. FinOps Module to API Mapping Matrix

| # | FinOps Module / View | Backend Endpoint | Request Parameters | Response Contract | Truthful State Representation |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | **Executive Cost Overview** | `GET /api/v1/finops/overview` | `connection_id`, `period`, `workspace_id` | `ExecutiveOverviewResponse` | 6 KPI cards, 30-day spend trend, composition chart, governance alert banner with "Approve & Start Ingestion" button. |
| **2** | **Cost Explorer** | `GET /api/v1/finops/cost-explorer` | `connection_id`, `workspace_id` | `CostExplorerResponse` | Spend breakdown by workspace/resource, DBU trends, billing ledger with CSV export trigger. |
| **3** | **Cost Allocation** | `GET /api/v1/finops/cost-allocation` | `connection_id`, `workspace_id` | `CostAllocationResponse` | Allocation by business unit, workspace, cluster type, and tag coverage percentage. |
| **4** | **Cost & Billing (Ledger)** | `GET /api/v1/finops/billing/usage` | `workspace_id`, `record_type`, `envelope=true` | `BillingUsageEnvelope` | Paginated raw/normalized meter events, exact source timestamp intervals, SKU names, signed quantities. |
| **5** | **Showback & Chargeback** | `GET /api/v1/finops/cost-allocation` | `workspace_id` | `CostAllocationResponse` | Departmental and project chargeback tables with exportable invoices. |
| **6** | **Forecast & Budgets** | `GET /api/v1/finops/forecast-budgets` | `workspace_id` | `ForecastBudgetsResponse` | Projected monthly run-rate, budget threshold warnings, interactive growth/optimization scenario slider. |
| **7** | **Anomaly Detection** | `GET /api/v1/finops/anomalies` | `workspace_id` | `AnomalyDetectionResponse` | Statistical usage spikes, root-cause SKU identification, anomaly state transitions (`investigating`, `dismissed`). |
| **8** | **Optimization Advisor** | `GET /api/v1/finops/optimization-advisor` | `workspace_id` | `OptimizationAdvisorResponse` | Actionable recommendations (e.g. Serverless SQL conversion, auto-stop tuning), projected savings, human-approval action tracking. |
| **9** | **AI & GenAI Economics** | `GET /api/v1/finops/ai-economics` | `workspace_id` | `AiEconomicsResponse` | Model serving endpoints, GPU cluster utilization, token burn rate, preview compute cost breakdown. |
| **10** | **DBU Consumption & Summary** | `GET /api/v1/finops/billing/summary` | `workspace_id` | `BillingSummaryResponse` | Total gross DBU, net DBU, retraction DBU, matched vs unmatched pricing counts, quantity coverage. |
| **11** | **Workspace Detail View** | `GET /api/v1/databricks/workspaces/health` | `workspace_id` | `WorkspaceHealth` | Real-time warehouse status (`STOPPED`), cluster inventory, runtime engine version, Unity Catalog enablement. |

---

## 3. Truthful State Machine & UI Badges

The UI implements explicit visual states to communicate data status honestly to operators:

```
[ WAREHOUSE STOPPED ] ──(Operator starts WH)──> [ RUNNING ]
         │                                            │
         ▼                                            ▼
[ Operational Blocker Banner ]              [ Operator Clicks Approve ]
"Compute suspended. Zero-execution guardrail"         │
                                                      ▼
                                            [ Ingestion Running ]
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
             [ PARTIAL_PRICING ]                                               [ RECONCILED ]
   "70.20% DBU Coverage (Genie unpriced)"                              "100% Usage Matched to Rate Card"
```

1. **`NO_DATA` / Ingestion Pending:** Rendered when no records exist in PostgreSQL. KPI cards display `$0.00` or `--` with an informational notice guiding the operator to approve ingestion.
2. **`WAREHOUSE_STOPPED`:** Rendered when the operator triggers ingestion but the target warehouse is suspended. Displays an amber blocker banner explaining that auto-resume is prohibited under FinOps zero-execution guardrails.
3. **`PARTIAL_PRICING`:** Rendered when all Serverless SQL compute is priced against list rates, but preview compute (e.g. Genie) lacks a published rate card entry. Preserves actual DBU with an explicit notice that unmatched compute is not artificially zeroed out.
4. **`RECONCILED`:** Rendered when 100% of metered DBU matches published list price intervals and all 6 mathematical identity checks pass.
5. **`FAILED`:** Rendered if statement execution fails or times out. Displays sanitized error codes with zero token leakage.

