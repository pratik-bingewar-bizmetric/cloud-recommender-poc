# Simplified Authorization, Stage A Report (and Stage B / C Plan)

- **Branch:** `feature/backend-security-hardening` (HEAD `902d220`, all work uncommitted, prior changes preserved).
- **Scope of this report:** Stage A only (route authorization and role simplification). Stages B and C are **not started**; the plan is in §6–§7. Work stops here for your review.
- **Approved decisions applied:** D2, D3, D4, D5, D6 (Stage A parts). D1 and D7 belong to Stage B.
- **Restrictions honoured:** no `.env` change, no migration, no cloud/Databricks/Fabric call, no billing or ingestion execution, no deployment, no commit.

---

## 1. What Stage A changed

| Area | Change |
|---|---|
| Roles (D2) | Six roles collapsed to **one restricted role, `FinOpsAdmin`**. `Admin`, `FinOpsAdministrator`, `PlatformAdministrator`, `Reader`, `FinOpsReader` no longer grant anything (also removed from the approval-token service and handler) |
| Baseline access | Delegated (user) tokens need the API scope (`access_as_user`, configurable). Roles are no longer an alternative to the scope |
| Operation classes | **P** public, **U** any authenticated user (every GET + 18 explicit non-GET operations), **R** `FinOpsAdmin` (default for any other non-GET, secure by default), **D** daemon |
| Daemon (D6) | App-only tokens (no `scp`) need the **separate application permission `FinOpsDaemon`** and may call **only** 4 read-only organization status endpoints. They get no user permissions and cannot reach any restricted operation (billing run and approval token remain human-only) |
| Attribution (D4) | Recommendation action and anomaly status are open to any authenticated user and the audit event records the **token-derived actor** (UPN → name → oid → sub). Removed a hard-coded developer name (`"pratik.bingewar"`) and the placeholder `"finops.operator"` from audit events; client-supplied actor values are ignored |
| Pricing refresh (D5) | Open to any authenticated user with a **15-minute cooldown per connection/subscription scope and region** (`PRICING_REFRESH_COOLDOWN_SECONDS`, default 900, configurable) and **single-flight protection** (409 while one is running, 429 + `Retry-After` during cooldown). The in-flight marker is released if a refresh fails |
| Error headers | The HTTP exception handler now preserves `exc.headers`, so `WWW-Authenticate` (401) and `Retry-After` (429) reach clients (review finding L1) |
| Dev identity | Now an ordinary authenticated user with **no roles by default**; add `FinOpsAdmin` via `DEV_AUTH_ROLES` to exercise restricted operations |

Authentication controls are untouched: Entra JWT validation, issuer/audience/tenant/exp/nbf, approved client (`azp`/`appid`), required scope, production startup guards, dev-auth bans, CORS, health sanitisation, docs off in production.

---

## 2. Authorization matrix after Stage A

Legend: **P** public · **U** authenticated user · **R** `FinOpsAdmin` (user token) · **D** daemon token allowed.

### 2.1 The 14 previously write-gated operations

| # | Operation | Before | After | Note |
|---|---|---|---|---|
| 1 | `POST /connections` | role | **R** (transitional) | Becomes owner operation in Stage B |
| 2 | `POST /connections/validate` | role | **R** (transitional) | Stage B |
| 3 | `POST /configuration` | role | **R** (transitional) | Stage B (also derive `created_by` from token) |
| 4 | `POST /databricks/connections/{id}/test` | role | **U** | Organization connectivity check (REST only) |
| 5 | `POST /databricks/connections/{id}/discovery/refresh` | role | **U** | No cooldown yet, see §5 |
| 6 | `POST /ingestion/{connection_id}/runs` | role | **R** | D3: organization ingestion stays restricted; owner access arrives in Stage B for personal connections |
| 7 | `POST /ingestion/runs/{run_id}/retry` | role | **R** | D3 / Stage B |
| 8 | `POST /finops/ingestion/validate` | role | **U** | Verified: warehouse status read only, no SQL |
| 9 | `POST /finops/ingestion/preview` | role | **U** | Verified: reads the in-memory ingested store, no SQL |
| 10 | `POST /finops/ingestion/run` | role | **R** | Billing execution; signed approval token still required |
| 11 | `POST /finops/ingestion/approval-token` | role + approval set | **R**, user tokens only | Only `FinOpsAdmin`; daemon tokens cannot reach it |
| 12 | `POST /finops/optimization-advisor/{id}/action` | role | **U** + attribution | Advisory state only |
| 13 | `POST /finops/anomalies/{id}/status` | role | **U** + attribution | |
| 14 | `POST /pricing/refresh` | role | **U** + cooldown/single-flight | |

Net: 7 operations moved to **U**, 7 remain **R** (3 of them transitional until Stage B).

### 2.2 Other operations

| Operations | Class |
|---|---|
| `GET /`, `/health`, `/health/ready`, `/api/v1/health[/ready]`, `/api/v1/catalog/services[…]` | **P** |
| All other `GET` operations | **U** |
| 11 read-style POSTs (analysis, architecture, forecast simulate, inventory analyze ×3, monitoring ×4, pricing simulate) | **U** |
| `GET /databricks/connections`, `GET /databricks/connections/{id}/health`, `GET /finops/ingestion/status`, `GET /finops/ingestion/runs` | **U** and **D** (daemon allowed) |
| Any new non-GET route | **R** by default |
| Everything else for daemon tokens | 403 `OPERATION_NOT_PERMITTED_FOR_APPLICATION` |

### 2.3 Status codes

| Situation | Status / code |
|---|---|
| No / invalid token | 401 |
| Valid token, unapproved client | 403 `UNAPPROVED_CLIENT_APPLICATION` |
| User token without required scope | 403 `INSUFFICIENT_SCOPE` |
| Daemon token without `FinOpsDaemon` | 403 `INSUFFICIENT_APPLICATION_PERMISSION` |
| Daemon token on a non-designated endpoint | 403 `OPERATION_NOT_PERMITTED_FOR_APPLICATION` |
| User without `FinOpsAdmin` on a restricted operation | 403 `INSUFFICIENT_PERMISSIONS` (unchanged code) |
| Pricing refresh during cooldown / concurrent | 429 `REFRESH_COOLDOWN` + `Retry-After` / 409 `REFRESH_IN_PROGRESS` |

---

## 3. Entra configuration implied (to be created later; nothing created)

| Item | Value |
|---|---|
| Delegated scope | `access_as_user` (user access) |
| Application role for users | `FinOpsAdmin` (restricted operations only) |
| Application permission for daemons | `FinOpsDaemon` (app-only tokens; allowed member type: application) |
| Approved clients | SPA and daemon client IDs in `ENTRA_ALLOWED_CLIENT_IDS` |
| New optional setting | `PRICING_REFRESH_COOLDOWN_SECONDS` (default 900) |

---

## 4. Files changed in Stage A

| File | Change |
|---|---|
| `backend/src/cloud_recommender/core/auth.py` | New model: role constants, `USER_NON_GET_ENDPOINTS`, `DAEMON_ALLOWED_ENDPOINTS`, `is_application_token`, baseline `require_api_access`, `enforce_route_policy`, `actor_for`; `require_roles` retained |
| `backend/src/cloud_recommender/core/refresh_guard.py` | **New**: cooldown + single-flight guard |
| `backend/src/cloud_recommender/core/config.py` | `pricing_refresh_cooldown_seconds`; `dev_auth_roles` default empty |
| `backend/src/cloud_recommender/api/routes/{connections,configuration,finops,pricing}.py` | Per-route role dependencies removed (router policy is the single source of truth); attribution; pricing guard and optional `connection_id`/`subscription_id` request fields (additive) |
| `backend/src/cloud_recommender/services/databricks/{finops_analytics_service,sql_client}.py`, `db/models.py` | Actor parameter; single approver role; doc text |
| `backend/src/cloud_recommender/main.py` | Exception headers preserved |
| Tests | `test_route_authorization_policy.py` rewritten (classification sweep), `test_security_hardening.py` authorization sections rewritten, **new** `test_stage_a_authorization.py`, role names updated in existing billing/ingestion/security suites, `conftest.py` dev role |

Not changed: `.env*`, `app.yaml`, migrations/schemas, `schemas/domain.py`, `docs/ADR/*`, frontend, Azure/Databricks integration code.

---

## 5. Tests and results

| Check | Result |
|---|---|
| Full backend suite | **799 passed, 8 skipped, 0 failed**, coverage 87% (previous state 777; baseline before hardening 664) |
| Route sweep (`test_route_authorization_policy.py`) | passes: all operations 401 without token except the frozen public list; the 18 user operations authorized for a scoped user with **no roles**; every other non-GET is 403; daemon tokens 403 everywhere except the 4 designated endpoints; frozen lists must match the application lists; meta-tests prove a new unprotected route is detected and a new protected route defaults to restricted |
| Stage A tests (`test_stage_a_authorization.py`) | 11 tests: attribution (service and routes, spoofed actor ignored), billing execution needs `FinOpsAdmin` on a user token and rejects daemon tokens, cooldown per scope, configurable cooldown, concurrent refresh 409, in-flight marker released on failure, `WWW-Authenticate` preserved |
| `ruff check` / `ruff format --check` | pass (153 files) |
| `mypy src` | pass (93 files) |
| `mypy src tests` (CI command) | one pre-existing, unrelated error (`tests/fixtures/billing_baseline.py` found under two module names) |

Existing tests adapted: approver roles `Admin`/`FinOpsAdministrator` → `FinOpsAdmin` (`test_m7_1_billing_hardening`, `test_p0_*`, `test_milestone_3h/3j2/3j3`); the two RBAC tests now assert that the retired roles are **rejected** (intended behaviour change); `test_entra_auth.py` tokens carry the `access_as_user` scope; one `test_finops_analytics` test now also asserts actor attribution. No pre-existing failures.

---

## 6. Honest gaps and decisions I need before Stage B/C

1. **Business-flow regression until Stage B.** Because ownership does not exist yet, `POST /connections`, `/connections/validate` and `POST /configuration` are **restricted to `FinOpsAdmin`** (not open to all users). Opening them now would let any user create connections that every other user can see (the store is a shared in-memory dict). They open to ordinary users in Stage B, scoped to the owner. If you prefer them open earlier despite that, say so, but I do not recommend it.
2. **Daemon allow-list is my proposal.** I chose 4 read-only organization status endpoints. D6 did not name the daemon's purpose; please confirm or replace the list (it is one frozen set in code and one in the test).
3. **Databricks discovery refresh/test** are open to any user with **no cooldown** (D5 covered pricing only). Risk: load amplification on the shared Databricks service principal. Recommend a configurable per-connection cooldown using the same guard (a small change). Needs your approval because it changes UX.
4. **Pricing cooldown semantics:** the cooldown starts when a refresh starts (a failed refresh also consumes it, so the upstream API cannot be hammered). State is **per process**; with more than one replica it must move to the shared database (Stage B).
5. **`pricing/refresh` scope:** the request has no connection today. I added optional `connection_id`/`subscription_id`; without them the key is `organization|<region>`. The UI does not send them yet.
6. **Recommendation/anomaly state is still a process-wide in-memory dict** (shared, lost on restart). Attribution is in place; durable per-actor storage is a Stage B/C item.
7. **`created_by` on `POST /configuration` is still client-supplied** (spoofable). Fixed together with ownership in Stage B.

---

## 7. Remaining work

### Stage B: persistent, encrypted, owner-bound Azure connections (D1, D7)

1. **Migration (written, not run):** table `cloud_connections` (`id` UUID, `owner_tid`, `owner_oid`, `provider`, `scope_id`, `display_name`, `auth_method`, `status`, `azure_tenant_id`, `azure_client_id`, `secret_ciphertext`, `key_id`, timestamps, `deleted_at`); indexes on owner; unique `(owner_oid, provider, scope_id)`.
2. **Encryption (managed key / envelope):** AES-256-GCM data keys wrapped by a managed key (Key Vault via managed identity, with a key-ring fallback `CONNECTION_ENCRYPTION_KEYS` for local/testing); AAD = connection id + owner oid; `key_id` stored for rotation; production startup requires the key configuration; **no key ⇒ credentials are refused (503), never stored in plaintext**; secrets never in responses, logs, exceptions or `repr`.
3. **Repository + service** replacing the class-level `_custom_connections` dict; ownership key `(tid, oid)` from the token; list returns **owned + organization** connections.
4. **Ownership dependency:** foreign or unknown connection ⇒ **404** (identical body); organization connections readable but **403 on update/delete** for ordinary users.
5. **New endpoints:** `PATCH /connections/{id}` (rename / rotate secret, re-validation) and `DELETE /connections/{id}` (hard-delete ciphertext). Open to the owner; **owner class O** added to the policy engine (frozen lists, cross-user test sweep).
6. **Open `POST /connections`, `/connections/validate`, `POST /configuration`, and personal-connection ingestion run/retry** to owners; organization ingestion stays `FinOpsAdmin` (D3); derive `created_by` from the token.
7. **Limits (D7, configurable):** `MAX_CONNECTIONS_PER_USER` (default 10), `CONNECTION_VALIDATION_ATTEMPTS_PER_MINUTE` (default 5), plus GUID validation of tenant/client/subscription IDs; per-user rate limiting and failed-attempt throttling (the endpoint is otherwise a credential oracle).
8. **Reject or flag write-capable principals:** on create/validate, read the principal's own effective permissions on the subscription and reject Owner/Contributor/write grants (AGENTS.md rule 3); GET-only guard around the ARM/Cost/Monitor client.
9. **Move shared state to the database:** recommendation/anomaly overrides + audit events (with actor), refresh-guard state for multi-replica use.
10. Add `data_access` states (`accessible`, `forbidden`, `unauthenticated`, `not_configured`, `error`, with `empty` only when genuinely empty); `list_connections` stops swallowing provider errors.

### Stage C: use the correct identity for Azure queries (critical requirement)

1. `ConnectionCredentialProvider`: decrypts the owner's secret in-process, mints short-lived ARM/Cost/Monitor tokens cached per connection (memory only), isolated per connection.
2. **Bind every Azure route to a connection:** subscription list = union(owned connections' accessible subscriptions, organization identity's); `GET /inventory/azure/subscriptions/{sub}/…`, `POST /inventory/azure/analyze`, `/inventory/compare`, monitoring, cost and configuration scope discovery must verify the subscription belongs to a connection the caller may use and then use **that connection's credential**. No fallback to the shared server identity for personal connections; a missing/invalid credential yields an explicit state, not shared-identity data.
3. Organization identity retained as a read-only **organization connection** (unchanged behaviour for existing Azure and Databricks users).
4. Cost/metrics: no invented values; inaccessible sections report `forbidden`/`unauthenticated`, empty ones report genuinely empty.
5. **Test requirements:** cross-user IDOR sweep on every owner route; assert the user's credential (not the server's) is used (mock ARM and compare issued tokens); ciphertext AAD tamper test; secret-redaction tests over responses/logs/exceptions; write-capable principal rejection; rate-limit/quota tests; migration tested on a scratch database only after you approve running it.

### Order and checkpoints
B1–B3 (storage, encryption, ownership) → review → B4–B10 → review → Stage C → final security review (re-run the route sweep and cross-user suite).

---

## 8. Behaviour changes to be aware of

- Tokens that carried only the retired roles lose restricted access; there are no such assignments today because Entra is not yet integrated.
- App-only tokens without `FinOpsDaemon` (or hitting any non-designated endpoint) get 403.
- A user token with a role but without the `access_as_user` scope is rejected (roles are no longer an alternative to the scope).
- Local development: dev identity has no roles; set `DEV_AUTH_ROLES=["FinOpsAdmin"]` to use restricted operations (`.env` not modified).
- Audit events no longer show a hard-coded developer name.

*Stopping here for review. No Stage B or C code or migration has been written or run.*
