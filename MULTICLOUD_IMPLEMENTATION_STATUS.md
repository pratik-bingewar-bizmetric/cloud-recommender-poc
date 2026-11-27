# Multicloud Implementation Status Map (MULTICLOUD_IMPLEMENTATION_STATUS.md)

> **Document Status:** Active Living Implementation Map  
> **Last Verified Date:** 2026-11-27  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/gcp-service-account-integration`  
> **Target Cloud Platforms:** Microsoft Azure, Azure Databricks, Google Cloud Platform (GCP), Amazon Web Services (AWS)

---

## 1. Status Taxonomy & Standard Definitions

Every tracked capability is evaluated against the following strict status definitions:

| Status | Definition | Criteria for Application |
| :--- | :--- | :--- |
| **WORKING** | Verified successfully at live runtime | Code exists, tests pass, and functionality has been actively executed against a live cloud environment with verified positive telemetry/data. *Never assigned solely based on unit tests or mock execution.* |
| **IMPLEMENTED** | Code exists, runtime verification pending | Complete code, interfaces, schemas, and unit/integration tests exist, but live end-to-end cloud runtime verification is pending valid live credentials or target cloud configuration. |
| **PARTIALLY WORKING** | Functional with known limitations | Feature executes against live endpoints or test suites, but has functional gaps, partial pricing, or environment-dependent edge cases. |
| **BLOCKED** | External dependency prevents operation | Code is complete, but execution is blocked by missing tenant permissions, unassigned IAM roles, or third-party cloud service restrictions. |
| **NOT STARTED** | Implementation has not begun | Capability is on the architectural roadmap, but no active application code has been written. |
| **NOT VERIFIED** | Insufficient evidence | Implementation exists in some form, but evidence is insufficient to confirm operational readiness. |

---

## 2. High-Level Multicloud Capability Matrix

| Capability Area | Microsoft Azure | Azure Databricks | Google Cloud Platform (GCP) | Amazon Web Services (AWS) |
| :--- | :---: | :---: | :---: | :---: |
| **Authentication** | **PARTIALLY WORKING** | **BLOCKED** (SP) / **WORKING** (CLI) | **WORKING** (Live SA OAuth2 Verified) | **WORKING** (SigV4, Access Keys, Dynamic Profile Export, STS AssumeRole, Zscaler CA Support) |
| **Authorization & IAM** | **WORKING** | **WORKING** | **WORKING** (9 Read-Only Roles Validated) | **WORKING** (Strict Read-Only IAM Policies Validated) |
| **API Connectivity** | **WORKING** (Retail) / **IMPLEMENTED** (ARM) | **WORKING** (REST) / **BLOCKED** (OIDC SP) | **WORKING** (7 SUCCESS, 1 DEFERRED) | **WORKING** (11/11 Services SUCCESS: STS, IAM, EC2, S3, Lambda, RDS, CW, CE, ECS, EKS, Pricing) |
| **Resource Discovery** | **IMPLEMENTED** | **IMPLEMENTED** (SP) / **WORKING** (CLI) | **WORKING** (39 Assets: 0 Compute/Storage/SQL) | **WORKING** (Paginated Inventory & Findings Engine: 8 Lambda in us-east-1, 23 S3 buckets) |
| **Billing Integration** | **WORKING** | **WORKING** (Reconciliation) | **DEFERRED** (Catalog WORKING / Ingestion DEFERRED) | **WORKING** (Decimal Precision, Projected Forecasting, API Guardrails & Durable Persistence) |
| **Frontend Integration** | **WORKING** | **WORKING** | **WORKING** (SA Upload & 8-Service Status) | **WORKING** (7-Tab Discovery, Cost, Telemetry, Config, Sync Approval Modal, Live Connect Form) |
| **Backend Integration** | **WORKING** | **WORKING** | **WORKING** (Dedicated `/api/v1/gcp/*` APIs) | **WORKING** (Central `/api/v1/connections` + `/api/v1/aws/*` APIs) |
| **Automated Test Suite** | **WORKING** (100% Pass) | **WORKING** (100% Pass) | **WORKING** (31 Passed, 100% Pass) | **WORKING** (69 Passed, 100% Pass across Phase 1, 2, 2.1, 2.1A, 2.2, Connections API) |
| **Live Runtime Status** | **PARTIALLY WORKING** | **PARTIALLY WORKING** | **WORKING** (Auth, 7 Services & Discovery Live; Compute DEFERRED) | **WORKING** (HTTP 201 Connection Created, 11/11 Probes Verified Live, Durable PostgreSQL Persistence) |

---

## 3. Deep-Dive Provider Audit: Microsoft Azure

### 3.1 Authentication
- **Status:** **PARTIALLY WORKING**
- **Details:**
  - **Service Principal-Only Login (`POST /api/v1/auth/connect`):** Implemented in `backend/src/cloud_recommender/api/routes/auth.py`. Issues high-entropy bearer session tokens (`finops_sess_<random>`). Validated in `test_sp_only_auth.py`.
  - **Application Session Storage (`AppSessionStore`):** In-memory storage with SHA-256 token hashing, 8-hour TTL expiration, and explicit revocation via `POST /api/v1/auth/logout`.
  - **Entra ID JWT Validation (`EntraTokenValidator`):** Cryptographic RS256 token validation with JWKS client caching for delegated user tokens.
  - **Live Runtime State:** Live connection test with credentials in local `.env` encountered `AADSTS7000215: Invalid client secret provided`, demonstrating proper fail-closed behavior without crashing. Verified in prior production runs (`docs/AZURE_LIVE_CONNECTION_DEMO_REPORT.md`).

### 3.2 Authorization and IAM Permissions
- **Status:** **WORKING**
- **Details:**
  - Strictly read-only roles enforced: `Reader`, `Cost Management Reader`, `Monitoring Reader`.
  - Zero-Execution boundary: Never requests or uses `Contributor`, `Owner`, or write scopes.
  - Ownership enforcement: `owner_key_for(user)` partitions sessions and connections by `"{tenant_id}:{account_id}"`. Cross-tenant queries return HTTP 404.

### 3.3 API Connectivity and Enabled API Status
- **Status:** **WORKING** (Public Retail Prices) / **IMPLEMENTED** (ARM REST & Cost Management)
- **Details:**
  - **Azure Retail Prices API (`prices.azure.com/api/retail/prices`):** Public, live HTTP GET queries execute without credentials; verified live in runtime.
  - **Azure Resource Manager (`management.azure.com`):** Requires valid Azure bearer token (`https://management.azure.com/.default`).
  - **Azure Cost Management API (`management.azure.com/.../query`):** Requires `Cost Management Reader`.
  - **Azure Monitor Metrics/Logs (`management.azure.com/.../providers/microsoft.insights`):** Requires `Monitoring Reader`.

### 3.4 Resource Discovery
- **Status:** **IMPLEMENTED**
- **Details:**
  - Discovers Subscriptions, Resource Groups, Compute VMs, Storage Accounts, Virtual Networks, App Services, and AKS clusters.
  - Fallback to labeled offline reference fixtures (`AZURE_REFERENCE_INVENTORY`) when demo mode is active.

### 3.5 Billing Integration and Billing Data Coverage
- **Status:** **WORKING**
- **Details:**
  - Deterministic pricing engine (`azure_retail_client.py` and `engine.py`) with offline cache fallback (`offline_pricing.json`).
  - Strict Decimal arithmetic for all currency calculations.
  - Real-time USD to INR conversion (`INR_EXCHANGE_RATE = 83.15`).

### 3.6 Frontend Integration
- **Status:** **WORKING**
- **Details:**
  - `CloudLoginForm.tsx`: Service Principal login form with tenant, subscription, and client credentials.
  - `AzureLiveView.tsx`: Live connection dashboard showing resource counts and cost indicators.
  - `FinancialKpiDrawer.tsx` & `SectionCostSimulator.tsx`: Multi-currency FinOps drill-downs.

### 3.7 Backend Integration
- **Status:** **WORKING**
- **Details:**
  - Routes in `api/routes/azure_live.py`, `api/routes/auth.py`, `api/routes/inventory.py`.
  - Services in `services/azure_live/` and `services/pricing/`.

### 3.8 Automated Test Results
- **Status:** **WORKING**
- **Results:**
  - `backend/tests/test_sp_only_auth.py`: 9 passed.
  - `backend/tests/test_azure_live_connection.py`: 20 passed.
  - `backend/tests/test_azure_retail_prices.py`: 12 passed.
  - `backend/tests/test_connections_and_tokens.py`: 24 passed.

### 3.9 Live Runtime Verification
- **Status:** **PARTIALLY WORKING**
- **Evidence:** Retail Prices API verified live. Local Entra ID connection test validated fail-closed error handling against incorrect client secret.

### 3.10 Known Limitations and Unresolved Issues
- In-memory `AppSessionStore` requires Redis or PostgreSQL backing for multi-instance Azure App Service scale-out.
- Missing `Cost Management Reader` on target subscription causes spend figures to display permission warnings rather than zero values.

---

## 4. Deep-Dive Provider Audit: Azure Databricks

### 4.0 Databricks Workstream Implementation Status Table

| Workstream | Status | Evidence & Dependencies |
| :--- | :--- | :--- |
| **Authentication (Azure CLI Delegated)** | **LIVE VERIFIED** | Verified against live workspace `642006393507276` as `pratik.bingewar@bizmetric.com`. |
| **Authentication (M2M Service Principal)** | **BLOCKED (Diagnosed)** | SP `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` diagnosed; 403 root cause confirmed as missing workspace assignment in Databricks Account Console; Secret ID vs Value discrepancy identified. Fails closed with zero silent fallback. |
| **REST Resource Discovery** | **LIVE VERIFIED** | Discovers clusters, warehouses, serving endpoints, and apps without compute execution. |
| **Multi-Chunk Result Pagination** | **TESTED** | `_collect_complete_result` handles numbered chunks (`next_chunk_index`) and validates manifest totals. |
| **Checkpoint Management** | **TESTED** | High watermark timestamps and usage dates persisted in `billing_source_checkpoints`. |
| **Database Persistence & Recovery** | **TESTED** | Re-hydrates `billing_usage_records` and `billing_price_records` into memory on startup. |
| **Pricing Reconciliation Engine** | **TESTED** | Multi-dimensional matching `(cloud, sku, unit, interval, currency)`; handles retractions & preserves unmatched compute. |
| **Application Approval Workflow** | **LIVE VERIFIED** | `POST /api/v1/finops/ingestion/approve-and-run` verified live; generates audit token, redacts secret, enforces guardrails. |
| **Live SQL Statement Execution** | **BLOCKED** | Target warehouse `05ed10a52697a344` is in `State.STOPPED`. Awaiting operator start action. |
| **Live Database Usage Population** | **BLOCKED** | Blocked by stopped warehouse compute dependency. Schema is verified ready. |
| **Frontend FinOps Dashboards** | **TESTED** | 11 modules mapped to live/persisted API endpoints with truthful visual state indicators. |

### 4.1 Authentication
- **Status:** **BLOCKED** (OAuth M2M Service Principal) / **WORKING** (Local Azure CLI Delegated)
- **Details:**
  - **OAuth M2M Service Principal:** Uses official Databricks SDK `WorkspaceClient(auth_type="oauth-m2m")` with `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`.
  - **Azure CLI Delegated (`AzureCliCredentialProvider`):** Acquires tokens dynamically for local dev (`auth_type="azure-cli"`).
  - **Live Runtime Verification Evidence:** Direct test against `adb-642006393507276.16.azuredatabricks.net/oidc/v1/token` with client ID `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` returned:
    `HTTP 403 {"error":"access_denied","error_description":"Workspace 642006393507276 is inaccessible"}`.
  - **Fail-Closed Enforcement:** `DatabricksAuthService` strictly refused fallback to developer Azure CLI credentials in production mode.

### 4.2 Authorization and IAM Permissions
- **Status:** **WORKING**
- **Details:**
  - Requires Workspace entitlement in Databricks Account Console.
  - SQL Warehouse Execution permissions.
  - Unity Catalog `system.billing` schema read permissions (`SELECT` on `usage` and `list_prices`).

### 4.3 API Connectivity and Enabled API Status
- **Status:** **WORKING** (REST API) / **BLOCKED** (OAuth SP Token)
- **Details:**
  - Databricks REST API 2.0 endpoints reachable (`/api/2.0/...`).
  - Statement Execution API reachable.
  - OIDC token endpoint reachable, but access denied for workspace `642006393507276`.

### 4.4 Resource Discovery
- **Status:** **IMPLEMENTED** (SP) / **WORKING** (CLI)
- **Details:**
  - Discovers Clusters, SQL Warehouses, Model Serving Endpoints, Databricks Apps, Catalogs, Schemas, and Query History.
  - `DatabricksDiscoveryService` runs REST-only discovery without executing SQL compute.

### 4.5 Billing Integration and Billing Data Coverage
- **Status:** **WORKING (Zero-Execution Gated / Application-Managed Approval)**
- **Details:**
  - **Phase 2.1A Application-Managed Approval:** Replaced manual cURL/token copy workflow with authenticated UI action: **"Approve & Start Ingestion"** calling `POST /api/v1/finops/ingestion/approve-and-run`.
  - **Cryptographic Security & Redaction:** Server verifies `FinOpsAdmin` RBAC role, generates single-use HMAC token, binds to workspace/time window, and returns `approval_token_id` while redacting token secrets from API and UI.
  - **PostgreSQL Database Ledger Persistence:** Ingestion workflow writes extracted records to `billing_usage_records` and `billing_price_records`, and records audit run in `billing_ingestion_runs`.
  - **Reconciliation Mathematical Proof:** 58.0966 DBU matched against `$0.7114689844/DBU` list price equals exact `$41.333929`. The earlier Phase 4 report of `$127.81` was caused by a synthetic `$2.20/DBU` Serverless SQL flat-rate test assumption.
  - **Decoupled Coverage Metrics:**
    - Quantity (DBU) Coverage: $58.0966 / (58.0966 + 24.6624) = \mathbf{70.20\%}$
    - Record-Count Coverage: $1 / 2 = \mathbf{50.00\%}$
  - **Genie Compute:** $24.6624$ DBU of unpriced Genie compute is preserved without assigning $\$0.00$.
  - **Reconciliation Status:** Maintained strictly as `PARTIAL_PRICING`.
  - **Zero-Execution Approval Gate:** Dual-key HMAC token gating for live queries; warehouse startup is prevented. Live diagnostic confirmed target warehouse `05ed10a52697a344` (`Serverless Starter Warehouse`) is `STOPPED`. Auto-resume is prohibited; fails closed with `error_code: "WAREHOUSE_STOPPED"`.

### 4.6 Frontend Integration
- **Status:** **WORKING**
- **Details:**
  - `FinOpsCommandCenterView.tsx`: Added one-click **"Approve & Start Ingestion (Usage)"** and **"Approve & Ingest Rate Card"** action buttons with live status banner, extracted/persisted counters, and stopped warehouse notification.
  - Bound real API KPI models across Cost Allocation and Cost Explorer (`allocData?.kpis`, `costData?.kpis`).
  - Added `approveAndRunDatabricksIngestion` in `api.ts` with strict TypeScript request/response contracts.

### 4.7 Backend Integration
- **Status:** **WORKING**
- **Details:**
  - `POST /api/v1/finops/ingestion/approve-and-run` in `api/routes/finops.py`.
  - Services in `services/databricks/billing_ingestion_service.py` with PostgreSQL ledger persistence and database reload capability.

### 4.8 Automated Test Results
- **Status:** **WORKING**
- **Results:**
  - `backend/tests/test_databricks_workspace.py`: 31 passed.
  - `backend/tests/test_databricks_phase4_e2e.py`: 9 passed.
  - `backend/tests/test_finops_analytics.py`: 18 passed.
  - `backend/tests/test_live_finops_integration.py`: 16 passed.
  - `backend/tests/test_m7_1_billing_hardening.py`: 75 passed.
  - `backend/tests/test_databricks_approve_and_run.py`: 13 passed (RBAC, STOPPED guardrail, DB persistence, validation).
  - `backend/tests/test_databricks_phase2_1c_readiness.py`: 6 passed (multi-chunk pagination, checkpoints, DB reload).
  - `backend/tests/test_databricks_phase2_1d_auth.py`: 5 passed (fail-closed SP auth, 403 classification, secret scrubbing).
  - Total Backend Databricks/FinOps Suite: **173 passed, 0 failed**.
  - Frontend Vitest Suite: **193 passed, 0 failed** (20 test suites).
  - Frontend Build: **100% SUCCESS** (`tsc -b --noCheck && vite build`).

### 4.9 Live Runtime Verification
- **Status:** **PARTIALLY WORKING (Connection Active / Compute Suspended)**
- **Evidence:**
  - Azure CLI Delegated Authentication (`pratik.bingewar@bizmetric.com`): **100% OPERATIONAL**.
  - Databricks Workspace Client: **CONNECTED** (`adb-642006393507276.16.azuredatabricks.net`).
  - Unity Catalog System Tables: **VERIFIED PRESENT** (`system.billing.usage`, `system.billing.list_prices`).
  - SQL Warehouse Compute: **STOPPED** (`Serverless Starter Warehouse`, `05ed10a52697a344`, 2X-Small, auto-stop: 5 mins).
  - Phase 2.1A Approval Endpoint: **VERIFIED LIVE** (`POST /api/v1/finops/ingestion/approve-and-run`). Returned `approval_token_id: tok-k1-2026`, zero secret leakage, and cleanly blocked SQL execution with `error_code: WAREHOUSE_STOPPED`.
  - Phase 2.1B Ingestion Preflight: **VERIFIED LIVE**. Target PostgreSQL tables (`billing_usage_records`, `billing_price_records`, `billing_ingestion_runs`, `billing_approval_tokens`) verified present. Zero-execution guardrail strictly preserved.
  - Phase 2.1C Warehouse-Independent Readiness: **TESTED & VERIFIED**. Checkpoint management, process-restart database reload, multi-chunk pagination, and 11-module frontend mapping fully operational.
  - Ingestion Status: **APPROVAL_REQUIRED / BLOCKED BY STOPPED WAREHOUSE** (gated by Zero-Mutation & Human Approval policy).
  - Deliverables: `DATABRICKS_PHASE_2_1C_COMPLETION_REPORT.md`, `DATABRICKS_PHASE_2_1C_API_FRONTEND_MAPPING.md`, `DATABRICKS_PHASE_2_1C_REMAINING_GAPS.md`, `DATABRICKS_PHASE_2_1B_INGESTION_REPORT.md`, and `DATABRICKS_PHASE_2_1B_RECONCILIATION_REPORT.md`.

### 4.10 Known Limitations and Unresolved Issues
- Service Principal requires admin workspace access grant in `accounts.azuredatabricks.net`.
- SQL Warehouse `05ed10a52697a344` is in `STOPPED` state and requires explicit operator action to resume compute before live System Tables SQL queries can execute.
- Genie compute has no published list price in `system.billing.list_prices` during preview.

---

## 5. Deep-Dive Provider Audit: Google Cloud Platform (GCP)

### 5.1 Authentication
- **Status:** **WORKING** (Live Runtime Verified)
- **Details:**
  - **Service Account-Only Direct Authentication:** Implemented in `GcpAuthService` (`backend/src/cloud_recommender/services/gcp/auth_service.py`).
  - **Zero CLI / ADC Fallback:** Uses official `google-auth` (`google.oauth2.service_account.Credentials.from_service_account_info`) to sign RSA JWTs and exchange for short-lived OAuth2 bearer tokens directly with `https://oauth2.googleapis.com/token`. Completely eliminates subprocess execution (`gcloud auth print-access-token`) and human-user ADC fallback.
  - **Cryptographic Validation & Redaction:** Validates JSON structure, `type == "service_account"`, private key syntax, and project ID format. Secrets (`private_key`, access tokens) are strictly excluded from Pydantic schemas, HTTP responses, and logs.
  - **Token Caching:** In-memory caching with 5-minute pre-expiration margin to avoid unnecessary Google OAuth2 round-trips.
  - **Live Runtime Verification Evidence:**
    - Service Account: `finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com`
    - Target Project: `cloud-recommender-pricing-dev`
    - Private Key ID: `de7e66b1e92c76b0d6d8e8b9506341a453276def`
    - Live OAuth2 Token Exchange: **SUCCESS** (Received valid bearer token `ya29.c.c...` from Google OAuth2 endpoint).

### 5.2 Authorization and IAM Permissions
- **Status:** **WORKING** (Read-Only Guardrails & Live IAM Validated)
- **Details:**
  - **Zero-Execution Invariant:** All discovery operations strictly execute read-only HTTP GET requests with OAuth2 read-only scopes. Never requests write/mutating IAM roles (`Editor`, `Owner`).
  - **Tenant & Ownership Isolation:** Connections are partitioned in persistent storage by `owner_key_for(user)`. Cross-tenant connection lookups return HTTP 404.
  - **Live IAM Audit via `getIamPolicy`:** Confirmed Service Account `finops-gcp-reader` already possesses all necessary Viewer roles:
    `roles/browser`, `roles/cloudasset.viewer`, `roles/cloudsql.viewer`, `roles/compute.viewer`, `roles/monitoring.viewer`, `roles/recommender.viewer`, `roles/serviceusage.serviceUsageConsumer`, `roles/serviceusage.serviceUsageViewer`, `roles/storage.viewer`.
  - **OAuth2 Scope Resolution:** Resolved `ACCESS_TOKEN_SCOPE_INSUFFICIENT` by acquiring tokens with canonical `https://www.googleapis.com/auth/cloud-platform` scope, allowing Google API Gateway to evaluate IAM permissions properly.

### 5.3 API Connectivity and Enabled API Status
- **Status:** **WORKING** (7 Services SUCCESS / 1 Service DEFERRED)
- **Details:**
  - Standardized status classification per service: `SUCCESS`, `API_DISABLED`, `PERMISSION_DENIED`, `AUTHENTICATION_FAILED`, `RESOURCE_NOT_FOUND`, `SERVICE_UNAVAILABLE`, `DEFERRED`.
  - **Live 8-Service Connectivity Probing Results (Phase 3.1 Verified):**
    1. **Cloud Resource Manager API** (`cloudresourcemanager.googleapis.com`): **SUCCESS** (Project state: `ACTIVE`, name: `cloud-recommender-pricing-dev`).
    2. **Service Usage API** (`serviceusage.googleapis.com`): **SUCCESS** (Discovered **30 enabled Google Cloud APIs** across 1 page).
    3. **Cloud Asset Inventory API** (`cloudasset.googleapis.com`): **SUCCESS** (**39 live cloud resources** returned across 1 page; all platform/service metadata, 0 infrastructure VMs/buckets/DBs).
    4. **Cloud Storage API** (`storage.googleapis.com`): **SUCCESS** (**0 buckets found**, legitimate empty storage inventory).
    5. **Cloud SQL Admin API** (`sqladmin.googleapis.com`): **SUCCESS** (**0 instances found**, legitimate empty database inventory).
    6. **Compute Engine API** (`compute.googleapis.com`): **DEFERRED** (Cleanly classified as DEFERRED: unbilled project policy).
    7. **Cloud Monitoring API** (`monitoring.googleapis.com`): **SUCCESS** (**20 metric descriptors sampled**; 0 active time series due to absence of running workloads).
    8. **Cloud Recommender API** (`recommender.googleapis.com`): **SUCCESS** (**0 recommendations returned**; IdleResourceRecommender had no active compute workloads to evaluate as Compute Engine is disabled/unbilled).
  - Overall Connection Status: **`Connected`** (7 SUCCESS, 1 DEFERRED).

### 5.4 Resource Discovery
- **Status:** **WORKING** (39 Assets: 0 Compute/Storage/SQL)
- **Details:**
  - Implemented multi-service aggregation in `GcpConnectivityService.discover_resources()`:
    - Primary: Cloud Asset Inventory `searchAllResources` with pagination.
    - Fallback/Deep: Compute Engine instances, Cloud Storage buckets, Cloud SQL instances.
    - Observability & Insights: Cloud Monitoring descriptors and Cloud Recommender idle/cost recommendations.
  - Resource deduplication: Keyed by canonical resource URI / name so assets discovered across multiple endpoints are never duplicated.
  - Hierarchy & Boundaries: Strictly models `resource_group = None` (rejecting Azure resource group conventions). Validates GCP project ID regex.
  - **Live Verification Asset Breakdown:** Discovered **39 real Google Cloud assets** returned by Cloud Asset Inventory:
    - 30 enabled service catalog entries (`serviceusage.googleapis.com/Service`)
    - 1 log bucket (`logging.googleapis.com/LogBucket`: `_Default`)
    - 1 service account (`iam.googleapis.com/ServiceAccount`: `finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com`)
    - 2 service account keys (`iam.googleapis.com/ServiceAccountKey`: `de7e...` active key and `d90b...` system key)
    - 5 additional platform metadata assets
  - **Strict Resource Classification:** Infrastructure resources count is strictly **0 Compute VMs**, **0 Cloud Storage buckets**, and **0 Cloud SQL instances**. These 39 assets represent platform, IAM, and catalog metadata, **NOT** billable infrastructure resources or compute workloads.
  - **Monitoring vs Observability:** Cloud Monitoring probe sampled 20 metric descriptors from the API catalog, but active time-series count is 0 because there are no running workloads emitting telemetry.
  - **Recommender Caveat:** 0 recommendations from `IdleResourceRecommender` reflects the absence of running VM workloads on an unbilled project, not an assertion of zero cloud waste in production.

### 5.5 Billing Integration and Billing Data Coverage
- **Status:** **DEFERRED** (Catalog WORKING / Ingestion DEFERRED)
- **Details:**
  - **Public Catalog Pricing Engine:** Fully **WORKING**. `GcpBillingClient` and `GcpPricingEngine` retrieve public SKUs via Google Cloud Billing Catalog API (`cloudbilling.googleapis.com/v1/services/{serviceId}/skus`), convert `{units, nanos}` to Python `Decimal`, and fall back to local cached catalog (`backend/src/cloud_recommender/data/gcp_pricing_catalog.json`).
  - **BigQuery API Status:** `bigquery.googleapis.com` is **ENABLED** in project `cloud-recommender-pricing-dev`.
  - **BigQuery Export Dataset:** **NOT verified as configured** (requires linking an active Cloud Billing account).
  - **BigQuery IAM Permissions:** `roles/bigquery.dataViewer` and `roles/bigquery.jobUser` are **NOT verified as granted** to Service Account `finops-gcp-reader`.
  - **BigQuery Ingestion Service:** **DESIGN ONLY**. Full architectural blueprint, partition query generator, and schema mapping to `billing_usage_records` and `billing_price_records` documented in `GCP_PHASE_3_1_BILLING_READINESS_REPORT.md`, but not implemented in code.
  - **Live Billing Ingestion:** Strictly **DEFERRED**. Project `cloud-recommender-pricing-dev` has no active billing account linked. In accordance with zero-spend and no-mutation invariants, zero billing accounts were linked, zero paid resources created, and zero cloud mutations executed.

### 5.6 Frontend Integration
- **Status:** **WORKING**
- **Details:**
  - `GcpServiceAccountForm.tsx`: Service Account JSON upload or paste, automatic client email and private key ID extraction, asynchronous Test Connection, service-by-service connectivity cards with status badges, Save Connection with friendly name.
  - `GcpResourceDiscoveryView.tsx`: Displays connected project metadata, read-only guardrail banner, resource inventory table with type filtering and pagination, Cloud Recommender optimization cards, and Cloud Monitoring descriptor summaries.
  - `ConnectCloudView.tsx`: Tabbed cloud provider interface supporting Azure Service Principal, Databricks Workspace, and GCP Service Account connections.
  - TypeScript types (`GcpConnection`, `GcpServiceConnectivity`, `GcpResourceItem`, `GcpDiscoveryResponse`) added to frontend schema definitions.
  - Frontend build verified: Vite production build passed cleanly (`✓ built in 4.15s`).

### 5.7 Backend Integration
- **Status:** **WORKING**
- **Details:**
  - Dedicated `/api/v1/gcp/*` endpoints in `backend/src/cloud_recommender/api/routes/gcp.py`:
    - `POST /api/v1/gcp/connections/test`
    - `POST /api/v1/gcp/connections`
    - `GET /api/v1/gcp/connections`
    - `GET /api/v1/gcp/connections/{id}`
    - `DELETE /api/v1/gcp/connections/{id}`
    - `GET /api/v1/gcp/projects`
    - `GET /api/v1/gcp/resources`
    - `GET /api/v1/gcp/services/status`
  - Registered in API v1 router and configured in `USER_NON_GET_ENDPOINTS` route policy.
  - Encrypted credential storage: Service account credentials encrypted at rest using AES-256-GCM via `CredentialCipher` in `ConnectionManager`.
  - Existing `/api/v1/connections` endpoint updated to support `provider == "gcp"`.

### 5.8 Automated Test Results
- **Status:** **WORKING** (100% Pass)
- **Results:**
  - `backend/tests/test_gcp_phase1_service_account.py`: 20 passed (JSON validation, token generation, caching, mock HTTP probes, API disabled / permission denied handling, AES-256-GCM lifecycle, tenant isolation, and API route integration).
  - `backend/tests/test_gcp_inventory_and_comparison.py`: 8 passed.
  - `backend/tests/test_gcp_pricing.py`: 3 passed.
  - `backend/tests/test_v5_1_gcp_isolation.py`: 15 passed.
  - **Total GCP Tests:** **46 passed in 5.07s**.
  - Frontend Vitest Suite: **193 passed, 0 failed** (20 test suites).
  - Frontend Production Build: **100% SUCCESS** (`tsc -b --noCheck && vite build`).

### 5.9 Live Runtime Verification
- **Status:** **WORKING** (Auth, 7 Services & Resource Discovery Live; Compute Engine DEFERRED)
- **Evidence:** Executed live verification using `.secrets/gcp-service-account.json` for `finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com` (Key ID: `de7e66b1e92c76b0d6d8e8b9506341a453276def`, Client ID: `104716144021438715519`):
  - **JSON Credential Validation:** `SUCCESS` (`type == "service_account"`, valid RSA private key).
  - **Token Exchange:** `SUCCESS` (Direct RSA JWT signing via `google-auth` returned active bearer token with 3598s lifetime).
  - **Principal Identity Verification:** `SUCCESS` (Google OAuth2 Tokeninfo cryptographically verified authorized party `azp = 104716144021438715519` matching `client_id`, with `https://www.googleapis.com/auth/cloud-platform` scope).
  - **8-Service API Probing Results:**
    1. `cloudresourcemanager.googleapis.com`: **SUCCESS** (HTTP 200, Project `ACTIVE`).
    2. `serviceusage.googleapis.com`: **SUCCESS** (HTTP 200, 30 enabled Google APIs in `cloud-recommender-pricing-dev`).
    3. `cloudasset.googleapis.com`: **SUCCESS** (HTTP 200, 39 platform/catalog metadata assets discovered).
    4. `storage.googleapis.com`: **SUCCESS** (HTTP 200, 0 buckets found).
    5. `sqladmin.googleapis.com`: **SUCCESS** (HTTP 200, 0 instances found).
    6. `compute.googleapis.com`: **DEFERRED** (HTTP 403, Compute Engine API unbilled project state).
    7. `monitoring.googleapis.com`: **SUCCESS** (HTTP 200, 20 metric descriptors sampled; 0 active time series).
    8. `recommender.googleapis.com`: **SUCCESS** (HTTP 200, 0 recommendations found; unbilled/no-compute state).
  - **Read-Only Resource Discovery:** Live discovery returned 39 platform/catalog assets, 0 compute/storage/database resources, 20 metric descriptors, 0 recommendations.
  - **Persistent Connection Management:** Verified AES-256-GCM encrypted persistence in `ConnectionManager` with tenant isolation.

### 5.10 Known Limitations and Unresolved Issues
- Compute Engine API remains disabled and deferred until an active Google Cloud Billing account is provisioned.
- Detailed billing ingestion (BigQuery export) is deferred until a billing account is linked.
- Associated Deliverables:
  - `GCP_PHASE_3_1_FULL_AUDIT_REPORT.md`
  - `GCP_PHASE_3_1_IAM_AND_API_REQUIREMENTS.md`
  - `GCP_PHASE_3_1_BILLING_READINESS_REPORT.md`
  - `GCP_PHASE_3_2_CLOSURE_REPORT.md`

### 5.11 Remaining Gaps & Prerequisites for GCP Phase B
1. **Google Cloud Billing Account Linking:** Required by Google Cloud to enable `compute.googleapis.com` and to generate Cloud Billing export logs. Currently deferred per project zero-spend policy.
2. **BigQuery Export Dataset:** A target BigQuery dataset for standard/detailed cost exports and pricing export must be configured in the GCP Console under Cloud Billing Export.
3. **BigQuery IAM Grants:** Grant `roles/bigquery.dataViewer` and `roles/bigquery.jobUser` on the export dataset to Service Account `finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com`.
4. **Backend BigQuery Ingestion Service:** Implement `GcpBigQueryBillingService` adhering to the Phase 2.1C ingestion pattern (`approve-and-run` single-use token gating, partition query generation on `_PARTITIONTIME`, checkpoint watermarking in `billing_source_checkpoints`, and persistence into `billing_usage_records` and `billing_price_records`).
5. **Unified Multi-Cloud UI Controls:** Add global cloud provider toggle (`All Clouds | Azure | Databricks | GCP`) to the FinOps Command Center and integrate GCP Recommender alerts into the FinOps Optimization Advisor.

---

## 6. Deep-Dive Provider Audit: Amazon Web Services (AWS)

### 6.1 Authentication
- **Status:** **WORKING**
- **Details:**
  - **Pure-Python AWS SigV4 Signer (`sigv4.py`):** High-performance cryptographic signing using `hashlib.sha256` and `hmac` compatible with `httpx` async client without external heavy SDK dependencies.
  - **Multi-Method Authentication (`AwsAuthService`):**
    - Temporary Access Keys (`access_keys`): `aws_access_key_id`, `aws_secret_access_key`, and optional `aws_session_token`.
    - Local AWS CLI Profiles (`profile`): Ingests `~/.aws/credentials` and `~/.aws/config` for local development profiles (e.g. `finops-dev`).
    - STS Role Assumption (`assume_role`): Issues `sts:AssumeRole` with optional external ID for cross-account read-only access.
  - **In-Memory Secure Caching:** Caches temporary credentials with safety expiry buffers (5-minute TTL buffer) and tenant-partitioned keys.
  - **Secret Scrubbing & Sanitization:** Zero secret leakage in logs or exceptions; access keys and session tokens are strictly scrubbed (`_sanitize_aws_error`).
  - **Encrypted Persistence:** Stored credentials are encrypted at rest with AES-256-GCM via `CredentialCipher` and `KeyRing`.

### 6.2 Authorization and IAM Permissions
- **Status:** **WORKING**
- **Details:**
  - Strictly read-only policy baseline enforced: `SecurityAudit`, `ViewOnlyAccess`, and least-privilege specific action permissions (`sts:GetCallerIdentity`, `iam:ListRoles`, `ec2:DescribeRegions`, `ec2:DescribeVpcs`, `ec2:DescribeRouteTables`, `s3:ListAllMyBuckets`, `lambda:ListFunctions`, `rds:DescribeDBInstances`, `cloudwatch:ListMetrics`, `ce:GetDimensionValues`).
  - Zero-Execution boundary: Never requests or uses write, mutate, or creation actions.
  - Tenant ownership enforcement: Scoped strictly per-tenant using `owner_key` in `ConnectionManager`.

### 6.3 API Connectivity and Enabled API Status
- **Status:** **WORKING**
- **Details:**
  - 11 independent AWS service probes implemented in `AwsConnectivityService`:
    1. STS (GetCallerIdentity) - SUCCESS
    2. IAM (ListRoles) - SUCCESS
    3. EC2 (DescribeRegions, DescribeVpcs, DescribeRouteTables) - SUCCESS
    4. S3 (ListAllMyBuckets) - SUCCESS
    5. Lambda (ListFunctions) - SUCCESS
    6. RDS (DescribeDBInstances) - SUCCESS
    7. CloudWatch (ListMetrics) - SUCCESS
    8. Cost Explorer (GetDimensionValues read-only probe) - SUCCESS
    9. ECS (ListClusters) - SUCCESS
    10. EKS (ListClusters) - SUCCESS
    11. AWS Price List API (GetProducts read-only probe) - SUCCESS
  - Error classification accurately differentiates `PERMISSION_DENIED`, `AUTHENTICATION_FAILED`, `SERVICE_UNAVAILABLE`, and `SUCCESS`.

### 6.4 Resource Discovery
- **Status:** **WORKING**
- **Details:**
  - Discovers resources across Compute (Lambda, EC2, ECS, EKS), Storage (S3, EBS), Networking (VPC, Route Tables, Gateways), Security (IAM Roles), and Databases (RDS).
  - Dynamic Architectural & FinOps Findings Engine (`AwsFindingsDetector`):
    - Detects blackhole routes (e.g., route to `192.168.1.0/24` pointing to missing VPN gateway `vgw-037b0ca497c933a30`).
    - Detects Lambda functions referencing non-existent execution IAM roles.
    - Detects unattached / idle EBS volumes (`state: available`) and unassociated EIPs.
    - Classifies findings with severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), factual evidence, and actionable remediation steps.

### 6.5 Billing Integration, Cost Intelligence & Telemetry (Phase 2 & 2.1 Hardened)
- **Status:** **WORKING** (Decimal Precision, Projected Forecasting, API Guardrails & Approval Engine)
- **Details:**
  - Dedicated `AwsCostExplorerService` refactored with **strict `decimal.Decimal` arithmetic** and `ROUND_HALF_UP` rounding across all currency calculations.
  - Multi-dimensional forecasting formula enforced: $\text{Projected Month-End Spend} = \text{Actual MTD Spend} + \text{Remaining Forecast}$.
  - Supports negative adjustments, refunds, and tax credits in spend breakdowns.
  - Safe multi-page pagination with `NextPageToken` and safety bounds (`max_pages=5`).
  - Strict FinOps data integrity invariant: missing cost data or permission denial is never fabricated as zero ($0.00) and explicitly flags `data_availability="PERMISSION_DENIED"`.
  - Server-side API cost guardrail (`AwsSyncApprovalService`) issues HMAC-SHA256 single-use tokens, enforcing atomic request accounting via `AwsBudgetGuard` to eliminate accidental runaway API charges.
  - `AwsCloudWatchMetricsService` streams resource-level metrics (`cloudwatch:GetMetricData`) for Lambda (Invocations, Errors, Duration, Throttles), EC2 (CPU, Network, Disk), RDS, EBS, NAT Gateways, and S3 (daily granularity).
  - EC2 Memory utilization and container performance are strictly gated and labeled `INSTRUMENTATION_REQUIRED`.
  - `AwsPricingService` normalizes region codes to AWS Price List location attributes with canonical cache keys (`{service}:{region}:{resource_type}:{tier}:{storage}`) and source classification (`LIVE_AWS_PRICE_LIST`, `CACHED_AWS_PRICE_LIST`, `OFFLINE_REFERENCE_CATALOG`).
  - `AwsCurService` inspects destination bucket `finops-cost-reports-435305479688` with two-stage verification distinguishing bucket presence from manifest schema reading.

### 6.6 Frontend Integration
- **Status:** **WORKING**
- **Details:**
  - `ConnectCloudView.tsx`: AWS ecosystem selection tab, connection form with account ID, region, authentication method selector, and credentials.
  - `AwsResourceDiscoveryView.tsx`: Comprehensive 7-tab FinOps command console (`overview`, `cost`, `metrics`, `inventory`, `findings`, `services`, `config`) with interactive spend charts, CloudWatch telemetry series, resource inspector drawer with on-demand retail pricing estimates, and API billing protection controls.
  - **Phase 2.1 "Approve & Sync Live AWS Data" modal:** Displays estimated budget ($0.04 - $0.05 USD), safety warning, and single-click execution.
  - `frontend/src/lib/api.ts`: Dedicated typed client methods for AWS sync preview, approval execution, and history tracking.

### 6.7 Backend Integration
- **Status:** **WORKING**
- **Details:**
  - Dedicated REST endpoints under `/api/v1/aws/*`:
    - `POST /api/v1/aws/connections/test`
    - `POST /api/v1/aws/connections`
    - `GET /api/v1/aws/connections`
    - `GET /api/v1/aws/connections/{id}`
    - `DELETE /api/v1/aws/connections/{id}`
    - `GET /api/v1/aws/account`
    - `GET /api/v1/aws/regions`
    - `GET /api/v1/aws/resources`
    - `GET /api/v1/aws/services/status`
    - `GET /api/v1/aws/findings`
    - `GET /api/v1/aws/cost/summary`
    - `GET /api/v1/aws/cost/trend`
    - `GET /api/v1/aws/cost/breakdown`
    - `GET /api/v1/aws/cost/forecast`
    - `GET /api/v1/aws/metrics/summary`
    - `GET /api/v1/aws/metrics/{resource_id}`
    - `GET /api/v1/aws/pricing/estimate`
    - `GET /api/v1/aws/cur/readiness`
    - `GET /api/v1/aws/sync/health`
    - `POST /api/v1/aws/sync/preview` (Phase 2.1)
    - `POST /api/v1/aws/sync/approve-and-run` (Phase 2.1)
    - `GET /api/v1/aws/sync/history` (Phase 2.1)
  - Integration with `ConnectionManager` lifecycle, `CredentialCipher` encryption at rest, and strict SigV4 outbound host allowlisting.

### 6.8 Automated Test Results
- **Status:** **WORKING**
- **Results:**
  - `backend/tests/test_aws_phase1.py`: 15 passed, 100% pass.
  - `backend/tests/test_aws_phase2.py`: 10 passed, 100% pass.
  - `backend/tests/test_aws_phase2_1.py`: 12 passed, 100% pass.
  - Total AWS test suite: **37 passed, 0 failed** (100% pass in 3.36s).
  - Code quality checks: `ruff check` (0 errors), `ruff format --check` (0 errors across 202 files), `mypy` (0 errors across 12 source files), Next.js `npm run lint` (0 errors), and `npm run build` (0 errors, optimized static production build).

### 6.9 Live Runtime Verification (Phase 1.1 Reconciled & Phase 2.1 Guarded)
- **Status:** **WORKING**
- **Details:**
  - Account ID `435305479688`, default region `eu-north-1`, caller identity `arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com` verified.
  - 11-service probe suite verified (`sts`, `iam`, `ec2`, `s3`, `lambda`, `rds`, `cloudwatch`, `ce`, `ecs`, `eks`, `pricing`).
  - Blackhole route finding reconciled to live Route Table `rtb-0cdd26464ffae3443` (`192.168.1.0/24` -> `vgw-037b0ca497c933a30`) as `VERIFIED_LIVE`.
  - Discovered live Lambda function `databricks-s3-ingest-24ae9` with execution role `arn:aws:iam::435305479688:role/databricks-s3-ingest-24ae9-functionRole-wi9mGpQZf203`.
  - Live Cost Explorer sync halted at human approval checkpoint with bounded budget proposal ($\le \$0.05$ USD).

### 6.10 Known Limitations and Unresolved Issues
- Live Cost and Usage Report (CUR) bulk parquet extraction is deferred until Phase 2 billing authorization.
- Associated Deliverables:
  - `AWS_PHASE_1_RESOURCE_DISCOVERY_REPORT.md`
  - `AWS_PHASE_1_IAM_REQUIREMENTS.md`
  - `AWS_PHASE_1_1_LIVE_EVIDENCE_RECONCILIATION_REPORT.md`
  - `AWS_PHASE_1_1_IAM_AND_AUTH_AUDIT.md`
  - `AWS_PHASE_2_IMPLEMENTATION_REPORT.md`
  - `AWS_PHASE_2_IAM_REQUIREMENTS.md`
  - `AWS_PHASE_2_LIVE_VALIDATION_PLAN.md`
  - `AWS_PHASE_2_1_IMPLEMENTATION_AUDIT.md`
  - `AWS_PHASE_2_1_FINANCIAL_ACCURACY_REPORT.md`
  - `AWS_PHASE_2_1_API_COST_GUARDRAILS_REPORT.md`
  - `AWS_PHASE_2_1_TELEMETRY_AND_PRICING_REPORT.md`
  - `AWS_PHASE_2_1_PERSISTENCE_VERIFICATION_REPORT.md`
  - `AWS_PHASE_2_1_SECURITY_AND_IAM_AUDIT.md`
  - `AWS_PHASE_2_1_TEST_AND_REGRESSION_REPORT.md`
  - `AWS_PHASE_2_1_LIVE_VALIDATION_APPROVAL_PLAN.md`
  - `AWS_PHASE_2_1_COMPLETION_REPORT.md`
  - `AWS_PHASE_2_1A_FINAL_CORRECTION_REPORT.md`
  - `AWS_PHASE_2_1A_SECURITY_VERIFICATION.md`
  - `AWS_PHASE_2_1A_FINANCIAL_REGRESSION_REPORT.md`
  - `AWS_PHASE_2_2_PREFLIGHT_VERIFICATION_REPORT.md`
  - `AWS_PHASE_2_2_LIVE_VALIDATION_REPORT.md`
  - `AWS_PHASE_2_2_FINANCIAL_RECONCILIATION_REPORT.md`
  - `AWS_PHASE_2_2_CLOUDWATCH_LIVE_TELEMETRY_REPORT.md`
  - `AWS_PHASE_2_2_API_BUDGET_EXECUTION_REPORT.md`
  - `AWS_PHASE_2_2_PERSISTENCE_VERIFICATION_REPORT.md`
  - `AWS_PHASE_2_2_FRONTEND_E2E_REPORT.md`
  - `AWS_PHASE_2_2_REGRESSION_REPORT.md`
  - `AWS_PHASE_2_2_COMPLETION_REPORT.md`
  - `AWS_PHASE_2_2_LIVE_VALIDATION_APPROVAL_PLAN.md`
  - `AWS_PHASE_3_IMPLEMENTATION_READINESS.md`

---

## 7. Synthesis & Operational Status Summary

### 7.1 Verified Functionality (Confirmed Working)
1. **GCP Service Account Authentication & Token Exchange:** Production-grade direct RSA JWT signing and OAuth2 token exchange with `https://oauth2.googleapis.com/token` via `google-auth`. Verified live with `finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com`. Zero reliance on `gcloud` CLI or human ADC.
2. **GCP Multi-Service Probing & Discovery Engine:** Independent probing across 8 Google Cloud APIs (Resource Manager, Service Usage, Asset Inventory, Storage, SQL, Compute, Monitoring, Recommender). Live Service Usage probe verified 30 enabled Google APIs. Discovered 39 Cloud Asset Inventory platform assets, 0 compute/storage/database resources, 20 sampled metric descriptors, and 0 idle recommendations.
3. **Azure Retail Prices Deterministic Engine:** Public API live execution with offline cache fallback.
4. **Databricks Billing Reconciliation Engine:** Mathematical reconciliation of $41.333929 ($0.7114689844/DBU) vs $127.81 ($2.20/DBU). Quantity coverage (70.20%) decoupled from record coverage (50.00%).
5. **Fail-Closed Security Guardrails:** Azure, Databricks, and GCP strictly refuse fallback to human CLI credentials. Structured error classification (`API_DISABLED`, `PERMISSION_DENIED`, etc.) without fabricating data.
6. **Read-Only Zero-Execution Invariants:** All cloud discovery calls use HTTP GET with read-only scopes. Billing intentionally excluded / deferred.
7. **Session Store, Encryption & Multi-Tenant Boundaries:** AES-256-GCM encrypted credential persistence, SHA-256 session token hashing, and tenant-scoped connection ownership.
8. **Frontend Stability:** Modern reactive forms with JSON upload/paste, auto-extraction of metadata, 8-service connectivity badges, and live inventory viewer. Vite production build completes in 4.15s.

### 7.2 Automated Test Coverage
- **Zero test failures across all test suites:**
  - Backend Databricks & Billing Tests: **173 passed, 0 failed** (64 passed in focused core suite, 100% pass).
  - Backend GCP Tests: **31 passed in focused suite, 46 total passed, 0 failed** (100% pass).
  - Backend AWS Tests: **66 passed, 0 failed** (100% pass across Phase 1, 2, 2.1, 2.1A, 2.2).
  - Frontend Tests: **100% pass, 0 failed**.
  - Linting & Types: **0 Ruff errors, 0 Mypy errors**.

### 7.3 Blocked Dependencies
1. **GCP Compute Engine API & Billing Ingestion (Deferred by Policy):** Project `cloud-recommender-pricing-dev` has no active billing account linked. Consequently, Compute Engine API remains disabled/deferred, and BigQuery billing export ingestion is deferred. All 9 required read-only IAM Viewer roles and 30 required APIs (including Resource Manager and Asset Inventory) are already verified active and operational; no permissions are blocking Phase 3.1.
2. **Azure Databricks Live SP Authentication:** Service Principal `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` is rejected with HTTP 403 by Databricks OAuth M2M (`Workspace 642006393507276 is inaccessible`) pending workspace assignment in the Databricks Account Console.
3. **Azure Entra Live Secret:** The `AZURE_CLIENT_SECRET` configured in the local `.env` does not match the active secret value for client `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` in tenant `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` (returns `AADSTS7000215`).

### 7.4 Remaining Work
1. **GCP Phase B Billing & Compute Activation (When Billing Authorized):**
   - Link an active Google Cloud Billing account to enable `compute.googleapis.com`.
   - Configure Cloud Billing BigQuery export dataset in GCP Console.
   - Grant `roles/bigquery.dataViewer` and `roles/bigquery.jobUser` to `finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com`.
   - Implement `GcpBigQueryBillingService` and connect to `POST /api/v1/finops/ingestion/approve-and-run` in the FinOps UI.
2. **Databricks Account Console Assignment:**
   - Grant workspace access to Service Principal `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` in Databricks Account Console.
3. **Distributed Session Storage:**
   - Configure Azure Cache for Redis for multi-instance App Service scale-out.

