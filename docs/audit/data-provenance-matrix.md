# FinOps & Infrastructure Intelligence Platform — Data Provenance Matrix

> **Status:** Phase 1 Evidence-Based Audit  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/premium-cloud-recommender-ui`  
> **Evaluation Date:** October 2026  

---

## 1. Classification Methodology & Provenance Categories

In accordance with the **Truthful Telemetry and Zero-Fabrication Mandate**, all data points rendered on the UI or processed by backend engines are classified under one of the following eight provenance tiers:

1. `LIVE_PROVIDER_DATA`: Real-time data obtained directly from an authenticated cloud provider API (e.g. ARM, Azure Monitor, GCP Cloud Asset Inventory).
2. `LIVE_DATABASE_DATA`: Data queried directly from the local PostgreSQL or SQLite database.
3. `CACHED_PROVIDER_DATA`: Official provider pricing catalogs or API responses cached locally with periodic revalidation.
4. `SYNTHETIC_DEMO_DATA`: Procedurally generated mock data used strictly for interface demonstration.
5. `BENCHMARK_DATA`: Verified, real-world architectural reference fixtures based on production telemetry snapshots.
6. `DERIVED_ESTIMATE`: Calculated outputs produced by deterministic math formulas, sizing algorithms, or rules engines.
7. `UNAVAILABLE`: Telemetry or metric data that cannot be collected due to lack of guest agents, missing IAM permissions, or inactive logging.
8. `UNKNOWN_PROVENANCE`: Unlabeled data whose origin or method of calculation is indeterminate.

---

## 2. Exhaustive Data Provenance Matrix

| Feature / UI Surface | Data Field / Dataset | Current Value / Sample | Provenance Classification | Upstream Data Source | Backend Pipeline / Query | Offline Behavior | Is Truthful in UI? | Notes / Remediation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Cloud Onboarding** | Azure Subscriptions List | `Smart Expense Prod`, `sub-prod-enterprise-01` | `LIVE_PROVIDER_DATA` / `BENCHMARK_DATA` | ARM `subscriptions` API / Local Fixture | `azure_inventory.py::list_subscriptions` | Returns `sub-prod-enterprise-01` fixture | **Yes** | Explicitly labeled as `live_authenticated` or `simulation_fixture`. |
| **Cloud Onboarding** | GCP Projects List | `cloud-recommender-pricing-dev`, `smart-expense-gcp-prod` | `LIVE_PROVIDER_DATA` / `BENCHMARK_DATA` | Cloud Resource Manager v3 API | `gcp_inventory.py::list_projects` | Returns `smart-expense-gcp-prod` benchmark | **Yes** | Distinguishes authenticated ADC session from mock fixture. |
| **Cloud Onboarding** | Provider Connection Health | `healthy`, `ready_to_connect`, `error` | `LIVE_PROVIDER_DATA` | Live HTTP probe to provider auth endpoint | `connection_service.py::validate_connection` | Validates local credentials or mock readiness | **Yes** | Validates read-only permissions without echoing secret tokens. |
| **Overview & Trends** | Scope Spend & Budget Rollup | `$1,420.50 / mo`, `82% of budget` | `DERIVED_ESTIMATE` | Aggregated from discovered resources & official rates | `azure_inventory.py` / `gcp_inventory.py` | Aggregates benchmark SKU rates | **Yes** | Clearly labeled as estimated spend based on discovered resources. |
| **Overview & Trends** | Compute CPU Timeseries | Time-series array `[12.4%, 18.2%, 24.1%]` | `LIVE_PROVIDER_DATA` / `UNAVAILABLE` | Azure Monitor / Cloud Monitoring | `monitoring_service.py::get_monitoring_overview` | Generates series only for compute VMs; empty for API-only scopes | **Yes** | Fixed: Prevents synthetic CPU graphs for scopes containing 0 VMs. |
| **Resources Inventory** | Discovered Asset Inventory | 31 GCP Records (25 APIs, 1 Key, 4 Logs) | `LIVE_PROVIDER_DATA` | Cloud Asset Inventory v1 API | `gcp_inventory.py::analyze_project` | Fallback to 8-resource benchmark topology | **Yes** | Categorization separates APIs (`api_service`) from true VMs/disks. |
| **Resources Inventory** | Resource Categories & Tags | `COMPUTE`, `DATABASE`, `STORAGE`, `INTEGRATION` | `LIVE_PROVIDER_DATA` | Native Provider Resource Types & Tags | `_map_asset_type_to_canonical` | Fixture tags | **Yes** | Native types mapped to canonical schema. |
| **Health Telemetry** | Host-Level CPU & Network | `Avg CPU: 22%`, `Network Out: 4.2 GB` | `LIVE_PROVIDER_DATA` | Platform Metrics (`microsoft.insights/metrics`) | `monitoring_service.py::_query_azure_resource_metrics` | Returns `UNAVAILABLE` if unmonitored | **Yes** | Truthful: No fabricated CPU when metric collection is missing. |
| **Health Telemetry** | In-Guest RAM & Disk I/O | `No guest telemetry available` | `UNAVAILABLE` | Requires AMA or Ops Agent | Metric probe returns empty / null | Displays "Guest Agent Required" pill | **Yes** | Explicitly instructs user to install Azure Monitor Agent. |
| **Active Alerts** | Platform Incidents & Alerts | `0 Active Critical Alerts` | `LIVE_PROVIDER_DATA` / `BENCHMARK_DATA` | Azure Resource Health / Cloud Monitoring | `monitoring_service.py` | Benchmark alerts for test scopes | **Yes** | Shows real alert count for live authenticated subscriptions. |
| **Hierarchy Explorer** | Cloud Resource Tree | Azure: Sub -> RG -> Resource; GCP: Org -> Folder -> Proj | `LIVE_PROVIDER_DATA` | ARM Resource Graph / Cloud Resource Manager | `azure_inventory.py` / `gcp_inventory.py` | Benchmark hierarchy trees | **Yes** | Strictly avoids synthetic Resource Groups for GCP projects. |
| **Log Explorer** | Audit & Activity Logs | JSON records with timestamps and callers | `LIVE_PROVIDER_DATA` / `BENCHMARK_DATA` | Azure Activity Log / Cloud Logging | `monitoring_service.py::search_logs` | Labeled benchmark log dataset | **Yes** | Automatic secret sanitization regex scrubs sensitive tokens. |
| **Token Economics** | Total AI Model Tokens | `0 tokens` or `12,450,000 tokens` | `LIVE_PROVIDER_DATA` / `BENCHMARK_DATA` / `UNAVAILABLE` | Azure Monitor Metrics (`ProcessedPromptTokens`) | `monitoring_service.py::get_token_economics` | Benchmark token breakdown | **Yes** (With Audit Limitation) | Distinguishes measured zero (`datapoints > 0, val = 0`) from unavailable telemetry (`datapoints == 0`). Note: Metric name query requires update. |
| **Token Economics** | Model Token Unit Rates | `$2.50 / M prompt`, `$10.00 / M comp` | `CACHED_PROVIDER_DATA` | Official Azure OpenAI & Vertex AI Pricing | Hardcoded reference rate table in `monitoring_service.py` | Offline static rate table | **Yes** | Reflects current official pay-as-you-go pricing for GPT-4o & Gemini. |
| **Cost & Waste** | Unattached Disk Waste | `$19.70 / mo savings per P10 disk` | `DERIVED_ESTIMATE` | ARM Resource Graph disk state & Retail Prices | `waste_debt_engine.py` | Evaluates benchmark disks | **Yes** | Non-destructive advisory. CLI recommendations use read-only inspection commands (`az disk show`). |
| **Cost & Waste** | Idle Compute Waste | `e2-micro oversized`, `$8.40 / mo` | `DERIVED_ESTIMATE` | Cloud Monitoring CPU history & Billing Catalog | `waste_debt_engine.py` | Evaluates benchmark VMs | **Yes** | Capped at resource spend to prevent double counting. |
| **Pricing Engine** | Azure Retail Prices Catalog | Hourly & Monthly rates for 7 curated services | `LIVE_PROVIDER_DATA` / `CACHED_PROVIDER_DATA` | Azure Retail Prices Public API | `azure_retail_client.py` | Fallback to `backend/.../data/curated_services.json` | **Yes** | Real live HTTP calls when connected; offline cache fallback when disconnected. |
| **Pricing Engine** | GCP Billing Catalog | SKU pricing for Cloud Run, Cloud SQL, Storage | `LIVE_PROVIDER_DATA` / `CACHED_PROVIDER_DATA` | Google Cloud Billing Catalog API v1 | `gcp_billing_client.py` | Fallback to `backend/.../data/gcp_curated_skus.json` | **Yes** | Verified with live `GCP_CLOUD_API_KEY`. |
| **Cost Simulator** | Interactive Architecture BOM | Itemized bill of materials & 5-month totals | `DERIVED_ESTIMATE` | Deterministic pricing calculation engine | `engine.py::AzurePricingEngine` | Deterministic local calculations | **Yes** | Zero LLM hallucination; 100% deterministic arithmetic. |
| **Multi-Cloud Compare**| Cross-Cloud Architectural BOM | Azure App Service vs GCP Cloud Run equivalency | `DERIVED_ESTIMATE` | Deterministic cross-cloud comparator | `multi_cloud_comparator.py` | Comparative benchmark models | **Yes** | Equal workload assumptions mapped across both cloud providers. |

---

## 3. Data Integrity & Authenticity Findings

1. **Zero Fabrication Policy Compliance:**  
   The platform strictly rejects the fabrication of telemetry data. When live data cannot be retrieved (e.g. absent guest agents, missing IAM roles, or uninstrumented AI endpoints), the system explicitly labels the state as `UNAVAILABLE` or `instrumentation_required` rather than rendering simulated metrics as live results.

2. **Benchmark Isolation:**  
   Benchmark reference fixtures (such as `sub-prod-enterprise-01` and `smart-expense-gcp-prod`) are clearly designated in the UI with badge indicators (`Reference Benchmark Fixture`), preventing confusion with live production workloads.

3. **Deterministic Pricing Guarantee:**  
   All cost estimates are derived from official provider pricing APIs or versioned offline cache files. Generative AI models are strictly prohibited from generating cost figures or SKU pricing.

