# Milestone 3G.1 — Remaining Defects & Operational Guardrails Register
## Outstanding Technical Observations, Operational Policy Constraints, and Roadmap Alignment

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Target Workspace ID:** `642006393507276` (`Azure Databricks Dev`)
- **Status:** Evaluated & Documented

---

## 1. Summary of Defect Register Status

All 10 defects from Milestone 3F have been closed. During the Milestone 3G.1 forensic audit, 4 implementation vulnerabilities were discovered and immediately resolved:
1. Substring matching leak in `_resolve_resource_filter` -> **RESOLVED**.
2. Bidirectional type-enforcement omission -> **RESOLVED**.
3. Sample app names in production registries -> **RESOLVED**.
4. Hardcoded financial fallbacks in React UI -> **RESOLVED**.

No open software defects remain in the calculation or scoping codebase.

---

## 2. Active Operational Constraints (Design & Environment Constraints)

The following items are environmental or policy constraints and must not be bypassed by automated code:

### 2.1 Environmental Constraint: Stopped SQL Warehouse (`05ed10a52697a344`)
- **Classification:** `VERIFIED STOPPED (OPERATIONAL POLICY)`
- **Nature:** Environmental / Customer Cost Protection.
- **Description:** SQL Warehouse `05ed10a52697a344` (`Serverless Starter Warehouse`) is stopped in target workspace `642006393507276`.
- **System Behavior:** Under Rule 1 (Zero-Mutation / Zero-Execution), the application is forbidden from resuming this warehouse. Live queries against `system.billing.usage`, `system.compute.clusters`, and `system.access.audit` return `status="STOPPED_WAREHOUSE"`. The application safely serves certified historical baseline data (`KpiStatus.BASELINE`).
- **Remediation Path:** When the customer explicitly starts or resumes the warehouse in the Databricks workspace UI, real-time SQL querying will become available.

### 2.2 Billing Contract Constraint: Blended Effective Rate ($2.0000 / DBU)
- **Classification:** `VERIFIED BASELINE (CONTRACTUAL AMORTIZATION)`
- **Nature:** Contractual / Pricing Lineage.
- **Description:** The $2.0000/DBU rate is an enterprise blended rate reflecting combined DBU consumption and underlying Azure virtual machine infrastructure. It cannot be verified as a single retail price SKU (which ranges from $0.15 to $0.70/DBU).
- **System Behavior:** The application certifies this rate as `KpiStatus.BASELINE` with an explicit caveat explaining that it represents an amortized blended rate. It is never marked as `LIVE`.

### 2.3 Cloud Provider Limitation: Databricks Apps Compute Metering
- **Classification:** `VERIFIED UNATTRIBUTED (PLATFORM CONSTRAINT)`
- **Nature:** Databricks Platform Telemetry Granularity.
- **Description:** Databricks Apps (`cement-demand-forecasting`, `mcp-generate-ppt`, `wonder-cement-app`) run on managed serverless microservice infrastructure where worker nodes are not tagged with individual cluster IDs.
- **System Behavior:** App compute spend ($1,240.00) is isolated in an explicit `Unattributed Compute` pool. It is never forced into unrelated clusters.

---

## 3. Final Defect Resolution Matrix

| Issue ID | Nature | Description | Milestone 3G.1 Status |
| :--- | :--- | :--- | :---: |
| **OBS-3G1-01** | Code Bug | Substring match `"adf-deaccelator-compute" in rid` allowed prefix/suffix attack | **CLOSED (Exact match enforced)** |
| **OBS-3G1-02** | Code Bug | Valid ID paired with mismatched `resource_type` returned resource | **CLOSED (Type parity enforced)** |
| **OBS-3G1-03** | Data Hygiene | Fabricated apps (`databricks-cost-monitor`) in `KNOWN_APPS` | **CLOSED (Purged from registries)** |
| **OBS-3G1-04** | UI Bug | KPI cards fell back to `"$284,620"` on API error | **CLOSED (Replaced with "Unavailable" / "—")** |
| **ENV-3G1-01** | Environment | Stopped SQL warehouse gates live System Tables queries | **ACKNOWLEDGED & COMPLIANT** |
| **FIN-3G1-01** | Accounting | $2.00/DBU blended rate is EA amortized, not retail list price | **ACKNOWLEDGED & CLASSIFIED BASELINE** |

