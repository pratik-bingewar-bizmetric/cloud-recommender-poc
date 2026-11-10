# Complete Interactive Controls Inventory Across All Databricks & Azure FinOps Modules

> **Platform:** Bizmetric Cloud & Databricks FinOps Command Center  
> **Milestone:** Milestone 3J.5 — Global UI, Hydration, Cloud Switching & Interactive Control Remediation  
> **Scope:** Comprehensive Inventory of All 52+ Interactive Selection Controls  
> **Status:** Audited & Verified  

---

## 1. Inventory Summary

This inventory catalogs every dropdown, selector, date picker, range slider, multi-select popover, and modal control across the Bizmetric FinOps Platform, covering all 26+ Databricks Command Center modules and Azure Cloud FinOps views.

| Control Category | Total Identified | Remediated / Verified | Unmanaged Selects Remaining |
| :--- | :---: | :---: | :---: |
| Single-Select Dropdowns & Filters | 21 | 21 | **0** |
| Date Pickers & Range Selectors | 4 | 4 | **0** |
| Search & Auto-Suggest Inputs | 9 | 9 | **0** |
| Tab & Segment Switchers | 6 | 6 | **0** |
| Range Sliders (What-If Simulation) | 3 | 3 | **0** |
| Resource & Scope Tree Selectors | 3 | 3 | **0** |
| Modal & Confirmation Controls | 6 | 6 | **0** |
| **Total Interactive Controls** | **52** | **52** | **0** |

---

## 2. Detailed Controls Inventory by Module

### 2.1 Global Application Shell & Header

| ID | Control Name | Type | Component Location | Options / States | Backend API / State Bound |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ctrl-global-search` | Global Resource Search | Search Input | `TopNav.tsx:64` | Text query string | Client filter across modules |
| `ctrl-global-switch` | Scope Switch Button | Action Button | `TopNav.tsx:97` | Navigate to Connect Cloud | `setActiveView("connections")` |
| `ctrl-sidebar-switch` | Cloud Accounts & Switch | Navigation Action | `Sidebar.tsx:557` | Navigate to Connect Cloud | `onViewChange("connections")` |
| `ctrl-sidebar-monitoring` | Monitoring Sub-Nav Accordion | Accordion Toggle | `Sidebar.tsx:392` | Expanded / Collapsed | `currentMonitoringTab` state |
| `ctrl-sidebar-databricks` | Databricks Modules Menu | Navigation Links | `Sidebar.tsx:526` | 26+ FinOps modules | `handleDatabricksModuleClick` |

### 2.2 Databricks FinOps Command Center & Executive Overview

| ID | Control Name | Type | Component Location | Options / States | Backend API / State Bound |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ctrl-fc-date-range` | Time Window Filter | Dropdown Select | `FinOpsCommandCenterView.tsx:492` | Last 30 Days, Last 7 Days, Month-to-Date, Quarter-to-Date, Last 90 Days, Custom Range | `getFinOpsOverview`, `getFinOpsCostExplorer` |
| `ctrl-fc-custom-start` | Custom Date Start | Date Input | `FinOpsCommandCenterView.tsx:507` | ISO Date `YYYY-MM-DD` | Filter range start |
| `ctrl-fc-custom-end` | Custom Date End | Date Input | `FinOpsCommandCenterView.tsx:516` | ISO Date `YYYY-MM-DD` | Filter range end |
| `ctrl-fc-currency` | Display Currency Selector | Dropdown Select | `FinOpsCommandCenterView.tsx:526` | USD ($), EUR (€), GBP (£), AUD (A$), CAD (C$), INR (₹) | `formatCost` currency engine |
| `ctrl-fc-cluster-filter` | Cluster Type Filter | Dropdown Select | `FinOpsCommandCenterView.tsx:1356` | All Cluster Types, All-Purpose, Jobs / Automated, SQL Serverless | Compute inventory view |
| `ctrl-fc-warehouse-filter` | Warehouse Size Filter | Dropdown Select | `FinOpsCommandCenterView.tsx:1406` | All Warehouse Sizes, 2X-Small, X-Small, Small, Medium, Large | Warehouse list filtering |
| `ctrl-fc-sim-compute` | Compute Growth Slider | Range Slider | `FinOpsCommandCenterView.tsx:1738` | -50% to +100% | `simulateFinOpsScenario` |
| `ctrl-fc-sim-token` | Token Growth Slider | Range Slider | `FinOpsCommandCenterView.tsx:1757` | -50% to +200% | `simulateFinOpsScenario` |
| `ctrl-fc-sim-growth` | Workload Scaling Slider | Range Slider | `FinOpsCommandCenterView.tsx:1776` | 0% to 50% | `simulateFinOpsScenario` |
| `ctrl-fc-export-type` | Export Report Type | Dropdown Select | `FinOpsCommandCenterView.tsx:2741` | Executive Cost Snapshot, Detailed Billing Ledger, AI Token Economics, Optimization Backlog, Chargeback Statement | Report template selection |
| `ctrl-fc-export-format` | Export File Format | Dropdown Select | `FinOpsCommandCenterView.tsx:2756` | CSV (Direct Download), PDF Summary, JSON Payload | `pdfGenerator.ts`, `csvGenerator.ts` |
| `ctrl-fc-ingest-preview` | Preview Ingestion | Action Button | `FinOpsCommandCenterView.tsx:2854` | Trigger dry-run preview | `previewFinOpsIngestion` |
| `ctrl-fc-ingest-run` | Run Ingestion | Action Button | `FinOpsCommandCenterView.tsx:2905` | Ingest System Tables | `runFinOpsIngestion` |

### 2.3 SQL Query Execution History & Workspace Detail View

| ID | Control Name | Type | Component Location | Options / States | Backend API / State Bound |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ctrl-ws-search` | Resource Filter Search | Search Input | `DatabricksWorkspaceDetailView.tsx:903` | Resource name search string | Client table filtering |
| `ctrl-ws-query-status` | Query Status Filter | Dropdown Select | `DatabricksWorkspaceDetailView.tsx:1963` | ALL, FINISHED, FAILED, RUNNING, CANCELLED | `getFinOpsQueryHistory` |
| `ctrl-ws-query-search` | Query Text Search | Search Input | `DatabricksWorkspaceDetailView.tsx:1982` | Query text or query ID | Query history filter |
| `ctrl-ws-duration-histo` | Duration Histogram Bucket Filter | Clickable Chart Bar | `QueryDurationHistogram.tsx:112` | <1s, 1s-5s, 5s-30s, 30s-2m, >2m | Filters query list below chart |
| `ctrl-ws-schema-filter` | System Tables Schema Filter | Dropdown Select | `DatabricksWorkspaceDetailView.tsx:2236` | All Schemas, billing, compute, access, query, storage | `getFinOpsSystemTables` |

### 2.4 Centralized Infrastructure Monitoring (8 Sub-Tabs)

| ID | Control Name | Type | Component Location | Options / States | Backend API / State Bound |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ctrl-mon-scope-badge` | Connected Scope Switch | Action Button | `SectionCentralizedMonitoring.tsx:763` | Navigate to Connect Cloud | `onSwitchConnection()` |
| `ctrl-mon-scope-select` | Scope Selector | Dropdown Select | `SectionCentralizedMonitoring.tsx:774` | Active subscriptions / projects | `loadScopes`, `getMonitoringOverview` |
| `ctrl-mon-range-preset` | Time Window Preset | Button Group | `SectionCentralizedMonitoring.tsx:827` | 1h, 24h, 7d, 30d | `getMonitoringOverview` |
| `ctrl-mon-log-search` | Log Search Input | Search Input | `SectionCentralizedMonitoring.tsx:2062` | Free-text search string | `searchMonitoringLogs` |
| `ctrl-mon-log-severity` | Log Severity Filter | Dropdown Select | `SectionCentralizedMonitoring.tsx:2078` | All Severities, Critical, Error, Warning, Info | `searchMonitoringLogs` |

### 2.5 Multi-Scope Configuration & Connect Cloud View

| ID | Control Name | Type | Component Location | Options / States | Backend API / State Bound |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ctrl-cfg-sub-select` | Subscription Selector | Dropdown Select | `ConfigurationView.tsx:265` | Discovered Azure subscriptions | `listAzureSubscriptions` |
| `ctrl-cfg-rg-tree` | Resource Group Multi-Select | Checkbox List | `ConfigurationView.tsx:320` | Dynamic RG list | `selectedResourceGroups` |
| `ctrl-cfg-apply` | Apply Scope Configuration | Action Button | `ConfigurationView.tsx:432` | Apply and navigate to FinOps | `onSaveScope` |
| `ctrl-conn-reconnect` | Verify Connection | Action Button | `ConnectCloudView.tsx:684` | Validate read-only credentials | `validateConnection` |
| `ctrl-conn-auth-method` | Auth Method Selector | Dropdown Select | `ConnectCloudView.tsx:886` | CLI Credentials, Service Principal, OAuth | New connection setup |

