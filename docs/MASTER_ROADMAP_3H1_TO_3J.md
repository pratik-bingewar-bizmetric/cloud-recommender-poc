# Master Implementation Roadmap: Databricks FinOps Command Center (Milestones 3H.1 to 3J)

- **Repository:** `cloud-recommender-poc`
- **Active Working Branch:** `feature/databricks-apps-integration`
- **Frozen Fabric Baseline Commit:** `c2c87027f64b59fb784d990b9485781dde05e6f8` (`finops-fabric-phase4-frozen`)
- **Target Databricks Workspace:** Azure Databricks Dev (`642006393507276`)
- **Target SQL Warehouse:** `Serverless Starter Warehouse` (`05ed10a52697a344`) — Observed State: `STOPPED`
- **Zero-Execution Boundary:** Active and strictly enforced.

---

## Roadmap Overview & Status Matrix

| Milestone | Sub-System / Capability | Primary Deliverables | Status |
|---|---|---|---|
| **3H.1** | Ingestion Hardening & Baseline Alignment | Alembic migration, Decimal persistence, Retraction convention, Approval token gate, Financial reconciliation | **IN PROGRESS** |
| **3H.2** | Authorized Live Billing Validation Readiness | System Tables schema validator, Preflight readiness screen, Query plan preview, Authorization protocol | **PLANNED** |
| **3I** | Historical Analytics & FinOps Intelligence | Time-series aggregation, Cost Explorer drilldowns, Executive Overview, Exact Cost Allocation rules | **PLANNED** |
| **3I.1** | Optimization Intelligence & Savings Validation | Rule-based advisor, 7-state recommendation model, 6-tier savings taxonomy (Potential to Verified) | **PLANNED** |
| **3I.2** | Forecasting, Anomaly Detection & Budgets | Statistical run-rate forecasting, Z-score anomaly detector, Multi-tier budget thresholds | **PLANNED** |
| **3I.3** | Showback, Chargeback & Workload Economics | Departmental showback, Chargeback calculation ledger, Unit economics (cost/query, cost/job, cost/token) | **PLANNED** |
| **3I.4** | Reporting, Audit & Governance | CSV/JSON export engine, Structured audit trail, 6-role RBAC governance matrix | **PLANNED** |
| **3J** | Production Readiness, Reliability & Acceptance | Health probes, Circuit breaker, Database migration verification, Full 15-module UI, Final acceptance matrix | **PLANNED** |

---

## Non-Negotiable Operating Principles

1. **Frozen Fabric Preservation:** `fabric-udf/`, `sync-agent/`, `function_app.py` remain 100% frozen.
2. **Zero Live SQL / Zero Warehouse Startup:** Compute warehouse `05ed10a52697a344` remains STOPPED. No queries executed against Databricks.
3. **Strict Human Authorization:** Client-side flags (`approved=true`) rejected; cryptographically secure server approval tokens required.
4. **Deterministic Arithmetic:** High-precision `Decimal` arithmetic for monetary fields; strict retraction sign conventions; zero fabricated zeros.
5. **Exact Scope Matching:** Zero substring/fuzzy resource matching.

