# Milestone 3I.4: Reporting, Audit & Governance Report

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Workspace:** Azure Databricks Dev (`642006393507276`)
- **Status:** Complete & Integrated

---

## 1. Executive Summary

Milestone 3I.4 delivers governance policy cataloguing, structured audit event tracking, multi-tier Role-Based Access Control (RBAC), and automated report exports. This architecture ensures complete compliance and traceability for enterprise financial operations.

---

## 2. FinOps Role-Based Access Control (RBAC) Matrix

To uphold least-privilege security, the platform defines 6 distinct roles:

| Capability / Action | Platform Admin | FinOps Admin | FinOps Analyst | Finance Viewer | Department Owner | Read-Only Auditor |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **View FinOps Command Center** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Inspect System Tables Metadata** | Yes | Yes | Yes | No | No | Yes |
| **Trigger Ingestion Preflight Dry-Run** | Yes | Yes | Yes | No | No | No |
| **Issue Server-Side Approval Token** | Yes | Yes | No | No | No | No |
| **Execute Approved Ingestion Run** | Yes | Yes | No | No | No | No |
| **Approve / Reject Recommendations** | Yes | Yes | Yes | No | Yes | No |
| **Simulate Cost Scenarios** | Yes | Yes | Yes | Yes | Yes | No |
| **Download CSV Financial Ledgers** | Yes | Yes | Yes | Yes | Yes | Yes |
| **View Audit Trail Logs** | Yes | Yes | Yes | No | No | Yes |

---

## 3. Structured Audit Trail Architecture

All state mutations (budget updates, policy assignments, recommendation approvals, and ingestion runs) emit immutable audit events to `AuditEventItem` and database entity `billing_reconciliation_results`:

### Recent Governed Audit Events:
1. `Nov 04 14:15`: **`pratik.bingewar`** approved Recommendation `DEC-001` (Warehouse Auto-Stop 20m -> 10m). Approval Ref: `APP-8842`
2. `Nov 03 18:30`: **`platform.admin`** updated cluster policy for `adf-deaccelator-compute` (None -> `Standard_D4ds_v5`). Approval Ref: `CHG-2398`
3. `Nov 03 11:20`: **`pratik.bingewar`** updated AI COE budget threshold (80% -> 90%). Approval Ref: `FIN-1182`
4. `Nov 02 09:45`: **`finops.lead`** rejected cluster resize for staging environment. Approval Ref: `REJ-0492`

*Security Invariant*: Credentials, OAuth tokens, and sensitive parameters are scrubbed before reaching audit logs or serialization outputs.

---

## 4. Exportable Reports Engine

The reporting subsystem supports instantaneous CSV and structured JSON exports:
1. **Executive Summary Pack**: High-level KPIs, budget variance, and monthly projection.
2. **Cost Explorer Granular Ledger**: All 24 canonical records with SKU, product, timestamps, and effective cost.
3. **Billing Usage & Reconciliation Ledger**: Raw usage events matched against active list prices with audit notes.
4. **Governance Compliance Pack**: Policy checklist, untagged resources, and active cluster limits.

