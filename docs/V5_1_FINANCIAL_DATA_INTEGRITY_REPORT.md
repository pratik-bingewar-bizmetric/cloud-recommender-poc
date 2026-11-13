# V5.1 Financial Data Integrity Remediation Report

Branch `feature/live-finops-kpi-integration`, baseline `4ae8a1a` (V5.1, pushed). No SQL was executed, no warehouse started, no billing ingestion run, no cloud resource or database schema changed, no credentials touched, no Databricks authentication or Fabric code changed.

## 1. Problem

Financial screens outside the Databricks modules rendered invented numbers whenever live data was missing:
`frontend/src/lib/financials.ts` returned hardcoded "reference" Azure/GCP summaries (spend `225.11`, savings `118.27`, GCP `280.87`/`84.27`), and several components turned `null` into `$0.00`. On the backend, a missing or expired Azure identity silently returned labelled `mock_fixture` inventory, and an authorized-but-empty subscription was replaced by fixture resources.

## 2. Hardcoded and fallback values found and removed

| Where | Removed |
|---|---|
| `lib/financials.ts` | `getAzureReferenceFinancials` / `getGcpReferenceFinancials` (about 360 lines: spend 225.11, savings 118.27, categories 91.25 / 73.00 / etc., 5 fake resource ids under `sub-prod-enterprise-01`); builder fallbacks `225.11`, `280.87`, `118.27`, `84.27`; invented category split (`rawSpend * 0.405 / 0.324 / 0.143 / 0.111 / 0.017`); `included_resources_count \|\| 9`; fake scope id/name (`sub-prod-enterprise-01`, "Production Enterprise Subscription", "Smart Expense GCP Production"); the default "no data" branch that returned the reference summary |
| `DashboardView.tsx` | default fake scope; 6-month trend invented from fixed multipliers (`0.76 … 1.0`) and a synthetic budget (`spend × 1.05`); the charts built on them |
| `LandingView.tsx` | `$225.11`, `$118.27`, `52.5%`, `$91.25 (41%)`, `$105.21 (47%)`, `$25.00 (11%)`, static "100% Verified", fake scope badge `sub-prod-enterprise-01`, fixed bar widths |
| `SectionCloudScopeInventory.tsx` | `parseFloat(x \|\| "0.00")` (null shown as `$0.00`) for monthly and annual savings |
| `SectionCentralizedMonitoring.tsx` | `monthly_cost ?? "0.00"` (null shown as `$0.00`) in resource detail |

A repo-wide scan of `frontend/src` now finds none of `225.11, 118.27, 280.87, 84.27, 105.21, 91.25, 52.5%`, `sub-prod-enterprise-01` or `Production Enterprise Subscription` (enforced by a test).

## 3. Behaviour now

| Situation | Result |
|---|---|
| Valid source value | actual value shown (rate-card spend stays labelled `estimated_public_list`; `actual_billed_monthly_spend` stays `null`) |
| Null / empty / non-finite value | **"No data available"**, never `$0.00` (`formatFinancialCurrency`) |
| No live source for a screen | `buildCanonicalFinancialSummary` returns `null`; the Dashboard shows "No data available" plus a message; Cost & Waste shows a status banner with the reason |
| Empty billing response | spend/savings stay `null`; categories empty (no invented split); message "No billing data." |
| Backend payload labelled `mock_fixture` / `simulation_fixture` / `ai_proposed` | treated as fixture: no summary is built; reason `FIXTURE_DATA` ("Authentication required") |
| Missing forecast | "Forecast unavailable." message constant |
| Azure and GCP | each summary uses only its own provider's source; with no source, neither is substituted |
| Confirmed zero (for example realized savings under the zero-execution policy) | still shown as a real `$0.00` |

New shared helpers in `lib/financials.ts`: `NO_DATA_LABEL`, `FINANCIAL_UNAVAILABLE_MESSAGES`, `toFiniteNumber`, `percentOf`, `isFixtureDataSource`, `financialUnavailableReason`. Types in `types/financials.ts` made nullable (`estimated_monthly_spend`, `potential_monthly_savings`, `projected_annual_savings`, `savings_percentage_of_spend`, finding spend/savings, resource counts). API contracts unchanged.

## 4. Backend fixture isolation (fail-closed)

* New setting `allow_demo_fixtures` (default `False`; env `ALLOW_DEMO_FIXTURES`). Fixtures are explicit opt-in only.
* `AzureInventoryService.list_subscriptions` and `analyze_subscription` raise `AzureAuthenticationRequired` when no Azure identity is available (expired `az login`, no SP) instead of returning fixtures. `main.py` maps it to **HTTP 401** `{"error": {"type": "azure_authentication_required", "message": "... Run 'az login' ..."}}`.
* The "ARM returned no resources, so substitute fixture" path is gated by the same flag; an authorized-but-empty or forbidden subscription now returns real (empty) results.
* `ConnectionService` no longer lists the "Azure Production Reference Scope (Simulation Fixture)" connection unless opted in.
* Development vs production authentication policy and Databricks authentication are unchanged.
* Tests opt in via `conftest.py` (`ALLOW_DEMO_FIXTURES=true`, plus `test_settings`); the fail-closed default is tested with an explicit `allow_demo_fixtures=False`.

## 5. Files changed

Frontend: `src/lib/financials.ts`, `src/types/financials.ts`, `src/components/{DashboardView,FinancialKpiDrawer,SectionCostWaste,SectionCentralizedMonitoring,SectionCloudScopeInventory,LandingView}.tsx`, new `test/financial-integrity.test.ts`.
Backend: `core/config.py`, `main.py`, `services/inventory/azure_inventory.py`, `services/connections/connection_service.py`, `tests/conftest.py`, new `tests/test_v5_1_fixture_isolation.py`.
Follow-up (section 8): `services/inventory/gcp_inventory.py`, `services/configuration/configuration_service.py`, `services/connections/connection_service.py` (GCP), `src/lib/financials.ts`, `SectionCentralizedMonitoring.tsx`, `SectionCostWaste.tsx`, `DashboardView.tsx`, `FinancialKpiDrawer.tsx`, `test/financial-integrity.test.ts`, new `tests/test_v5_1_gcp_isolation.py`.
Docs: this report.

## 6. Affected screens

Executive Cloud FinOps Dashboard, Cost & Waste, Azure Centralized Monitoring KPI strip and resource detail, Financial KPI drawer (CSV export now blank instead of `0`), Cloud Scope Inventory savings cards, Landing preview, Connection list. The 21 Databricks workspace/FinOps modules were already null-safe and are unchanged.

## 7. Tests

| Suite | Result |
|---|---|
| Backend `pytest backend/tests` | **463 passed, 3 skipped, 0 failed** (456 before plus 7 new) |
| Backend `ruff check`, `mypy src` | pass (89 files) |
| Frontend `npm test` | **12 suites, 82 tests, 0 failures** (new file: 14 tests) |
| Frontend `typecheck`, `lint`, production `build` | pass |
| Browser (Chrome, live app) | Dashboard shows "No data available" and the explanatory message; Cost & Waste shows "No data available" on all three KPIs; no known hardcoded value anywhere; 0 page errors |

New backend tests (`test_v5_1_fixture_isolation.py`): default off; list and analyze fail closed; opt-in still labelled; authorized-empty subscription not replaced; no reference connection; API returns 401 with no fixture content. New frontend tests cover all hardcoded values (source scan), null/NaN formatting, confirmed zero, empty billing, fixture payloads, real-data rendering, Azure vs GCP separation and the greenfield simulation label. Existing suites continue to cover Azure Resource Group discovery (`test_m2_5_azure_discovery.py`, 7 tests) and Databricks discovery / connection state (`test_databricks_workspace.py`, `test_m2_4_connection_state.py`, `connection-state.test.ts`).

## 8. Gap closure (follow-up commit `fix(finops): complete financial data error handling`)

The first pass left four gaps. All are now closed.

### 8.1 Cost & Waste: HTTP error states

Root cause: `fetchAnalysis` in `SectionCentralizedMonitoring.tsx` caught the analysis error and only called `console.warn`, so a 401/403/500 left `analysisData` null and the screen fell through to the generic "No data available".

Fix: the component now keeps only the HTTP status of a failed call (`analysisError: { status } | null`, cleared on retry/success) and passes it to `SectionCostWaste`, which shows one status line via `financialErrorFromStatus` (new, in `lib/financials.ts`). Only a fixed message and the numeric status are ever rendered; the server's message, tokens and stack traces are never shown or logged (the console warning now logs the status only).

| Situation | Message |
|---|---|
| HTTP 401 | "Authentication required — run az login." (GCP: "… run gcloud auth login.") |
| HTTP 403 | "Access denied — check your Azure permissions." (GCP: "… GCP permissions.") |
| Successful response with no billing figure | "No billing data available." |
| Other failure | "Azure financial data could not be loaded (HTTP 500)." / "(network error)." |

Also fixed while verifying in the browser: on a failed analysis the page still showed "Actionable Opportunities: 0 / 0 waste • 0 tech debt" and "Zero unattached disks, oversized compute, or idle storage detected". Those zero/"nothing found" claims are now shown only when the analysis actually returned; otherwise "No data available", "Analysis unavailable" and "Findings unavailable. <status message>". The API response contract is unchanged.

### 8.2 GCP fixture isolation (`gcp_inventory.py`, `connection_service.py`, `configuration_service.py`)

Before: no credentials, a failed call, an empty result, or simply the project id `smart-expense-gcp-prod` (even with a valid token) returned the labelled reference fixture. Connections listed a "Smart Expense GCP Production (Reference Project Fixture)" entry, and the configuration tree attached invented assets (`gce-app-01`, `cloudsql-pg-01`) to every project, including live ones.

| Case | Now |
|---|---|
| No GCP credentials (`list_projects`, `analyze_project`) | HTTP 401 "GCP authentication required: no valid Google Cloud identity …"; no fixture |
| Expired / invalid token | explicit 401 (even with the demo opt-in) |
| Insufficient IAM | explicit 403 |
| Upstream failure (non-200 / exception) | HTTP 502 "… no fixture data is substituted"; no fixture |
| Authorized but empty project list | `[]` (real result, never a fixture) |
| `smart-expense-gcp-prod` with a valid token | analysed live, not served from the fixture |
| Fixtures | only with the existing explicit `allow_demo_fixtures` opt-in (default off, so production stays fail-closed); still labelled `mock_fixture` |
| Connection list | no reference GCP connection unless opted in |
| Configuration discovery tree | invented assets only for the labelled fixture project; live projects get no invented children |
| Provider status text | no longer promises fixture data unless opted in |

Legitimate live retrieval (project search, hierarchy, asset discovery) is untouched and covered by a test.

### 8.3 Card formatting

New `periodSuffix(value, suffix)`: returns the suffix only for a finite value. `/mo`, `/yr`, `/month`, `/year` are now omitted whenever the amount is unavailable (Dashboard cards and finding rows, Cost & Waste cards and waste pool, Monitoring KPI strip and resource sizing, KPI drawer headline/totals/finding rows) and kept for real values. A genuine zero still renders `$0.00` with its suffix. The Dashboard's "Save up to $X/mo" button becomes "Savings: No data available" when unknown.

## 9. Test results (follow-up)

| Suite | Result |
|---|---|
| Backend `pytest backend/tests` | **478 passed, 3 skipped, 0 failed** (463 before plus 15 new GCP tests) |
| Backend `ruff check`, `mypy src` | pass (89 source files); touched files formatted |
| Frontend `npm test` | **12 suites, 92 tests, 0 failures** (financial-integrity file now 24 tests, 10 new) |
| Frontend `typecheck`, `lint`, production `build` | pass |
| Databricks Dev discovery (live, fresh backend) | `completed` / `LIVE`, connection `connected`: 1 cluster, 1 warehouse, 27 serving endpoints, 9 catalogs, 3 apps |
| Azure Resource Groups (live) | subscription 1 (Disabled): 6 RGs, `OK`; Microsoft Azure India (Enabled): 1 RG, `OK`; both `live_authenticated` via `azure_cli_session` |
| GCP on this host (no GCP credentials) | `GET /inventory/gcp/projects` and `POST /inventory/gcp/analyze` both return 401 with the explicit message and no fixture content |
| Browser (Chrome, live app, analysis call intercepted) | 401, 403 and 500 each show the exact message above; no leaked server text (a planted token/trace string never appears); no "No data available/mo" or "/yr"; Actionable Opportunities and the "zero findings" sentence no longer claim zero on failure; 0 page errors |

New backend tests (`test_v5_1_gcp_isolation.py`, 15): missing credentials fail closed for list and analyze (reference and custom project ids); status text; explicit opt-in still labelled; expired token 401 with and without opt-in; 403; upstream failure 502; authorized-empty not replaced; live listing intact; reference id with a token goes live; no reference connection; no invented assets for live projects; discovery without credentials reports failure instead of a fixture tree. New frontend tests cover 401/403/other/network mapping, no token or stack text in messages, empty-success message, the Monitoring-to-Cost & Waste error plumbing, `periodSuffix`, preserved `$0.00` zero, and the no-zero-claim-on-failure guard.

## 10. Remaining dependencies and known gaps

1. Restart any long-running backend to pick up the GCP and Azure fail-closed behaviour; an older process still serves fixtures.
2. Greenfield architect simulation keeps its labelled estimate (`simulation_benchmark`), including its built-in 18% savings heuristic and two illustrative findings; these are estimates, not actuals, and are labelled so.
3. Other static, non-financial illustration in the Landing preview ("8" monitored resources, 99.95% SLA, the sample blueprint) is unchanged.
4. Per-finding and per-resource figures that are read directly from API strings (for example `parseFloat(finding.potential_monthly_savings)` in the finding detail panel and the per-resource-group totals) are unchanged; they assume the API sends a value and are not part of the KPI cards.
5. Real spend still requires approved billing ingestion (warehouse start and approval token), unchanged.
