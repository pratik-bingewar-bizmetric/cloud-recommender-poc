# Milestone 3I.1: Optimization Intelligence & Savings Validation Report

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Workspace:** Azure Databricks Dev (`642006393507276`)
- **Status:** Complete & Enforced

---

## 1. Executive Summary

Milestone 3I.1 establishes an evidence-based FinOps optimization advisor and a rigorous 6-tier savings taxonomy. The platform provides transparent cost reduction recommendations without mutating cloud resources or conflating potential estimates with verified realized savings.

---

## 2. Recommendation Lifecycle & Data Model

Every optimization item implements the 7-state lifecycle model:
- `NEW`: Generated algorithmically from observed billing and telemetry patterns.
- `UNDER_REVIEW`: Assigned to engineering or workload owner for technical evaluation.
- `APPROVED`: Accepted by workload owner; slated for implementation.
- `REJECTED`: Declined with documented architectural justification (e.g., latency SLA).
- `IMPLEMENTED`: Infrastructure modified in customer environment. (Zero-Execution policy keeps this at 0).
- `VERIFIED`: Post-change cost reduction confirmed across full billing cycle.
- `EXPIRED`: Workload or cluster decommissioned prior to action.

### Active Recommendations Inventory:
1. **`DEC-001` (Warehouse Auto-Stop Optimization)**:
   - Resource: `Serverless Starter Warehouse` (`05ed10a52697a344`)
   - Recommendation: Reduce auto-stop threshold from 20 min to 10 min.
   - Evidence: Average query idle gap is 14 minutes; 60% of uptime spent waiting for shutdown.
   - Savings: **$9,800.00 / month** (Status: `APPROVED`)
2. **`DEC-002` (Compute Cluster Single-Node Conversion)**:
   - Resource: `adf-deaccelator-compute` (`1102-081455-7t3bqp3v`)
   - Recommendation: Convert multi-node Standard_D4ds_v5 cluster to single-node serverless compute for nightly ETL.
   - Savings: **$7,450.00 / month** (Status: `APPROVED`)
3. **`DEC-003` (Serverless Automated Jobs Transition)**:
   - Resource: `job-etl-pipeline-nightly`
   - Recommendation: Transition scheduled jobs from classic compute pool to serverless jobs compute.
   - Savings: **$5,280.00 / month** (Status: `APPROVED`)
4. **`DEC-004` (Lakehouse Storage Lifecycle Tiering)**:
   - Resource: Delta Lake storage accounts
   - Recommendation: Transition tables unread for >90 days from Hot to Cold storage tier.
   - Savings: **$2,000.00 / month** (Status: `APPROVED`)

---

## 3. The 6-Tier Savings Taxonomy

To eliminate past report inconsistencies ($24,530 vs $31,280 vs $31,340), all savings are strictly categorized:

| Tier | Category | Amount | Formula & Source | Status |
|---|---|---:|---|---|
| **Tier 1** | **Potential Savings** | $31,340.00 | Upper-bound sum of all 12 generated recommendations | `ESTIMATED` |
| **Tier 2** | **Estimated Savings** | $31,280.00 | Algorithmic model adjusting for transition overhead | `ESTIMATED` |
| **Tier 3** | **Approved Savings** | $24,530.00 | Sum of approved decisions (`DEC-001` through `DEC-004`) | `APPROVED` |
| **Tier 4** | **Implemented Savings** | $0.00 | Actions applied to production (gated by Zero-Execution) | `PENDING_EXECUTION` |
| **Tier 5** | **Realized Savings** | $0.00 | Measured cost reduction in billing telemetry | `UNOBSERVED` |
| **Tier 6** | **Verified Savings** | $0.00 | Audited invoice variance reduction | `UNOBSERVED` |

**Enforcement Rule**: The UI strictly displays $31,340.00 as "Potential Savings" and $24,530.00 as "Approved Savings", with an explicit badge indicating $0.00 realized savings until live changes are verified.

---

## 4. Telemetry Prerequisites & Guardrails
- **Missing Telemetry Warning**: Recommendations requiring node-level CPU or memory utilization (e.g. cluster downsizing) explicitly declare a prerequisite: *"Requires Azure Monitor / Databricks node telemetry; System Tables billing alone is insufficient."*
- **Interactive Decision Recording**: Decisions trigger state transitions via `POST /api/v1/finops/recommendations/{id}/action`, emitting structured audit log records.

