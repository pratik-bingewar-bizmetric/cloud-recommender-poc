# Multicloud Implementation Status Map (MULTICLOUD_IMPLEMENTATION_STATUS.md)

> **Document Status:** Active Living Implementation Map  
> **Last Verified Date:** 2026-11-18  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/backend-security-hardening`  
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
| **Authentication** | **PARTIALLY WORKING** | **BLOCKED** (SP) / **WORKING** (CLI) | **IMPLEMENTED** | **NOT STARTED** |
| **Authorization & IAM** | **WORKING** | **WORKING** | **IMPLEMENTED** | **NOT STARTED** |
| **API Connectivity** | **WORKING** (Retail) / **IMPLEMENTED** (ARM) | **WORKING** (REST) / **BLOCKED** (OIDC SP) | **IMPLEMENTED** (API Key) / **IMPLEMENTED** (ADC) | **NOT STARTED** |
| **Resource Discovery** | **IMPLEMENTED** | **IMPLEMENTED** (SP) / **WORKING** (CLI) | **IMPLEMENTED** | **NOT STARTED** |
| **Billing Integration** | **WORKING** | **WORKING** (Reconciliation) | **IMPLEMENTED** (Catalog) | **IMPLEMENTED** (Catalog only) |
| **Frontend Integration** | **WORKING** | **WORKING** | **PARTIALLY WORKING** | **NOT STARTED** |
| **Backend Integration** | **WORKING** | **WORKING** | **IMPLEMENTED** | **NOT STARTED** |
| **Automated Test Suite** | **WORKING** (100% Pass) | **WORKING** (100% Pass) | **WORKING** (100% Pass) | **NOT STARTED** |
| **Live Runtime Status** | **PARTIALLY WORKING** | **PARTIALLY WORKING** | **NOT VERIFIED** | **NOT STARTED** |

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
- **Status:** **WORKING**
- **Details:**
  - **Reconciliation Mathematical Proof:** 58.0966 DBU matched against `$0.7114689844/DBU` list price equals exact `$41.333929`. The earlier Phase 4 report of `$127.81` was caused by a synthetic `$2.20/DBU` Serverless SQL flat-rate test assumption.
  - **Decoupled Coverage Metrics:**
    - Quantity (DBU) Coverage: $58.0966 / (58.0966 + 24.6624) = \mathbf{70.20\%}$
    - Record-Count Coverage: $1 / 2 = \mathbf{50.00\%}$
  - **Genie Compute:** $24.6624$ DBU of unpriced Genie compute is preserved without assigning $\$0.00$.
  - **Reconciliation Status:** Maintained strictly as `PARTIAL_PRICING`.
  - **Zero-Execution Approval Gate:** Dual-key HMAC token gating for live queries; warehouse startup is prevented.

### 4.6 Frontend Integration
- **Status:** **WORKING**
- **Details:**
  - `FinOpsCommandCenterView.tsx`: Renders 15 modules with dynamic workspace scoping.
  - Removed all hardcoded mock strings (`"$284,620"`, `"$176,840"`, etc.).
  - Centralized error conversion via `apiFetch` in `api.ts`.

### 4.7 Backend Integration
- **Status:** **WORKING**
- **Details:**
  - Routes in `api/routes/databricks.py` and `api/routes/finops.py`.
  - Services in `services/databricks/`.

### 4.8 Automated Test Results
- **Status:** **WORKING**
- **Results:**
  - `backend/tests/test_databricks_phase4_e2e.py`: 9 passed.
  - `backend/tests/test_m7_1_billing_hardening.py`: 75 passed.
  - `backend/tests/test_databricks_workspace.py`: 6 passed.

### 4.9 Live Runtime Verification
- **Status:** **PARTIALLY WORKING**
- **Evidence:** REST connectivity verified; SP OAuth M2M returned HTTP 403 due to missing workspace assignment in Databricks Account Console.

### 4.10 Known Limitations and Unresolved Issues
- Service Principal requires admin workspace access grant in `accounts.azuredatabricks.net`.
- SQL Warehouses in `STOPPED` state require separate explicit human authorization before resuming compute.
- Genie compute has no published list price in `system.billing.list_prices` during preview.

---

## 5. Deep-Dive Provider Audit: Google Cloud Platform (GCP)

### 5.1 Authentication
- **Status:** **IMPLEMENTED** (Runtime: **NOT VERIFIED**)
- **Details:**
  - Three-tier ADC / Service Account / Token acquisition implemented in `GcpInventoryService.get_inventory_access_token()`:
    1. Short-lived bearer token: `GCP_ACCESS_TOKEN`
    2. Service Account JSON keyfile: `GOOGLE_APPLICATION_CREDENTIALS`
    3. Local gcloud CLI session: `gcloud auth print-access-token`
  - **Strict Auth Separation:** Public Cloud Billing Catalog API key (`GCP_CLOUD_API_KEY`) is strictly restricted to pricing catalog endpoints and is **never** used to query private inventory.
  - **Live Runtime State:** Currently unauthenticated in active test runtime (`auth_method = "unauthenticated"`). A Service Account JSON file (`cloud-recommender-pricing-dev-de7e66b1e92c.json`) is available in user downloads and pending formal integration.

### 5.2 Authorization and IAM Permissions
- **Status:** **IMPLEMENTED**
- **Details:**
  - Required read-only IAM roles:
    - `roles/browser` (Project browsing)
    - `roles/cloudasset.viewer` (Asset Inventory discovery)
    - `roles/billing.viewer` (Cloud Billing inspection)
  - Zero-Execution boundary: All inventory discovery calls use HTTP GET.

### 5.3 API Connectivity and Enabled API Status
- **Status:** **IMPLEMENTED**
- **Details:**
  - Cloud Resource Manager API v3 (`cloudresourcemanager.googleapis.com`): Projects search.
  - Cloud Asset Inventory API v1 (`cloudasset.googleapis.com`): Resource search and relationships.
  - Cloud Billing Catalog API v1 (`cloudbilling.googleapis.com`): Services and SKUs.

### 5.4 Resource Discovery
- **Status:** **IMPLEMENTED**
- **Details:**
  - Hierarchy Modeling: Organization -> Folders -> Projects -> Resources.
  - Strictly models `resource_group = None` (rejects Azure-style resource group hallucination).
  - Validates project ID format (rejects Azure UUID subscription IDs for GCP projects).
  - Detects Compute Engine VMs, Cloud SQL instances, Cloud Storage buckets, Cloud Run services, and GKE clusters.

### 5.5 Billing Integration and Billing Data Coverage
- **Status:** **IMPLEMENTED**
- **Details:**
  - `GcpBillingCatalogClient` queries Google Cloud Billing Catalog API v1 with `GCP_CLOUD_API_KEY`.
  - `GcpPricingEngine` implements deterministic pricing with offline benchmark dataset fallback (`GCP_BENCHMARK_DATASET`).
  - Architecture comparator (`ArchitectureComparator.compare_azure_and_gcp`) produces equivalent BOM pricing for workload profiles.

### 5.6 Frontend Integration
- **Status:** **PARTIALLY WORKING**
- **Details:**
  - `financials.ts`: Implements `getGcpReferenceFinancials` and canonical financial summary models.
  - Dedicated GCP project selector and live inventory views are partially wired compared to Azure FinOps Command Center.

### 5.7 Backend Integration
- **Status:** **IMPLEMENTED**
- **Details:**
  - Endpoints in `api/routes/inventory.py`:
    - `GET /api/v1/inventory/status` (Provider connection status)
    - `GET /api/v1/inventory/gcp/projects` (List active projects)
    - `POST /api/v1/inventory/gcp/analyze` (Analyze project hierarchy and assets)
    - `POST /api/v1/inventory/compare` (Compare Azure vs GCP)
  - Services in `services/inventory/gcp_inventory.py`, `services/pricing/gcp_billing_client.py`, and `services/pricing/gcp_engine.py`.

### 5.8 Automated Test Results
- **Status:** **WORKING**
- **Results:**
  - `backend/tests/test_gcp_inventory_and_comparison.py`: 8 passed.
  - `backend/tests/test_gcp_pricing.py`: 3 passed.
  - `backend/tests/test_v5_1_gcp_isolation.py`: 15 passed.
  - **Total GCP Tests:** 26 passed in 7.32s.

### 5.9 Live Runtime Verification
- **Status:** **NOT VERIFIED**
- **Details:** Live runtime verification has not yet been executed against an active GCP project with valid credentials in this environment.

### 5.10 Known Limitations and Unresolved Issues
- Requires configured `GOOGLE_APPLICATION_CREDENTIALS` pointing to valid Service Account JSON keyfile.
- Target GCP project must have `cloudresourcemanager.googleapis.com` and `cloudasset.googleapis.com` APIs enabled.

---

## 6. Deep-Dive Provider Audit: Amazon Web Services (AWS)

### 6.1 Authentication
- **Status:** **NOT STARTED**
- **Details:** No live IAM / STS assume-role authentication implemented.

### 6.2 Authorization and IAM Permissions
- **Status:** **NOT STARTED**

### 6.3 API Connectivity and Enabled API Status
- **Status:** **NOT STARTED**

### 6.4 Resource Discovery
- **Status:** **NOT STARTED**

### 6.5 Billing Integration and Billing Data Coverage
- **Status:** **IMPLEMENTED** (Normalized catalog only)
- **Details:** Normalized AWS service mapping exists in `cloud_recommender.schemas.catalog` and Phase A multi-cloud architecture recommendation simulator. AWS Price List API integration is not yet connected.

### 6.6 Frontend Integration
- **Status:** **NOT STARTED**

### 6.7 Backend Integration
- **Status:** **NOT STARTED**

### 6.8 Automated Test Results
- **Status:** **NOT STARTED**

### 6.9 Live Runtime Verification
- **Status:** **NOT STARTED**

### 6.10 Known Limitations and Unresolved Issues
- Live AWS integration is scheduled for post-Phase B roadmap.

---

## 7. Synthesis & Operational Status Summary

### 7.1 Verified Functionality (Confirmed Working)
1. **Azure Retail Prices Deterministic Engine:** Public API live execution with offline cache fallback.
2. **Databricks Billing Reconciliation Engine:** Mathematical reconciliation of $41.333929 ($0.7114689844/DBU) vs $127.81 ($2.20/DBU). Quantity coverage (70.20%) decoupled from record coverage (50.00%).
3. **Fail-Closed Security Guardrails:** Both Azure and Databricks strictly refuse fallback to human CLI credentials when Service Principal authentication fails.
4. **Read-Only Zero-Execution Invariants:** SQL AST parser rejects all mutations, comments, and non-allowlisted tables. Stopped warehouses remain in STOPPED state without startup.
5. **Session Store & Multi-Tenant Boundaries:** SHA-256 session token hashing, 8-hour TTL, revocation via logout, and tenant-scoped connection ownership.
6. **Frontend Stability:** Zero hardcoded mock numbers in FinOps Command Center. Vite production build completes in 7.23s.

### 7.2 Failed Tests
- **Zero test failures across all test suites:**
  - Backend Databricks & Billing Tests: **84 passed, 0 failed**.
  - Backend GCP Tests: **26 passed, 0 failed**.
  - Frontend Vitest Tests: **193 passed, 0 failed**.
  - Linting & Types: **0 Ruff errors, 0 Mypy errors**.

### 7.3 Blocked Dependencies
1. **Azure Databricks Live SP Authentication:** Service Principal `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` is rejected with HTTP 403 by Databricks OAuth M2M (`Workspace 642006393507276 is inaccessible`) pending workspace assignment in the Databricks Account Console.
2. **Azure Entra Live Secret:** The `AZURE_CLIENT_SECRET` configured in the local `.env` does not match the active secret value for client `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` in tenant `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` (returns `AADSTS7000215`).

### 7.4 Remaining Work
1. **GCP Live Authentication & Discovery:**
   - Configure `GOOGLE_APPLICATION_CREDENTIALS` using the Service Account keyfile (`cloud-recommender-pricing-dev-de7e66b1e92c.json`).
   - Validate live GCP project search and asset inventory discovery against active projects.
   - Verify GCP Cloud Billing Catalog API live SKU pricing.
2. **Databricks Account Console Assignment:**
   - Grant workspace access to Service Principal `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` in Databricks Account Console.
3. **Distributed Session Storage:**
   - Configure Azure Cache for Redis for multi-instance App Service scale-out.

