# Backend Security Hardening — Implementation Report

- **Branch:** `feature/backend-security-hardening` (created from `feature/live-finops-kpi-integration`)
- **Starting commit:** `902d2208c884a0233ba05bf5217ea83f80213070` ("V1 Ready for demo fore real values")
- **State:** changes are **uncommitted** in the working tree (nothing committed or pushed).
- **Scope:** FastAPI backend only. No frontend, schema, migration, `.env`, cloud, Databricks or Fabric change.

> **Update:** the authentication flow, required variables and authorization strategy in §3–§5 were extended by `docs/SECURITY_REVIEW_REMEDIATION.md` (scope/client baseline, secure-by-default write policy, explicit `APP_ENV`, no default tenant, docs disabled in production, split serving vs script configuration). Where they differ, the remediation document is current.

## 1. Vulnerabilities fixed (each verified against the code first)

| # | Finding in earlier reports | Verified on branch | Fix |
|---|---|---|---|
| V1 | `ENTRA_AUTH_ENABLED` defaults to `false`; when false every caller became an `Admin` dev identity (`core/auth.py` `get_current_user`) | Confirmed | Dev identity now requires explicit `DEV_AUTH_ENABLED=true`, only in `development`/`testing`, and is **Reader-only** by default |
| V2 | Invalid / forged / expired tokens were swallowed (`except Exception: pass`) and downgraded to the dev Admin identity | Confirmed | Any supplied bearer token is always validated; failure is always HTTP 401 |
| V3 | Audience check skipped when `ENTRA_AUDIENCE` unset (`verify_aud = bool(audience)`) | Confirmed | Audience, issuer, tenant mandatory; validator rejects every token (401 `AUTH_NOT_CONFIGURED`) if tenant/audience are missing |
| V4 | `tid` check only applied if the claim was present | Confirmed | `tid` is required and must equal `ENTRA_TENANT_ID`; `exp`, `nbf`, `iss`, `aud` are required claims |
| V5 | Production could start with insecure/default `SECRET_KEY`, missing `FINOPS_SIGNING_SECRET`, auth off, localhost CORS | Confirmed | Startup validation (see §4) |
| V6 | CORS `allow_methods/headers=["*"]` with credentials in every environment | Confirmed | Production: `GET, POST, OPTIONS` and `Authorization, Content-Type, Accept` only |
| V7 | `/health/ready` returned DB host, database name, driver, DSN target and raw driver exception text | Confirmed | Public probe returns only `connected` / `disconnected` + generic `database_unreachable`; environment label omitted in production |
| V8 | Only `connections` create enforced roles; other state-changing / spend-relevant routes were open to any authenticated caller | Confirmed | Write roles enforced on 5 routes (§5) |

## 2. Files changed

| File | Change |
|---|---|
| `backend/src/cloud_recommender/core/config.py` | New `dev_auth_enabled`, `dev_auth_roles`; `InsecureConfigurationError`; `is_insecure_secret`, `is_local_origin`; `model_validator` `validate_security_configuration` |
| `backend/src/cloud_recommender/core/auth.py` | Strict `validate_token`; rewritten `get_current_user`; role constants `WRITE_ROLES` etc. |
| `backend/src/cloud_recommender/main.py` | Production-restricted CORS methods/headers |
| `backend/src/cloud_recommender/api/routes/health.py` | Sanitised DB status; environment hidden in production |
| `backend/src/cloud_recommender/api/routes/connections.py` | Create-connection uses `WRITE_ROLES` |
| `backend/src/cloud_recommender/api/routes/configuration.py` | Save configuration requires `WRITE_ROLES` |
| `backend/src/cloud_recommender/api/routes/finops.py` | Decision action, anomaly status and ingestion run require `WRITE_ROLES` |
| `backend/tests/test_security_hardening.py` | **New**, 48 tests |
| `backend/tests/security_fixtures.py` | **New**, shared valid production security settings (throw-away values) |
| `backend/tests/conftest.py` | Opt in to dev auth for the legacy suite (`DEV_AUTH_ENABLED`, `DEV_AUTH_ROLES` env defaults; test settings) |
| `backend/tests/test_config.py`, `test_databricks_workspace.py`, `test_m2_5_auth_separation.py`, `test_milestone_3j3_security.py` | Existing tests that built a bare `app_env="production"` now supply valid production security settings (or use `staging` for the service-level fail-closed check). Test intent unchanged |
| `docs/BACKEND_SECURITY_HARDENING_IMPLEMENTATION.md` | This document |

Not changed: `schemas/domain.py`, `docs/ADR/*`, migrations, `.env*`, `app.yaml`, frontend, `fabric-integration/`.

## 3. Authentication flow after the change

```
Request ──► get_current_user
  ├─ Bearer token present ─► EntraTokenValidator.validate_token  (ALWAYS, in every environment)
  │      tenant+audience configured? no → 401 AUTH_NOT_CONFIGURED
  │      alg == RS256, signature (JWKS)  → else 401
  │      iss ∈ {login.microsoftonline.com/{tid}/v2.0, sts.windows.net/{tid}/}
  │      aud == ENTRA_AUDIENCE; exp, nbf, iat verified; exp/nbf/iss/aud required
  │      tid claim present and == ENTRA_TENANT_ID
  │      ──► AuthenticatedUser(roles from `roles`, scopes from `scp`)
  ├─ No token, ENTRA_AUTH_ENABLED=true ─► 401 MISSING_BEARER_TOKEN
  ├─ No token, entra off, DEV_AUTH_ENABLED=true, APP_ENV∈{development,testing}
  │      ──► dev identity "local-dev-user", roles = DEV_AUTH_ROLES (default ["Reader"])
  └─ otherwise ─► 401 AUTHENTICATION_REQUIRED
Role gate (require_roles) → 403 INSUFFICIENT_PERMISSIONS
```

Public routes (unchanged): `/`, `/health`, `/health/ready`, `/api/v1/health*`, `/api/v1/catalog`, `/docs`, `/redoc`, `/openapi.json`.

## 4. Environment variables

**Required in production (names only)** — the process refuses to start (`InsecureConfigurationError`) if any is missing or unsafe:

| Variable | Rule |
|---|---|
| `APP_ENV=production` | – |
| `ENTRA_AUTH_ENABLED` | must be `true` |
| `ENTRA_TENANT_ID` | valid GUID |
| `ENTRA_AUDIENCE` | non-empty (client ID or API URI of the backend app registration) |
| `SECRET_KEY` | ≥ 32 chars, ≥ 8 distinct chars, no placeholder/default markers |
| `FINOPS_SIGNING_SECRET` | same rules |
| `CORS_ORIGINS` | explicitly set; no `localhost`/loopback/`*` |
| `DEBUG` | must be `false` |
| `DEV_AUTH_ENABLED` | must be unset/`false` (rejected in production **and staging**) |

Also enforced in **any** environment: `ENTRA_AUTH_ENABLED=true` requires `ENTRA_TENANT_ID` and `ENTRA_AUDIENCE`.
Error messages list variable names only; values are never echoed (the exception is deliberately not a `ValueError`, so pydantic cannot append `input_value`).

Optional: `DEV_AUTH_ROLES` (JSON list, development/testing only).

## 5. Authorization strategy

| Class | Routes | Requirement |
|---|---|---|
| Read / analytics / discovery / pricing / inventory / monitoring / FinOps reads / `POST …/simulate`, analysis, architecture | existing | Any authenticated caller (unchanged; no legitimate read workflow broken) |
| **Write roles** (`Admin`, `FinOpsAdmin`, `FinOpsAdministrator`, `PlatformAdministrator`) | `POST /connections`, `POST /configuration`, `POST /finops/optimization-advisor/{id}/action`, `POST /finops/anomalies/{id}/status`, `POST /finops/ingestion/run` | `roles` claim contains one of them |
| Approval-token issuance | `POST /finops/ingestion/approval-token` | Unchanged and narrower: `Admin`, `FinOpsAdministrator`, `PlatformAdministrator` |

`scp` is parsed but not enforced (Entra app roles are the authorization mechanism). No role is granted implicitly.
**Operational impact:** once Entra is enabled, users need these app roles assigned in the Entra app registration to use the five write routes. Without role definitions, those routes return 403 by design.

## 6. Development vs production behaviour

| | Development / testing | Production |
|---|---|---|
| Tokenless request | Allowed **only** with `DEV_AUTH_ENABLED=true`; identity is Reader-only (not Admin) | 401 |
| Invalid / forged token | 401 | 401 |
| Valid token | Accepted if `ENTRA_*` configured | Accepted |
| CORS | Permissive methods/headers, local origins kept | Restricted verbs/headers, explicit origins only |
| Health | Environment label shown | Environment label hidden |

**Action for local developers:** the old behaviour (implicit Admin without any setting) is gone. Add `DEV_AUTH_ENABLED=true` (and `DEV_AUTH_ROLES=["Admin","Reader"]` if you need write routes) to your local `.env`. I did **not** edit any `.env` file, per the task restrictions, so the existing local `.env` will now get 401 until this is added. Also, a local client that sends a bearer token the backend cannot validate (e.g. the Rayfin session token with no `ENTRA_*` configured) is now rejected rather than ignored.

## 7. Tests

`pytest backend/tests` : **712 passed, 8 skipped, 0 failed** (baseline before changes: 664 passed, 8 skipped), total coverage 87%.

New file `tests/test_security_hardening.py` (48 tests):

| Requirement | Test(s) | Result |
|---|---|---|
| Missing bearer token → 401 | `test_missing_bearer_token_returns_401` | pass |
| Malformed token → 401 | `test_malformed_token_returns_401`, non-RS256 | pass |
| Expired / wrong issuer / wrong audience / wrong tenant claim → 401 | `test_invalid_claims_return_401` (4 params) | pass |
| Missing `tid`/`aud`/`exp`/`nbf`/`iss` → 401; future `nbf` → 401 | parametrised | pass |
| Invalid signature → 401 | foreign key pair | pass |
| Valid token → authenticated | `test_valid_token_is_authenticated` | pass |
| Prod auth disabled / audience / tenant / secrets / CORS / debug / dev-auth → startup failure | `test_production_misconfiguration_fails_startup` (15 params) + explicit-CORS test | pass |
| Secret values never in error text | `test_configuration_error_never_echoes_secret_values` | pass |
| Dev mode explicitly permitted; not enabled → 401 | two tests | pass |
| Invalid / forged token in dev → 401, never Admin | three tests | pass |
| Dev identity not Admin; unreachable in production even if validation bypassed | two tests | pass |
| Validator without audience rejects all tokens | one test | pass |
| Reader blocked (403) on write routes, allowed to read; write role passes gate | two tests | pass |
| Production CORS: origin, localhost and `DELETE` restricted | one test | pass |
| Health leaks nothing (host, user, port, driver, secrets) | one test | pass |

Existing suites (`test_entra_auth.py`, Databricks, FinOps, billing, ingestion, inventory, connections, CORS, health) pass unchanged except the adaptations listed in §2. Tests use in-process throw-away RSA keys and test JWKS injection; no real tokens or secrets.

**Lint / types:** `ruff check src tests` and `ruff format --check src tests` pass; `mypy src` passes (92 files, no issues). `mypy src tests` (the CI command) reports one error that pre-exists and is unrelated (`tests/fixtures/billing_baseline.py` found under two module names, no `__init__.py`). Running mypy on the test files directly also reports `import-untyped` for `cloud_recommender` imports, an environment artifact (the package resolves as installed). I did not run the frontend checks (no frontend change).

## 8. Remaining security gaps

1. **Token compatibility with Fabric/Rayfin is still unproven.** The SPA forwards a Rayfin session token; the backend now (correctly) rejects anything but an Entra token for `ENTRA_AUDIENCE`. The frontend must acquire a backend-audience Entra token (frontend task, out of scope here).
2. No Entra app roles are defined yet; the five write routes will 403 until they are.
3. `scp` is not enforced; `require_roles` is role-only.
4. `/docs`, `/redoc`, `/openapi.json` remain public in production (API surface disclosure).
5. No HTTPS enforcement/HSTS in-app (relies on the hosting platform's TLS termination); no rate limiting.
6. `EntraTokenValidator(test_keys=…)` is a test hook that bypasses JWKS; it is never wired in application code but could be restricted further.
7. The unhandled-exception handler returns `str(exc)` when `DEBUG=true`; production now forces `DEBUG=false`.
8. `app.yaml` (Databricks Apps) sets no `ENTRA_*`, `SECRET_KEY`, `FINOPS_SIGNING_SECRET` or `CORS_ORIGINS`; if it is deployed with `APP_ENV=production` it will now **fail to start** until they are supplied (intended).
9. Frontend/Fabric changes, Key Vault integration, rate limiting and PostgreSQL/network hardening are separate work items.

## 9. Next steps: Entra app registration and token compatibility testing (not performed here)

1. Create an Entra app registration for the backend API; set an Application ID URI; use it (or the client ID) as `ENTRA_AUDIENCE`; set `ENTRA_TENANT_ID`.
2. Define app roles (`Admin`/`FinOpsAdmin`/`FinOpsAdministrator`/`PlatformAdministrator`, plus a reader role) and assign them to users/groups.
3. Register the SPA as a client with a delegated permission to the backend scope; plan admin consent via the tenant admin (not done here).
4. Update the SPA to request a token for that scope (MSAL) instead of forwarding the Rayfin token (frontend change).
5. Start the backend locally with `ENTRA_AUTH_ENABLED=true` and the above settings; run the token compatibility test: decode only non-secret claims (`iss`, `aud`, `exp`, `scp`, `roles`) in-browser, discard the token, and call `/api/v1/connections` expecting 200, plus a negative call with the Rayfin token expecting 401.
6. Provide production secrets (`SECRET_KEY`, `FINOPS_SIGNING_SECRET`, DB, Azure, Databricks) from a secret store; set `CORS_ORIGINS` to the exact Fabric hosting origin.
7. Re-run `docs/FABRIC_PRE_DEPLOYMENT_VALIDATION_REPORT.md` checks against the deployed backend.
