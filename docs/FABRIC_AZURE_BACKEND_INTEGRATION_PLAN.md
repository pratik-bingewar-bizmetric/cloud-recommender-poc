# Microsoft Fabric Frontend to Azure FastAPI Backend Integration Plan

> **Document Status:** Architectural Assessment & Integration Specification (Investigation Only)  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/backend-security-hardening`  
> **Target Azure App Service:** `FinopsBackendApp`  
> **Backend Hostname:** `https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net`  
> **Fabric App Origin:** `https://app.fabric.microsoft.com` / `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`  
> **Fabric Item ID:** `31c70ef5-3a22-4bb8-aab5-3e2f0850b087`  
> **Fabric Workspace ID:** `672a6995-4190-4000-befd-5cc6479c3f74`  
> **Tenant ID:** `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`  

---

## 1. Executive Summary & Architectural Overview

### 1.1 Objective & Target State
The objective is to establish secure, end-to-end communication between the **Microsoft Fabric React Frontend** (hosted statically within Microsoft Fabric Custom Apps) and the **Centralized FastAPI Backend** hosted on Azure App Service (`FinopsBackendApp`).

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Microsoft Fabric Custom App (Browser)                │
│                                                                        │
│   Origin: https://app.fabric.microsoft.com (Iframe Host)               │
│   Hosted Webapp: true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net │
│   Implementation: fabric-integration/finops-app/packages/frontend      │
│   Stack: React 19, Vite 8, Tailwind 4, MSAL Browser                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    │ HTTPS + Bearer JWT (Backend API Scope)
                                    │ CORS Preflight: OPTIONS
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               Azure App Service (Linux / Python 3.12)                  │
│                                                                        │
│   Hostname: finopsbackendapp-f3a0dya4cpederg0.centralindia-01...       │
│   App Service: FinopsBackendApp                                        │
│   Framework: FastAPI (ASGI Uvicorn)                                    │
│   Validation: Cryptographic RS256 JWKS verification via Entra ID       │
│   Authorization: Client ID check, Scope enforcement, Role verification  │
└───────────────────┬───────────────────────────────┬────────────────────┘
                    │                               │
         Database-Dependent              Database-Independent
         (Connections, Config)           (Pricing, Recommendations,
                    │                     Telemetry, Analysis, Databricks)
                    ▼                               │
        ┌───────────────────────┐                   ▼
        │ PostgreSQL (Pending)  │       ┌───────────────────────┐
        │ Managed Flex Server   │       │ Azure Management SDK  │
        │ Ingestion / Audit     │       │ Azure Monitor SDK     │
        └───────────────────────┘       │ Databricks REST API   │
                                        │ Retail Prices API     │
                                        └───────────────────────┘
```

### 1.2 Current Architectural State & Key Findings
1. **Frontend Identification:**
   - **Fabric App Frontend:** Located at `fabric-integration/finops-app/packages/frontend`. This is a dedicated React 19 + Vite 8 Single-Page Application (SPA) designed for Fabric Custom Apps static hosting.
   - **Next.js Frontend:** Located at `frontend/`. This is a Next.js 14 App Router application with server-side rewrites requiring a Node.js server (e.g., Databricks Apps or container).
2. **Fabric UDF Routing Defect in Production Build:**
   - In `fabric-integration/finops-app/packages/frontend/src/lib/api.ts`, several key methods branch to call `fabric-udf-client.ts` when `VITE_USE_FABRIC_UDF === "true"`.
   - In `.env.production`, `VITE_USE_FABRIC_UDF=true` is set, while `VITE_API_BASE_URL` is omitted.
   - When `VITE_API_BASE_URL` is not provided, `getApiBaseUrl()` defaults to the Fabric User Data Function (UDF) base URL (`https://api.fabric.microsoft.com/v1/workspaces/.../userDataFunctions/...`).
   - Consequently, requests for the 15 FinOps modules, Databricks workspaces, architecture recommendations, and cloud configurations attempt to call endpoints on the Fabric UDF RPC that **do not exist**, failing silently or producing 404/400 errors.
   - Furthermore, `checkBackendHealth()` returns a hardcoded `{ status: "healthy" }` when `VITE_USE_FABRIC_UDF === "true"`, completely bypassing the real backend health probe.
3. **Database Decoupling:**
   - PostgreSQL is not yet provisioned. The backend is already architected to fail gracefully:
     - Root `/health` probe returns HTTP 200 without database connectivity.
     - Pure computational endpoints (Analysis, Architecture, Pricing, Azure Live SP Session, Databricks connection test) operate without PostgreSQL.
     - Database-dependent routes return a structured HTTP 503 `DATABASE_UNAVAILABLE` rather than crashing.

---

## 2. Frontend-to-Backend API Mapping

The following matrix maps every major frontend feature in `fabric-integration/finops-app/packages/frontend` to the corresponding FastAPI backend endpoint, detailing HTTP method, schema, auth requirements, and current behavior.

| Feature Area | Frontend Function (`src/lib/api.ts`) | Backend Endpoint | Method | Backend Auth Dependency | Current Data Source / Bug |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Health Check** | `checkBackendHealth()` | `/health` | `GET` | Public (No Auth) | **Defect:** Returns mock `{ status: "healthy" }` if `VITE_USE_FABRIC_UDF=true`. |
| **Requirements Analysis** | `analyzeRequirements()` | `/api/v1/analysis/requirements` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}` (broken if pointed to UDF). |
| **Architecture Generation** | `generateArchitecture()` | `/api/v1/architecture/generate` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}` (broken if pointed to UDF). |
| **Cost Pricing Simulation** | `simulatePricing()` | `/api/v1/pricing/simulate` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}`. Pure calculation engine. |
| **Cloud Provider Status** | `getProvidersStatus()` | `/api/v1/inventory/providers/status` | `GET` | `enforce_route_policy` (Safe GET) | **Defect:** Diverted to `udfListConnections()` when `VITE_USE_FABRIC_UDF=true`. |
| **Azure Subscriptions** | `listAzureSubscriptions()` | `/api/v1/inventory/azure/subscriptions` | `GET` | `enforce_route_policy` (Safe GET) | **Defect:** Diverted to `udfListConnections("azure")` when `VITE_USE_FABRIC_UDF=true`. |
| **Azure Scope Analysis** | `analyzeAzureSubscription()` | `/api/v1/inventory/azure/analyze` | `POST` | `enforce_route_policy` (Class U) | **Defect:** Synthesizes fake object combining `udfGetInventory` & `udfGetCostWaste` if `VITE_USE_FABRIC_UDF=true`. |
| **GCP Projects** | `listGcpProjects()` | `/api/v1/inventory/gcp/projects` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **GCP Project Analysis** | `analyzeGcpProject()` | `/api/v1/inventory/gcp/analyze` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}`. |
| **Multi-Cloud Comparison** | `compareMultiCloud()` | `/api/v1/inventory/compare` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}`. |
| **Centralized Monitoring** | `getMonitoringOverview()` | `/api/v1/monitoring/overview` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}`. |
| **Resource Monitoring Detail** | `getResourceMonitoringDetail()` | `/api/v1/monitoring/resources/detail` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}`. |
| **Monitoring Logs Search** | `searchMonitoringLogs()` | `/api/v1/monitoring/logs/search` | `POST` | `enforce_route_policy` (Class U) | Calls `${API_BASE_URL}`. |
| **Monitoring Sources** | `getMonitoringSources()` | `/api/v1/monitoring/sources` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Token Economics** | `getTokenEconomics()` | `/api/v1/monitoring/token-economics` | `POST` | `enforce_route_policy` (Class U) | **Defect:** Diverted to `udfGetTokenEconomics` when `VITE_USE_FABRIC_UDF=true`. |
| **List Cloud Connections** | `listConnections()` | `/api/v1/connections` | `GET` | `enforce_route_policy` (Safe GET) | **Defect:** Diverted to `udfListConnections()` when `VITE_USE_FABRIC_UDF=true`. Needs DB. |
| **Validate Connection** | `validateConnection()` | `/api/v1/connections/validate` | `POST` | `enforce_route_policy` (Class U) | **Defect:** Diverted to `udfValidateConnection()` when `VITE_USE_FABRIC_UDF=true`. |
| **Create Connection** | `createConnection()` | `/api/v1/connections` | `POST` | `enforce_route_policy` (Class U) | **Defect:** Diverted to `udfCreateConnection()` when `VITE_USE_FABRIC_UDF=true`. Needs DB. |
| **Delete Connection** | `deleteConnection()` | `/api/v1/connections/{id}` | `DELETE` | `enforce_route_policy` (Class U) | **Defect:** Diverted to `udfDeleteConnection()` when `VITE_USE_FABRIC_UDF=true`. Needs DB. |
| **Live Azure SP Connect** | `connectAzureLive()` | `/api/v1/azure/connect` | `POST` | `enforce_route_policy` (Class U) | In-memory owner session. Works without PostgreSQL. |
| **Live Azure SP Validate** | `validateAzureLive()` | `/api/v1/azure/validate` | `POST` | `enforce_route_policy` (Class U) | Validates live ARM token against Azure. |
| **Live Azure Subscriptions**| `getAzureLiveSubscriptions()`| `/api/v1/azure/{id}/subscriptions` | `GET` | `enforce_route_policy` (Safe GET) | Queries ARM live subscriptions. |
| **FinOps Overview** | `getFinOpsOverview()` | `/api/v1/finops/overview` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Cost Explorer** | `getFinOpsCostExplorer()` | `/api/v1/finops/cost-explorer` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Cost Allocation** | `getFinOpsCostAllocation()` | `/api/v1/finops/cost-allocation` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Compute Warehouses** | `getFinOpsComputeWarehouses()` | `/api/v1/finops/compute-warehouses` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **AI Economics** | `getFinOpsAiEconomics()` | `/api/v1/finops/ai-economics` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Data Storage** | `getFinOpsDataStorage()` | `/api/v1/finops/data-storage` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Network & Cloud** | `getFinOpsNetworkCloud()` | `/api/v1/finops/network-cloud` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Optimization Advisor** | `getFinOpsOptimizationAdvisor()`| `/api/v1/finops/optimization-advisor`| `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Record Decision Action** | `recordFinOpsRecommendationAction()`| `/api/v1/finops/optimization-advisor/{id}/action`| `POST` | `enforce_route_policy` (Class U) | Attributed audit action. |
| **Forecast & Budgets** | `getFinOpsForecastBudgets()` | `/api/v1/finops/forecast-budgets` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Simulate Scenario** | `simulateFinOpsScenario()` | `/api/v1/finops/forecast-budgets/simulate` | `POST` | `enforce_route_policy` (Class U) | Pure computation. |
| **Anomaly Detection** | `getFinOpsAnomalyDetection()` | `/api/v1/finops/anomaly-detection` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Governance Policies** | `getFinOpsGovernancePolicies()` | `/api/v1/finops/governance-policies`| `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Showback / Chargeback** | `getFinOpsShowbackChargeback()` | `/api/v1/finops/showback-chargeback`| `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Workload Economics** | `getFinOpsWorkloadEconomics()` | `/api/v1/finops/workload-economics`| `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Reports & Audit** | `getFinOpsReportsAudit()` | `/api/v1/finops/reports-audit` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Settings & Integrations** | `getFinOpsSettingsIntegrations()`| `/api/v1/finops/settings-integrations`| `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Databricks Connections** | `listDatabricksConnections()` | `/api/v1/databricks/connections` | `GET` | `enforce_route_policy` (Safe GET) | Calls `${API_BASE_URL}`. |
| **Test Databricks Conn** | `testDatabricksConnection()` | `/api/v1/databricks/test-connection` | `POST` | `enforce_route_policy` (Class U) | Tests workspace URL / PAT / OAuth. |
| **Databricks Discovery** | `getWorkspaceDiscovery()` | `/api/v1/databricks/discovery/{id}` | `GET` | `enforce_route_policy` (Safe GET) | Returns clusters, warehouses, jobs. |
| **Refresh Discovery** | `refreshWorkspaceDiscovery()` | `/api/v1/databricks/refresh-discovery/{id}` | `POST` | `enforce_route_policy` (Class U) | Triggers active discovery sync. |
| **Databricks Health** | `getWorkspaceHealth()` | `/api/v1/databricks/health/{id}` | `GET` | `enforce_route_policy` (Safe GET) | Evaluates workspace reachability. |
| **Configuration Scopes** | `discoverScopes()` | `/api/v1/configuration/scopes` | `GET` | `enforce_route_policy` (Safe GET) | Multi-cloud scope hierarchy. |
| **Get Configuration** | `getConfiguration()` | `/api/v1/configuration` | `GET` | `enforce_route_policy` (Safe GET) | Selected scopes & workspaces. |
| **Save Configuration** | `saveConfiguration()` | `/api/v1/configuration` | `POST` | `enforce_route_policy` (Class R / Admin)| Requires `FinOpsAdmin` role. |
| **Ingestion Readiness** | `checkIngestionReadiness()` | `/api/v1/ingestion/readiness` | `GET` | `enforce_route_policy` (Safe GET) | Verifies ingestion pre-requisites. |
| **Trigger Ingestion** | `triggerIngestionRun()` | `/api/v1/ingestion/runs` | `POST` | `enforce_route_policy` (Class R / Admin)| Requires `FinOpsAdmin` role. |

---

## 3. Authentication Compatibility Findings

### 3.1 Token Disambiguation (The 3 Token Types)
A critical insight discovered during repository inspection is that **three completely distinct token types** exist across the platform. They are **not interchangeable**:

```
                               ┌──────────────────────────────────────────────────────────┐
                               │           Microsoft Entra ID / IdP Authority             │
                               └────────────┬─────────────────────────────┬───────────────┘
                                            │                             │
                     Audience: api://<backend-app-id>       Audience: https://analysis.windows.net/powerbi/api
                     Scope: access_as_user                  Scope: user_impersonation
                                            │                             │
                                            ▼                             ▼
                              ┌───────────────────────────┐ ┌───────────────────────────┐
                              │ Backend API Bearer Token  │ │  Fabric UDF Bearer Token  │
                              │ (FastAPI Authentication)  │ │ (Power BI REST / Execute) │
                              └─────────────┬─────────────┘ └─────────────┬─────────────┘
                                            │                             │
                                            ▼                             ▼
                              FastAPI Backend (/api/v1/*)    Fabric Python UDF RPC
                              ✅ HTTP 200 OK                 ✅ HTTP 200 OK
                              ❌ Sent to UDF -> HTTP 401     ❌ Sent to FastAPI -> HTTP 401
                                                              (INVALID_AUDIENCE)
```

1. **Rayfin Session Token:**
   - Generated by the local Rayfin mock/dev server or stored in localStorage `authSession`.
   - **Nature:** Internal application session key (`pk-...`).
   - **Backend Compatibility:** **COMPLETELY INCOMPATIBLE**. Has no RS256 signature, no Entra issuer, and no JWT structure. FastAPI rejects it immediately with HTTP 401 (`MALFORMED_TOKEN` or `INVALID_SIGNATURE`).
2. **Fabric / Power BI Delegated Entra Token:**
   - Acquired via MSAL with scope `https://analysis.windows.net/powerbi/api/user_impersonation` or `UserDataFunction.Execute.All`.
   - **Audience (`aud`):** `https://analysis.windows.net/powerbi/api`.
   - **Backend Compatibility:** **INCOMPATIBLE WITH FASTAPI BACKEND**.
   - If sent to the FastAPI backend, PyJWT fails at line 270 of `backend/.../core/auth.py` with:
     ```
     HTTP 401 UNAUTHORIZED: {"error_code": "INVALID_AUDIENCE", "message": "Token audience does not match configured backend audience"}
     ```
   - **Use Case:** Strictly reserved for calling Microsoft Fabric's own REST API:
     `https://api.fabric.microsoft.com/v1/workspaces/{wId}/userDataFunctions/{uId}/functions/{fName}/invoke`.
3. **Custom FinOps Backend Entra Token:**
   - Acquired via MSAL with delegated scope: `api://<backend-app-id>/access_as_user`.
   - **Audience (`aud`):** Matches `ENTRA_AUDIENCE` (`api://<backend-app-id>` or `<backend-app-id>`).
   - **Authorized Client (`azp`):** Matches the Fabric SPA's Application (client) ID registered in `ENTRA_ALLOWED_CLIENT_IDS`.
   - **Tenant (`tid`):** Matches `ENTRA_TENANT_ID`.
   - **Scopes (`scp`):** Contains `access_as_user` (matching `ENTRA_REQUIRED_SCOPES`).
   - **Backend Compatibility:** **100% REQUIRED FOR FASTAPI**.

### 3.2 Backend Validation Rules (`backend/src/cloud_recommender/core/auth.py`)
When `ENTRA_AUTH_ENABLED=true`:
1. **Issuer Verification:** Must be `https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0` or `https://sts.windows.net/{ENTRA_TENANT_ID}/`.
2. **Key Resolution:** Dynamically fetches signing keys from `https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys`.
3. **Audience Check:** Exactly matches `ENTRA_AUDIENCE`.
4. **Tenant Isolation:** Rejects tokens from any other directory (`tid != ENTRA_TENANT_ID`).
5. **Client Application Approval:** `user.client_id` (`azp` in v2 tokens, `appid` in v1 tokens) must match one of `ENTRA_ALLOWED_CLIENT_IDS`.
6. **Scope Enforcement:** User tokens must carry the scope `access_as_user`.
7. **Role Enforcement:** Endpoints in `USER_NON_GET_ENDPOINTS` and all `GET` routes are open to users. Mutation/Configuration routes (e.g. `saveConfiguration`, `triggerIngestionRun`) strictly require the `FinOpsAdmin` role in `user.roles`.

---

## 4. Required Microsoft Entra ID App Registrations

To establish secure, standards-compliant authentication without secrets in the browser, **two App Registrations** must exist in the tenant `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`.

### App Registration 1: FinOps Backend API
- **Display Name:** `FinOps-Backend-API`
- **Application (client) ID:** `<BACKEND_CLIENT_ID>` (GUID)
- **Supported account types:** Accounts in this organizational directory only (Single tenant).
- **Application ID URI:** `api://<BACKEND_CLIENT_ID>` (or `api://finops-backend-api`)
- **Expose an API:**
  - **Scope Name:** `access_as_user`
  - **Who can consent:** Admins and users
  - **Admin consent display name:** `Access FinOps Backend API as user`
  - **Admin consent description:** `Allows the FinOps React frontend to access backend services on behalf of the signed-in user.`
- **App Roles:**
  - **Role 1:**
    - Display Name: `FinOps Admin`
    - Allowed member types: `Users/Groups`
    - Value: `FinOpsAdmin`
    - Description: `Full administrative access to restricted FinOps mutation and configuration endpoints.`
  - **Role 2:**
    - Display Name: `FinOps Daemon`
    - Allowed member types: `Applications`
    - Value: `FinOpsDaemon`
    - Description: `Application-only access to read-only status endpoints for background daemons.`
- **Authorized Client Applications:**
  - Add `<FRONTEND_SPA_CLIENT_ID>` with authorized scope: `api://<BACKEND_CLIENT_ID>/access_as_user`.

### App Registration 2: FinOps Frontend SPA (Fabric Custom App)
- **Display Name:** `FinOps-Fabric-Frontend`
- **Application (client) ID:** `<FRONTEND_SPA_CLIENT_ID>` (GUID)
- **Supported account types:** Accounts in this organizational directory only (Single tenant).
- **Authentication (Platform Configurations):**
  - **Add Platform:** Single-page application (SPA)
  - **Redirect URIs:**
    - `https://app.fabric.microsoft.com/redirect.html`
    - `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net/redirect.html`
    - `http://localhost:5174/redirect.html` (Local development)
  - **Implicit grant and hybrid flows:** Leave both unchecked (MSAL Browser uses Auth Code Flow with PKCE).
- **API Permissions:**
  - **Backend API:** Delegated permission `api://<BACKEND_CLIENT_ID>/access_as_user` (Admin consent granted).
  - **Power BI Service (Optional for UDFs):** Delegated permission `UserDataFunction.Execute.All` or `Item.Execute.All`.
  - **Microsoft Graph:** Delegated permission `User.Read`.

---

## 5. Environment Variable Configuration

### 5.1 Frontend Build Environment Variables (`packages/frontend/.env.production`)

```ini
# Central FastAPI Backend URL (Azure App Service)
VITE_API_BASE_URL=https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1

# Microsoft Entra ID - Frontend SPA Client ID
VITE_ENTRA_CLIENT_ID=<FRONTEND_SPA_CLIENT_ID>

# Microsoft Entra ID - Tenant ID
VITE_ENTRA_TENANT_ID=fe82a67c-faa7-4d9a-bbfa-7d25b7047b41

# Microsoft Entra ID - Backend API Scope
VITE_ENTRA_API_SCOPE=api://<BACKEND_CLIENT_ID>/access_as_user

# Disable generic UDF interception for standard API calls
VITE_USE_FABRIC_UDF=false

# Fabric Metadata (Preserved for Lakehouse / Fabric-specific features)
VITE_FABRIC_TENANT_ID=fe82a67c-faa7-4d9a-bbfa-7d25b7047b41
VITE_FABRIC_WORKSPACE_ID=672a6995-4190-4000-befd-5cc6479c3f74
VITE_FABRIC_UDF_ID=8c5bbc01-c941-4f0e-90d3-7053921c32f8
VITE_FABRIC_PORTAL_URL=https://app.fabric.microsoft.com
```

### 5.2 Backend App Service Environment Configuration (`FinopsBackendApp`)

Configure the following settings in Azure Portal → App Service `FinopsBackendApp` → Configuration / Environment Variables:

```ini
# Runtime Environment
APP_ENV=production
DEBUG=false
APP_NAME=Cloud Recommender API

# Microsoft Entra ID Cryptographic Verification
ENTRA_AUTH_ENABLED=true
ENTRA_TENANT_ID=fe82a67c-faa7-4d9a-bbfa-7d25b7047b41
ENTRA_AUDIENCE=api://<BACKEND_CLIENT_ID>
ENTRA_REQUIRED_SCOPES=access_as_user
ENTRA_ALLOWED_CLIENT_IDS=<FRONTEND_SPA_CLIENT_ID>

# CORS Origin Allowlist (Must be explicit https:// origins; no wildcards)
CORS_ORIGINS=https://app.fabric.microsoft.com,https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net

# Application Security Secrets (>= 32 chars non-default)
SECRET_KEY=<SECURE_GENERATED_32_CHAR_SECRET>
FINOPS_SIGNING_SECRET=<SECURE_GENERATED_32_CHAR_SECRET>

# Cloud Integrations & Storage (Safe fallback until PostgreSQL is provisioned)
LLM_PROVIDER=mock
OFFLINE_PRICING_MODE=true
CONNECTION_STORE=database
CONNECTION_KEY_PROVIDER=env
ALLOW_CLI_CONNECTIONS=false
```

---

## 6. CORS and Security Audit

### 6.1 Current Backend CORS Implementation
In [backend/src/cloud_recommender/main.py](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/main.py#L90-L99):
```python
is_production = settings.app_env == "production"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"] if is_production else ["*"],
    allow_headers=["Authorization", "Content-Type", "Accept"] if is_production else ["*"],
)
```

### 6.2 Critical CORS Findings & Recommendations
1. **Allowed Methods Limitation:**
   - In production, `allow_methods` is restricted to `["GET", "POST", "OPTIONS"]`.
   - However, the API provides:
     - `DELETE /api/v1/connections/{connection_id}`
     - `PATCH /api/v1/connections/{connection_id}`
     - `DELETE /api/v1/azure/{connection_id}`
   - **Issue:** A browser executing `DELETE` or `PATCH` triggers an `OPTIONS` preflight checking `Access-Control-Request-Method: DELETE`. With current production settings, the preflight fails with HTTP 400/405.
   - **Recommendation (When modifying code):** Expand production `allow_methods` to include `"DELETE"` and `"PATCH"`:
     ```python
     allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"] if is_production else ["*"]
     ```
2. **Allowed Headers:**
   - `"Authorization"`, `"Content-Type"`, and `"Accept"` are permitted, which accommodates MSAL Bearer token headers and JSON payloads.
3. **Allowed Origins:**
   - Backend `validate_for_serving` strictly verifies:
     - No wildcard `*`.
     - No localhost.
     - Must start with `https://`.
   - Settings parsing (`split_entra_lists` and `validate_cors_origins`) handles both JSON arrays (`["https://..."]`) and comma-separated strings (`https://...,https://...`).
4. **Fabric Iframe Considerations:**
   - When the React application is embedded in the Fabric Portal (`https://app.fabric.microsoft.com`), the browser sets the `Origin` header to `https://app.fabric.microsoft.com` (or the direct hosting webapp domain).
   - Both origins **must** be present in `CORS_ORIGINS`.

---

## 7. Database and Service Availability Handling

### 7.1 Current System Resilience Without PostgreSQL
1. **Liveness Probe (`/health`):**
   - Returns HTTP 200 immediately. No database queries are performed.
2. **Readiness Probe (`/health/ready`):**
   - Evaluates PostgreSQL connectivity via `check_db_health()`.
   - Returns HTTP 503 `status: "not_ready"` when PostgreSQL is not reachable, explicitly reporting:
     ```json
     {
       "status": "not_ready",
       "dependencies": {
         "database": {
           "status": "disconnected",
           "error": "database_unreachable"
         }
       }
     }
     ```
3. **Database-Dependent Endpoints:**
   - Protected by global exception handlers catching `SQLAlchemyError` and `ConnectionError`.
   - Returns HTTP 503:
     ```json
     {
       "error": {
         "code": 503,
         "message": {
           "error_code": "DATABASE_UNAVAILABLE",
           "message": "The application database is unavailable or not initialised (an administrator must apply the pending database migrations). Nothing was saved."
         },
         "type": "database_unavailable"
       }
     }
     ```
4. **Database-Independent Operations (Fully Functional):**
   - Requirements extraction & analysis (`/api/v1/analysis/requirements`).
   - Multi-cloud architecture generation (`/api/v1/architecture/generate`).
   - Cost simulation & SKU pricing (`/api/v1/pricing/simulate`).
   - Live Azure Service Principal session demo (`/api/v1/azure/*`).
   - Centralized monitoring & token simulation (`/api/v1/monitoring/*`).
   - Databricks workspace connection testing (`/api/v1/databricks/test-connection`).

### 7.2 Frontend UX Requirements for Service Availability
1. The frontend must parse HTTP 503 responses with `error_code: "DATABASE_UNAVAILABLE"` and display an informative non-blocking status banner:
   > *"Persistent cloud connection storage is temporarily unavailable awaiting database initialization. Live session testing and architecture simulation remain fully available."*
2. Zero synthetic mock data should be injected when the database is unavailable.

---

## 8. Proposed Files to Modify (Post-Investigation Implementation Scope)

When approval is granted to proceed with implementation, the following targeted edits are planned:

### 1. `fabric-integration/finops-app/packages/frontend/src/lib/api.ts`
- **Decouple UDF branching:** Ensure that general platform endpoints (`getProvidersStatus`, `listAzureSubscriptions`, `analyzeAzureSubscription`, `listConnections`, `validateConnection`, `createConnection`, `deleteConnection`, `getTokenEconomics`) call `${API_BASE_URL}` rather than diverting to `fabric-udf-client.ts`.
- **Preserve Fabric UDF Client:** Keep `fabric-udf-client.ts` strictly for Fabric Lakehouse queries and specialized Fabric UDF RPC functions.
- **Real Health Check:** Update `checkBackendHealth()` to always probe the real backend `/health` endpoint instead of returning `{ status: "healthy" }` when `VITE_USE_FABRIC_UDF === "true"`.
- **Standardized Error Handling:** Enhance `handleResponse` to surface clear UI messages for HTTP 401 (Sign-in required), HTTP 403 (Role `FinOpsAdmin` required), and HTTP 503 (`DATABASE_UNAVAILABLE`).

### 2. `fabric-integration/finops-app/packages/frontend/.env.production`
- Add `VITE_API_BASE_URL=https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1`.
- Set `VITE_USE_FABRIC_UDF=false`.
- Configure `VITE_ENTRA_CLIENT_ID`, `VITE_ENTRA_TENANT_ID`, and `VITE_ENTRA_API_SCOPE`.

### 3. `backend/src/cloud_recommender/main.py`
- Update CORS middleware `allow_methods` to include `"PATCH"` and `"DELETE"` in production.

---

## 9. Comprehensive Integration Testing Plan

### Phase 1: Network & Probe Verification
1. **Backend Liveness:**
   - Execute: `GET https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/health`
   - Expected: HTTP 200 `{ "status": "ok", "service": "Cloud Recommender API", "version": "0.1.0" }`.
2. **Backend Readiness (PostgreSQL Unprovisioned):**
   - Execute: `GET https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/health/ready`
   - Expected: HTTP 503 `{ "status": "not_ready", "dependencies": { "database": { "status": "disconnected" } } }`.
3. **CORS Preflight Simulation:**
   - Execute:
     ```bash
     curl -I -X OPTIONS https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1/finops/overview \
       -H "Origin: https://app.fabric.microsoft.com" \
       -H "Access-Control-Request-Method: GET" \
       -H "Access-Control-Request-Headers: Authorization,Content-Type"
     ```
   - Expected: HTTP 200 with headers:
     - `Access-Control-Allow-Origin: https://app.fabric.microsoft.com`
     - `Access-Control-Allow-Credentials: true`
     - `Access-Control-Allow-Headers: Authorization, Content-Type, Accept`

### Phase 2: Security & Authentication Gate Verification
1. **Unauthenticated Access:**
   - Request: `GET /api/v1/finops/overview` without `Authorization` header.
   - Expected: HTTP 401 `{ "error": { "code": 401, "message": "Authorization header with a valid Bearer token is required..." } }`.
2. **Malformed Token:**
   - Request: `GET /api/v1/finops/overview` with `Authorization: Bearer invalid.token.payload`.
   - Expected: HTTP 401 `MALFORMED_TOKEN` or `INVALID_SIGNATURE`.
3. **Mismatched Audience (Fabric UDF Token):**
   - Request: `GET /api/v1/finops/overview` with token issued for audience `https://analysis.windows.net/powerbi/api`.
   - Expected: HTTP 401 `INVALID_AUDIENCE`.
4. **Unapproved Client ID:**
   - Request: `GET /api/v1/finops/overview` with valid token issued for an unlisted client ID.
   - Expected: HTTP 403 `UNAPPROVED_CLIENT_APPLICATION`.
5. **Role Check (Standard User on Restricted Route):**
   - Request: `POST /api/v1/configuration` with valid user token lacking `FinOpsAdmin`.
   - Expected: HTTP 403 `INSUFFICIENT_PERMISSIONS`.

### Phase 3: End-to-End Functional Flows
1. **Architecture & Pricing Flow (Database-Independent):**
   - User inputs application requirements → Frontend calls `/api/v1/analysis/requirements` → Displays profile.
   - User clicks Generate Architecture → Frontend calls `/api/v1/architecture/generate` → Displays multi-cloud topologies.
   - User requests cost estimation → Frontend calls `/api/v1/pricing/simulate` → Displays deterministic BOM.
2. **Live Azure Service Principal Flow:**
   - User supplies Azure credentials in `AzureLiveView` → Frontend calls `/api/v1/azure/connect` → In-memory session initialized.
   - Frontend calls `/api/v1/azure/{id}/subscriptions` → Displays real subscription inventory.
3. **Database Unavailable Flow:**
   - User attempts to persist connection in `ConnectCloudView` → Backend returns HTTP 503 `DATABASE_UNAVAILABLE`.
   - Frontend displays actionable error modal informing the user that PostgreSQL is awaiting migration.

---

## 10. Deployment Sequence & Execution Runbook

```
Step 1: Entra ID Configuration
  ├── Register Backend API & Expose Scope (access_as_user)
  ├── Define App Roles (FinOpsAdmin, FinOpsDaemon)
  ├── Register Frontend SPA & Authorize Delegated Scope
  └── Assign FinOpsAdmin role to target test user

Step 2: Azure App Service Configuration (FinopsBackendApp)
  ├── Set ENTRA_AUTH_ENABLED=true
  ├── Set ENTRA_TENANT_ID, ENTRA_AUDIENCE, ENTRA_ALLOWED_CLIENT_IDS
  ├── Set CORS_ORIGINS=https://app.fabric.microsoft.com,https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net
  └── Set SECRET_KEY, FINOPS_SIGNING_SECRET

Step 3: Frontend Build & Configuration
  ├── Configure packages/frontend/.env.production with VITE_API_BASE_URL and ENTRA settings
  ├── Set VITE_USE_FABRIC_UDF=false
  ├── Build frontend bundle: npm --prefix fabric-integration/finops-app/packages/frontend run build
  └── Package / deploy to Fabric Custom App

Step 4: End-to-End Verification
  ├── Test /health and CORS preflight
  ├── Verify interactive MSAL popup sign-in
  ├── Validate authenticated data fetching across FinOps modules
  └── Verify graceful HTTP 503 banner for database-dependent features
```

---

## 11. Remaining Blockers & Prerequisite Approvals

1. **Entra App Registrations:** Requires tenant administrator access in tenant `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` to register or verify the two applications and grant admin consent for `access_as_user`.
2. **Azure App Service Configuration:** Setting `ENTRA_AUTH_ENABLED=true`, `CORS_ORIGINS`, and secret variables in App Service `FinopsBackendApp` application settings.
3. **PostgreSQL Flexible Server:** Database provisioning remains pending; until provisioned, connection persistence and historical audit records will return HTTP 503 (advisory and analytical features operate unaffected).
4. **Approval to Modify Code:** Explicit user approval is required before making the minimal changes to `fabric-integration/finops-app/packages/frontend/src/lib/api.ts` and `backend/src/cloud_recommender/main.py`.

