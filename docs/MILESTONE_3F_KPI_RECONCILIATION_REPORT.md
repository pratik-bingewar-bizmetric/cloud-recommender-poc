# Milestone 3F — Financial KPI Reconciliation & Mathematical Integrity Report

**Date:** November 7, 2026  
**Repository:** `cloud-recommender-poc`  
**Active Branch:** `feature/databricks-apps-integration`  
**Audit Target:** Azure Databricks workspace `642006393507276`  

---

## 1. Audit of the Seven Core Executive KPIs

This section provides the full forensic analysis of each of the seven executive KPIs rendered in the FinOps Command Center.

---

### KPI 1: Total Cloud Spend
- **Displayed Value:** `$284,620` (Workspace Level) | `$42,180` (Warehouse Filter) | `$24,600` (Cluster Filter) | `$26,740` (Serving Filter) | `$0 (Unattributed)` (App Filter)
- **Unit & Currency:** `USD` | Currency: `USD`
- **Claimed Source:** `Azure Cost Management & Databricks Ingestion`
- **Actual Implementation Source:** Hardcoded constant in `FinOpsAnalyticsService.get_executive_overview()` (line 596).
- **Underlying SQL / API Call:** None. No live REST request is made to Azure Cost Management API (`management.azure.com/providers/Microsoft.CostManagement/query`) or Databricks billing API.
- **Date Range & Timezone:** Month-to-date (Nov 01 - Nov 20, 2026 UTC).
- **Aggregation Formula:** Intended to be `SUM(Azure VM Spend) + SUM(Databricks DBU Spend) + SUM(Storage & Network)`. In practice, returns a fixed float `284620.0`.
- **Pricing Validity Interval:** Assumed calendar month rate cards.
- **Data Freshness Timestamp:** Labeled as `"Live Azure Databricks"`, but is an in-memory baseline.
- **Value Classification:** **CALCULATED BASELINE MODEL (NON-LIVE)**.
- **Reconciliation Audit Findings:**
  - When child filter `resource_id="05ed10a52697a344"` is applied, value drops to `$42,180`.
  - When an unknown resource ID (e.g. `"unknown-guid-1234"`) is passed, value silently reverts to the full `$284,620` rather than `$0.00`.

---

### KPI 2: Databricks Platform Spend
- **Displayed Value:** `$176,840` (Workspace Level) | `$42,180` (Warehouse Filter) | `$24,600` (Cluster Filter) | `$26,740` (Serving Filter) | `$0` (App Filter)
- **Unit & Currency:** `USD` | Currency: `USD`
- **Claimed Source:** `Azure Databricks DBU Metering`
- **Actual Implementation Source:** Hardcoded constant in `FinOpsAnalyticsService.get_executive_overview()` (line 609).
- **Underlying SQL / API Call:** Intended query: `SELECT SUM(usage_quantity * list_price) FROM system.billing.usage`. In practice, no SQL is executed due to stopped warehouse state.
- **Date Range & Timezone:** Current calendar month (UTC).
- **Aggregation Formula:** `SUM(DBU Consumption * Effective DBU Rate)`.
- **Value Classification:** **CALCULATED BASELINE MODEL (NON-LIVE)**.
- **Reconciliation Audit Findings:**
  - **Severe Rate Variance:** The platform claims `dbu_consumption = 88,420 DBU` and `effective_rate = $0.148 / DBU`.
    - Mathematical calculation: `88,420 DBU * $0.148/DBU = $13,086.16`.
    - Reported Databricks spend: **`$176,840.00`**.
    - **Reconciliation Variance:** **`$163,753.84`** (an order of magnitude mismatch).
    - If `$176,840` were correct for `88,420 DBU`, the actual effective rate is `$2.00 / DBU`, not `$0.148 / DBU`.

---

### KPI 3: AI & GenAI Spend
- **Displayed Value:** `$38,460` (Executive Overview) | `$26,740` (Serving Endpoint Filter) | `$4,280 / mo` (Databricks Workspace Detail View Module 11)
- **Unit & Currency:** `USD` | Currency: `USD`
- **Claimed Source:** `Databricks Model Serving (27 endpoints)`
- **Actual Implementation Source:** Hardcoded constant in `FinOpsAnalyticsService.get_executive_overview()` (line 622) vs hardcoded JSX in `DatabricksWorkspaceDetailView.tsx` (line 1904).
- **Underlying SQL / API Call:** Intended query: `SELECT SUM(cost) FROM system.ai_gateway.usage`. In practice, no live API call is executed.
- **Date Range & Timezone:** Current month (UTC).
- **Aggregation Formula:** Intended to be `SUM(Model Serving DBUs) + SUM(External Model Invocations)`.
- **Value Classification:** **FIXTURE ESTIMATE (NON-LIVE)**.
- **Reconciliation Audit Findings:**
  - **Internal Cross-Module Discrepancy:**
    - Executive Overview KPI 3 reports **`$38,460`**.
    - Spend Composition Chart (Module 1) reports AI as **`$59,770`** (variance: **`$21,310`**).
    - Databricks Workspace Detail View (Module 11) reports AI Spend as **`$4,280 / mo`** (variance: **`$34,180`**).
    - Model Serving Filter reports **`$26,740`**.

---

### KPI 4: DBU Consumption
- **Displayed Value:** `88,420 DBU` (Overview) | `19,172 DBU` (Warehouse) | `11,180 DBU` (Cluster) | `6,685 DBU` (Serving) | `310 DBU (Unattributed)` (App) | `1,420.5 DBUs` (Databricks Workspace Detail View Module 13)
- **Unit & Currency:** `DBU` | Currency: `None`
- **Claimed Source:** `Azure Databricks DBU Metering (system.billing.usage)`
- **Actual Implementation Source:** Hardcoded in `FinOpsAnalyticsService.get_executive_overview()` (line 635).
- **Underlying SQL / API Call:** `SELECT sum(usage_quantity) FROM system.billing.usage WHERE usage_unit = 'DBU'`. No SQL executed.
- **Date Range & Timezone:** Current month (UTC).
- **Aggregation Formula:** Sum of all compute DBU meters.
- **Value Classification:** **CALCULATED BASELINE MODEL (NON-LIVE)**.
- **Reconciliation Audit Findings:**
  - **Cross-Component Discrepancy:** The Executive Overview reports `88,420 DBU`, whereas Module 13 (Cost & Billing in the Databricks Workspace view) reports `1,420.5 DBUs`.
  - **Strict Unit Isolation Verified:** In all backend schemas, `dbu_consumption` has `currency=None` and `unit="DBU"`, preventing mixing with token counts or dollars.

---

### KPI 5: Savings Opportunity
- **Displayed Value:** `$31,280` (Overview) | `$4,200` (Warehouse) | `$3,600` (Cluster) | `$5,400` (Serving) | `$250` (App)
- **Unit & Currency:** `USD` | Currency: `USD`
- **Claimed Source:** `FinOps Optimization Advisor`
- **Actual Implementation Source:** Hardcoded sum in `FinOpsAnalyticsService.get_executive_overview()` (line 648) and `get_optimization_advisor()` (line 2639).
- **Underlying SQL / API Call:** None.
- **Aggregation Formula:** Sum of estimated savings across recommendations `dec-01` ($8,400), `dec-02` ($6,100), `dec-03` ($2,750), `dec-04` ($3,460), `dec-05` ($3,820) = `$24,530`.
- **Value Classification:** **ADVISORY FIXTURE MODEL**.
- **Reconciliation Audit Findings:**
  - **Recommendation Sum Mismatch:** The 5 active recommendations in `_get_decisions()` sum to **`$24,530`** ($8,400 + $6,100 + $2,750 + $3,460 + $3,820). However, the Savings Opportunity KPI displays **`$31,280`** (unreconciled difference: **`$6,750`**).

---

### KPI 6: Forecasted Spend
- **Displayed Value:** `$319,500` (Overview) | `$48,000` (Warehouse) | `$28,000` (Cluster) | `$31,000` (Serving) | `$1,500` (App)
- **Unit & Currency:** `USD` | Currency: `USD`
- **Claimed Source:** `Linear Regression & Run-Rate Engine`
- **Actual Implementation Source:** Hardcoded baseline in `FinOpsAnalyticsService.get_executive_overview()` (line 661).
- **Underlying SQL / API Call:** None.
- **Aggregation Formula:** Formula in `simulate_forecast_scenario()`:
  `result = base * (1 + growth/100) - (91420 * c/100) - (38460 * t/100)`.
  With defaults (`growth=0`, `c=0`, `t=0`), evaluates to `319,500.0`.
- **Value Classification:** **PARAMETRIC MODEL (CALCULATED)**.
- **Reconciliation Audit Findings:**
  - Approved budget is `$300,000`. Forecast is `$319,500`, resulting in a `$19,500` over-budget variance.
  - The forecast is internally consistent within the scenario simulation model, but is anchored to a synthetic baseline.

---

### KPI 7: Cost Anomalies
- **Displayed Value:** `7` (Overview) | `1` (Warehouse) | `1` (Cluster) | `2` (Serving) | `0` (App)
- **Unit & Currency:** `count` | Currency: `None`
- **Claimed Source:** `Databricks Usage Anomaly Detector`
- **Actual Implementation Source:** Hardcoded float `7.0` in `FinOpsAnalyticsService.get_executive_overview()` (line 674).
- **Underlying SQL / API Call:** None.
- **Aggregation Formula:** Intended to be `COUNT(active anomalies where status = 'Open')`.
- **Value Classification:** **FIXTURE COUNT (NON-LIVE)**.
- **Reconciliation Audit Findings:**
  - In `get_anomaly_detection()` (Module 10), the list `anomalies` contains **3 items** (`anom-01`, `anom-02`, `anom-03`). However, the `open_anomalies` KPI displays **`7`**.
  - Four anomalies are missing from the underlying detail list.

---

## 2. Cross-Module Mathematical Reconciliation Summary

| Metric / Dimension | Module 1 (Overview) | Module 2 (Cost Explorer) | Module 4 (Compute) | Module 5 (AI Economics) | Databricks Detail View | Reconciled? | Variance / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Total Cloud Spend** | $284,620 | N/A | N/A | N/A | N/A | **NO** | Ledger in Mod 2 sums to $43,350 |
| **Databricks Spend** | $176,840 | $176,840 (Gross KPI) | N/A | N/A | N/A | **PARTIAL** | Matches KPI, but ledger rows sum to $43,350 |
| **AI / GenAI Spend** | $38,460 | N/A | N/A | $38,460 | $4,280 | **NO** | Detail view reports $4,280; Mod 1 Spend Comp reports $59,770 |
| **Compute Spend** | $108,155 (Comp) | N/A | $91,420 | N/A | N/A | **NO** | $16,735 variance between Mod 1 composition and Mod 4 KPI |
| **DBU Consumption** | 88,420 DBU | N/A | N/A | N/A | 1,420.5 DBU | **NO** | 87,000 DBU gap between Overview and Detail View Mod 13 |
| **Token Volume** | N/A | N/A | N/A | 10.28B (Input + Output) | 42.8M | **NO** | 10.24 Billion token mismatch |
| **Savings Opportunity**| $31,280 | N/A | $14,800 | N/A | N/A | **NO** | Sum of recommendations is $24,530 |
| **Open Anomalies** | 7 | N/A | N/A | N/A | N/A | **NO** | Detail list contains only 3 items |

---

## 3. Retractions, Adjustments & Double-Counting Audit

1. **Billing Retractions & Rebills:**
   - Databricks usage records occasionally contain negative usage quantities or retraction adjustments (`usage_quantity < 0`).
   - The current Cost Explorer logic uses simple addition: `total_effective = sum(r.effective_cost for r in billing_ledger)`.
   - In the mock fixture, no retraction records are currently present. However, the calculation logic is mathematically capable of reducing total spend if negative retraction items are injected.
2. **Double-Counting Prevention:**
   - In Module 1, `total_spend = $284,620` and `databricks_spend = $176,840`.
   - The UI presentation clearly labels `total_spend` as inclusive of Databricks spend plus Azure host infrastructure ($107,780).
   - Databricks spend is not added to Total Spend in the executive cards, avoiding double counting on the top row.
3. **Credit and Discount Adjustments:**
   - In `get_cost_explorer()`, `credits_discounts` is reported as `$8,260`.
   - It is correctly labeled as commercial EA adjustments and is not deducted twice from gross consumption.

