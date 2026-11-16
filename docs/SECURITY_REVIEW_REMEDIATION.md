# Security Review Remediation

- **Branch:** `feature/backend-security-hardening` (HEAD still `902d2208`; all work is **uncommitted**).
- **Addresses:** findings H1, H2, M1, M2, M3, M5 from `docs/SECURITY_IMPLEMENTATION_REVIEW.md`.
- **Scope:** backend only. No frontend, `.env`, migration, cloud, Databricks, Fabric or Entra action was performed; no migration or audit script was executed (the migration runner's config builder was exercised in a test, without database access).
- **Supersedes in part:** `docs/BACKEND_SECURITY_HARDENING_IMPLEMENTATION.md` §3–§5 (flow, variables, authorization). Where they differ, this document is current.

---

## 1. Findings resolved

| ID | Finding | Resolution |
|---|---|---|
| **H1** | Many state-changing / externally-acting POST routes had no write authorization | **Secure-by-default method policy** applied at the router level: every non-GET/HEAD/OPTIONS operation requires a write role unless its endpoint is on an explicit, test-frozen read-style allow-list (11 read-only computations). 14 operations are write-gated, including ingestion runs and retries, Databricks discovery refresh/test, connection validate, pricing refresh, and FinOps ingestion validate/preview. A new route is protected automatically. |
| **H2** | Any valid token for the audience was "authenticated"; `scp` ignored; `azp` unchecked | New baseline layer `require_api_access`: approved calling app (`azp`/`appid` ∈ `ENTRA_ALLOWED_CLIENT_IDS`, mandatory in production) **and** a required delegated scope (`ENTRA_REQUIRED_SCOPES`, default `access_as_user`) **or** an application role. 401 = authentication failure; 403 = authorization failure. |
| **M1** | Tenant defaulted to a hard-coded GUID, making "required" vacuous | Default removed (`None`). Auth requires an explicit, GUID-formatted `ENTRA_TENANT_ID` in every environment where Entra is enabled, and in production. |
| **M2** | `/docs`, `/redoc`, `/openapi.json` public in production | Disabled (404) in production; unchanged in development/testing. Root endpoint reports `"docs": "disabled"` in production. |
| **M3** | Scripts inherited full web-server production requirements | Validation split: construction-time **consistency** checks (explicit `APP_ENV`, no dev auth outside dev/test or on hosting platforms, coherent Entra settings) apply everywhere; **serving** requirements live in `Settings.validate_for_serving()`, called by `create_app()` and the lifespan, never by scripts. Scripts use `get_operational_settings()`; migration errors are credential-redacted. |
| **M5** | `APP_ENV` silently defaulted to `development` | `APP_ENV` must be set explicitly to a valid value or `Settings` raises `InsecureConfigurationError` (also at import of `cloud_recommender.main`, so an unconfigured server cannot start). Dev auth is additionally refused on managed hosting platforms (`CONTAINER_APP_NAME`, `WEBSITE_SITE_NAME`, `DATABRICKS_APP_PORT`, `KUBERNETES_SERVICE_HOST`, `FUNCTIONS_WORKER_RUNTIME`), at construction **and** at request time. |

Additional hardening done along the way (no change in intent): production CORS now also requires `https://` origins (review L9); the dev identity logs a warning whenever used; the 403 error code for missing write role stays `INSUFFICIENT_PERMISSIONS` so the existing API contract is unchanged.

---

## 2. Files changed (this task)

| File | Change |
|---|---|
| `backend/src/cloud_recommender/core/config.py` | Explicit `APP_ENV` validator; tenant default removed; `ENTRA_REQUIRED_SCOPES`, `ENTRA_ALLOWED_CLIENT_IDS`; hosted-runtime detection; consistency validator vs `validate_for_serving()`; `get_operational_settings()`; `redact_connection_string()` |
| `backend/src/cloud_recommender/core/auth.py` | `client_id`, `is_development_identity`; `require_api_access`; `enforce_route_policy`; `READ_ROLES`, `READ_STYLE_NON_GET_ENDPOINTS`; hosted-runtime re-check for dev identity |
| `backend/src/cloud_recommender/api/v1/router.py` | Router-level dependency is now `enforce_route_policy` |
| `backend/src/cloud_recommender/main.py` | `validate_for_serving()` in `create_app` and lifespan; docs disabled in production |
| `backend/scripts/run_migrations.py`, `databricks_access_audit.py` | Use `get_operational_settings()`; redacted error output |
| `backend/tests/test_security_hardening.py` | Rewritten for the new model (106 tests) |
| `backend/tests/test_route_authorization_policy.py` | **New**, route-policy sweep (7 tests) |
| `backend/tests/security_fixtures.py` | Extended: constants, RSA/token/app helpers |
| `backend/tests/conftest.py`, `test_config.py`, `test_databricks_workspace.py` | Explicit `APP_ENV=testing` for the session; invalid-environment test expects `InsecureConfigurationError`; one Databricks test pins `APP_ENV=production` for its scenario |

Earlier-task files (routes, health, etc.) are unchanged by this task, except that the five per-route role dependencies remain as defence in depth alongside the router policy. Not changed: `.env*`, `app.yaml`, migrations, `schemas/domain.py`, `docs/ADR/*`, frontend, `fabric-integration/`.

---

## 3. Authorization model

### 3.1 Layers (every protected request, in order)

| # | Layer | Failure |
|---|---|---|
| 1 | Valid Entra JWT: RS256 signature, tenant issuer (v1/v2), audience, `tid`, `exp`, `nbf` | **401** |
| 2 | Approved client: `azp` (v2) or `appid` (v1) ∈ `ENTRA_ALLOWED_CLIENT_IDS` (mandatory in production; skipped only if the list is empty outside production) | **403** `UNAPPROVED_CLIENT_APPLICATION` |
| 3 | API access: token has ≥ 1 scope from `ENTRA_REQUIRED_SCOPES` (delegated tokens) **or** a role in `READ_ROLES ∪ WRITE_ROLES` (application tokens / role-based access) | **403** `INSUFFICIENT_SCOPE` |
| 4 | Method policy: non-GET/HEAD/OPTIONS needs a `WRITE_ROLES` role unless the endpoint is classified read-style | **403** `INSUFFICIENT_PERMISSIONS` |
| – | Endpoint-specific: `POST /finops/ingestion/approval-token` additionally requires `Admin`, `FinOpsAdministrator` or `PlatformAdministrator` (unchanged, narrower) | **403** |

A valid signature and audience alone grants nothing. The development identity (no token) skips layers 2–3, holds only `DEV_AUTH_ROLES` (default `Reader`), and still passes through layer 4.

### 3.2 Required Entra configuration (to be created later; nothing was created)

| Item | Value / purpose |
|---|---|
| Application ID URI / audience | `ENTRA_AUDIENCE` |
| Exposed delegated scope | `access_as_user` (default; configurable via `ENTRA_REQUIRED_SCOPES`) |
| Approved clients | SPA / client application IDs → `ENTRA_ALLOWED_CLIENT_IDS` (GUIDs) |
| App roles | `FinOpsReader` (read), `Reader` (read, also the dev default); write set: `Admin`, `FinOpsAdmin`, `FinOpsAdministrator`, `PlatformAdministrator` |
| Enterprise application | "Assignment required = Yes" recommended so only assigned users/groups can obtain tokens |
| Token version | v2 recommended (`azp`); v1 tokens (`appid`) are also interpreted |

### 3.3 Authorization matrix

Legend: **Auth** = layers 1–3 (token + approved client + scope/role). **Write** = additionally a `WRITE_ROLES` role. 401 without a token for every row except **Public**.

| Operation(s) | Policy |
|---|---|
| `GET /`, `GET /health`, `GET /health/ready`, `GET /api/v1/health`, `GET /api/v1/health/ready`, `GET /api/v1/catalog/services[...]` (3) | **Public** (no token) |
| All other `GET` operations (connections, configuration, ingestion reads, Databricks reads, FinOps reads, inventory, monitoring, pricing reads) | **Auth** |
| `POST /analysis/requirements`, `POST /architecture/generate` | **Auth** (read-style computation) |
| `POST /finops/forecast-budgets/simulate`, `POST /pricing/simulate` | **Auth** (read-style) |
| `POST /inventory/azure/analyze`, `/inventory/gcp/analyze`, `/inventory/compare` | **Auth** (read-style) |
| `POST /monitoring/overview`, `/resource`, `/logs`, `/token-economics` | **Auth** (read-style) |
| `POST /connections` | **Write** |
| `POST /connections/validate` | **Write** |
| `POST /configuration` | **Write** |
| `POST /databricks/connections/{id}/test` | **Write** |
| `POST /databricks/connections/{id}/discovery/refresh` | **Write** |
| `POST /ingestion/{connection_id}/runs`, `POST /ingestion/runs/{run_id}/retry` | **Write** |
| `POST /finops/ingestion/validate`, `/ingestion/preview`, `/ingestion/run` | **Write** |
| `POST /finops/ingestion/approval-token` | **Write** + approval-role subset |
| `POST /finops/optimization-advisor/{id}/action`, `POST /finops/anomalies/{id}/status` | **Write** |
| `POST /pricing/refresh` | **Write** |
| Any new non-GET route | **Write** by default; read-style only by editing both the app allow-list and the frozen test list |
| `/docs`, `/redoc`, `/openapi.json` | Development/testing only; **404 in production** |

---

## 4. Configuration reference (names only)

**Always (construction time):** `APP_ENV` must be explicitly one of `development|testing|staging|production`; `ENTRA_AUTH_ENABLED=true` ⇒ `ENTRA_TENANT_ID` (GUID) and `ENTRA_AUDIENCE`; `DEV_AUTH_ENABLED` only in development/testing and never on a hosting platform.

**Production web server (`validate_for_serving`)**: `ENTRA_AUTH_ENABLED=true`, `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE`, `ENTRA_REQUIRED_SCOPES` (non-empty; default present), `ENTRA_ALLOWED_CLIENT_IDS` (GUID list, non-empty), `SECRET_KEY`, `FINOPS_SIGNING_SECRET`, `CORS_ORIGINS` (explicit, `https://`, no localhost/wildcard), `DEBUG=false`.

**Operational scripts:** `APP_ENV` + their own settings (e.g. `DATABASE_URL`) only. List variables accept a JSON array or a comma/space separated string.

---

## 5. Tests and results

| Check | Result |
|---|---|
| Full backend suite (`pytest backend/tests`, coverage on) | **777 passed, 8 skipped, 0 failed** (prior state: 712 passed; baseline before any hardening: 664 passed). Coverage 87% |
| Security tests (`test_security_hardening.py`) | 106 passed |
| Route authorization coverage (`test_route_authorization_policy.py`) | 7 passed: all operations 401 without token except the frozen public list; every non-GET 403 for a scoped reader except the frozen read-style list; allow-list integrity; meta-tests prove the sweep detects a newly added unprotected route and that a new route behind the router defaults to write-role-required |
| `ruff check src tests scripts` | pass |
| `ruff format --check src tests scripts` | pass (151 files) |
| `mypy src` | pass (92 files, no issues) |
| `mypy src tests` (CI command) | one error that **pre-exists** and is unrelated: `tests/fixtures/billing_baseline.py` found under two module names, which stops the run. Running mypy on the new test files directly shows only `import-untyped` / `no-any-return` noise caused by the local environment resolving `cloud_recommender` as an installed package (same noise exists for `conftest.py`) |

Coverage of each finding:

| Finding | Tests |
|---|---|
| H1 | 13 parametrised write-path 403 tests; per-write-role pass-through; read-style needs only API access; route sweep; new-route default; dev identity cannot write unless granted |
| H2 | no scope/role → 403; wrong scope → 403; app token needs role; unapproved/missing client → 403; `appid` accepted; string `roles`; 401-vs-403 separation |
| M1 | no default tenant; production without tenant fails; GUID format enforced |
| M2 | `/docs`, `/redoc`, `/openapi.json` → 404 in production, 200 in development; root hides docs |
| M3 | operational settings load under production with only DB settings yet cannot start/serve; dev auth still rejected; migration runner config builds under minimal production env; scripts reference only operational settings; DSN redaction |
| M5 | missing/empty/invalid `APP_ENV` fails; dev auth rejected in production/staging and on each hosting marker (construction and runtime); runtime re-check with validation bypassed |

**Pre-existing failures:** none. Two existing tests needed adaptation, not because of bugs but because behaviour intentionally changed: invalid `APP_ENV` now raises `InsecureConfigurationError` instead of a pydantic `ValidationError`; and one Databricks test relies on `os.environ["APP_ENV"]` taking priority over `settings.app_env`, so it now pins `APP_ENV=production` explicitly.

---

## 6. Operational notes / behaviour changes

1. **`APP_ENV` is mandatory.** Importing `cloud_recommender.main` (e.g. `uvicorn cloud_recommender.main:app`) without it fails immediately. The existing local `.env` already contains an `APP_ENV` key (value not inspected); `app.yaml` sets `production`.
2. **Local development** still needs `DEV_AUTH_ENABLED=true` (from the previous task) and, for write routes, `DEV_AUTH_ROLES=["Admin","Reader"]`. `.env` was not modified.
3. **`app.yaml` (Databricks Apps)** will not start in production until `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE`, `ENTRA_ALLOWED_CLIENT_IDS`, `SECRET_KEY`, `FINOPS_SIGNING_SECRET` and `CORS_ORIGINS` are supplied (and `ENTRA_AUTH_ENABLED=true`). Intended.
4. **Existing UIs** still cannot obtain a backend-audience token (frontend work, outside this task).
5. Once Entra is enabled, users need at least the delegated scope (or a read role) to use any API, and a write role for the 14 write operations.

---

## 7. Outstanding findings

| ID | Status | Note |
|---|---|---|
| H1, H2, M1, M2, M3, M5 | **Resolved** | See §1 |
| M4 | Open (out of scope) | Next.js UI sends no token; Fabric SPA sends a Rayfin token. Needs the MSAL backend-audience flow (frontend task) |
| L1 | Open | `WWW-Authenticate` header still dropped by the custom HTTP exception handler |
| L2 | Open | Library/exception text still appears in some 401/500 messages |
| L3 | Open | No JWT clock-skew leeway |
| L4 | Open | `EntraTokenValidator(test_keys=…)` hook not restricted to testing; token `ver` not pinned |
| L5 | Open | `finops_verification_keys` strength unchecked; `secret_key` is validated but unused in `src` |
| L6 | Open | Unauthenticated `/health/ready` still performs a DB probe and reports integration status |
| L7 | Open | Legacy direct-call branch in `issue_approval_token` |
| L8 | Partly resolved | Route-policy sweep added; no tests yet for `WWW-Authenticate`/leeway |
| L9 | Resolved | Production CORS requires `https://` |
| New | Observation | `staging` is not subject to the production serving rules (only dev-auth is refused there) |
| New | Observation | Allow-listed read-style POSTs (LLM/analysis, inventory analyze, monitoring queries) can still incur provider cost for any holder of API access; consider a per-user rate limit |
| New | Observation | Scope names and role names are conventions defined here; they must be created in the Entra app registration exactly as listed in §3.2 |

---

## 8. Next step

Proceed with Entra API integration (app registration, app roles, approved client IDs, SPA token flow) using §3.2, then re-run the route sweep (`pytest backend/tests/test_route_authorization_policy.py`) and the security suite against the deployed configuration. Remaining Low findings can be batched into one follow-up.
