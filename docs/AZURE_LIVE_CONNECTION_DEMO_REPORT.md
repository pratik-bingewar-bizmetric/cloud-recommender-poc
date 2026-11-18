# Azure Live Connection Demo MVP: Implementation Report

- **Branch:** `feature/backend-security-hardening` (HEAD `902d220`, all work uncommitted, earlier work preserved).
- **Status:** MVP implemented and tested **against mocked Microsoft Entra ID / Azure Resource Manager**. It has **not** been run against a real Azure tenant, a real Entra app registration, or the Fabric-hosted app (restricted by the task; see §9 for what that means for confidence).
- **Not done (per restrictions):** no provisioning, deployment, Entra registration, consent, migration, `.env` edit, billing/ingestion execution, commit or push.

---

## 1. What the demo does

1. The user opens the Fabric-hosted app and **signs in to the backend API** with their Microsoft work account (MSAL, backend-audience token).
2. The user enters **Tenant ID, Client ID, Client Secret** (and optionally a subscription) of **their own Azure service principal**.
3. The backend validates the credentials **directly with Microsoft Entra ID**, **discards the secret**, keeps only the short-lived Azure token in memory and returns an opaque connection id.
4. The dashboard shows subscriptions, resource groups, resources, resource-type breakdown, Azure Monitor metrics and Cost Management data, each with an explicit **access state** and the **connection/subscription it came from**.
5. Disconnect forgets the token and the in-memory secret. Nothing is persisted.

Data is **never** fetched with the server's own Azure identity, `DefaultAzureCredential`, or an Azure CLI session for personal connections (enforced by code and tests, §7).

---

## 2. Architecture and authentication flow

```
Browser (Fabric-hosted Vite SPA)                        Azure App Service (FastAPI, 1 instance)
────────────────────────────────                        ───────────────────────────────────────
(1) MSAL popup ──► Entra ID ──► access token for the BACKEND API (aud = API, azp = SPA, scp = access_as_user)
                       held in memory (MSAL memoryStorage)

(2) POST /api/v1/azure/connections            ───►  validate Entra JWT (signature, iss, aud, tid, exp, nbf),
    Authorization: Bearer <backend token>             approved client (azp), required scope  → else 401/403
    body: tenant_id, client_id, client_secret          │
    (secret only in this body, HTTPS)                  ├─ POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
                                                       │   (client_credentials, scope https://management.azure.com/.default)
                                                       ├─ secret discarded; ARM token kept in memory, bound to the user (tid:oid)
                                                       └─ GET /subscriptions → subscriptions domain
                                      ◄───  connection_id (opaque), connection info, subscriptions (+ access state)

(3) GET …/connections/{id}/subscriptions/{sub}/overview|resources|metrics|cost
    (backend token again)                    ───►  owner check (404 for anyone else) → ARM calls with THAT connection's token
```

- **Two different tokens, never mixed:** the *backend API token* (who the app user is) and the *Azure ARM token* (the user's service principal). Rayfin/Fabric session tokens are never read, forwarded or accepted by the backend.
- **Secret handling:** in the browser it exists only in React memory (a ref) so the page can silently reconnect if the backend's token expires; it is wiped on Disconnect and cleared from the input after submit. In the backend it exists only inside the connect request.
- **Backend authentication is unchanged and mandatory** (JWT validation, approved client, required scope; no dev auth in production).

---

## 3. Files changed

### Backend (`backend/`)

| File | Change |
|---|---|
| `src/cloud_recommender/api/routes/azure_live.py` | **New**: live connection API (§4) |
| `src/cloud_recommender/schemas/azure_live.py` | **New**: request/response models, `DataAccessState`, `DataDomain`, `DataSource` |
| `src/cloud_recommender/services/azure_live/credentials.py` | **New**: Entra client-credentials token acquisition (httpx), safe error categories |
| `src/cloud_recommender/services/azure_live/arm_client.py` | **New**: read-only ARM client (GET + Cost Management query POST only; refuses foreign hosts and foreign `nextLink`s) |
| `src/cloud_recommender/services/azure_live/session_store.py` | **New**: owner-bound in-memory sessions (TTL, per-user cap), sliding-window attempt limiter |
| `src/cloud_recommender/services/azure_live/data_service.py` | **New**: per-domain fetching, state classification, cost/metrics parsing, overview |
| `src/cloud_recommender/services/azure_live/validation.py` | **New**: GUID and ARM resource-id validation (no URL/path injection) |
| `src/cloud_recommender/api/v1/router.py` | Mounts the new router behind the standard auth policy |
| `src/cloud_recommender/core/auth.py` | `owner_key_for()`; the 3 new non-GET operations classified as user operations |
| `src/cloud_recommender/core/config.py` | New settings (names in §8.3) |
| `src/cloud_recommender/main.py` | **Security fix**: request-validation errors no longer log or echo submitted values (`input`/`ctx` dropped) so a malformed request can never leak the client secret |
| `startup.sh` | **New**: App Service startup command (single uvicorn worker) |
| `tests/test_azure_live_connection.py`, `tests/test_app_service_readiness.py` | **New** (37 tests) |
| `tests/test_route_authorization_policy.py`, `tests/test_security_hardening.py` | Frozen route classification updated for the 3 new operations (list size 18 → 21) |

### Frontend (`fabric-integration/finops-app/packages/frontend/`)

| File | Change |
|---|---|
| `src/components/azure-live/{AzureLiveView,AzureConnectionForm,AzureLiveDashboard,DataDomainNotice}.tsx` | **New** UI |
| `src/hooks/use-azure-live-connection.ts` | **New**: connection state; secret kept in a ref; one silent reconnect if the backend forgot the session |
| `src/lib/azureLiveApi.ts` | **New**: typed API client (bearer token, `credentials: omit`, `cache: no-store`, no UDF/localhost fallback) |
| `src/services/entra-token.service.ts`, `src/config/entra.ts` | **New**: MSAL backend-audience token acquisition, in-memory token cache |
| `src/auth/redirect-bridge.ts`, `redirect.html`, `src/auth/popup-relay.ts`, `popup-relay.html` | **New**: MSAL v5 redirect bridge and popup relay pages (extra Vite entries) |
| `src/types/azureLive.ts`, `src/vite-env.d.ts` | **New** types; typed `VITE_ENTRA_*` variables |
| `src/components/Sidebar.tsx`, `src/FinOpsApp.tsx` | "Azure Live" navigation item and view; the onboarding screen now offers the live service-principal connection (default tab) beside the existing connections |
| `vite.config.ts` | Multi-page build entries for the two sign-in helper pages |
| `package.json`, `package-lock.json` | `@azure/msal-browser@^5.27.0` declared as a direct dependency (it was already installed transitively; lock updated offline, no download) |
| `src/test/azure-live.spec.tsx` | **New** (19 tests) |
| `src/Root.spec.tsx` | 10 assertions adapted (see §7 note) |

Not modified: any `.env*` file, `app.yaml`, `rayfin.yml`, migrations, Databricks code, `schemas/domain.py`, ADRs.

---

## 4. API endpoints (all under `/api/v1/azure/connections`, Entra token required)

| Method and path | Purpose | Class |
|---|---|---|
| `POST /` | Connect: validate credentials with Entra, create session, list subscriptions (optional `subscription_id` access check) | user |
| `POST /{id}/validate` | Re-validate the token against Azure | user (owner) |
| `DELETE /{id}` | Disconnect | user (owner) |
| `GET /{id}/subscriptions` | Fetch subscriptions | user (owner) |
| `GET /{id}/subscriptions/{sub}/resource-groups` | Resource groups | user (owner) |
| `GET /{id}/subscriptions/{sub}/resources[?resource_group=]` | Inventory (paged, capped) + type breakdown | user (owner) |
| `GET /{id}/subscriptions/{sub}/resource?resource_id=` | Resource detail (API version resolved from the provider's stable versions) | user (owner) |
| `GET /{id}/subscriptions/{sub}/metrics/definitions?resource_id=` | Available Azure Monitor metrics | user (owner) |
| `GET /{id}/subscriptions/{sub}/metrics?resource_id=&metric_names=&hours=&interval=&aggregation=` | Metric values | user (owner) |
| `GET /{id}/subscriptions/{sub}/cost?period=month_to_date\|last_month` | Actual cost (Cost Management query) | user (owner) |
| `GET /{id}/subscriptions/{sub}/overview` | All dashboard domains fetched independently | user (owner) |

Behaviour: other users, unknown and expired connections all get an identical **404**; connect/validate are limited to **5 attempts per minute per user** (429 + `Retry-After`, configurable) and **10 connections per user** (409). Tenant/client/subscription IDs must be GUIDs; resource IDs must belong to the selected subscription (422 otherwise, no Azure call).

Existing endpoints (including the organization Azure inventory and all Databricks/FinOps routes) are **unchanged**.

---

## 5. Data access transparency

Every domain returns `state`, an explanation, the **required role** when denied, HTTP/Azure error codes, retry hints and a `source` (connection, client, subscription, API, time).

| State | When | Example message |
|---|---|---|
| `accessible` | 200 with items | none |
| `empty` | 200 with no items | "No resources exist in this scope (the principal can read it)." / cost: "…not a statement that spend is zero" |
| `permission_denied` | 403 | "Assign the 'Cost Management Reader' role on the subscription." |
| `unavailable` | 401 (token expired/revoked), 404, 400/409 (e.g. cost unsupported for the offer) | Azure's own sanitized message |
| `error` | network failure, 429, 5xx | "Azure is rate limiting this request. Retry in 37 seconds." |

Rules implemented and tested: cost totals are **never** shown as zero when access is missing or no rows were returned (`items: null` / empty, UI shows "—" and a badge); a failure in one domain never hides another (`overview` runs domains concurrently, each with its own state); multiple currencies yield no combined total; metric series with no datapoints are reported as `empty`, not 0.

---

## 6. Azure permission requirements for the user's service principal

| Data | Azure role (scope: subscription) | Resource provider |
|---|---|---|
| Subscriptions, resource groups, resources, resource detail | **Reader** | `Microsoft.Resources` |
| Monitoring metrics | **Monitoring Reader** (Reader also grants read on most metrics) | `Microsoft.Insights` |
| Cost data | **Cost Management Reader** | `Microsoft.CostManagement` (cost data can lag for new subscriptions; some offers do not support the query API) |

Use read-only roles only (project rule). The demo does not yet block a principal that has write roles (planned in Stage B of the authorization work); the client itself is physically read-only (see §7).

---

## 7. Acceptance tests

| # | Acceptance test | Result | Evidence |
|---|---|---|---|
| 1 | Invalid Azure credentials are rejected | **Pass** (mocked Entra) | 3 parametrised cases (wrong secret, unknown app, unknown tenant) → 400 with category, no session, no Azure data call, secret absent from response; Entra outage → 502 (not mislabelled as bad credentials) |
| 2 | Valid credentials return accessible subscriptions | **Pass** (mocked) | Subscriptions from the mocked ARM, `source.connection_id` present, optional subscription access check, `permission_denied` for an inaccessible requested subscription, `empty` with guidance when none |
| 3 | Selecting a subscription returns its resource groups | **Pass** (mocked) | `resource-groups` returns the groups with source subscription |
| 4 | Inventory fetched using the supplied identity | **Pass** (mocked) | Paged inventory + type breakdown; **every ARM request carried the user's token; the only token request used the user's client id; the server's configured client id/secret were never sent** |
| 5 | Missing Cost Management permission clearly reported | **Pass** | `permission_denied`, `required_permission: "Cost Management Reader"`, no numbers; UI shows the explanation and never `$0` (frontend test) |
| 6 | No Azure CLI session required | **Pass** | Flow runs with `subprocess.Popen/run` patched to fail, server SP env set and `AZURE_AUTH_METHOD=azure_cli`; no Azure CLI, `DefaultAzureCredential` or server identity involved |
| 7 | No secret in logs or persistent browser storage | **Pass** | Backend: captured structlog + stdlib logs and all responses (success, bad credentials, malformed body, extra field) contain no secret; session store repr has neither secret nor token. Frontend: `localStorage`/`sessionStorage` empty and `setItem` never called with the secret; secret absent from the DOM; request URL/headers carry no secret |
| 8 | Backend authentication remains mandatory | **Pass** | All endpoints 401 without a token (and nothing reaches Entra/Azure); Rayfin-style (wrong audience, HS256, opaque) tokens → 401; missing scope or unapproved client → 403; route-policy sweep updated and green |
| 9 | Existing Databricks regression tests pass | **Pass** | Full backend suite green (below), includes all Databricks tests |
| 10 | Frontend production build succeeds | **Pass** (with a noted deviation) | `vite build` succeeded; `dist/` contains `index.html`, `redirect.html`, `popup-relay.html` |

Note on adapted existing tests: `Root.spec.tsx` asserted the old onboarding heading as proof that protected content renders after Rayfin sign-in. The onboarding screen now defaults to the live-connection tab, so those 10 assertions look for the "Connect my Azure account" tab instead (same intent: protected content appears only after authentication).

### Test and check results

| Check | Result |
|---|---|
| Backend `pytest tests` | **836 passed, 8 skipped, 0 failed**, coverage 87% (new modules: routes 97%, schemas 100%, session store 99%, credentials 90%, data service 90%, ARM client 88%) |
| Backend `ruff check` / `ruff format --check` | pass (163 files) |
| Backend `mypy src` | pass (101 files) |
| Frontend `vitest run` | **146 passed** (14 files; 19 new, 10 adapted) |
| Frontend `eslint` on all new/changed files | clean (0 errors, 0 warnings) |
| Frontend `tsc -b` | **55 pre-existing errors in 9 untouched files** (e.g. `ConfigurationView.tsx`, `api.ts`, Databricks views); **0 errors in new or modified files**. The project's own build script uses `--noCheck`, which is why these never failed a build |
| Frontend build | `npx vite build` in `packages/frontend`: success. **Deviation:** I did not run `npm run build`/`build:fabric` because their `prebuild` step (`rayfin env`) regenerates `packages/frontend/.env.local`, a `.env` file I was told not to modify. Run the official script at deployment time |

---

## 8. Manual setup still required (cannot be automated here)

### 8.1 Microsoft Entra ID (tenant administrator)

1. **Backend API app registration**
   - Set the **Application ID URI** (e.g. `api://<backend-app-id>`); this value is `ENTRA_AUDIENCE`.
   - **Expose an API** → add delegated scope **`access_as_user`** (admins and users can consent).
   - Manifest: `requestedAccessTokenVersion` (`accessTokenAcceptedVersion`) = **2**.
   - Optional: app role `FinOpsAdmin` (only needed for restricted billing operations, not for this demo).
2. **SPA app registration** (the frontend)
   - Platform **Single-page application**; redirect URIs: `https://<fabric-hosting-origin>/redirect.html` (the exact hosting URL, e.g. the `*.webapp.fabricapps.net` origin of the Rayfin deployment).
   - API permissions → add the delegated permission `access_as_user` of the backend API; **grant admin consent** (or pre-authorize the SPA client ID on the backend registration) so users do not see a consent prompt.
   - Its **Application (client) ID** goes into `ENTRA_ALLOWED_CLIENT_IDS` (backend) and `VITE_ENTRA_CLIENT_ID` (frontend).
3. Recommended: on the backend's enterprise application set **Assignment required = Yes** and assign the demo users.
4. **The demo user's Azure service principal** (their own): create/choose it and assign the roles in §6.

None of this was performed.

### 8.2 Fabric static hosting
- The two helper pages (`/redirect.html`, `/popup-relay.html`) must be **reachable without Fabric sign-in** (the current `rayfin.yml` uses `assetAccess: public`, so they are). If you switch to `protected`, test the popup flow.
- Build-time variables (public identifiers, not secrets): `VITE_API_BASE_URL=https://<app>.azurewebsites.net/api/v1`, `VITE_ENTRA_CLIENT_ID`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_API_SCOPE=api://<backend-app-id>/access_as_user`. Put them in the build environment or `.env.production` (not in the generated `.env.local`). The existing `VITE_USE_FABRIC_UDF=true` does not affect the new screen.
- Real-browser verification of the MSAL popup flow, including when the app is embedded in the Fabric portal iframe (popup relay), must be done after the registrations exist.

### 8.3 Backend configuration (Azure App Service)

Required application settings (**names only**; secret values go in Key Vault references or protected app settings, never in the repo):

| Setting | Value / note |
|---|---|
| `APP_ENV` | `production` |
| `ENTRA_AUTH_ENABLED` | `true` |
| `ENTRA_TENANT_ID` | tenant GUID |
| `ENTRA_AUDIENCE` | Application ID URI of the backend API registration |
| `ENTRA_REQUIRED_SCOPES` | `access_as_user` (default) |
| `ENTRA_ALLOWED_CLIENT_IDS` | SPA client ID(s) |
| `CORS_ORIGINS` | exactly the Fabric hosting origin (`https://…`) |
| `SECRET_KEY`, `FINOPS_SIGNING_SECRET` | **secrets**, ≥ 32 random characters (production startup refuses defaults) |
| `DEBUG` | `false` |
| `DATABRICKS_INVENTORY_REFRESH_SECONDS` | `0` (Databricks refresher not needed for the demo) |
| `WEBSITES_PORT` | `8000` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` (Oryx installs `requirements.txt`) |
| Optional tuning | `AZURE_LIVE_SESSION_TTL_SECONDS` (3300), `AZURE_LIVE_MAX_CONNECTIONS_PER_USER` (10), `AZURE_LIVE_CONNECT_ATTEMPTS_PER_MINUTE` (5), `AZURE_LIVE_MAX_RESOURCES` (5000), `AZURE_LIVE_REQUEST_TIMEOUT_SECONDS` (30), `AZURE_AUTHORITY_URL` |
| **Do not set** | `AZURE_CLIENT_ID/SECRET/TENANT_ID/SUBSCRIPTION_ID`, `DEV_AUTH_ENABLED` |

---

## 9. Azure App Service deployment requirements (nothing provisioned or assumed to exist)

- **Plan/runtime:** Linux App Service plan (B2 or P1v3 suggested), **Python 3.12**.
- **Startup command:** `bash startup.sh` (single uvicorn worker, binds `0.0.0.0:$WEBSITES_PORT`, `--proxy-headers`). Deploy the **contents of `backend/`** (`requirements.txt`, `startup.sh`, `src/`) as the site root; exclude `tests/`, `.venv`.
- **Single instance:** scale-out = **1**, one worker. Sessions are in process memory; a second instance or worker would make connections appear "expired" randomly.
- **Health check:** path `/health` (public, returns 200 and no internal details). `/health/ready` reports the database and returns 503 when none is configured (expected for the demo).
- **HTTPS:** HTTPS Only = On, minimum TLS 1.2; TLS terminates at App Service; no HTTP origin in `CORS_ORIGINS` (production startup rejects it).
- **CORS:** only the Fabric hosting origin; methods `GET, POST, OPTIONS`; headers `Authorization, Content-Type, Accept`.
- **Outbound access:** `login.microsoftonline.com` (Entra token endpoint and signing keys) and `management.azure.com` must be reachable; if outbound is restricted, allow them.
- **Database:** none needed for this demo (no connection is attempted at startup; verified by test). DB-backed features (configuration, ingestion) are unavailable until a database exists.
- **API docs:** `/docs`, `/redoc`, `/openapi.json` return 404 in production.
- Secrets: use Key Vault references for `SECRET_KEY` / `FINOPS_SIGNING_SECRET`; the demo user's service principal secret never reaches the server's configuration.

---

## 10. Known demo limitations

1. **Verified only against mocks.** Entra and ARM behaviours (token endpoint errors, paging, Cost Management response shape, metrics API) are modeled from documented behaviour; real-tenant differences may need small fixes (e.g. cost column naming, provider API-version resolution, throttling).
2. **Sessions are in memory:** lost on restart/redeploy and not shared across instances. The UI silently reconnects once using the in-memory secret if the page is still open; otherwise the user re-enters it.
3. **Token lifetime ~1 hour:** a session lasts at most ~55 minutes (token expiry), then reconnect.
4. **The secret lives in browser memory while connected** (needed for silent reconnect). A script injection (XSS) in the page could read it; apply a strict Content-Security-Policy on the hosting and keep the page free of third-party scripts. Disconnect wipes it.
5. **No write-permission screening yet:** a service principal with Contributor/Owner can be connected (the client is read-only by construction, but the principal's grants are not inspected). Planned in the Stage B authorization work.
6. **Cost Management API:** frequently rate limited (429) and sometimes delayed; shown as `error` with a retry hint. Some subscription offers do not support it (`unavailable`). Only month-to-date and last-month, grouped by service; no per-resource cost.
7. **Inventory caps:** 5000 resources per call (`truncated: true` is shown), first 200 rows displayed; no server-side search.
8. **Metrics:** values are fetched for the metrics the user selects (last 24 h, hourly, one aggregation); no charts.
9. **Existing "Existing connections" onboarding and organization inventory still use the server identity/CLI by design** (preserved, clearly separated from the live flow).
10. **Interactive sign-in untested end-to-end:** MSAL v5 requires the redirect-bridge and popup-relay pages (added); behaviour inside the Fabric portal iframe must be validated manually once the registrations exist.
11. **Pre-existing frontend type errors** (55 in 9 other files) remain; they predate this work and do not block the build because the build skips type-checking.
12. Multi-tenant / sovereign clouds: only the public cloud by default (`AZURE_AUTHORITY_URL` and `AZURE_ARM_BASE_URL` can be changed).

---

## 11. Suggested verification once registrations exist (no cloud action taken here)

1. Deploy backend with the §8.3 settings; confirm `GET /health` and that `POST /api/v1/azure/connections` returns 401 without a token.
2. Build and publish the frontend with the §8.2 variables; open the Fabric app; click **Sign in with Microsoft** (expect no consent prompt if pre-authorized).
3. Enter a read-only service principal; confirm subscriptions, resource groups, inventory, metrics and cost (or a precise `permission_denied`).
4. Remove **Cost Management Reader** from the principal and click Refresh: cost must switch to `permission_denied` while inventory stays visible.
5. Run a second user: they must not see or use the first user's connection (404).
