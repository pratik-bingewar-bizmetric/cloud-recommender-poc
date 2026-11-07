# Milestone 3D: Dynamic Cloud Resource Selection & Context-Aware Navigation

**Repository:** `cloud-recommender-poc`  
**Active Branch:** `feature/databricks-apps-integration`  
**Frozen Fabric Baseline:** `c2c87027f64b59fb784d990b9485781dde05e6f8` (Preserved 100% untouched)  
**Target Application URL:** `http://localhost:3000` (Next.js 14 App Router)  
**Backend API URL:** `http://localhost:8000/api/v1` (FastAPI / Uvicorn)  
**Date:** November 2026  
**Status:** Completed & Certified  

---

## 1. Executive Summary

Milestone 3D successfully delivers a **production-grade dynamic cloud resource selection and context-aware navigation experience** inside the existing Next.js frontend (`frontend/` at `http://localhost:3000`) and FastAPI backend (`backend/` at `http://localhost:8000`).

The implementation adheres strictly to the Golden Principles established in `AGENTS.md`:
1. **Preserve Existing Navigation:** All 8 existing monitoring sub-tabs, Executive Dashboard, AI Cloud Architect, Subscriptions (Inventory), Governance & Settings, and Zero-Execution badges remain active and unbroken.
2. **Dynamic Context-Aware Sidebar:** When a Databricks workspace is active, the navigation seamlessly surfaces a dedicated `DATABRICKS WORKSPACE` group with all 14 working modules. When an Azure Resource Group is active, it focuses on Azure resource inventory and monitoring.
3. **Truthful Telemetry & Zero Cloud Mutation:** SQL Warehouse `05ed10a52697a344` (`Serverless Starter Warehouse`) is truthfully reported as `STOPPED`. The application enforces a strict read-only policy and never executes start, resume, or mutation operations on cloud infrastructure.
4. **AWS Exclusion Enforced:** In strict accordance with the prompt, only Azure subscriptions, Azure Resource Groups, and Azure Databricks workspace `642006393507276` are enabled; AWS remains explicitly excluded from active selection scopes.

---

## 2. Architecture & Component Structure

### 2.1 Dynamic Navigation Registry (`frontend/src/lib/navigationRegistry.ts`)
A typed registry defining the 14 core Databricks modules, their categories, icons, paths, and status badges:

| # | Module ID | Title | Group | Badge / Capability |
|---|---|---|---|---|
| 1 | `overview` | Workspace Overview | Overview | `Connected` (Live Azure Databricks dev) |
| 2 | `clusters` | Compute Clusters | Compute & Data | `Inventory` (All-purpose & Job clusters) |
| 3 | `warehouses` | SQL Warehouses | Compute & Data | `STOPPED` (Zero-Execution Policy enforced) |
| 4 | `jobs` | Jobs & Workflows | Compute & Data | Multi-task schedules & triggers |
| 5 | `pipelines` | Pipelines (DLT) | Compute & Data | Delta Live Tables configurations |
| 6 | `serving` | Model Serving Endpoints | AI & Models | `27 Models` (Discovered serving endpoints) |
| 7 | `catalog` | Unity Catalog | Compute & Data | 3-Level Namespace Explorer |
| 8 | `apps` | Databricks Apps | Compute & Data | `3 Discovered` (cost-monitor, finops-agent, lakehouse-optimizer) |
| 9 | `system_tables`| System Tables | System Diagnostics | `10 Tables` (Diagnostic Schema Probe) |
| 10 | `query_history`| Query History | System Diagnostics | Query metrics & execution history |
| 11 | `ai_economics` | AI & Token Economics | AI & Models | `FinOps` (DBRX, Llama-3, token ratios) |
| 12 | `audit` | Audit & Governance | Governance & Cost | Access audit & read-only verification |
| 13 | `billing` | Cost & Billing | Governance & Cost | DBU consumption & host VM allocation |
| 14 | `discovery_history`| Discovery History | System Diagnostics | Chronological sync ledger |

### 2.2 Cloud Scope & Discovery Manager (`frontend/src/components/ConfigurationView.tsx`)
- **Provider Switcher:** Toggle between Azure (Subscriptions & Resource Groups) and Azure Databricks Workspace (`642006393507276`).
- **Azure Scope Selection:** One-click selection of active resource groups (e.g. `rg-finops-eastus`).
- **Databricks Scope Selection:** Selects workspace `642006393507276`, triggers dynamic sidebar injection, and activates Databricks analytics.
- **Action Toolbar:**
  - *Test Connection:* Validates live Azure CLI token and caller identity against Databricks.
  - *Refresh Discovery:* Live probe across all categories with upsert semantics.
  - *Select Workspace / Resource Group:* Instant context switch without page reload.
  - *Clear Selection:* Resets to global overview.
  - *Diagnostics:* Inspects RBAC permissions (`Reader`, `Cost Management Reader`), read-only boundary checks, and zero-mutation guarantees.

### 2.3 Comprehensive Databricks Workspace View (`frontend/src/components/DatabricksWorkspaceDetailView.tsx`)
- Provides deep, dedicated visual inspection for each of the 14 Databricks modules.
- Truthfully articulates the stopped warehouse state and explains why `system.billing` query execution requires an active warehouse while schema metadata is verified via Unity Catalog.

### 2.4 Context-Aware Sidebar (`frontend/src/components/Sidebar.tsx`)
- Dynamically injects the `DATABRICKS WORKSPACE` 14-module navigation group when Databricks is selected.
- Displays active scope badge with one-click "Change" link.
- Retains all 8 monitoring sub-tabs: Overview & Trends, Resources, Health, Active Alerts, Hierarchy Explorer, Log Explorer, Token Economics, Cost & Waste.

---

## 3. Scope Switching Flow

```
+-------------------------------------------------------------+
|                      Top Navigation                         |
|   Active Scope: [Azure Databricks Dev (642006393507276)]   |
+-------------------------------------------------------------+
                              |
       +----------------------+----------------------+
       |                                             |
[Select Azure RG]                         [Select Databricks Workspace]
       |                                             |
       v                                             v
Sidebar: Default Azure FinOps             Sidebar: Dynamic Section
- Home                                    - Home
- Dashboard                               - Dashboard
- Subscriptions                           - Subscriptions
- Monitoring (8 Sub-tabs)                 - Monitoring (8 Sub-tabs)
- Scope & Discovery                       - Scope & Discovery
                                          - DATABRICKS WORKSPACE (14 Modules)
                                            ├── Overview
                                            ├── Compute Clusters
                                            ├── SQL Warehouses (STOPPED)
                                            ├── Jobs & Workflows
                                            ├── Pipelines (DLT)
                                            ├── Model Serving (27 Models)
                                            ├── Unity Catalog
                                            ├── Databricks Apps (3 Apps)
                                            ├── System Tables (10 Tables)
                                            ├── Query History
                                            ├── AI & Token Economics
                                            ├── Audit & Governance
                                            ├── Cost & Billing
                                            └── Discovery History
```

---

## 4. Verification Protocol

- **Frontend Typecheck (`tsc --noEmit`):** 0 errors.
- **Frontend Linter (`next lint`):** 0 warnings, 0 errors.
- **Backend Linter (`ruff check backend/`):** All checks passed (0 errors).
- **Backend Typecheck (`mypy backend/src`):** Success (0 errors in 81 files).
- **Frozen Fabric Baseline:** `c2c87027f64b59fb784d990b9485781dde05e6f8` completely untouched.

