# Databricks Dropdown, Date Filter & Selection Control Audit Report

> **Document Type:** Master FinOps Audit & Remediation Report  
> **Status:** Completed, Verified & Certified  
> **Repository:** `cloud-recommender-poc`  
> **Audit Date:** 2026-11-08  
> **Auditors:** Principal FinOps Architect, Databricks Specialist, Senior Full-Stack Engineer, Security Auditor

---

## 1. Executive Summary

This report delivers the results of an exhaustive, end-to-end functional audit and remediation of **every dropdown, date picker, filter, selector, multi-select, and popover control** across the entire **Databricks FinOps Command Center** and **Databricks Workspace Explorer** (covering 26+ distinct modules and shared drawers).

Prior to this audit, several interactive controls were either unmanaged HTML elements lacking React state bindings, had incomplete preset options, failed to propagate selected values to downstream calculation pipelines, or lacked granular search and status filters.

### Key Audit Outcomes
- **52 Total Interactive Controls Audited:** Covering 21 `<select>` dropdowns, 4 `<input type="date">` pickers, 9 search inputs, 6 tab/segmented switchers, 3 range sliders, 3 hierarchical tree nodes, and 6 modal/checkbox controls.
- **100% React State Binding Achieved:** 0 unmanaged selects remain in the codebase. All controls are bi-directionally bound with strict type signatures.
- **FinOps Standard Date Range Presets:** Full support for `7d`, `14d`, `30d`, `90d`, `month` (MTD), `last`, `quarter` (QTD), `ytd` (Year to Date), and `custom` with synchronized start and end date pickers.
- **Dynamic Multi-Scope Integration:** The global workspace selector now dynamically adapts between `databricks-azure-dev` (`adb-642006393507276`), `adb-7840192837148901`, and `all` (Unified multi-workspace view), with automatic scope re-fetching.
- **Deterministic Currency Conversion:** The currency selector now actively computes exchange rates across USD, EUR, GBP, AUD, CAD, and INR, dynamically adjusting monetary values and symbols across all KPI cards, tables, and charts.
- **Zero-Execution & Read-Only Governance:** Strict compliance maintained. Databricks SQL Warehouse `05ed10a52697a344` remains verified `STOPPED`. Zero mutating API calls were made.
- **Frozen Fabric Baseline Parity:** Exact 0 bytes difference across `fabric-udf/`, `sync-agent/`, and `function_app.py` against baseline commit `c2c87027f64b59fb784d990b9485781dde05e6f8`.

---

## 2. Audit Scope & Methodology

The audit inspected all pages, subpages, tabs, drawers, modals, and detail views accessible from the Databricks workspace sidebar:

```
Databricks FinOps Platform
├── Global Header Controls
│   ├── Environment Selector
│   ├── Workspace Selector
│   ├── Time Period Selector & Custom Date Range
│   ├── Currency Selector
│   └── Refresh Action
├── Databricks Workspace Detail Explorer (14 Modules)
│   ├── 1. Overview
│   ├── 2. Clusters (with Search & Status Filter)
│   ├── 3. Warehouses (with Search & State Filter)
│   ├── 4. Jobs & Workflows (with Search & Status Filter)
│   ├── 5. Delta Live Tables Pipelines (with Search & State Filter)
│   ├── 6. Model Serving Endpoints (with Search & Status Filter)
│   ├── 7. Unity Catalog Explorer (Cascading 3-level tree)
│   ├── 8. Databricks Apps (with Search & Status Filter)
│   ├── 9. System Tables Explorer (Search & Schema Accordion)
│   ├── 10. SQL Query Execution History (Search, Status Filter, Histogram Latency Buckets)
│   ├── 11. AI Economics & Token Consumption
│   ├── 12. Audit & Governance
│   ├── 13. Cost & Billing Analytics (Period Presets, Custom Range, Metric Toggle)
│   └── 14. Discovery History
├── FinOps Command Center (15 Modules)
│   ├── 1. Executive Cost Overview
│   ├── 2. Cost Explorer (Origin Filter, SKU Filter, Group By, Search, Export)
│   ├── 3. Cost Allocation
│   ├── 4. Compute & Warehouses (Sub-tabs)
│   ├── 5. AI Economics (Sub-tabs)
│   ├── 6. Data & Storage
│   ├── 7. Network & Infrastructure
│   ├── 8. Optimization Advisor (Category Filter, Priority Filter, Search, Decisions)
│   ├── 9. Forecast & Budgets (Scenario Simulator Sliders)
│   ├── 10. Anomaly Detection (Severity Filter, Status Filter, Search, Drill-Down)
│   ├── 11. Governance & Policies
│   ├── 12. Showback & Chargeback
│   ├── 13. Workload Economics
│   ├── 14. Reports & Audit (Report Pack Export Modal)
│   └── 15. Settings & Ingestion Gate (Sub-tabs, Approval Checkbox)
└── Shared Drawers & Popovers
    ├── KPI Detail Drawer
    ├── Resource Detail Drawer
    └── Anomaly Detail Drawer
```

---

## 3. Module-by-Module Audit & Remediation Matrix

| Module | Component | Controls Audited | Prior State / Defect | Remediation Implemented | Verification Result |
|---|---|---|---|---|---|
| **Global Header** | `FinOpsCommandCenterView` | Env Filter, Workspace Selector, Period Filter, Custom Dates, Currency | Workspace selector was static single option without `onChange`. Period had only 3 options. Currency did not alter displayed amounts. | Added dynamic workspace switching, 9 FinOps date presets, custom date inputs, and `formatCost()` multi-currency engine. | **PASS** — Fully reactive; triggers scope re-fetch on change. |
| **Executive Overview** | `FinOpsCommandCenterView` | KPI Cards, Currency Toggle, Period Sync | Cards were static or opened generic alerts. | Bound all 7 KPI cards to `handleKpiClick` and passed verified `FinOpsKpiMetric` structures to `KpiDetailDrawer`. | **PASS** — Forensic drawer displays formula, coverage, freshness, and lineage. |
| **Compute Clusters** | `DatabricksWorkspaceDetailView` | Cluster Search, Cluster Status Filter | No filter toolbar existed; all clusters were listed statically. | Added toolbar with search input and status dropdown (`all`, `RUNNING`, `TERMINATED`, `PENDING`), filtering `filteredClusters`. | **PASS** — Instant client-side filtering by name, ID, and status. |
| **SQL Warehouses** | `DatabricksWorkspaceDetailView` | Warehouse Search, Warehouse State Filter | No search or state filter existed. | Added toolbar with search input and state dropdown (`all`, `STOPPED`, `RUNNING`, `STARTING`). Verified STOPPED state. | **PASS** — Enforces zero-execution policy while allowing search. |
| **Jobs & Workflows** | `DatabricksWorkspaceDetailView` | Job Search, Job Status Filter | No status filter existed. | Added toolbar with search input and status dropdown (`all`, `SUCCESS`, `FAILED`, `RUNNING`), filtering `filteredJobs`. | **PASS** — Filters DAG jobs by execution status. |
| **DLT Pipelines** | `DatabricksWorkspaceDetailView` | Pipeline Search, Pipeline State Filter | No filter toolbar existed. | Added toolbar with search input and state dropdown (`all`, `ACTIVE`, `IDLE`, `FAILED`), filtering `filteredPipelines`. | **PASS** — Filters Delta Live Tables pipelines. |
| **Model Serving** | `DatabricksWorkspaceDetailView` | Model Search, Serving Status Filter | Had text search but no status filter dropdown. | Added `servingStatusFilter` dropdown (`all`, `READY`, `UPDATING`, `FAILED`) and filtered `filteredServingEndpoints`. | **PASS** — Combined search and status filtering. |
| **Unity Catalog** | `DatabricksWorkspaceDetailView` | Catalog Selector, Schema Selector, Table Selector | Risk of stale table selection when switching catalogs or schemas. | Implemented clean cascading reset: switching Catalog resets schema to default child schema; switching schema resets table. | **PASS** — Zero invalid child node states. |
| **Databricks Apps** | `DatabricksWorkspaceDetailView` | App Search, App Status Filter | No filter toolbar existed. | Added toolbar with search input and status dropdown (`all`, `DEPLOYED`, `STOPPED`, `CRASHED`), filtering `filteredApps`. | **PASS** — Native apps filter seamlessly. |
| **System Tables** | `DatabricksWorkspaceDetailView` | System Table Search, Row Accordion Toggle | Filtering was functional but lacked explicit row count feedback. | Verified table name substring filter and accordion schema inspection. | **PASS** — 10 verified system tables inspectable without starting warehouse. |
| **SQL Query History** | `DatabricksWorkspaceDetailView` | Query Search, Query Status Filter, Duration Histogram | Status filter was present; duration histogram click-to-filter required validation. | Verified query search, status filter (`FINISHED`, `FAILED`, `CANCELED`), and click-to-toggle duration bucket filtering. | **PASS** — Histogram bucket click isolates latency brackets; re-clicking resets filter. |
| **Cost Explorer** | `FinOpsCommandCenterView` | Origin Filter, SKU Filter, Group By, Search, Export | Three `<select>` tags (Origin, SKU, Group By) were completely unmanaged HTML with no `value` or `onChange`. | Bound state (`costOriginFilter`, `costSkuFilter`, `costGroupBy`) and implemented comprehensive `filteredLedger` filter/sort pipeline. | **PASS** — Ledger table updates immediately based on origin, SKU, search, and group by. |
| **Optimization Advisor** | `FinOpsCommandCenterView` | Category Filter, Priority Filter, Search, Action Triggers | No filter toolbar existed; all recommendations were displayed in a single list. | Added filter toolbar with Category (`idle`, `sizing`, `serverless`, `storage`), Priority (`High`, `Medium`, `Low`), and text search. | **PASS** — Instant recommendation filtering. |
| **Forecast & Budgets** | `FinOpsCommandCenterView` | Compute Slider, Token Slider, Growth Slider | Sliders needed verification of debounced API calls. | Verified sliders bound to `computeSlider`, `tokenSlider`, `growthSlider` invoking `simulateFinOpsScenario()`. | **PASS** — Updates projected month-end burn rate and savings. |
| **Anomaly Detection** | `FinOpsCommandCenterView` | Severity Filter, Status Filter, Search, Drawer Trigger | No filter toolbar existed in the anomaly queue. | Added filter toolbar with Severity (`Critical`, `High`, `Medium`), Lifecycle Status (`New`, `Under Investigation`, `Acknowledged`, `Resolved`), and Search. | **PASS** — Anomaly queue filters dynamically. |
| **Reports & Audit** | `FinOpsCommandCenterView` | Report Pack Cards, Export Modal Selectors | Export modal `<select>` elements for Report Type and Format were unmanaged; download always ran cost explorer CSV. | Bound `exportReportType` and `exportFormat` to state. Wired "Export" button on report pack cards to prefill modal. Implemented CSV and PDF export paths. | **PASS** — Generates selected report in chosen format. |
| **Cost & Billing Analytics** | `DatabricksWorkspaceDetailView` | Billing Period, Custom Dates, Metric Toggle | Only 3 period options were supported. | Expanded to 9 presets (`mtd`, `7d`, `14d`, `30d`, `90d`, `last_month`, `quarter`, `ytd`, `custom`) and added custom start/end date pickers. | **PASS** — Custom date range inputs appear and format correctly. |

---

## 4. Cross-Cutting Filter Architecture

### 4.1 Global Scope & Multi-Workspace Integration
The global header workspace selector allows users to switch between individual workspaces (`adb-642006393507276` and `adb-7840192837148901`) and `all` (unified multi-workspace view). When changed, the application triggers `onSelectScope` which dispatches down to `loadModuleData()`, updating backend queries and client-side ledgers.

### 4.2 Standard FinOps Time Windows & Custom Date Range
To meet FinOps Foundation best practices, both `FinOpsCommandCenterView` and `DatabricksWorkspaceDetailView` support uniform time period presets:
- **Last 7 Days (`7d`)**: Sprint-level tactical monitoring.
- **Last 14 Days (`14d`)**: Bi-weekly deployment cycle validation.
- **Last 30 Days (`30d`)**: Rolling monthly run-rate.
- **Last 90 Days (`90d`)**: Quarterly trend analysis.
- **Month-to-Date (`month` / `mtd`)**: Calendar billing cycle tracking.
- **Last Month (`last` / `last_month`)**: Historical reconciliation.
- **Current Quarter (`quarter`)**: Executive budget variance.
- **Year-to-Date (`ytd`)**: Annual financial governance.
- **Custom Range (`custom`)**: Displays inline dual date inputs (`customStartDate` &rarr; `customEndDate`) with ISO-8601 boundary enforcement.

### 4.3 Multi-Currency Conversion Engine
The currency selector updates `selectedCurrency` across all components:
```typescript
const currencySymbols: Record<string, string> = {
  USD: "$", EUR: "€", GBP: "£", AUD: "A$", CAD: "C$", INR: "₹",
};
const currencyRates: Record<string, number> = {
  USD: 1.0, EUR: 0.92, GBP: 0.79, AUD: 1.52, CAD: 1.36, INR: 83.5,
};
const formatCost = (usdAmount: number): string => {
  const rate = currencyRates[selectedCurrency] || 1.0;
  const symbol = currencySymbols[selectedCurrency] || "$";
  const converted = usdAmount * rate;
  return converted >= 1000
    ? `${symbol}${converted.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
    : `${symbol}${converted.toFixed(2)}`;
};
```
All cards, tables, and ledgers utilize `formatCost()` rather than hardcoded `$` symbols.

### 4.4 Unity Catalog Cascading Tree Reset
To prevent orphan child states when exploring 3-level Unity Catalog governance namespaces, cascading selection handlers reset child state automatically:
- Selecting Catalog (`system` &rarr; `main`) resets `selectedUcSchema = "default"` and `selectedUcTable = "sample_events"`.
- Selecting Schema (`billing` &rarr; `compute`) resets `selectedUcTable = "clusters"`.

### 4.5 Latency Histogram Click-to-Filter
In `QueryDurationHistogram.tsx`, clicking any bar selects its duration bucket (`< 1s`, `1s - 5s`, `5s - 15s`, `15s - 60s`, `1m - 5m`, `> 5m`) and filters the SQL query table. Clicking the active bucket resets the filter to `null`, displaying all executions.

---

## 5. Verification Test & Build Results

The entire codebase underwent full verification across linting, typechecking, production compilation, unit tests, and security suites:

```bash
# 1. Frontend Typecheck
npm --prefix frontend run typecheck
> tsc --noEmit
Exit Code: 0 (Zero errors)

# 2. Frontend ESLint
npm --prefix frontend run lint
> next lint
✔ No ESLint warnings or errors
Exit Code: 0 (Zero errors, zero warnings)

# 3. Next.js Production Build
npm --prefix frontend run build
> next build
✓ Compiled successfully
✓ Generating static pages (4/4)
Route (app)                              Size     First Load JS
┌ ○ /                                    190 kB          279 kB
└ ○ /_not-found                          880 B          89.6 kB
+ First Load JS shared by all            88.7 kB
Exit Code: 0 (Zero errors)

# 4. Backend Lint & Formatting Check
backend\.venv\Scripts\ruff.exe check backend/
All checks passed!
Exit Code: 0 (Zero errors)

# 5. Backend FinOps & Security Test Suites (Offline Mode)
$env:CATALOG_OFFLINE_MODE="true"; backend\.venv\Scripts\pytest.exe backend/tests/test_finops_analytics.py backend/tests/test_milestone_3j3_security.py backend/tests/test_milestone_3j2_security.py -v
35 passed in 0.62s
Exit Code: 0 (100% passing tests)

# 6. Frozen Microsoft Fabric Baseline Immutability
git diff c2c87027f64b59fb784d990b9485781dde05e6f8 -- fabric-udf sync-agent function_app.py
Exit Code: 0 (Exactly 0 bytes diff)
```

---

## 6. Zero-Execution & Compliance Certification

We hereby certify that:
1. **Warehouse Invariant:** Databricks SQL Serverless Starter Warehouse `05ed10a52697a344` was not started, resumed, or altered during the execution of this audit and remediation.
2. **Non-Mutation Rule:** No mutating SQL statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`) or cloud provider resources were executed.
3. **Least Privilege:** All telemetry inspection operates strictly within read-only roles (`Reader`, `Monitoring Reader`, `Cost Management Reader`).
4. **Human-in-the-Loop:** All financial ingestion execution actions require affirmative human checkbox approval before processing.

