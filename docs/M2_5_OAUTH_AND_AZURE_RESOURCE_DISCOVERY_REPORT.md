# M2.5 — OAuth Rotation, Databricks Access Audit & Azure Resource Discovery

Branch `feature/live-finops-kpi-integration` (nothing committed). No secret, token or permission change was made; no SQL was executed; no warehouse or cluster was started; no Azure resource was touched. All Azure/Databricks calls were read-only GETs.

## 1. New OAuth secret validation (value never recorded)

| Check | Result |
|---|---|
| Secret location | `.env` → `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`, read via `core/config.py` `Settings`, resolved in `services/databricks/auth.py` (`_resolve_sp_credentials`) |
| Client authentication against `/oidc/v1/token` | Passes on the Dev and Prod workspaces (the new secret is accepted; no `invalid_client`) |
| Token → workspace access | **Fails: HTTP 403 "Workspace … is inaccessible"** on Dev (642006393507276) and Prod (7405608085231210). The service principal is not assigned to either workspace. The AWS registry entry returns 401 `invalid_client` (different account). |
| Conclusion | A successful token request is **not** proof of API access. The new secret authenticates the SP but the SP has no workspace membership, so every API is unreachable in SP mode. |
| Refresh / expiry | `auth.py` caches the token with its expiry and re-mints on expiry or `force_refresh`; the cache is per-process, so a restart clears tokens minted from the previous secret. Secret and token strings are redacted in all error paths. |
| Auth mode in use | DEV_LOCAL keeps `azure-cli` (unchanged); PROD/oauth selects the SP. Not changed. |

## 2. SP identity verification

Token probe claims (non-secret only): issuer is the workspace OIDC endpoint, `scope=all-apis`, subject is the SP application id in `DATABRICKS_CLIENT_ID`. Workspace access is the missing piece, not scopes.

## 3. API scope coverage

`all-apis` is requested; it covers every REST API the app uses. Scope is not the blocker — workspace assignment is.

## 4. Databricks access matrix (Dev workspace, Azure CLI identity; script `backend/scripts/databricks_access_audit.py`)

Re-run: `PYTHONPATH=backend/src python backend/scripts/databricks_access_audit.py <connection_id> <sp|cli>`. Records HTTP status, auth, permission, count, pagination, latency and retrieval time per API, never secrets.

| API | HTTP | Result |
|---|---|---|
| Current user / workspace info | 200 | OK |
| Clusters | 200 | 1 |
| SQL warehouses | 200 | 1 (state STOPPED) |
| Jobs, job runs | 200 | 0 (confirmed empty) |
| Pipelines | 200 | 0 (confirmed empty) |
| Model serving | 200 | 27 |
| Apps | 200 | 3 |
| MLflow experiments | 200 | OK |
| Query history (REST) | 200 | OK, paginated |
| Unity Catalog | 200 | metastore present; 9 catalogs visible only with browse, 4 without |
| System table metadata (billing, compute, query, serving, ai_gateway) | 200 | 46 tables listed |
| Effective grants on `system.billing.usage`, `list_prices`, `system.query.history`, `system.compute.warehouses` | 200 | caller has SELECT, USE CATALOG, USE SCHEMA |
| Warehouse permissions (CAN_USE) | 403 | not verifiable by the caller |
| Account-level system schema status | 403 | "not an account admin" — unverifiable here |
| **SP identity, any API** | **403** | workspace inaccessible (section 1) |

## 5. System Tables / billing ingestion diagnosis

* Metastore: present. `system.billing.*` schemas visible. Privileges: SELECT / USE CATALOG / USE SCHEMA granted to the caller.
* **Blocker 1 — SQL warehouse `05ed10a52697a344` is STOPPED.** Billing rows can only be read via SQL; starting it needs your explicit approval.
* **Blocker 2 — approval gate.** `BillingIngestionService.run_ingestion` refuses without a valid server-issued approval token (`approval_required` status), by design.
* Ingestion design (read from code, no SQL run): rows are deduplicated by `record_id`, filtered by `workspace_id` and period, and kept in an **in-memory** store (`_usage_store`). There is **no database persistence**, so a backend restart empties it. Summary, reconciliation and the dashboards read that store.
* Therefore no billing rows exist and Cost & Billing / Executive Overview spend stays `-` with a reason. Nothing is invented and no fixture is used. This is correct behaviour, not a defect.
* **Approval needed to proceed:** (a) approve starting the warehouse (cost: warehouse size × runtime), (b) approve one bounded read-only ingestion (workspace, period). Persistence of ingested rows is a separate follow-up decision.

## 6. Azure subscription access matrix (Azure CLI user `pratik.bingewar@bizmetric.com`, tenant `fe82a67c-…`, token audience `https://management.azure.com/`)

| Subscription | State | RG list | Resources | Pages |
|---|---|---|---|---|
| Azure subscription 1 `f718c261-…` | **Disabled** | 200 → 6 | 200 → 18 | 1 |
| Microsoft Azure India `9636348b-…` | Enabled | 200 → 1 | 200 → 21 | 1 |

* Why "Enabled returns no RGs" was shown: the UI had hard-wired empty RG lists and no backend endpoint existed; the existing `_arm_get_all` also swallows every non-200 as an empty list. It was an app gap, not authorization. ARM actually returns 1 RG for the Enabled subscription.
* Why Disabled was selectable: subscription state was displayed but never enforced. Now Disabled subscriptions are greyed, labelled, not selectable (existing selection can be cleared), and excluded from Select All.

## 7. Resource Group discovery (implemented)

* `GET /api/v1/inventory/azure/subscriptions/{id}/resource-groups` → ARM `GET /subscriptions/{id}/resourcegroups`, all `nextLink` pages, each RG linked to its subscription (id, name, location, provisioning state, tags, managedBy).
* Response carries `subscription_state`, `status` (`OK`, `EMPTY`, `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `ERROR`), `http_status`, `page_count`, `auth_method`, `retrieved_at`, `last_success_at`, `stale`.
* Empty ≠ authorization failure (`EMPTY` vs `FORBIDDEN`; 403 message names the missing `Reader` role). A failed refresh returns the last good inventory with `stale=true`. No hardcoded names or counts; without an identity the result is `UNAUTHENTICATED` with no items.
* Files: `schemas/azure_discovery.py`, `services/azure/discovery_service.py`, route in `api/routes/inventory.py`.

## 8. Azure resource inventory (implemented)

* `GET /api/v1/inventory/azure/subscriptions/{id}/resources[?resource_group=]`: id, name, type, subscription, resource group, location, kind, sku, provisioning state, created/changed time, tags. Real data verified: 18 and 21 resources.
* The ARM list API does not return per-resource `properties`; those need a per-type GET and are not fetched. Azure Monitor metrics are available through the existing monitoring service; utilization or cost is **not** claimed from inventory.

## 9. Azure authorization

* Subscription 1: effective permission `*` (Owner-class via the CLI user) — the CLI identity is **over-privileged** versus the read-only policy.
* Microsoft Azure India: ARM reads succeed but `Microsoft.Authorization/permissions` reports no actions, so the exact role could not be confirmed from the API; verify in the portal.
* **`AZURE_CLIENT_SECRET` is rejected by Entra (AADSTS7000215, invalid secret)**, so the configured SP cannot reach ARM. The app silently falls back to the CLI session (`auth_method: azure_cli_session`). Not changed by me.
* The Databricks SP secret does not grant ARM access (separate Entra app). No roles were granted.
* Cost Management Reader at billing scope: not verifiable here; cost values stay `-`.

## 10. Missing RBAC / required actions (yours to approve)

1. Assign the Databricks SP to the Dev and Prod workspaces (workspace admin / account admin).
2. Replace `AZURE_CLIENT_SECRET` with a valid secret for the Azure SP, then grant it `Reader` (+ `Cost Management Reader`, `Monitoring Reader`) only.
3. Approve warehouse start + one bounded billing ingestion.
4. Optionally grant the CLI user CAN_USE verification / replace Owner-class access with Reader for production use.

## 11. Remaining blocked metrics

Spend, cost explorer, forecasts, anomalies, DBU and query cost correlation, token usage (needs `system.serving`/`ai_gateway` rows), utilization, and Azure cost all remain `-` with reasons until items 1–3 are done.

## 12. Tests and browser verification

| Gate | Result |
|---|---|
| `ruff check backend/` | pass |
| `ruff format --check backend/` | 2 pre-existing unformatted files not touched by this work (`scripts/run_migrations.py` and one other); new files formatted |
| `mypy src` | pass (89 files). `mypy .` from `backend/` has a pre-existing fixture module-path error |
| `pytest backend/tests` | **450 passed, 3 skipped** (new `test_m2_5_azure_discovery.py`: 7 tests — paging, empty vs forbidden, stale cache, no identity, resource RG parsing, network error) |
| Frontend `typecheck` / `lint` / `test` / `build` | pass (11 test suites) |
| Browser (real Chrome via puppeteer, isolated ports) | Configuration page shows live subscription cards: Disabled sub 1 → 18 resources / 6 RGs (greyed, labelled, not selectable); Enabled sub → 21 resources / 1 RG; RG cards list real names, regions, per-RG counts; no console errors; Databricks registry shows Dev/Prod |

### Side fixes found while verifying
* `AzureInventoryService.get_access_token` ran `az account get-access-token` with blocking `subprocess.run` inside an async handler (up to ~19 s event-loop stalls, serialising ARM calls). It now runs via `asyncio.to_thread`; discovery also uses a 5-minute in-process token cache.
* `next dev` with alternate `NEXT_DIST_DIR` kept appending `.next-*` entries to `frontend/tsconfig.json`; I removed those includes (its reformatting of arrays remains).

### Notes
* Leftover dev servers from my first attempt may still be listening on ports 8004/3004 (that frontend points at the stale :8000 backend); they were not killed. Restart your own backend on :8000 to pick up the new routes.
* "Reader Role Enforced" in the page header is a static label, not an RBAC check.

## 13. Regression investigation: "Databricks Dev stopped working after the Resource Group change"

**Result: no code regression found; not reproducible on current code.**

| Check | Evidence |
|---|---|
| Resolver (`DatabricksAuthService.create_workspace_client`), Dev host, default settings | selects `azure-cli`; `GET /scim/v2/Me` returns the human user `pratik.bingewar@bizmetric.com` |
| Same, forced `oauth-m2m` (Service Principal) | token endpoint accepts the secret; workspace returns `access_denied: Workspace 642006393507276 is inaccessible`. This is the pre-existing SP assignment problem, identical to your PowerShell baseline |
| Fresh backend, current code | Dev `connected`, discovery `completed` / `LIVE`; stays connected while 4 concurrent ARM RG/resource calls run |
| Config (A–D) | `APP_ENV=development`; `DATABRICKS_AUTH_TYPE` unset in `.env` and in the process environment, so default `azure-cli`; `.env` has `DATABRICKS_CLIENT_ID/SECRET` populated and `AZURE_CLIENT_ID` equals `DATABRICKS_CLIENT_ID` (same app), but the Dev path ignores them |
| Credential reuse (E, G, H) | M2.5 touched only `azure_inventory.py` (blocking `az` call moved to a thread), `inventory.py`, and new `azure_discovery.py` / `discovery_service.py`; the new service contains no Databricks code, and no code writes to `os.environ` |
| Registry / workspace (F, I) | `workspace_service.py` untouched by M2.5; Dev host/id/warehouse unchanged |
| Fail-closed logic (J) | Applies only to production or an explicit `oauth`/`oauth-m2m` setting; DEV_LOCAL never uses it |

`auth.py`, `config.py`, `workspace_service.py` and the registry differ from `HEAD` (uncommitted M1–M2.4 work, not M2.5); the Dev-uses-Azure-CLI rule has been in place since then.

**What explains the symptom (environment, not code):**
1. `frontend/.env.local` pins `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`, `.env` runs the API on `API_PORT=8001`, and no backend is listening on `:8000` now. A UI built against `:8000` has no Databricks data.
2. Several backends run side by side (`:8001` pre-M2.5, no RG route; `:8002`; `:8004` M2.5; the frontend on `:3001` proxies to a dead `:8003`). Backends that have not yet been asked for Dev show `ready_to_connect` (the background refresher only refreshes *touched* connections), so Dev looks "unavailable" until the UI requests it.
3. An exported `DATABRICKS_AUTH_TYPE`, `DATABRICKS_CLIENT_*` or `APP_ENV` in the launching shell (for example left over from the PowerShell SP tests) overrides `.env` and would switch Dev to the SP. I could not see your shell; check with `echo $env:DATABRICKS_AUTH_TYPE` before starting the backend.

**Correction applied:** none to production code (no defect to fix). Added `backend/tests/test_m2_5_auth_separation.py` (6 tests) pinning: Dev uses Azure CLI even when SP secrets exist; `AZURE_*` is never used for Databricks; Dev with no CLI session fails closed instead of using the SP; production without SP credentials fails closed and never touches the CLI; production uses the Databricks SP; the RG discovery service has no Databricks coupling.

**Tests:** backend 456 passed / 3 skipped; frontend 11 suites passed; live Dev test via the Azure CLI identity succeeded (above).
