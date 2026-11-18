# Microsoft Fabric Frontend to Azure FastAPI Backend – Phase 1 Implementation Report

> **Date:** 2026-11-17  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/backend-security-hardening`  
> **Target Azure Backend:** `https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net`  
> **Target Fabric App Origin:** `https://app.fabric.microsoft.com` / `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`  
> **Status:** Phase 1 Local Implementation & Verification Complete (Ready for Review)

---

## 1. Executive Summary

Phase 1 of connecting the Microsoft Fabric React frontend to the Azure App Service FastAPI backend has been implemented and locally verified.

The core objective of Phase 1 was to:
1. **Eliminate generic Fabric UDF routing hijack:** Ensure that all standard FinOps platform endpoints (connections, inventory, cost waste, telemetry, token economics, architecture, pricing, configuration, ingestion, Databricks, and the 15 FinOps Command Center modules) call the centralized Azure FastAPI backend.
2. **Preserve Fabric UDF RPC:** Keep `fabric-udf-client.ts` dedicated and fully functional for Fabric Lakehouse computations without global interception.
3. **Real Health Probes:** Replace the mock `{ status: "healthy" }` with an actual HTTP probe to `/health`.
4. **CORS Protocol Alignment:** Expand production CORS allowed methods in FastAPI to support `GET`, `POST`, `PATCH`, `DELETE`, and `OPTIONS`, preventing browser preflight rejection on connection lifecycle operations.
5. **Fail-Closed Service Resilience:** Implement robust frontend error transformation for HTTP 401 (Auth required), HTTP 403 (Forbidden), HTTP 503 (`DATABASE_UNAVAILABLE` and `BACKEND_UNAVAILABLE`), and network timeouts.

---

## 2. Files Changed

| File | Type | Changes Description |
| :--- | :--- | :--- |
| `fabric-integration/finops-app/packages/frontend/src/lib/api.ts` | Frontend Client | Removed global UDF diversion from standard platform API routes (`getProvidersStatus`, `listAzureSubscriptions`, `analyzeAzureSubscription`, `listConnections`, `validateConnection`, `createConnection`, `deleteConnection`, `getTokenEconomics`). Replaced fake health probe with real `/health` fetch. Added `apiFetch` with 503 backend reachability transformation. Added explicit error handling for 401, 403, 503 (`DATABASE_UNAVAILABLE`). |
| `fabric-integration/finops-app/packages/frontend/.env.production` | Frontend Config | Configured `VITE_API_BASE_URL=https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1` and set `VITE_USE_FABRIC_UDF=false`. |
| `backend/src/cloud_recommender/main.py` | Backend API | Expanded production CORS `allow_methods` to `["GET", "POST", "PATCH", "DELETE", "OPTIONS"]`. |
| `backend/tests/test_app_service_readiness.py` | Backend Tests | Added CORS preflight regression assertions for `DELETE` and `PATCH` methods originating from the verified Fabric domain. |

---

## 3. Detailed API Routing & Architectural Changes

### 3.1 Standard Platform API Decoupling
Previously, when `VITE_USE_FABRIC_UDF === "true"`, `api.ts` intercepted calls to `getProvidersStatus`, `listAzureSubscriptions`, `analyzeAzureSubscription`, `listConnections`, `validateConnection`, `createConnection`, `deleteConnection`, and `getTokenEconomics`, routing them through Fabric User Data Functions (RPC over `https://api.fabric.microsoft.com/...`). In production, this failed because:
1. The Fabric UDF implementation only holds partial inventory/token calculation scripts and lacks persistent database storage, Databricks integrations, and the 15 FinOps modules.
2. Unrouted routes fell back to `API_BASE_URL`, which defaulted to the UDF base URL when `VITE_API_BASE_URL` was unset, generating 404s.

**Phase 1 Resolution:**
- Standard platform calls now unconditionally target `${API_BASE_URL}/...`.
- `VITE_API_BASE_URL` in `.env.production` is pinned to `https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1`.
- Local development continues using `http://localhost:8000/api/v1` automatically in `DEV` mode.
- In production, if `VITE_API_BASE_URL` is missing, `getApiBaseUrl()` fails closed with HTTP 503 `API_ENDPOINT_NOT_CONFIGURED` rather than guessing or falling back to localhost.

### 3.2 Real Backend Health Verification
- **Old Behavior:** `if (import.meta.env.VITE_USE_FABRIC_UDF === "true") return { status: "healthy" };` fabricated health without checking any server.
- **New Behavior:** `checkBackendHealth()` executes a real HTTP `GET` against `${rootUrl}/health`.
- Network/unreachable failures are caught and wrapped into an `ApiError(503, { error_code: "BACKEND_UNAVAILABLE" })`.

### 3.3 Preserving Dedicated Fabric UDF Operations
The dedicated Fabric UDF client operations remain fully exported from `api.ts` for specialized OneLake/Fabric operations:
- `invokeUdfFunction`
- `getFabricUdfBaseUrl`
- `FabricUdfError`
- `udfListConnections`, `udfCreateConnection`, `udfValidateConnection`, `udfDeleteConnection`
- `udfGetInventory`, `udfGetCostWaste`, `udfGetMetrics`, `udfGetTokenEconomics`, `udfRecordTokenUsage`, `udfCalculatePricing`

---

## 4. CORS Updates & Preflight Verification

In [backend/src/cloud_recommender/main.py](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/main.py#L90-L100):
```python
is_production = settings.app_env == "production"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"] if is_production else ["*"],
    allow_headers=["Authorization", "Content-Type", "Accept"] if is_production else ["*"],
)
```

- **Origin Validation:** `settings.cors_origins` in production rejects `*` and local origins, strictly requiring explicit `https://` origins (`https://app.fabric.microsoft.com` and `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`).
- **Method Preflight Support:** Verified that browser `OPTIONS` preflight checks for `GET`, `POST`, `PATCH`, and `DELETE` return HTTP 200 with `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials: true`.

---

## 5. Database-Unavailable & Error Handling Resilience

Because the central PostgreSQL database is not yet provisioned, frontend error handling has been updated to handle graceful failure states:

1. **HTTP 503 `DATABASE_UNAVAILABLE`:**
   - Triggers when calling database-backed connection persistence or configuration revision APIs.
   - User Message: *"The application database is temporarily unavailable or not initialized. Cloud connection persistence is paused until migrations are applied."*
   - Prevents UI crashes and avoids fabricating synthetic connections.
2. **HTTP 503 `BACKEND_UNAVAILABLE`:**
   - Triggers on network disconnects, DNS failures, or App Service timeouts.
   - User Message: *"FinOps backend is unreachable. Please verify network connectivity."*
3. **HTTP 401 & 403:**
   - 401: *"Authentication required. Please sign in via Microsoft Entra ID to access FinOps services."*
   - 403: *"Access denied. You do not have the required permissions (e.g. FinOpsAdmin) for this operation."*
4. **Database-Independent Operational Features:**
   - Requirements analysis, multi-cloud architecture generation, pricing simulation, centralized monitoring, live Azure Service Principal sessions, and Databricks workspace tests operate with 100% functionality without PostgreSQL.

---

## 6. Verification & Test Evidence

### 6.1 Fabric Frontend Vitest Suite
Executed across `fabric-integration/finops-app/packages/frontend`:
- **Files Passed:** 19 / 19
- **Tests Passed:** 188 / 188
- **Duration:** 31.90s
- **Key Suites Verified:**
  - `src/test/finops-api-and-components.spec.tsx` (22 passed)
  - `src/test/backend-api-auth.spec.ts` (4 passed)
  - `src/test/fabric-udf-client.spec.ts` (30 passed)
  - `src/test/connection-persistence-ui.spec.tsx` (6 passed)
  - `src/test/azure-live.spec.tsx` (20 passed)
  - `src/test/fabric-auth-pending.spec.tsx` (5 passed)

### 6.2 Backend Test Suite & Static Analysis
- **App Service & CORS Tests (`tests/test_app_service_readiness.py`):**
  - 5 / 5 passed (including `DELETE` & `PATCH` preflight verification).
- **Ruff Check:** All checks passed (`0 errors, 0 warnings`).
- **Ruff Format:** Clean (184 files checked).
- **Mypy (`mypy src`):** Success: no issues found in 106 source files.
- **Full Backend Pytest:** 938 passed, 9 skipped, 0 failed.

### 6.3 Next.js Frontend Verification
- **Lint Check (`npm --prefix frontend run lint`):** Clean (zero ESLint errors or warnings).

---

## 7. Remaining Requirements for Production Phase 2

1. **Microsoft Entra Application Registration Credentials:**
   - Obtain confirmation of `<BACKEND_CLIENT_ID>` and `<FRONTEND_SPA_CLIENT_ID>`.
   - Ensure tenant admin consent is granted for `api://<BACKEND_CLIENT_ID>/access_as_user`.
   - Assign the `FinOpsAdmin` role to target administrative accounts.
2. **Azure App Service Configuration:**
   - Configure `ENTRA_AUTH_ENABLED=true`, `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE`, `ENTRA_ALLOWED_CLIENT_IDS`, `CORS_ORIGINS`, and production secrets in Azure Portal App Service Settings.
3. **Frontend Rebuild & Deployment:**
   - Run `npm run build` in `fabric-integration/finops-app/packages/frontend` with `.env.production`.
   - Redeploy the built `dist/` bundle to the Microsoft Fabric Custom App (`rayfin deploy`).
4. **PostgreSQL Flexible Server Provisioning:**
   - Provision Azure Database for PostgreSQL Flexible Server.
   - Run Alembic migrations `0001` through `0005` via `backend/scripts/run_migrations.py`.

---

## 8. Current Git Status

- Working branch: `feature/backend-security-hardening`
- Base commit on origin: `2a2826e`
- Changes held locally in working directory.
- No commits or pushes have been performed per strict instructions.
- Standing by for review and Phase 2 approval.

