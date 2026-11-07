# Milestone 3G — Known Limitations & Operational Constraints
## System Boundaries, Stopped Warehouse Gating, and Baseline Attribution Constraints

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Target Workspace ID:** `642006393507276` (`Azure Databricks Dev`)
- **Engine Version:** `v2.0.0-canonical`
- **Status:** Documented & Binding

---

## 1. System Boundaries & Design Intent

Milestone 3G establishes complete mathematical and scope integrity for the Azure Databricks FinOps Command Center. In accordance with strict operational rules and customer cost governance, certain infrastructure constraints are intentionally enforced:

---

## 2. Inventory of Known Limitations

### 2.1 Stopped SQL Warehouse & Live System Tables Gating
- **Condition:** SQL Warehouse `05ed10a52697a344` (`Starter Warehouse`) is currently in the `STOPPED` state in workspace `642006393507276`.
- **Operational Constraint:** Under Rule 1 (Strict Zero-Execution / Zero-Mutation Policy), the application is **strictly forbidden from resuming or starting this warehouse** automatically.
- **Impact on System Tables:** Real-time SQL queries against `system.billing.usage`, `system.compute.clusters`, and `system.access.audit` cannot be executed live without resuming the warehouse.
- **Handling & Transparency:**
  - System Tables Explorer explicitly displays `warehouse_state: STOPPED`.
  - All 10 System Tables return `status="STOPPED_WAREHOUSE"`.
  - The UI presents verified schema columns and metadata without throwing unhandled exceptions.
  - The application relies on certified historical baseline telemetry (`KpiStatus.BASELINE`) rather than generating synthetic query results.

### 2.2 Databricks Apps Compute Tagging & Attribution
- **Condition:** Databricks Apps (e.g. `databricks-cost-monitor`) operate on managed serverless container infrastructure where underlying compute is provisioned inside Databricks-managed subscriptions.
- **Constraint:** Dedicated billing tags for app worker runtimes are not yet emitted by the Azure Databricks billing API as discrete cluster IDs.
- **Handling & Transparency:**
  - App compute spend ($1,240.00) is isolated in an explicit `Unattributed Compute` pool.
  - The application labels the figure as `"$1,240.00 (Unattributed)"` with an advisory notice explaining that fine-grained container tagging is pending Databricks platform GA.
  - Unattributed spend is **never** artificially forced into unrelated interactive clusters.

### 2.3 Single-Region Azure EA Currency Denomination
- **Condition:** All baseline telemetry, ledger line items, and unit economics are denominated in **USD** based on an Azure Enterprise Agreement rate card.
- **Constraint:** Multi-currency conversions (e.g. EUR, GBP, INR) and localized tax/VAT adjustments are not calculated at this stage.
- **Handling & Transparency:** All KPI response payloads explicitly specify `currency: "USD"` and `unit: "USD"`.

### 2.4 Historical Query History Log Size
- **Condition:** Query history is retrieved from historical query execution snapshots.
- **Constraint:** The current dataset preserves 7 representative query execution records (covering `FINISHED`, `FAILED`, and `CANCELLED` states with execution runtimes, warehouse IDs, and error messages).
- **Handling:** Pagination controls support up to 50 items per page; future milestones will stream larger query audit datasets from long-term Fabric Delta storage.

---

## 3. Operational Guarantees

1. **Zero Customer Mutation:** The application will never create, modify, restart, resize, or delete Azure or Databricks infrastructure.
2. **Zero Hallucinated Metrics:** Every metric has an explicit `formula`, `data_source`, and `status`. No synthetic number is presented as `LIVE`.
3. **No Unauthenticated Leaks:** Scope mismatches immediately reject queries before data retrieval.
4. **Preserved Fabric Baseline:** The underlying Microsoft Fabric baseline (`c2c87027f64b59fb784d990b9485781dde05e6f8`) remains completely intact and unaffected.

