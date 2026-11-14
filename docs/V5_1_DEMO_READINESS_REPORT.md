# Cloud Recommender V5.1 — Demo Readiness Report

Date 2026-11-14 · branch `feature/live-finops-kpi-integration` · HEAD `b199b0c` (unchanged; nothing staged, committed or pushed).
Live verification used the existing identities only: Azure CLI session `pratik.bingewar@bizmetric.com` for Azure ARM and for the Azure Databricks **Dev** workspace (`642006393507276`). Every live call was a read-only GET.

**Not done, by instruction:** no SQL, no warehouse start, no billing ingestion, no approval token, no migration, no resource/permission/credential change, no Fabric change.

## 0. Verdict

The application can demonstrate **real Azure and real Databricks Dev data** with honest states. Core discovery, monitoring probes and the FinOps module states were verified live through the running API. Three things limit what can be claimed:

1. **Frontend rendering was not visually verified** (no browser available in this environment). Verified instead: API contracts consumed by the UI, `lint`, `typecheck`, 14 test suites and the production build.
2. **Spend, budgets, forecasts and anomalies cannot be shown live**: they need approved billing SQL on a started warehouse, which was prohibited. The UI shows `BLOCKED_PENDING_APPROVAL` / `UNAVAILABLE`, never invented numbers.
3. **Unity Catalog metadata is PARTIAL** (access gaps below).

## 1. Azure — module by module (live)

| Module | Evidence | Class |
|---|---|---|
| Authentication | `azure_cli_session`, token acquired | PASS |
| Subscriptions | 2 real subscriptions: *Azure subscription 1* (state **Disabled**), *Microsoft Azure India* (Enabled); `data_source=live_authenticated` | PASS |
| Resource groups | sub 1: 6, India: 1; 1 page each, complete; subscription state reported ("Disabled: read-only, may be incomplete") | PASS |
| Resources | sub 1: **18**, India: **21**; 1 page each, complete (types below) | PASS |
| Databricks workspaces (ARM) | sub 1: 0; India: **2** (`adb-deaccelerator-dev` ws `642006393507276`, `adb-deaccelerator-dev-prod` ws `7405608085231210`) | PASS |
| Scope discovery (`/configuration/scopes/discover`) | status ready, `data_source=live`, 39 resources, 2 workspaces, tree of 2 subs; now carries `completeness` + exact `source_errors` | PASS |
| Provider status | 2 authorised subscriptions, ARM via CLI | PASS |
| Monitoring capabilities (probes) | see §7 | PASS (probed) |
| Resource details / configurations / metric **values** | Azure `analyze` endpoints (per-resource details, metrics values, waste findings) were **not exercised** | NOT_VERIFIED |
| Cost Management | not called (POST query; `Cost Management Reader` unverified) | NOT_VERIFIED |

India resource types (live): VNet 1, NSG 1, Data Factory 1, Key Vault 1, Logic App 1, Storage account 1, SQL server 1 + **5 databases**, **Databricks workspaces 2**, Access connector 1, Web connections 2, Event Grid topic 1, App Insights 1, Private DNS zone 1 + link 1. Sub 1: Cognitive Services accounts 7 (+4 projects), PostgreSQL flexible server 1, Key Vault 1, App Service plan 1 + site 1, managed identity 1, Log Analytics workspace 1, AI Search 1.

## 2. Databricks Dev — module by module (live, REST/SDK only)

Health: `connected`, user `pratik.bingewar@bizmetric.com`, auth `azure-cli / profile:azure-dev`. Discovery `completed`, 79 records (counts from the live API; 3 connections are registered: Dev, Prod (service principal), AWS FinOps — only Dev was exercised).

| Module | Live result | Class |
|---|---|---|
| Workspace | 1 | PASS |
| Clusters / compute | 1 cluster (`1102-081455-7t3bqp3v`); cluster policies 1 | PASS |
| SQL warehouses | 1 (`05ed10a52697a344`, state **STOPPED**; not started) | PASS |
| Instance pools | API succeeded, 0 | NO_DATA |
| Jobs / job runs | API succeeded, 0 / 0 | NO_DATA |
| Pipelines | API succeeded, 0 | NO_DATA |
| Model Serving | **27** endpoints | PASS |
| MLflow | 1 experiment + 35 recent runs (runs are a most-recent window; flagged if more exist) | PASS |
| Databricks Apps | **3** | PASS |
| Unity Catalog | **9 catalogs, 108 schemas, 780 tables** retrieved; `discovery_state=PARTIAL` (`PARTIAL_DISCOVERY`: some child schema / table-detail / permission lookups failed; 6 of 9 catalogs report `schemas_status=PARTIAL`) | **PARTIAL** |
| System-table metadata | `LIVE` (Unity Catalog API only; row access not exercised, no SQL) | PASS |
| Query history | `LIVE` | PASS |
| Prod workspace (service principal) / AWS workspace | not exercised here; earlier audits recorded 403 for the service principal | NOT_VERIFIED / ACCESS_REQUIRED |
| Billing / system.billing rows | prohibited | NOT_VERIFIED |

FinOps API (29 GET endpoints, all HTTP 200, live): KPI states are honest — e.g. `compute-warehouses` LIVE 1 / BLOCKED_PENDING_APPROVAL 2 / UNAVAILABLE 1; `governance-policies` LIVE 1 / UNAVAILABLE 3; `workload-economics` LIVE 1; `optimization-advisor` CALCULATED 2 (rule-based from live configuration, no invented savings); `overview`, `ai-economics`, `cost-explorer`, `forecast-budgets`, `anomaly-detection` BLOCKED_PENDING_APPROVAL / UNAVAILABLE; `network-cloud` NOT_AUTHORIZED. No value is shown for spend.

## 3. Actual live counts

Azure: 2 subscriptions (1 Enabled, 1 Disabled), 7 resource groups, 39 resources, 2 Databricks workspaces. Databricks Dev: 1 cluster, 1 warehouse (STOPPED), 27 serving endpoints, 3 apps, 1 MLflow experiment, 35 runs, 9 catalogs / 108 schemas / 780 tables (partial), 0 jobs, 0 pipelines, 0 pools.

## 4. Pagination completeness

- **Azure ARM** (`_arm_get_all`): follows every `nextLink`; found live that ARM can return **short or empty pages with a `nextLink`** (a `$top=1` probe returned 0 items plus a link), so a first-page read is unsafe. Now bounded retries on 429/5xx with `Retry-After`, repeated-link and page-limit guards, and a per-call log (`pages`, `records`, `complete`, exact HTTP status, error). A failed or interrupted read is reported **INCOMPLETE** with the records retrieved, never as complete. All live reads above finished in 1 page, `complete=true`.
- **Databricks**: SDK iterators follow service page tokens; the default safety bound was raised 500 → 10 000 and a hit bound is reported as `has_more` / INCOMPLETE. All live categories reported `has_more=false`. Not removed: job-run window (most recent 100), MLflow runs (most recent 50 across ≤100 experiments), per-table detail (25), run artefacts (25) — these are intentional recent-window samples and are flagged when more exist.
- Throttling and failure paths were verified with mock transports only (not provoked live).

## 5. Screens / pages verified

API contracts behind the Azure inventory, configuration/scope, monitoring, Databricks connection/discovery/Unity Catalog/system tables/query history and all 29 FinOps endpoints were exercised against the running backend. **Page rendering was not viewed**; verified by static build only (`next build` prerender, 14 test suites, lint, typecheck). Treat visual rendering as **NOT_VERIFIED** and do a 5-minute click-through before the demo.

## 6. Removed hardcoded / mock data

| Item | Action |
|---|---|
| `KNOWN_WAREHOUSES/CLUSTERS/SERVING_ENDPOINTS/APPS`, `HISTORICAL_FIXTURE_ENDPOINTS` (analytics) | **Removed** — resource existence now comes from live discovery (and from ingested billing attribution); newly created resources are recognised, deleted ones are not |
| `AUTHORIZED_WORKSPACES` fixed workspace ids | **Removed** — scope validation uses the live workspace registry |
| `/monitoring/sources` env-var "connected/simulation_fixture" and invented retention (90/30) | **Replaced** by real probes; retention is `null` (not reported by the APIs) |
| Azure/Databricks/GCP **ingestion providers** fabricated success results: Azure unauth fixture, Azure *live* path (`cost 14.20`, `CPU 38.0`), Databricks (`estimated_cost_usd 7.36`), GCP (`8.75`, `0.38`) | **Fixed** — unauthenticated Azure ⇒ FAILED, live Azure reports identifiers only (cost/metrics "not extracted"), Databricks no cost record, GCP ⇒ SKIPPED; fixtures only with `ALLOW_DEMO_FIXTURES=true` and labelled |
| Azure scope topology fixture (earlier P1), preview dates, USD/FX conversion (earlier) | Already removed |
| Dashboard INR toggle and `INR_EXCHANGE_RATE = 83.15`; `lib/currency.ts` EUR/GBP/AUD/CAD/INR rates; "rate effective October 2026" | **Removed** (§8) |
| Silent partial ARM results | **Fixed** (§4) |
| Still present but labelled/gated: monitoring benchmark (`simulation_benchmark`) paths reachable only when not live; `connection_service` demo scope (gated by `allow_demo_fixtures`); `cost_management_service` default subscription id/dates (parameter defaults, not normal-path data) | Documented |

## 7. Monitoring availability (live probes, existing identity)

| Capability | Result |
|---|---|
| Subscriptions (Reader) | AVAILABLE, 2 |
| `Microsoft.Insights` provider | AVAILABLE, `registrationState=Registered` |
| Activity log (`Monitoring Reader`) | AVAILABLE (last 24 h, top 1 returned) |
| Resources | AVAILABLE, 21 (1 page, complete) |
| Metric definitions | AVAILABLE, 24 definitions (probed on a virtual network) |
| Cost Management | NOT_PROBED (needs a POST; not exercised) |
| Retention | **Not stated** — no read-only API reports it |
| GCP | `not_authenticated` (no credentials) |

Statuses used: AVAILABLE, NO_DATA, ACCESS_DENIED (401/403 with the required permission named), UNAVAILABLE (404/405/501), ERROR, NOT_PROBED. The probe takes ~35 s cold, so results are cached for 120 s.

## 8. Financial data and currency provenance

- **Databricks spend/budget/forecast/anomalies: unavailable** (no billing ingested; prohibited). States shown: BLOCKED_PENDING_APPROVAL / UNAVAILABLE. Nothing is estimated.
- **Azure Dashboard / drawers**: amounts are catalog-price estimates from the Azure Retail Prices API, which reports **USD**. The USD/INR toggle and the hardcoded rate were removed; the badge reads "USD (as reported)". `rate_effective_date` is `null` (the API doesn't provide one) instead of a fixed "October 2026".
- **FinOps command centre**: shows only the billed currency, no picker, no conversion; mixed currencies are shown as unavailable (previous phase). `lib/currency.ts` now contains no exchange rates.
- Exports (CSV/PDF/JSON) state the source currency and no conversion trail.

## 9. Access gaps and exact IT requests

Only gaps observed live or recorded in earlier read-only audits are listed; no permission was requested or changed.

| # | Source | Observation | Request |
|---|---|---|---|
| 1 | Databricks Unity Catalog (Dev) | `PARTIAL_DISCOVERY`: schema / table-detail / grant lookups failed for some objects in 6 of 9 catalogs (`dbt_project_catalog`, `deacc_config_db`, `metrobank_poc_internal`, `system`, `wonder_cement_ai_ml`, `wonder_cement_ai_ml_prod`). The API does not itemise which call failed | Grant the demo identity `USE CATALOG` + `USE SCHEMA` (and `BROWSE`) on those catalogs, or confirm they are intentionally restricted; re-run discovery to get exact errors |
| 2 | Databricks billing system tables | Not attempted (prohibited). `SELECT` on `system.billing.usage` / `list_prices` is unknown | Metadata-only grants check, then separately approved SQL (M7) |
| 3 | Databricks SQL warehouse permissions/config | `CAN_MANAGE` absent (earlier audit) so permissions/config detail is 403 | `CAN_MANAGE` on the warehouse, if that detail is wanted |
| 4 | Databricks account-level APIs | 403 (earlier audit) | Account admin role, if account-level data is wanted |
| 5 | Databricks Prod workspace (service principal) | 403 (earlier audit); not re-tested | Add the service principal to the workspace, or use delegated CLI auth |
| 6 | Azure Cost Management | Not exercised | Verify `Cost Management Reader` on both subscriptions |
| 7 | Azure subscription "Azure subscription 1" | State **Disabled**: ARM is read-only, inventory may be incomplete | Re-enable the subscription if full data is expected |
| 8 | Azure Monitor metric values | Definitions work; values not exercised | Confirm `Monitoring Reader` on the resources to be demonstrated |

## 10. Regression results

| Check | Baseline | Now |
|---|---|---|
| Backend pytest | 641 passed, 8 skipped | **664 passed, 8 skipped, 0 failed** (+23 new demo-readiness tests) |
| `ruff check .` / `mypy src` | clean / clean | clean / clean (92 files) |
| `ruff format --check .` | only pre-existing `scripts/run_migrations.py` | same |
| Frontend `npm test` | 14 suites | 14 suites pass |
| Frontend lint / typecheck / production build | pass | pass |

Tests changed on purpose: three older tests asserted the removed hardcoded registries (`test_milestone_3g2/3g3_reconciliation`) and now assert live-discovery behaviour; the frontend currency tests (`controls`, `financial-integrity`) now assert "no FX, no conversion". Two intermediate failures (mock `AsyncMock(spec=…)` lacking `pagination_log`) were fixed by reading the log defensively. All 8 skips are the 3 originals plus 5 PostgreSQL tests.

## 11. Remaining demo limitations

- Visual rendering unverified; no browser here.
- Billing/spend/forecast/budget are unavailable by design until the approved M7 steps; the **approval-token route authentication gap**, PostgreSQL evidence and Statement-API evidence from the earlier reviews are still open and block any billing step.
- Azure per-resource details, metric *values*, waste findings and Cost Management were not verified live. `monitoring/sources` is slow on a cold call (~35 s).
- Unity Catalog is partial; the Prod/AWS workspaces were not exercised.
- Uniform provenance (P5): inventory, discovery, FinOps KPIs, scope discovery and monitoring each expose source / scope / last sync / record count / status / completeness / error, but they are separate response shapes, not one shared schema.
- Demo fixtures remain off by default; the test suite turns them on globally, so default-off is proven only by tests that pass explicit settings.
- A **local dev backend (uvicorn, port 8765)** I started for the live checks is **still running** — I could not stop it (the process kill was denied). It only performs the read-only metadata refresher; stop it manually (`Stop-Process` on the uvicorn python process) before the demo to free the port.

## 12. Git

Branch `feature/live-finops-kpi-integration`, HEAD `b199b0c`, nothing staged. Earlier uncommitted work (M7.1, P0/P1, pre-P2) is preserved; new in this sprint — modified: `finops_analytics_service.py`, `azure_inventory.py`, `discovery_service.py`, `configuration_service.py`, `schemas/configuration.py`, `api/routes/monitoring.py`, ingestion providers (azure/databricks/gcp), frontend `DashboardView.tsx`, `FinancialKpiDrawer.tsx`, `lib/currency.ts`, `lib/financials.ts`, `types/financials.ts`, `types/index.ts`, four older tests; new — `services/monitoring/capability_probe.py`, `tests/test_demo_readiness.py`, this report. Do **not** commit `docs/databricks_api_audit/` (raw tenant JSON) or any `.env` file; `frontend/tsconfig.json` shows modified by line endings only.
