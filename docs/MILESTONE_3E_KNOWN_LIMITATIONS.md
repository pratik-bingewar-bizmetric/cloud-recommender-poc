# Milestone 3E — Known Limitations & Technical Constraints

**Date:** November 6, 2026  
**Repository:** `cloud-recommender-poc`  
**Active Branch:** `feature/databricks-apps-integration`  
**Target Workspace:** Azure Databricks Dev (`642006393507276`)  

---

## 1. Overview of Operational & Technical Boundaries

Milestone 3E operates under strict security, architectural, and cloud policy constraints. This document details known limitations, their technical root causes, and how the platform transparently handles them.

---

## 2. Inventory of Known Limitations

### 2.1 Stopped SQL Warehouse & Live SQL Execution Gate
- **Observation:** SQL Warehouse `05ed10a52697a344` (`Serverless Starter Warehouse`) is in a `STOPPED` state in workspace `642006393507276`.
- **Constraint:** Running ad-hoc SQL statements against system tables (e.g. `SELECT * FROM system.billing.usage`) via the SQL Execution API requires an active, running warehouse.
- **Handling:**
  - The application strictly enforces the **Zero-Execution Policy**. It will **never** automatically call `POST /api/2.0/sql/warehouses/start` or attempt to resume compute resources on the customer tenant.
  - The System Tables matrix displays the truthful status `STOPPED_WAREHOUSE` alongside verified schema column metadata retrieved via the read-only Unity Catalog REST API.
  - Query History displays preserved historical executions and duration histograms without requiring warehouse resumption.

### 2.2 Read-Only Scope & Role Boundary
- **Observation:** The application connects to Azure and Databricks using least-privilege read-only credentials (`Reader`, `Monitoring Reader`, `Account User / Read-Only`).
- **Constraint:** The application cannot:
  - Create or alter clusters, pools, or jobs.
  - Restart failed Delta Live Tables pipelines.
  - Modify Unity Catalog table ACLs or grant permissions.
  - Apply automated optimization recommendations (e.g. reducing cluster size or setting auto-stop).
- **Handling:** All recommendations in the **Optimization Advisor** are presented as advisory guidance with impact scores, savings estimates, and step-by-step instructions for human operators to execute in the Databricks console.

### 2.3 Cloud Provider Scope Exclusion (AWS Databricks)
- **Observation:** Milestone 3E is scoped strictly to **Azure Databricks**.
- **Constraint:** AWS Databricks workspace discovery, AWS Price List API, and AWS multi-cloud comparisons remain disabled or stubbed in this milestone.
- **Handling:** The UI explicitly flags AWS Databricks as *"Excluded in Milestone 3E (Azure Databricks Focus)"*.

### 2.4 Unattributed Shared Resource & Databricks Apps Cost
- **Observation:** In multi-tenant Databricks workspaces without mandatory tag enforcement policies, certain workloads (such as Databricks Apps, shared serverless warehouses, or system maintenance jobs) lack explicit user attribution tags.
- **Constraint:** Precise user-level or department-level cost disaggregation cannot be mathematically calculated without risking distorted chargeback reports.
- **Handling:** The platform isolates unmapped app compute into a dedicated **Unattributed Cost Bucket** ($0 MTD or unmapped variance), clearly notifying the user rather than arbitrarily splitting costs across clusters.

### 2.5 Real-Time Token Streaming vs. Accounting Batching
- **Observation:** Model Serving Gateway telemetry records token counts in near-real-time via endpoint logging, whereas Azure billing ledgers are reconciled in batches every 4 to 24 hours.
- **Constraint:** A temporary latency delta may exist between real-time token throughput metrics and invoice-reconciled DBU charges.
- **Handling:** Each KPI card and drawer displays a `data_freshness` timestamp and source attribution flag (`Model Serving Gateway` vs. `Azure Billing Meter`).

---

## 3. Safe Failure & Fallback Behavior Summary

| Failure Trigger | Architectural Fallback Mechanism | User Notification / State |
| :--- | :--- | :--- |
| **SQL Warehouse Stopped** | Schema inspected via REST API; query execution paused | Amber badge `STOPPED_WAREHOUSE` with explanatory tooltip |
| **Azure CLI / SPN Token Expiry** | Diagnostics service detects auth failure | Displays clear guidance on required roles (`Reader`) |
| **Azure Pricing API Throttle** | Engine falls back to static JSON rate card | Informs user that offline pricing reference was applied |
| **Unmapped Workspace ID** | `validate_scope()` rejects foreign scope | Returns HTTP 400 Bad Request with actionable message |
| **Child Scope Reset** | Clicking "Reset Filter" reverts to parent workspace | TopNav and Sidebar instantly reflect parent workspace scope |

