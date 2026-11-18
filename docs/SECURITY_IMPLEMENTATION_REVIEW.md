# Security Implementation Review — `feature/backend-security-hardening`

- **Reviewed:** working-tree diff against `902d2208` (12 modified + 3 new files), `docs/BACKEND_SECURITY_HARDENING_IMPLEMENTATION.md`, `backend/tests/test_security_hardening.py`.
- **Method:** read the diff; executed read-only, in-process probes against `create_app()` with throw-away keys and a production-style `Settings` (no network, no cloud calls, no files modified, no packages installed, no environment variables changed). Probe scripts live in the session scratchpad, not in the repo.
- **Date:** 2026-11-16.

---

## 0. Verdict

**GO for Entra API integration**, conditional on the findings below being tracked as part of that work. **NO-GO for any production deployment** until High findings H1 and H2 and Medium findings M1–M4 are closed.

Reason: the authentication core (token validation, fail-closed defaults, startup guards) is sound and verified. The remaining problems are **authorization design** (who may do what once authenticated) and **operational compatibility**. Both are naturally resolved while defining the Entra app registration, app roles and the SPA token flow, so they should not block starting that work, but they must be finished before anything is exposed.

---

## 1. Summary of Review Questions

| # | Question | Result | Evidence |
|---|---|---|---|
| 1 | Every protected API rejects missing and invalid tokens | **PASS** | Black-box sweep of all **82** OpenAPI operations on a production-style app: every operation returned 401 for no token **and** for a garbage token except 8 intentionally public ones (see §2). |
| 2 | JWT issuer/audience/tenant/signature/exp/nbf validation | **PASS** (minor notes L3, L4) | `core/auth.py::EntraTokenValidator.validate_token`; 48 new tests incl. each claim. |
| 3 | Role enforcement on all sensitive writes | **FAIL (partial)** | 5 routes gated; **≥ 7 other state-changing or externally-acting POST routes are not** (H1). |
| 4 | Routes that accidentally bypass auth | **PASS** | Only `/`, `/health`, `/health/ready`, `/api/v1/health*`, `/api/v1/catalog/*` are public; all intentional. |
| 5 | `/docs`, `/redoc`, `/openapi.json` | **FAIL** | All three return 200 without a token in production configuration; 318 KB schema exposing 82 operations (M2). |
| 6 | `scp` and `roles` interpreted and enforced | **PARTIAL** | `roles` parsed correctly and enforced on 5 routes; `scp` parsed and **never enforced**; no baseline role/scope for authenticated access (H2). |
| 7 | Production cannot enable dev auth | **PASS with caveat** | Startup validator rejects `DEV_AUTH_ENABLED` outside development/testing; runtime re-check in `get_current_user`. Caveat: guard keys off `APP_ENV` only (M5). |
| 8 | Azure and Databricks compatibility | **PARTIAL** | Integration code untouched and 712 tests pass; but operational scripts, `app.yaml` and the Next.js frontend are affected (M3, M4). |
| 9 | Security regressions introduced | **None of High severity introduced**; two compatibility regressions (M3, M4), one minor header regression (L1). |

---

## 2. Verified Facts (what is correct)

1. **Authentication sweep (verified by execution).** 82 operations: 74 return 401 for both "no token" and "garbage token"; 8 public GETs: `/`, `/health`, `/health/ready`, `/api/v1/health`, `/api/v1/health/ready`, `/api/v1/catalog/services`, `/api/v1/catalog/services/{provider}/{service_id}`, `/api/v1/catalog/services/{service_id}`. No public POST/PUT/PATCH/DELETE exists.
2. **JWT checks** (`validate_token`): RS256 only (header `alg` checked before key lookup); `audience`, `issuer` (v1 and v2 tenant issuers), `exp`, `nbf`, `iat` verified; `exp`, `nbf`, `iss`, `aud` required; `tid` required and must equal `ENTRA_TENANT_ID`; missing tenant/audience configuration rejects every token (`AUTH_NOT_CONFIGURED`). Signature verification uses JWKS or injected test keys only.
3. **Dev auth.** A supplied token is always validated; invalid → 401 in all environments; dev identity only when Entra is off, `DEV_AUTH_ENABLED=true` and `APP_ENV ∈ {development, testing}`; default roles `["Reader"]`. Production/staging with `DEV_AUTH_ENABLED=true` → startup failure.
4. **Startup guard** (`Settings.validate_security_configuration`): raises `InsecureConfigurationError` (not `ValueError`, so pydantic cannot echo `input_value`), names variables only.
5. **CORS** (`main.py`): production methods `GET, POST, OPTIONS`; headers `Authorization, Content-Type, Accept`; preflight verified (200 with those headers).
6. **Health sanitisation**: DB probe reduced to a status flag; verified by test.
7. **Role gating verified for**: `POST /connections`, `POST /configuration`, `POST /finops/optimization-advisor/{id}/action`, `POST /finops/anomalies/{id}/status`, `POST /finops/ingestion/run` (403 for `Reader`).

---

## 3. Findings

Severity scale: **High** = exploitable authorization gap or deployment blocker; **Medium** = should fix before production; **Low** = hardening / hygiene.

### H1 — Sensitive state-changing / externally-acting routes have no role requirement (HIGH)

- **Files / functions:**
  - `api/routes/ingestion.py::trigger_run` (`POST /api/v1/ingestion/{connection_id}/runs`) and `retry_run` (`POST /api/v1/ingestion/runs/{run_id}/retry`)
  - `api/routes/databricks.py::refresh_workspace_discovery` (`POST …/discovery/refresh`) and `test_databricks_connection` (`POST …/test`)
  - `api/routes/connections.py::validate_connection` (`POST /connections/validate`)
  - `api/routes/pricing.py::refresh_prices` (`POST /pricing/refresh`, rewrites the price cache from an external API)
  - `api/routes/finops.py::validate_ingestion`, `preview_ingestion` (`POST /finops/ingestion/validate|preview`)
- **Evidence:** the route map shows these POSTs carry only `require_authenticated_user` (router-level). The implementation document (§5) states that "write roles" gate "operations that persist state or can trigger spend/ingestion" yet lists only five routes; the scope-aware ingestion trigger, which persists run records and pulls cloud data, is not among them. `finops/ingestion/run` is gated while the equivalent `ingestion/{id}/runs` is not, which is inconsistent.
- **Impact:** any holder of a valid token for the audience can trigger ingestion runs, live Databricks discovery (REST load against the customer workspace), and cache rewrites. This does not violate the read-only/zero-execution boundary toward customer clouds, but it permits unprivileged state change and load.
- **Correction:** define the rule once, "every non-GET route requires `WRITE_ROLES` unless explicitly listed as a read-style POST (e.g. `simulate`, `analysis`, `architecture`, `inventory/*/analyze`, `monitoring/*`)". Apply `Depends(require_roles(*WRITE_ROLES))` to the routes above (or a dedicated `OPERATOR_ROLES` for refresh/test/validate). Add a **route-policy test** that enumerates `app.openapi()` and fails when a non-GET operation is neither role-gated nor on an explicit allow-list (the same sweep used in this review).

### H2 — No baseline authorization: any valid token for the audience is "authenticated"; `scp` is ignored (HIGH)

- **File / function:** `core/auth.py::validate_token` (returns `AuthenticatedUser` with `scopes` populated) and `get_current_user`; `api/v1/router.py` (`auth_deps = [Depends(require_authenticated_user)]`).
- **Evidence:** `require_authenticated_user` returns the user without checking `roles` or `scopes`. `scopes` is parsed (`raw_scp.split(" ")`) but referenced nowhere in `src`. No check on `azp`/`appid`, `idtyp`, or token type (delegated vs application-only).
- **Impact:** every read endpoint (all FinOps cost, billing, inventory and Databricks data) is available to any principal that can obtain a token for the API. In Entra this is *every user in the tenant* unless the enterprise application has "Assignment required = Yes", and any app granted the API's permissions (including app-only tokens carrying only `roles`).
- **Correction:** add a baseline gate on the whole protected router: require a role from a defined set (e.g. `FinOps.Reader` or any `WRITE_ROLES`) **or** the delegated scope (e.g. `access_as_user`). Document which claim is authoritative: roles for app/user permissions, `scp` for delegated SPA access. Consider checking `azp` against the SPA client ID. Enforce "Assignment required" on the enterprise application. Add tests for: valid token with no role/scope → 403; delegated scope accepted; app-only token handling.

### M1 — "`ENTRA_TENANT_ID` is required in production" is vacuous because the field has a hard-coded default (MEDIUM)

- **File / function:** `core/config.py` `Settings.entra_tenant_id` (default `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`) and `validate_security_configuration`.
- **Evidence (executed):** `Settings(app_env="production", …all other security fields…)` with `entra_tenant_id` omitted starts successfully and resolves to the default GUID. Implementation doc §4 lists the variable as "required … valid GUID".
- **Impact:** a deployment that forgets `ENTRA_TENANT_ID` silently trusts a specific tenant baked into source. Not a bypass for this organisation, but the control does not do what is documented, and it would be wrong for any other tenant.
- **Correction:** default to `None`; require explicit `"entra_tenant_id" in model_fields_set` (or non-default) in production. Update the existing tests that rely on the default tenant.

### M2 — OpenAPI/Swagger/ReDoc publicly exposed in every environment (MEDIUM)

- **File / function:** `main.py::create_app` (`docs_url="/docs"`, `redoc_url="/redoc"`, `openapi_url="/openapi.json"`).
- **Evidence (executed, production settings, no token):** `/docs` 200, `/redoc` 200, `/openapi.json` 200 (318,141 bytes, 82 operations incl. request/response schemas and internal route names). They are outside `auth_deps`.
- **Correction:** in production pass `docs_url=None, redoc_url=None, openapi_url=None`, or protect them with `require_authenticated_user` plus a role. Add a test.

### M3 — Operational scripts and ops tooling now require the full production security configuration (MEDIUM, compatibility)

- **Files:** `backend/scripts/run_migrations.py` (`get_settings()` at lines 32 and 103), `backend/scripts/databricks_access_audit.py:228`, `main.py` (module-level `app = create_app()` builds Settings at import).
- **Evidence:** `Settings` validation runs on any construction; with `APP_ENV=production` a migration or audit run now fails unless Entra, secrets and CORS are all set, even though those scripts never serve HTTP.
- **Impact:** a controlled migration job (explicitly an operator step per policy) cannot run in a production-labelled environment without injecting unrelated secrets, which encourages copying secrets into job configs.
- **Correction:** keep strict validation for the web process (e.g. validate in `create_app()`/lifespan, or via a `Settings.validate_for_serving()` called there) and let non-serving scripts load Settings without the serving-only checks. Add a test for the migration runner under `APP_ENV=production` with only DB settings.

### M4 — Existing UIs cannot authenticate against the hardened backend (MEDIUM, compatibility)

- **Evidence:** the Next.js `frontend/` never sends an `Authorization` header (the only grep hit in `frontend/src` is unrelated UI text). The Fabric SPA sends a Rayfin session token which the backend now rejects. In production the Databricks Apps path (`app.yaml` sets none of `ENTRA_*`, `SECRET_KEY`, `FINOPS_SIGNING_SECRET`, `CORS_ORIGINS`) will fail to start, and even with those values the Next.js UI would receive 401 for every `/api/v1` call.
- **Impact:** the existing V1 demo deployment path stops working in production by design until a token flow exists. This is the intended consequence of fail-closed behaviour, but it means "Azure and Databricks integrations remain compatible" holds for the backend code only, not for end-to-end deployments.
- **Correction:** deliver the SPA token flow (MSAL, backend-audience scope) as the next task; for Databricks Apps decide whether to validate Databricks-forwarded identity or keep that target non-production. Do not weaken the backend to accommodate either.

### M5 — Production guards depend solely on `APP_ENV` (MEDIUM)

- **File / function:** `core/config.py` (`app_env` default `"development"`; `validate_security_configuration`).
- **Evidence:** if a hosted instance is started without `APP_ENV=production`, none of the production checks apply: default CORS (includes localhost, permissive methods/headers), default `SECRET_KEY`, optional signing secret. If such an instance also sets `DEV_AUTH_ENABLED=true`, every caller is an anonymous `Reader` over real cloud data. `api_host` default is `0.0.0.0`.
- **Correction:** (a) default `app_env` to `production` or fail when unset in a container (e.g. detect `CONTAINER_APP_NAME`, `WEBSITE_SITE_NAME`, `DATABRICKS_APP_PORT`); (b) permit `DEV_AUTH_ENABLED` only when `api_host` is a loopback address; (c) log a prominent startup warning whenever dev auth is active. Optional: extend the signing-secret and Entra requirements to `staging`.

### L1 — `WWW-Authenticate` header dropped on 401 (LOW)

- **File / function:** `main.py::http_exception_handler` returns `JSONResponse` without `exc.headers`.
- **Evidence (executed):** header absent on all 401 responses even though `get_current_user` sets it.
- **Correction:** pass `headers=exc.headers` in the handler (RFC 6750 compliance; helps MSAL/clients).

### L2 — Authentication error messages disclose library detail (LOW)

- **File / function:** `core/auth.py` (`Unable to parse JWT header: {exc}`, `Token decoding failed: {exc}`, `…not found in JWKS: {exc}`); also `ingestion.py::trigger_run` returns `Ingestion run failed unexpectedly: {exc}` (pre-existing).
- **Correction:** return generic client messages with stable `error_code`; log the detail server-side only.

### L3 — No clock-skew leeway (LOW, availability)

- **Evidence:** `jwt.decode(...)` call has no `leeway`; `nbf`/`exp`/`iat` are checked with zero tolerance.
- **Impact:** tokens issued by Entra can be rejected as "not yet valid" under small clock drift between the caller and the host.
- **Correction:** `leeway=60` (seconds) on `jwt.decode`; keep tests for 10-minute-future `nbf`.

### L4 — Token-validation test hook and issuer breadth (LOW)

- **File:** `core/auth.py::EntraTokenValidator(test_keys=…)` — bypasses JWKS and any `kid`; never set in app code but is a production-reachable parameter. Both v1 and v2 issuers are accepted for the tenant; acceptable, but `ver` is not checked against the app registration's `accessTokenAcceptedVersion`.
- **Correction:** assert `test_keys` only when `app_env == "testing"`; pin the accepted token version once the app registration exists.

### L5 — Key-ring and secret hygiene gaps (LOW)

- `finops_verification_keys` (HMAC verification key ring in `services/databricks/sql_client.py:443`) is not strength-checked by the production guard.
- `secret_key` is validated but **not referenced anywhere in `src`** (grep), so the check gives false assurance; either use it or remove it.
- Marker-based placeholder detection may reject legitimately random secrets that happen to contain `example`, `default`, `replace` or `xxx` (very unlikely); document this.

### L6 — `/health/ready` is unauthenticated and does work per call (LOW)

- Each call opens a DB connection (2 s timeout) and returns integration state (`azure_integration`, `llm_orchestration.provider`, `microsoft_fabric`, `pricing_engine.mode`) plus `version`. Minor disclosure and a cheap amplification vector.
- **Correction:** return only `status` in production, cache the probe for a few seconds, and rate-limit at the platform edge.

### L7 — Legacy test hook in the approval-token route (LOW)

- `api/routes/finops.py::issue_approval_token` contains `if not isinstance(current_user, AuthenticatedUser): … current_user = get_current_user()`. Unreachable through FastAPI (the dependency always yields `AuthenticatedUser`), but a direct call raises `AttributeError` and the branch trusts a body-supplied `approver_roles`. Remove the harness branch and have tests use dependency overrides.

### L8 — Test-suite coverage gaps (LOW)

- No test enumerates routes to prove auth/role policy (add the sweep from H1).
- Role-403 tests cover 3 of the 5 gated routes in the new file (`connections` is in `test_entra_auth.py`; `optimization-advisor/action` has none).
- `conftest.py` sets `DEV_AUTH_ENABLED=true` for the whole legacy suite, so default-deny behaviour is exercised only by the dedicated hardening tests (acceptable, but note it).
- No tests for docs exposure, `WWW-Authenticate`, leeway, or the `staging` environment.

### L9 — Production CORS permits non-TLS origins (LOW)

- `is_local_origin` rejects localhost/loopback/`*`, but `http://` non-local origins are accepted. Require `https://` in production.

---

## 4. Checks Specifically Requested

### 4.1 Missing / invalid tokens → 401 on every protected API
PASS. 74 of 74 protected operations returned 401 without a token and with `Bearer garbage.token.value`. Public set listed in §2.

### 4.2 JWT validation matrix

| Check | Implementation | Test | Status |
|---|---|---|---|
| Signature RS256 | `alg` header check + `jwt.decode(algorithms=["RS256"])` | invalid signature; HS256 forged | PASS |
| Issuer | v1/v2 tenant issuers | wrong issuer | PASS |
| Audience | mandatory, `ENTRA_AUDIENCE` | wrong audience; validator without audience | PASS |
| Tenant | `tid` required and equal | wrong tenant; missing `tid` | PASS (M1: tenant default) |
| Expiry | `verify_exp`, required | expired; missing `exp` | PASS |
| Not-before | `verify_nbf`, required | future `nbf`; missing `nbf` | PASS (L3: no leeway) |

### 4.3 Roles / scopes
`roles`: string-or-list handled; compared case-sensitively with `WRITE_ROLES`. `scp`: split into `scopes`, unused. Group/`wids` claims ignored. No baseline role/scope (H2).

### 4.4 Dev-auth in production
Startup rejects; runtime re-check present and tested with `model_construct` (validation bypassed) → 401. Residual risk M5.

### 4.5 Azure / Databricks compatibility
Integration modules unchanged; 712 passed / 8 skipped (baseline 664 / 8) with five existing tests adapted only to supply valid production security settings. Residual compatibility issues: M3, M4. Databricks auth (`oauth` service principal) and Azure service-principal paths are independent of the new settings (they do not read `entra_*` or `dev_auth_*`); `reload_settings()` still constructs `Settings` and will now apply the same validation.

---

## 5. Prioritised Remediation Plan

| Priority | Item | Effort |
|---|---|---|
| 1 | H1: role policy for all non-GET routes + route-policy test | S |
| 2 | H2: baseline role/scope gate, decide `scp` vs `roles`, `azp` check | S–M (needs app registration design) |
| 3 | M1: remove tenant default; M2: disable/protect docs in production | XS |
| 4 | M3: split serving-only validation from `Settings` construction | S |
| 5 | M5: environment detection / loopback-only dev auth | S |
| 6 | L1–L3, L7, L9 | XS each |
| 7 | M4: SPA token flow (separate task, needed for integration) | M |

---

## 6. Recommendation

### **GO — proceed to Entra API integration** (app registration design, app roles, SPA token flow, token compatibility test).

Conditions:
1. Treat **H1 and H2** as part of the same work: the app-role definitions and the baseline gate are designed together with the registration.
2. Do **not** deploy or expose the backend to a Fabric-hosted frontend until H1, H2, M1, M2, M3 and M5 are fixed and re-reviewed.
3. Re-run the route sweep and this review after those fixes.

*No files other than this document were created or modified during the review.*
