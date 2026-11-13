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

## 8. Remaining dependencies and known gaps

1. Your running backend must be restarted to pick up the 401 behaviour; an older process still serves fixtures.
2. A 401 from the analysis call shows as "No data available" on the Cost & Waste banner (reason `NO_DATA`); the "Authentication required" text appears for fixture-labelled payloads. Surfacing the 401 message there needs the fetch error to be passed down (small follow-up).
3. Greenfield architect simulation keeps its labelled estimate (`simulation_benchmark`), including its built-in 18% savings heuristic and two illustrative findings; these are estimates, not actuals, and are labelled so.
4. GCP inventory still returns labelled `mock_fixture` when ADC is missing (the frontend refuses to render it as financials; backend gating for GCP is not part of this change).
5. Other static, non-financial illustration in the Landing preview ("8" monitored resources, 99.95% SLA, the sample blueprint) is unchanged.
6. "No data available" appears next to the `/mo` and `/yr` suffixes on some cards; cosmetic.
7. Real spend still requires approved billing ingestion (warehouse start and approval token), unchanged.
