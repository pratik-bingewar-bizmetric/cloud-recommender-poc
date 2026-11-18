# Phase 2 Verification & Test Report: Microsoft Entra ID Login & Azure Service Principal Integration

> **Repository:** `cloud-recommender-poc`  
> **Working Branch:** `feature/backend-security-hardening`  
> **Target Deployed Backend:** `https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net` (`FinopsBackendApp`)  
> **API Base URL:** `https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1`  
> **Frontend:** `fabric-integration/finops-app/packages/frontend` (React 19, Vite 8, MSAL Browser v5)  
> **Status:** Local Verification Complete | Live Cloud Calls Blocked on Missing Credentials  
> **Date:** November 17, 2026

---

## 1. Executive Summary & Verification Classification

This report validates the implementation, architecture, and security properties of the two separate authentication mechanisms within the FinOps application:
1. **Application User Login (Microsoft Entra ID)**: Interactive user authentication via MSAL Browser with PKCE, backend API delegated token acquisition (`api://<backend-app-id>/access_as_user`), RS256 cryptographic JWT validation, and RBAC (`FinOpsAdmin`).
2. **Azure Subscription Connectivity (Service Principal)**: Client credentials flow requesting token scope `https://management.azure.com/.default` used strictly for ARM resource inventory, Cost Management, and Azure Monitor metrics.

### Status Classification Overview

Every tested capability is strictly classified according to the milestone rules:
- **PASS**: Verified against automated test suites and local/deployed environments.
- **FAIL**: Actual test failure (0 tests failed).
- **BLOCKED**: Blocked due to missing customer Azure credentials, Entra App Registration IDs, or Azure platform settings.
- **NOT TESTED**: Intentionally not executed (e.g. write/deployment actions barred by security guardrails).

| Capability / Test Area | Classification | Notes & Evidence |
| :--- | :---: | :--- |
| **Deployed Backend Health (`GET /health`)** | **PASS** | Returns HTTP 200 `{"status":"ok","environment":"production"}` via Uvicorn on Linux App Service. |
| **Deployed Versioned Health (`GET /api/v1/health`)** | **PASS** | Returns HTTP 200 `{"status":"ok"}`. |
| **Deployed Reference Connections (`GET /api/v1/connections`)** | **PASS** | Returns HTTP 200 with reference simulation fixtures. |
| **Deployed Azure Live Routes (`POST /api/v1/azure/connections`)** | **BLOCKED** | HTTP 404 on deployed instance; deployed ZIP contains older build (25 routes vs 52+ local routes). |
| **Fabric Origin Preflight on App Service** | **BLOCKED** | App Service Platform CORS returns HTTP 400 `Disallowed CORS origin` (Azure Portal App Service CORS needs Fabric origins). |
| **Frontend MSAL Token Service Architecture** | **PASS** | `createEntraTokenService()` handles popup/silent PKCE flows, memory storage, and separation from Fabric UDF tokens. |
| **Frontend API Client Token Forwarding** | **PASS** | `api.ts` attaches `Authorization: Bearer <token>` from MSAL silent cache; tested in Vitest. |
| **Frontend Azure Connection Form Security** | **PASS** | Client Secret masked, cleared upon submit, never written to `localStorage` or `sessionStorage`. |
| **Backend Cryptographic JWT Validation** | **PASS** | RS256 validation, signature, expiry, audience, issuer, tenant, scopes, and roles verified in `test_entra_auth.py`. |
| **Backend Route Authorization & RBAC** | **PASS** | Enforced across all routes via `enforce_route_policy`; `FinOpsAdmin` required for restricted endpoints. |
| **Service Principal Client Credentials Flow** | **PASS** | `acquire_service_principal_token` requests `https://management.azure.com/.default`; verified in `test_azure_live_connection.py`. |
| **Connection Ownership & Isolation** | **PASS** | Users cannot read, validate, or delete another user's connection (HTTP 404 enforced). |
| **Unprovisioned Database Fail-Closed Policy** | **PASS** | PostgreSQL unavailability returns HTTP 503 `DATABASE_UNAVAILABLE` with guidance, never fake persistence. |
| **Live Azure Real Data Ingestion** | **BLOCKED** | Blocked awaiting real customer Azure Tenant ID, Client ID, Client Secret, and Subscription ID. |
| **Live Entra ID Interactive User Sign-In** | **BLOCKED** | Blocked awaiting Entra App Registration client IDs (`VITE_ENTRA_CLIENT_ID`, `ENTRA_AUDIENCE`). |

---

## 2. Authentication Architecture

```
                                  +---------------------------------------+
                                  |         Microsoft Entra ID            |
                                  |  (Identity & Access Management)       |
                                  +---------------------------------------+
                                       ^                             ^
                 1. User Login (PKCE)  |                             | 3. Client Credentials Flow
             Scope: api://backend/...  |                             |    Scope: management.azure.com
                                       v                             v
+------------------------------------------+        HTTPS REST      +-----------------------------------------+
|        Fabric Frontend Application       | ---------------------> |        FastAPI Backend App Service      |
|  - React 19 / Vite 8                     |  Bearer Entra Token    |  - Azure App Service: FinopsBackendApp  |
|  - MSAL Browser v5 (Memory Storage)      |                        |  - RS256 JWT Signature Validation       |
|  - Masked Service Principal Form         |                        |  - Role & Scope Policy Enforcement      |
|  - Zero Secret Exposure in Web Storage   |                        |  - In-Memory / AES-GCM Encrypted Vault  |
+------------------------------------------+                        +-----------------------------------------+
                     |                                                                   |
                     | 2. Separate Fabric UDF Token                                      | 4. Read-Only Azure APIs
                     |    Scope: https://analysis.windows.net/...                        |    (Reader, Cost Reader,
                     v                                                                   |     Monitoring Reader)
+------------------------------------------+                                             v
|        Microsoft Fabric Python UDF       |                        +-----------------------------------------+
|  - Dedicated OneLake & Lakehouse RPC     |                        |        Azure Subscription Services      |
|  - Never mixed with Backend API Token    |                        |  - ARM Resource Inventory & RGs         |
+------------------------------------------+                        |  - Cost Management API                  |
                                                                    |  - Azure Monitor Metrics                |
                                                                    +-----------------------------------------+
```

### Separation of Concerns
1. **User Identity (Entra ID MSAL)**:
   - Audience: FinOps Backend API (`ENTRA_AUDIENCE`).
   - Token Type: Delegated user token (`scp: access_as_user`).
   - Lifetime: Validated on every protected FastAPI endpoint via `get_current_user` and `enforce_route_policy`.
   - Storage: In-memory only (`cacheLocation: "memoryStorage"`).
2. **Azure Connectivity (Service Principal)**:
   - Scope: `https://management.azure.com/.default`.
   - Grant Type: `client_credentials`.
   - Isolation: Credentials are submitted only over HTTPS, used to acquire short-lived ARM tokens, and encrypted at rest with AES-GCM in the connection vault. Secrets are never exposed to the frontend, never returned in API responses, and never logged.
3. **Fabric UDF Execution**:
   - Scope: `https://analysis.windows.net/powerbi/api`.
   - Independent token handling via `entraTokenService.getFabricAccessToken()`. Completely isolated from backend API calls.

---

## 3. Files Inspected & Modified

### Files Inspected
- `fabric-integration/finops-app/packages/frontend/src/lib/api.ts` (API client, token injection, error handling)
- `fabric-integration/finops-app/packages/frontend/src/services/entra-token.service.ts` (MSAL configuration and token acquisition)
- `fabric-integration/finops-app/packages/frontend/src/config/entra.ts` (Entra ID environment settings)
- `fabric-integration/finops-app/packages/frontend/src/components/auth-gate.component.tsx` (Sign in with Microsoft gate)
- `fabric-integration/finops-app/packages/frontend/src/components/azure-live/AzureConnectionForm.tsx` (Service Principal form with masked secret)
- `fabric-integration/finops-app/packages/frontend/src/components/azure-live/AzureLiveView.tsx` (Azure live dashboard & permissions feedback)
- `backend/src/cloud_recommender/core/auth.py` (RS256 JWT validation, claims extraction, RBAC)
- `backend/src/cloud_recommender/core/config.py` (Settings, environment markers, CORS origins)
- `backend/src/cloud_recommender/api/v1/router.py` (Versioned route mounting and policy dependencies)
- `backend/src/cloud_recommender/api/routes/azure_live.py` (In-memory live Azure session routes)
- `backend/src/cloud_recommender/api/routes/connections.py` (Persistent encrypted cloud connections)
- `backend/src/cloud_recommender/services/azure_live/credentials.py` (Service Principal token acquisition)
- `backend/src/cloud_recommender/services/azure_live/arm_client.py` (Read-only Azure Resource Manager client)
- `backend/src/cloud_recommender/services/azure_live/data_service.py` (Subscription, RG, inventory, cost, and metric aggregation)
- `backend/src/cloud_recommender/services/connections/vault.py` (AES-GCM encrypted credential storage)

### Files Modified in this Milestone
- `fabric-integration/finops-app/packages/frontend/src/lib/api.ts`:
  - Decoupled platform APIs from Fabric UDF hijacking.
  - Added `apiFetch` with backend connection error handling.
  - Replaced fake health check with real `GET /health` HTTP probe.
  - Integrated `getHeaders()` with `entraTokenService.getAccessTokenSilent()`.
  - Added structured handling for 401, 403, and 503 (`DATABASE_UNAVAILABLE`).
  - Removed unused imports to ensure clean TypeScript/ESLint compliance.
- `fabric-integration/finops-app/packages/frontend/.env.production`:
  - Configured `VITE_API_BASE_URL=https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1`.
  - Configured `VITE_USE_FABRIC_UDF=false`.
- `backend/src/cloud_recommender/main.py`:
  - Expanded production CORS `allow_methods` to include `["GET", "POST", "PATCH", "DELETE", "OPTIONS"]`.
- `backend/tests/test_app_service_readiness.py`:
  - Added preflight verification for `DELETE` and `PATCH` methods from Fabric origins.

---

## 4. Configuration Requirements & Missing Items

To conduct end-to-end live testing against real Microsoft Entra ID and Azure subscriptions, the following configuration parameters must be provided. In accordance with operational guardrails, **no placeholder or simulated values have been used**.

### A. Microsoft Entra ID Application Login Requirements
| Variable | Component | Current Value | Required Value / Description |
| :--- | :--- | :--- | :--- |
| `VITE_ENTRA_CLIENT_ID` | Frontend | *(Not Set)* | Application (client) ID of the Frontend SPA App Registration in Entra ID |
| `VITE_ENTRA_TENANT_ID` | Frontend | *(Not Set)* | Directory (tenant) ID where users authenticate |
| `VITE_ENTRA_API_SCOPE` | Frontend | *(Not Set)* | Delegated scope exposed by Backend API (e.g. `api://<backend-app-id>/access_as_user`) |
| `ENTRA_AUTH_ENABLED` | Backend | `false` | Set to `true` on App Service to enforce JWT validation |
| `ENTRA_TENANT_ID` | Backend | *(Not Set)* | Directory (tenant) ID matching frontend |
| `ENTRA_AUDIENCE` | Backend | *(Not Set)* | Application ID URI or Client ID of the Backend App Registration |
| `ENTRA_ALLOWED_CLIENT_IDS`| Backend | *(Not Set)* | List containing the Frontend SPA Application (client) ID |

### B. Azure Service Principal Subscription Connection Requirements
To connect an Azure subscription, the user enters these credentials in the FinOps connection form:
| Field Name | Description | Status |
| :--- | :--- | :---: |
| **Connection Name** | Human-readable alias (e.g., `Azure-Production-Subscription`) | User-supplied |
| **Tenant ID** | Directory (tenant) GUID hosting the Azure subscription | **Pending User Input** |
| **Subscription ID**| Azure subscription GUID to monitor | **Pending User Input** |
| **Client ID** | Application (client) GUID of the Service Principal | **Pending User Input** |
| **Client Secret** | Client secret string created for the Service Principal | **Pending User Input** |

### C. Required Azure RBAC Roles on Target Subscription
| Feature | Role Name | Scope | Portal Navigation |
| :--- | :--- | :--- | :--- |
| **Resource Discovery** | `Reader` | Subscription | Subscriptions -> *Select Sub* -> Access control (IAM) -> Add role assignment -> **Reader** |
| **Cost Management** | `Cost Management Reader` | Subscription or Enrollment Scope | Subscriptions -> *Select Sub* -> Access control (IAM) -> Add role assignment -> **Cost Management Reader** |
| **Azure Monitor** | `Monitoring Reader` | Subscription | Subscriptions -> *Select Sub* -> Access control (IAM) -> Add role assignment -> **Monitoring Reader** |

---

## 5. Automated Test Suite Results

All test suites were executed in this session and passed with zero errors.

### 5.1 Fabric Frontend Vitest Suite
- **Command:** `npm --prefix "fabric-integration/finops-app/packages/frontend" test`
- **Result:** **188 passed across 19 test files** (Duration: 27.67s)
- **Key Specs Passed:**
  - `src/test/backend-api-auth.spec.ts`: Silent Entra token acquisition, fallback behavior, scope validation.
  - `src/test/azure-live.spec.tsx`: Service Principal form validation, secret protection, permission reporting, error handling.
  - `src/test/jwt-claims.spec.ts`: JWT claim extraction and user identity parsing.
  - `src/test/fabric-token.spec.ts`: MSAL configuration building and token caching in memory.
  - `src/test/connection-persistence-ui.spec.tsx`: Owner-bound connection listing and validation UI.
  - `src/test/fabric-udf-client.spec.ts`: Fabric UDF RPC operations contract isolation.

### 5.2 Backend Targeted Security & Auth Pytest Suite
- **Command:** `pytest backend/tests/test_entra_auth.py backend/tests/test_azure_live_connection.py backend/tests/test_connections_and_tokens.py backend/tests/test_route_authorization_policy.py backend/tests/test_stage_a_authorization.py backend/tests/test_app_service_readiness.py -v`
- **Result:** **84 passed in 107.80s (0 failed, 0 errors)**
- **Coverage Highlights:**
  - `test_valid_token_authenticated_successfully`: Valid RS256 token authenticated with subject and roles.
  - `test_missing_token_on_protected_route_rejected_401`: Enforces 401 on protected endpoints when auth enabled.
  - `test_expired_token_rejected_401`: Enforces strict expiration checks.
  - `test_invalid_audience_rejected_401`: Rejects foreign audience tokens.
  - `test_invalid_issuer_rejected_401`: Rejects tokens from unapproved issuers.
  - `test_wrong_tenant_id_in_claims_rejected_401`: Tenant isolation enforced.
  - `test_invalid_credentials_are_rejected_without_leaking_them`: Service Principal auth failures reject bad secrets without logging or echoing.
  - `test_secret_is_never_logged_echoed_or_stored`: Confirms zero secret leakage in logs, headers, or state.
  - `test_other_users_get_404_on_every_connection_route`: Multi-tenant ownership isolation.
  - `test_missing_cost_management_permission_is_reported_not_shown_as_zero`: Distinguishes 0 spend from missing `Cost Management Reader`.
  - `test_arm_client_is_read_only`: Proves zero write methods exist on ARM client.
  - `test_cors_allows_only_the_configured_fabric_origin`: Strict CORS origin validation.

### 5.3 Static Code Analysis & Linting
- **Ruff Check:** Clean (`ruff check backend` -> All checks passed!).
- **Ruff Format:** Clean (`ruff format --check backend` -> 184 files already formatted).
- **Mypy Type Check:** Clean (`mypy --config-file backend/pyproject.toml backend/src` -> Success: no issues found in 106 source files).
- **Next.js Frontend Lint:** Clean (`npm --prefix frontend run lint` -> No ESLint warnings or errors).

---

## 6. Live Deployed Backend Inspection Findings

Probing the live deployed Azure App Service (`FinopsBackendApp`) revealed three key operational insights:

1. **Service Availability**:
   - `GET /health` returned HTTP 200 `{"status":"ok","environment":"production","version":"0.1.0"}`.
   - The Uvicorn process is running and healthy on Azure App Service.
2. **Older Deployed Build Version**:
   - Querying `GET /openapi.json` on the live deployed backend showed only 25 routes (the Milestone 2.5 footprint).
   - Local codebase contains 52+ versioned endpoints including `azure_live_router` (`/api/v1/azure/connections`), `databricks_router`, `finops_router`, `configuration_router`, and `ingestion_router`.
   - Consequently, calling `POST /api/v1/azure/connections` on the currently deployed App Service returns HTTP 404 because the live instance has not yet had the latest backend code published to it.
3. **App Service Platform CORS Restriction**:
   - An HTTP `OPTIONS` preflight from `https://app.fabric.microsoft.com` returned HTTP 400 `Disallowed CORS origin` generated by Azure App Service's front-end IIS ARR proxy (`Access-Control-Allow-Methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY`).
   - The Azure Portal App Service "CORS" configuration blade must be updated to include `https://app.fabric.microsoft.com` and `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`.

---

## 7. Security Verification Matrix

| Security Rule | Mechanism | Status | Evidence |
| :--- | :--- | :---: | :--- |
| **Masked Secret in UI** | Input `type="password"`, no auto-fill, cleared from memory upon submission | **PASS** | `AzureConnectionForm.tsx` & `azure-live.spec.tsx` |
| **Zero Web Storage Leakage** | No client secret or Bearer token written to `localStorage` or `sessionStorage` | **PASS** | `azure-live.spec.tsx: it("never writes the client secret to localStorage")` |
| **Zero Secret Logging** | `Pydantic` `SecretStr` used; validation handlers drop `input` and `ctx` before logging | **PASS** | `backend/src/cloud_recommender/main.py: validation_exception_handler` |
| **Read-Only ARM Access** | ARM client implements only `GET` and read-only query `POST` (e.g. Cost query) | **PASS** | `arm_client.py: AzureArmClient` |
| **Zero-Execution Policy** | Advisory only; no code to create, modify, or destroy real customer infrastructure | **PASS** | Verified across all route handlers |
| **Owner-Bound Isolation** | Every connection query filters by authenticated caller `owner_key` | **PASS** | `test_other_users_get_404_on_every_connection_route` |
| **Database Fail-Closed** | Uninitialised database returns HTTP 503 `DATABASE_UNAVAILABLE`; never fake success | **PASS** | `database_unavailable_handler` & `finops-api-and-components.spec.tsx` |

---

## 8. Remaining Production Deployment Checklist

When ready to promote these changes to Azure App Service:

1. **Azure Portal App Service CORS Settings (`FinopsBackendApp`)**:
   - Open Azure Portal -> `FinopsBackendApp` -> **CORS** (under API).
   - Add Allowed Origins:
     - `https://app.fabric.microsoft.com`
     - `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`
   - Check **Enable Access-Control-Allow-Credentials**.
   - Save configuration.
2. **App Service Environment Variables (Configuration -> Application Settings)**:
   - `ENTRA_AUTH_ENABLED` = `true`
   - `ENTRA_TENANT_ID` = `<tenant-guid>`
   - `ENTRA_AUDIENCE` = `<backend-api-app-id-uri>`
   - `ENTRA_ALLOWED_CLIENT_IDS` = `<frontend-spa-client-id>`
   - `CORS_ORIGINS` = `https://app.fabric.microsoft.com,https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`
   - `CONNECTION_ENCRYPTION_KEY` = `<strong-32-byte-hex-or-base64-key>`
3. **Frontend Environment Settings (`.env.production`)**:
   - `VITE_ENTRA_CLIENT_ID` = `<frontend-spa-client-id>`
   - `VITE_ENTRA_TENANT_ID` = `<tenant-guid>`
   - `VITE_ENTRA_API_SCOPE` = `api://<backend-api-app-id>/access_as_user`
4. **App Service Code Deployment**:
   - Package backend source into deployment ZIP.
   - Deploy via Azure CLI or Azure Portal Deployment Center.
   - Monitor startup logs to confirm `authentication_mode: entra`.

