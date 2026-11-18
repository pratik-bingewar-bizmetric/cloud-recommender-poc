# Cloud Recommender V5.1 — Working Baseline Verification

Verified 2026-11-13 against the running application. **Read-only**: only HTTP GETs against the local backend/frontend, `git status/diff/log`, file reads, and a port probe. No code, schema, credential, permission, Git or cloud state was changed. No SQL was executed and the SQL warehouse was not started by this verification.

## 1. Git state (no change made)

| Item | Value |
|---|---|
| Branch | `feature/live-finops-kpi-integration` |
| HEAD | `df6868b` (Merge PR #6, feature/databricks-apps-integration) |
| Staged | 0 |
| Modified (tracked) | 76 files (backend routes/services/schemas/tests, frontend components, `.gitignore`, `app.yaml`) |
| Untracked | 38 paths: new backend modules (`schemas/azure_discovery.py`, `schemas/canonical_financial.py`, `services/azure/`, `services/databricks/refresher.py`, `scripts/databricks_access_audit.py`), new tests (`test_m2_3/4/5_*`, `test_live_finops_integration.py`, `tests/fixtures/`), new frontend libs/tests (`connectionState`, `finopsProvenance`, `refreshScheduler`, `useDatabricksConnection`, `FinOpsProvenance.tsx`, 2 test files), and docs (M2_3, M2_4, M2_5 reports, `docs/audits/*`, `docs/architecture/`, `docs/databricks_api_audit/`) |
| Nothing is committed | all M1–M2.5 work exists only in the working tree; a loss of the working directory would lose it |

## 2. Configuration and port mapping

| Component | Value |
|---|---|
| Frontend | `http://localhost:3000` (Next.js dev, HTTP 200) |
| Backend | `http://localhost:8000` (`/health` ok, `/health/ready`: database `connected`) |
| PostgreSQL | `localhost:5432`, database `cloud_recommender`, driver `postgresql+asyncpg` (accepting connections; Windows service `postgresql-x64-16`) |
| Browser → API | `frontend/.env.local`: `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` (direct to `:8000`) |
| Next.js proxy | `next.config.mjs` rewrites `/api`, `/health`, `/docs`, `/openapi.json` to `INTERNAL_BACKEND_URL` (default `http://127.0.0.1:8000`); verified `:3000/api/v1/databricks/connections` returns the same data |
| `.env` (repo root) | `APP_ENV=development`, **`API_PORT=8001`** (not used by the running `:8000` backend; see issue 8), `DATABASE_URL` points at localhost:5432 |
| Databricks auth | `DATABRICKS_AUTH_TYPE` unset → default `azure-cli`; Dev connection `auth_method: azure-cli / profile:azure-dev`, authenticated as `pratik.bingewar@bizmetric.com`, `connection_state: CONNECTED` |
| Workspace registry | Dev `642006393507276` (`connected`); Prod `7405608085231210` and AWS FinOps `2250283018608626` are `ready_to_connect` (out of scope, not exercised) |

## 3. Dev workspace connection and discovery (live, REST only)

`GET /databricks/connections/databricks-azure-dev/discovery` → HTTP 200, `overall_status: completed`, `data_status: LIVE`.

| Category | State | Count | Source API |
|---|---|---|---|
| workspace | LIVE | 1 | `current_user.me` |
| clusters | LIVE | 1 | `clusters.list` |
| cluster_policies | LIVE | 1 | `cluster_policies.list` |
| instance_pools | NO_DATA (confirmed empty) | 0 | `instance_pools.list` |
| warehouses | LIVE | 1 (Serverless Starter Warehouse) | `warehouses.list` |
| jobs / job_runs | NO_DATA (confirmed empty) | 0 / 0 | `jobs.list` / `jobs.list_runs` |
| pipelines | NO_DATA (confirmed empty) | 0 | `pipelines.list_pipelines` |
| model_serving | LIVE | 27 | `serving_endpoints.list` |
| mlflow | LIVE | 36 | `experiments.search_experiments` + runs |
| unity_catalog | LIVE | 9 catalogs | `catalogs.list` |
| apps | LIVE | 3 | `apps.list` |

Also LIVE: system-table metadata (46 tables), query history (50 records, paginated). Health endpoint reports `last_verified_at` / `last_discovery_at`.

## 4. Azure subscriptions, Resource Groups and inventory (live ARM, Azure CLI identity)

| Subscription | State | Source | Resource Groups | Resources |
|---|---|---|---|---|
| Azure subscription 1 `f718c261-…` | **Disabled** (greyed, not selectable in UI) | `live_authenticated` | 6, status OK | 18, status OK |
| Microsoft Azure India `9636348b-…` | Enabled | `live_authenticated` | 1 (`rg-deaccelerator-dev`), status OK | 21, status OK |

Auth method for both: `azure_cli_session`. Responses carry `status`, `http_status`, `page_count`, `retrieved_at`, `last_success_at`, `stale`. Empty is distinguished from forbidden; a failed refresh keeps the last good inventory marked stale (unit-tested).

## 5. Module-wise verification (21 modules: 11 workspace + 10 FinOps)

You referred to "15 Databricks modules"; the sidebar defines 21 (11 under Workspace & Operations, 10 under FinOps). All 21 were checked; the "15" mapping could not be identified from the code.

| # | Module | Endpoint | HTTP | Data source | Classification today | Missing data shown as |
|---|---|---|---|---|---|---|
| 1 | Overview | `/databricks/.../discovery` | 200 | Databricks SDK REST | LIVE | counts from API; confirmed-empty categories show 0 only because the API confirmed empty |
| 2 | Clusters | discovery `clusters` | 200 | `clusters.list` | LIVE (1) | utilization `-` |
| 3 | Warehouses | discovery `warehouses` | 200 | `warehouses.list` | LIVE (1, STOPPED) | utilization `-` |
| 4 | Jobs & Workflows | discovery `jobs`, `job_runs` | 200 | `jobs.list` | NO_DATA, empty confirmed | n/a |
| 5 | Pipelines | discovery `pipelines` | 200 | `pipelines.list_pipelines` | NO_DATA, empty confirmed | n/a |
| 6 | Model Serving | discovery `model_serving` | 200 | `serving_endpoints.list` | LIVE (27) | usage `-` |
| 7 | Unity Catalog | `/unity-catalog` | 200 | `catalogs/schemas/tables` REST | LIVE (9 catalogs) | size `-` |
| 8 | Databricks Apps | discovery `apps` | 200 | `apps.list` | LIVE (3) | n/a |
| 9 | System Tables | `/system-tables` | 200 | `tables.list` metadata only | LIVE metadata (46 tables); no rows | no sample rows |
| 10 | Query History | `/query-history` | 200 | `query_history.list` REST | LIVE (50, paginated) | cost correlation `-` |
| 11 | Audit & Governance | discovery / `reports-audit` | 200 | local audit trail | LIVE (0 events, real events only) | n/a |
| 12 | Executive Overview | `/finops/overview` | 200 | inventory LIVE; spend blocked | inventory LIVE; spend `BLOCKED_PENDING_APPROVAL` | `value: null` + reason (`-`) |
| 13 | Cost Explorer | `/finops/cost-explorer` | 200 | billing ledger (none ingested) | BLOCKED_PENDING_APPROVAL / UNAVAILABLE | `null` + reason |
| 14 | Cost Allocation | `/finops/cost-allocation` | 200 | billing + tags | BLOCKED_PENDING_APPROVAL | `null` + reason |
| 15 | Cost & Billing | `/finops/showback-chargeback` | 200 | billing statements | BLOCKED_PENDING_APPROVAL | `null` + reason |
| 16 | Forecast & Budgets | `/finops/forecast-budgets` | 200 | needs ≥14 days billing + `finops_monthly_budget_usd` | INSUFFICIENT_HISTORY / UNAVAILABLE | `null` + reason |
| 17 | Anomaly Detection | `/finops/anomaly-detection` | 200 | needs ≥14 days billing | BLOCKED_PENDING_APPROVAL | `null` + reason |
| 18 | Optimization Advisor | `/finops/optimization-advisor` | 200 | configuration findings from live inventory | LIVE (0 findings) | savings `null` |
| 19 | AI Economics | `/finops/ai-economics` | 200 | 27 endpoints LIVE; token/usage needs SQL | endpoints LIVE; usage BLOCKED_PENDING_APPROVAL | tokens/cost `null` + reason |
| 20 | Governance & Policies | `/finops/governance-policies` | 200 | cluster policies/owners from API | LIVE | compliance `-` |
| 21 | Reports & Audit | `/finops/reports-audit` | 200 | 4 static report-pack templates, 0 audit events | template metadata / empty | n/a |

Billing pipeline: `/finops/billing/summary` → `data_status: NO_BILLING_ROWS`, `total_dbu/net_dbu/total_spend_verified: null`; `/finops/ingestion/status` → `warehouse_status: WAREHOUSE_STOPPED`, `system_tables_status: APPROVAL_REQUIRED`, `last_successful_ingestion: null`, `total_usage_records_ingested: 0`; `/finops/ingestion/runs` → `[]`; reconciliation `usage_record_count: 0` (rate-card rows `price_record_count: 5` are list prices, not spend).

## 6. Hardcoded / mocked / estimated / fallback data

**Databricks and FinOps modules (21 above): none found.** Every KPI inspected (`total_spend`, `dbu_consumption`, `ai_spend`, tokens, forecast, anomalies, etc.) returns `value: null` with a status and reason; none returns a fabricated 0. Zero appears only where the API confirmed an empty list. A grep for mock/fixture/sample/random literals in the FinOps and Databricks frontend components found none.

**Outside those modules (outstanding):**
1. `frontend/src/lib/financials.ts` contains hardcoded Azure/GCP "reference" financials (spend `225.11`, savings `118.27`, GCP `280.87`, 5 resource ids under `sub-prod-enterprise-01`, INR rate `83.15`). `buildCanonicalFinancialSummary` falls back to the literals `225.11` / `280.87` when a scope has no cost value. It feeds `DashboardView`, `SectionCostWaste`, `SectionCentralizedMonitoring` and `FinancialKpiDrawer`. These are the Azure monitoring / Cost & Waste screens, not the Databricks modules. `getAzureReferenceFinancials` / `getGcpReferenceFinancials` have no other callers (dead code).
2. Backend labelled fixtures when unauthenticated: `list_subscriptions` (`data_source: mock_fixture`), `_get_demo_fixture_analysis`, `connection_service` "Simulation Fixture", `monitoring` `simulation_fixture`, GCP reference project, `foundry_provider` `mock_fallback_fixture`. They are labelled with provenance, and not active in this run (all Azure responses are `live_authenticated`), but they would show fixture data if the CLI session expired.
3. Service catalog and pricing use curated offline fixtures by design (`OFFLINE_PRICING_MODE=true`, `CATALOG_OFFLINE_MODE=true`); that is the AGENTS.md offline-pricing requirement, not Databricks data.

## 7. No SQL, warehouse start or cloud mutation

| Check | Result |
|---|---|
| SQL warehouse state | STOPPED (`Serverless Starter Warehouse`), unchanged |
| SQL execution | The only `statement_execution.execute_statement` call in the codebase (`sql_client.py:897`) sits behind a read-only validator, a signed single-use approval token, and a STOPPED-warehouse refusal. Ingestion runs `[]`, 0 usage records, no last ingestion ⇒ never executed |
| Warehouse/cluster start/create/edit | no call sites in `backend/src` (grep for `warehouses.start/create/edit/stop`, `clusters.start/create/edit/delete`: none) |
| Azure | only ARM `GET` listings (subscriptions, resourcegroups, resources, subscription state); no PUT/POST/DELETE issued |
| This verification | GET requests only |

## 8. Fabric integration

`fabric-integration/` has exactly one change vs `HEAD`: `sync-agent/config.py` `DEFAULT_SUBSCRIPTION_ID` `f718c261-…` → `9636348b-…` (the pre-existing user modification, preserved). No other Fabric file or Fabric backend/frontend file differs from `HEAD`; Fabric stays disabled (`FABRIC_ENABLED=false`).

## 9. Outstanding issues and dependencies

| # | Issue | Dependency / action |
|---|---|---|
| 1 | Spend, DBU, tokens, forecasts, anomalies, allocation all `-` | Explicit approval to start the warehouse and run one bounded read-only billing ingestion (signed approval token) |
| 2 | Billing store is in-memory (`_usage_store`); a backend restart empties ingested rows | Persistence decision (PostgreSQL) before relying on ingested data |
| 3 | Databricks service principal (`1dc51b34-…`) cannot access Dev/Prod ("Workspace … is inaccessible") | Workspace admin must assign it; not needed for Azure-CLI Dev |
| 4 | `AZURE_CLIENT_SECRET` is rejected by Entra (AADSTS7000215); Azure calls silently use the CLI session | Replace the secret; grant only Reader / Cost Management Reader / Monitoring Reader |
| 5 | CLI identity has `*` permissions on subscription 1 (over-privileged vs read-only policy) | Use Reader for production |
| 6 | Hardcoded Azure/GCP reference financials in `frontend/src/lib/financials.ts` (section 6.1) | Remove fallback literals or label them; not changed (read-only task) |
| 7 | Everything is uncommitted on `feature/live-finops-kpi-integration` | Commit/backup when you choose |
| 8 | `.env` `API_PORT=8001`, `.env.local` / proxy default `8000`, README says `--port 8000`; leftover dev servers from earlier verification may still hold `:3001`, `:3004`–`:3007`, `:8002`, `:8004` | Standardise on 8000/3000; stop leftovers with the shutdown commands |
| 9 | Dev shows `ready_to_connect` on a freshly started backend until the UI requests it (refresher only refreshes recently requested connections) | Open the Dev workspace once after startup |
| 10 | Warehouse CAN_USE and account-level system-schema status unverifiable with this identity | Account/warehouse admin to confirm before approving ingestion |
| 11 | "15 modules" does not match the 21 defined modules | Confirm intended list |
| 12 | `ruff format --check` flags 2 pre-existing files (e.g. `scripts/run_migrations.py`); `mypy .` from `backend/` has a fixture module-path error (`mypy src` is clean) | Optional cleanup |

## 10. Startup and shutdown commands

Prerequisites: PostgreSQL service `postgresql-x64-16` running, `az login` active for `pratik.bingewar@bizmetric.com` (tenant `fe82a67c-…`), `.env` at the repo root.

**Start (PowerShell, from the repo root):**
```powershell
# Terminal 1: backend on :8000 (run from the repo root so .env is found)
$env:PYTHONPATH = "backend/src"
Remove-Item Env:DATABRICKS_AUTH_TYPE, Env:DATABRICKS_CLIENT_ID, Env:DATABRICKS_CLIENT_SECRET, Env:APP_ENV -ErrorAction SilentlyContinue
backend\.venv\Scripts\python.exe -m uvicorn cloud_recommender.main:app --port 8000

# Terminal 2: frontend on :3000
cd frontend
npm run dev
```
Then open `http://localhost:3000`, select the Azure account → Configured Scope, and open the Dev workspace so it connects.

**Health checks:**
```powershell
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8000/api/v1/databricks/connections
```

**Shutdown:**
```powershell
# Ctrl+C in each terminal, or by port:
Get-NetTCPConnection -LocalPort 3000,8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess }
# netstat fallback: netstat -ano | findstr ":8000 :3000"  then  taskkill /PID <pid> /F
```
Do not stop PostgreSQL unless intended (`Stop-Service postgresql-x64-16` needs an elevated shell). Stopping the app does not change the warehouse (it stays STOPPED) or any cloud resource.

## 11. Regression gates (last run, before this report)

Backend `pytest`: 456 passed, 3 skipped. Frontend `npm test`: 11 suites passed; typecheck, lint and production build passed earlier in M2.5. Not re-run for this read-only task.
