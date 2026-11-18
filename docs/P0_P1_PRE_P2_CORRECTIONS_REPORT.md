# P0/P1 Pre-P2 Corrections Report

Branch `feature/live-finops-kpi-integration`, HEAD `b199b0c` (unchanged). Nothing staged, committed or pushed. P2 was not started.
Scope: only the three corrections requested after `P0_P1_INDEPENDENT_CODE_REVIEW.md` (D5 completeness, USD assumptions, report accuracy).

**This does not make P0/P1 accepted.** The approval-token route, PostgreSQL evidence, Statement-API evidence and several smaller review items remain open (§7).

## 1. D5 attribution completeness

**Change.** `finops_analytics_service.py` no longer keeps its own attribution key list. `_RESOURCE_META_KEYS` and `_FILTER_META_KEYS` are derived from `billing_sql.ATTRIBUTION_RULES`, so analytics and ingestion cannot drift: same keys, same priority order.

| Key | Billing type | Analytics label |
|---|---|---|
| `warehouse_id` | SQL_WAREHOUSE | warehouse |
| `endpoint_id`, `endpoint_name` | SERVING_ENDPOINT | serving |
| `app_id` | APP | app |
| `job_id` | JOB | job |
| `dlt_pipeline_id` | PIPELINE | pipeline |
| `cluster_id` | CLUSTER | cluster |
| `instance_pool_id` | POOL | **pool (new)** |
| `notebook_id` | NOTEBOOK | **notebook (new)** |
| `serverless_compute_id` | SERVERLESS | **serverless (new)** |

Existing behaviour is preserved: the warehouse, cluster, serving and app filters and the priority order for rows carrying several keys are unchanged (the earlier hand-written order already matched). New effect: rows that carry only a pool, notebook or serverless id now get a resource attribution and a cost driver (`pool: <id>`) instead of falling back to a bare SKU.

**Tests** (`backend/tests/test_pre_p2_corrections.py`): the key set and order equal the billing rules; for every one of the 10 keys a row is attributed to the right resource by billing (`resolve_resource`, exact-id `get_billing_summary`) and by analytics (`_resource_of`, typed filter, id-only filter), a sibling row and an unrelated row are excluded, and a partial id never matches; multi-key priority agrees in both layers; the four pre-existing filters still work; a pool-only row appears as a cost driver.

## 2. Hardcoded USD assumptions removed

**Review result.** The `"USD"` unit was used as a marker on ~100 KPI call sites and `_usd()` hardcoded `$`; `currency="USD"` was the default. The FinOps frontend additionally let the user pick EUR/GBP/AUD/CAD/INR and **converted amounts client-side with hardcoded exchange rates** (`lib/currency.ts`) while treating the source as USD — a silent, unsourced conversion.

**Backend** (`finops_analytics_service.py`):
- A per-read currency state is derived from the **priced rows of the workspace scope** (one code, mixed, or none) and used by every KPI. Currency is judged on the whole workspace scope so a per-resource read cannot disagree with the scope-level figures around it.
- `_mk_kpi`: money units now take their currency from that state — `unit` becomes the real code (`EUR`, `EUR/DBU`), `currency` carries it, formatting is `$1,234.50` only for USD and `1,234.50 EUR` otherwise (no symbol guessing). Non-money KPIs carry no currency. Unknown currency (no priced rows) ⇒ no currency claim.
- **Mixed currencies**: money KPIs become `value=None`, `UNAVAILABLE`, `formatted_value="-"`, `currency=None`, with the reason "priced billing rows use more than one currency (USD, EUR) … never merged or converted". DBU quantities stay visible. Costs of priced rows are withheld at the source (`_billing_rows`), so no downstream figure can sum currencies; direct formatters show `n/a (mixed currencies)`.
- All direct formatters (cost drivers, anomalies, recommendations, scenario) use the currency-aware `_money()`; the former `_usd` is gone.
- CSV export: header is `List Cost (<currency>)` / `Effective Cost (<currency>)` (or "mixed currencies" / "currency unknown"), no `$`, and cost cells are empty when the currency is not confirmed.
- Rate card list rates show each price's own `currency_code`.
- **Budget**: `FINOPS_MONTHLY_BUDGET_USD` is explicitly USD, so `approved_budget` is the one KPI with a *confirmed* `USD` currency. Budget utilisation, projected overrun and budget controls are computed only when the actuals are USD (or there are no rows); a USD budget is never compared with EUR or mixed actuals. Actual and forecast KPIs still display in their own currency.
- Billing-service responses were already per-currency (previous phase); unchanged.

**Frontend**:
- `lib/billing.ts`: `sourceCurrencyOf`, `formatSourceMoney`, `sourceCurrencyLabel`, `currencyColumnName`, `singleCurrency` — no conversion; USD → `$`, others → amount + code; mixed → `n/a (mixed currencies)`; unknown → `-`.
- `FinOpsCommandCenterView.tsx`: the currency picker and the FX conversion are removed; a static badge states the billed currency; every `fmtMoney(...)` (13 sites) and `formatCost` now use the source currency; hardcoded `$` template literals, "USD" headings and "Cost (USD)" were replaced; the ledger table uses each row's own `currency`; reconciliation tiles use the reconciliation's currency and tolerate `null` totals (mixed/unpriced); CSV/PDF/JSON exports state the source currency and no longer claim a conversion trail; JSON `total_spend` is `null` when mixed.
- `types/index.ts`: `BillingSummaryResponse` gains `spend_by_currency`, `price_card_complete`; `BillingReconciliationResponse` gains `cost_by_currency` and nullable `gross_cost`/`net_cost` (matches the backend).
- The module `lib/currency.ts` was **not removed** (compatibility). It is no longer imported by the FinOps view, which a test enforces. Not reviewed or changed: `DashboardView`/`FinancialKpiDrawer` (Azure architecture financials with their own USD/INR toggle) — a separate source, listed in §7.

**Tests.**
- Backend (`test_pre_p2_corrections.py`): `format_money`; **USD** scope keeps `$`/`USD` for executive and cost-explorer KPIs; **EUR** scope shows `EUR` unit/currency/`30.00 EUR`, `2.0000 EUR / DBU`, no `$` or `USD` on any KPI, EUR CSV header and body, EUR cost drivers, EUR rate cards, non-money KPIs without currency; **mixed** scope: KPIs unavailable with reason, CSV header "mixed currencies" and empty cost cells, drivers without `$`, provenance says costs are withheld; **no rows**: no currency claim anywhere; **budget**: USD compared, EUR and mixed not compared, budget itself confirmed USD; currency state does not leak between requests.
- Frontend (`currency-honesty.test.ts`): USD, EUR/INR (no FX), mixed, unknown/null/NaN, and a source scan proving the view no longer imports `lib/currency`, has no currency picker, no `$` template literal and no "Cost (USD)".

## 3. Remediation report corrected

`docs/P0_P1_REMEDIATION_REPORT.md` now opens with a status-correction table and its per-item statuses were changed: D5 *partially complete*, currency handling *incomplete*, token scope *partially complete*, approval-token authentication *FAILED*, PostgreSQL tests *not executed* (with the two known defects), Statement-API evidence *NOT VERIFIED*, run-result toast *open*; section 10 now says "Not accepted". No full acceptance is claimed.

## 4. Backward compatibility

- **Azure**: no Azure code path touched in this task; the authenticated discovery and the P1 change are as before.
- **Databricks**: discovery code untouched; analytics changes affect only billing-derived KPI presentation and attribution. USD-priced data renders exactly as before (the existing 612 tests, which exercise baseline USD KPIs, pass unchanged).
- **Fabric**: not touched. **Authentication**: not changed.
- **API contracts**: additive only. Existing KPI fields are all present; values change only where the old value was wrong (non-USD currency or unknown currency shown as USD) — consumers that hardcoded the string `"USD"` for `unit`/`currency` will now see the real code, `CURRENCY`/`CURRENCY/DBU` when unknown, or `null`. Frontend modules and pages are all retained; only the currency picker was removed.
- **Isolation**: billing changes stay in the analytics presentation layer and billing service; discovery does not depend on them, and resource metadata remains visible when billing is unavailable.

## 5. Validation (compared with baseline)

| Check | Baseline | Now |
|---|---|---|
| Backend pytest | 553 passed, 3 skipped (original) / 612 passed, 8 skipped (after P0/P1) | **641 passed, 8 skipped, 0 failed** (+29 new); coverage 86% (`finops_analytics_service` 95%) |
| `ruff check .` | clean | clean |
| `ruff format --check .` | only pre-existing `scripts/run_migrations.py` | same |
| `mypy src` | clean | clean (91 files) |
| Frontend `npm test` | 13 suites | **14 suites**, 0 failures |
| Frontend lint / typecheck / production build | pass | pass |

The 8 skips are the 3 original skips plus the 5 PostgreSQL tests (no disposable database). Two intermediate issues were found and fixed while implementing (a ruff class-scope/ContextVar complaint, and a TypeScript use-before-declaration of the reconciliation state); neither affected a test baseline.

## 6. Restrictions — confirmation

No live Azure or Databricks call, no SQL, no warehouse start, no approval token minted, no ingestion, no migration applied, no credential or permission change, no Fabric change, no commit or push, no destructive Git command. All tests ran offline against fakes and the mock provider; the frontend build and tests ran locally.

## 7. Still open (not part of this task)

- **Approval-token route (FAILED)**: broad / side-effect SQL can be signed (`ai_query`, `http_request`, `identity_metadata`, cross joins, other workspaces); response echoes the request's workspace; default `entra_auth_enabled=false` makes every caller an Admin; `/ingestion/run` has no auth dependency. Blocks any live step.
- **PostgreSQL integration tests**: never executed; two defects (`text()` ignoring the private schema; vacuous outage assertions) unfixed.
- **Statement-API behaviour**: NOT VERIFIED against real payloads; `spend_complete` still ignores `price_card_complete`.
- **Run-result toast** still says "Ingestion completed" for `failed`/`incomplete`.
- Other money displays not reviewed here: Azure architecture financials (`DashboardView`, `FinancialKpiDrawer`, `lib/financials.ts`, which still has its own USD/INR toggle and a `$` default in `fmtMoney`'s no-formatter path); stale defaults in `cost_management_service`; P2–P5 items from the audit (hardcoded `KNOWN_*` registries, monitoring simulation labels, discovery caps).

## 8. Git state

Branch `feature/live-finops-kpi-integration`, HEAD `b199b0c`, nothing staged. New files in this task: `backend/tests/test_pre_p2_corrections.py`, `frontend/test/currency-honesty.test.ts`, this report; modified: `finops_analytics_service.py`, `FinOpsCommandCenterView.tsx`, `frontend/src/lib/billing.ts`, `frontend/src/types/index.ts`, `docs/P0_P1_REMEDIATION_REPORT.md`. All earlier uncommitted and untracked files are preserved. Do **not** commit `docs/databricks_api_audit/` (raw tenant audit JSON); `frontend/tsconfig.json` shows modified with line-ending-only differences — do not stage.
