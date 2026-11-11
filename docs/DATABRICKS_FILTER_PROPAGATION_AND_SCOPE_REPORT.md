# Databricks FinOps Filter Propagation & Scope Architecture Report

> **Platform:** Bizmetric Cloud & Databricks FinOps Command Center  
> **Milestone:** Milestone 3J.5 — Global UI, Hydration, Cloud Switching & Interactive Control Remediation  
> **Topic:** Multi-Scope Propagation, Dynamic Re-Fetching, & Cache Lifecycle  
> **Status:** Active & Verified  

---

## 1. Scope & Filter Architecture Overview

In an enterprise Databricks environment spanning multiple Azure subscriptions, Databricks workspaces, and Fabric Lakehouses, filter consistency is paramount. A filter applied in one view must neither leak into an unrelated cloud tenant nor leave stale cache in memory.

### 1.1 Global State Hierarchy

```
Global Scope Context (app/page.tsx)
 ├── activeConnection: CloudConnection | null
 ├── activeScope: CloudScope | null
 │    ├── subscription_ids: string[]
 │    ├── resource_group_ids: string[]
 │    └── workspace_ids: string[]
 ├── activeView: "home" | "connections" | "monitoring" | "inventory" | "compare" | "databricks"
 └── globalLoadingManager: TopLoadingProgressBar
```

---

## 2. Scope Switching Data Flow & Life Cycle

When a user switches their cloud connection via the **Switch** button in `TopNav`, the `Sidebar` footer, or `SectionCentralizedMonitoring`:

1. **Navigation Trigger:**
   `onSwitchConnection()` sets `activeView = "connections"`, opening `ConnectCloudView`.
2. **Authentication & Validation:**
   User selects an authorized connection (e.g. `conn-azure-prod` or `conn-databricks-azure`). The system calls `validateConnection(connId)`.
3. **State Propagation:**
   `app/page.tsx` receives the validated `CloudConnection` and dispatches updates to:
   - `setActiveConnection(conn)`
   - `setSelectedWorkspaceId(conn.scope_id)`
   - Updates downstream modules via props.
4. **Child State Reset & Cache Invalidation:**
   Dependent child filters in `FinOpsCommandCenterView` and `DatabricksWorkspaceDetailView` reset:
   - Cluster type filter resets to `"all"`.
   - Warehouse size filter resets to `"all"`.
   - Query duration histogram bucket resets to `null`.
   - Table pagination resets to `page = 1`.
5. **Fresh Data Ingestion:**
   The active module immediately triggers a fresh API call scoped to the newly selected ID (e.g. `getFinOpsOverview(workspaceId)` or `getMonitoringOverview(provider, scopeId)`).

---

## 3. Filter Parameter Mapping to Backend APIs

| User Filter Control | Component State | Backend API Endpoint | Query / Body Payload Field |
| :--- | :--- | :--- | :--- |
| **Active Workspace** | `selectedWorkspaceId` | `/api/v1/finops/overview` | `workspace_id={id}` |
| **Date Range Preset** | `selectedDateRange` | `/api/v1/finops/cost-explorer` | `start_date`, `end_date` |
| **Custom Start/End** | `customStartDate/EndDate` | `/api/v1/finops/billing/reconciliation` | `start_date`, `end_date` |
| **Display Currency** | `selectedCurrency` | Client-Side Traceable Engine (`currency.ts`) | Converted with central-bank rate |
| **Query Status** | `queryStatusFilter` | `/api/v1/finops/query-history` | `status={status}` |
| **Duration Bucket** | `selectedDurationBucket` | `/api/v1/finops/query-history` | `min_duration_ms`, `max_duration_ms` |
| **Schema Explorer** | `selectedSchemaFilter` | `/api/v1/finops/system-tables` | `schema_name={name}` |
| **Monitoring Range** | `timeWindow` | `/api/v1/monitoring/overview` | `range_preset={1h|24h|7d|30d}` |
| **Monitoring Granularity** | `metricInterval` | `/api/v1/monitoring/resource` | `granularity={1m|5m|15m|1h|1d}` |
| **Log Severity** | `logSeverity` | `/api/v1/monitoring/logs` | `severity={critical|error|warning|info}` |

---

## 4. Zero-Execution & Security Guardrails During Filter Operations

1. **Strictly Read-Only Queries:** All backend routes triggered by filter adjustments execute `SELECT` or read-only REST calls. No mutation routes are triggered.
2. **Anti-Leakage Isolation:** Azure subscription IDs are never forwarded to GCP APIs; Databricks workspace IDs are strictly validated before querying system tables.
3. **Compute Safety:** Serverless Starter Warehouse `05ed10a52697a344` remains unmutated (`STOPPED`) during all filter and histogram operations.

