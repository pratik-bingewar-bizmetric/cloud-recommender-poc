# M2.4 Strict Live Data Verification Report

> **Branch:** `feature/live-finops-kpi-integration` · **HEAD:** `df6868b` (unchanged, nothing committed) · **Date:** 2026-11-13
> **Workspace:** `adb-deaccelerator-dev` (`642006393507276`) · **Auth:** Azure CLI delegated (M2.2A, unchanged)
> **Boundaries honoured:** no SQL executed, warehouse `05ed10a52697a344` never started (STOPPED throughout), no cluster/permission/Azure changes, production authentication untouched.

## 0. Answer to "is the application 100% live?"

**No.** Every value the dashboard shows is now either real, or `-` with a stated reason. But the largest block of KPIs (spend, DBU, forecast, anomalies, utilization, tokens, storage size) is **blocked pending your approval** to run read-only SQL on the stopped warehouse, and network/Azure-cost metrics need Azure `Cost Management Reader`. Those show `-` today. Section 7 lists each one.

## 1. Why the screenshots looked wrong (the eight discrepancies, traced to code)

| # | Observation | Root cause (verified) | Fix |
|---|---|---|---|
| 4, 5, 6, 7 | 11 records / 88,420 DBU / $284,620 / $176,840 / $319,500 / $300,000 | The backend process serving port 8000 (PID 11728, started 09:39) **predated the M2.3 changes and ran without `--reload`**. It was still executing the old code that seeded 11 fake usage rows and hardcoded the rest. `curl :8000/api/v1/finops/ingestion/status` returned `total_usage_records_ingested: 11` while the repository code returned none. | M2.3 removed the seed; this milestone verified against fresh processes. **Action for you: restart your backend** (and use `--reload` as `startup.bat` does). I did not kill your processes (the attempt was declined). |
| 1 | Header "Connected", sidebar "Unavailable" | Two causes. (a) Each surface derived its own badge (`ingestionStatus.connection_status`, `error`, `backendStatus`, registry status), and a module API error flipped the header. (b) **Backend race:** the API creates a new `DatabricksWorkspaceService` per request and each instance replaced the shared registry entry with a *copy*, so a `CONNECTED` status set by a long-running discovery was lost. Health then reported `DISCONNECTED` right after a successful discovery. | One backend `connection_state`, one frontend `deriveConnectionView` rendered by every surface; registry entry is now a single process-wide object (regression test added). |
| 2, 3 | Apps 0, Clusters 0 | `DatabricksWorkspaceDetailView` derived counts from `discovery?.resources`; a null/failed discovery rendered as `0`. Also a **failed refresh overwrote the good inventory cache with an empty response**. | Counts show `-` unless that category's query succeeded; failed refreshes keep the last good inventory and mark it stale. Verified live: 1 cluster, 3 apps. |
| 8 | "Production" selector on a Dev workspace | `envFilter` defaulted to `"Production"` and a hardcoded scope default also said Production; backend only echoed the parameter. | Environment is read from the selected workspace (`development`) and shown read-only. |

## 2. Hardcoded / mock values found (and removed)

**Backend:** (M2.3) seeded billing rows and hardcoded modules; (M2.4) `connection created_at/updated_at` constants, fixed `"BASELINE"/"RECONCILED"` billing statuses with zeros, KPI text strings ("Awaiting billing data") instead of `-`, a request-time warm-up that blocked on full discovery.
**Frontend:** `SEED_CONNECTIONS` (fake "Azure Production Account … sub-prod-01, 48 resource groups, 98 resources, CONNECTED"), fake offline validation success ("verified offline mode", `discovered_resource_count: 98`), a hardcoded **demo connection** that was marked connected/live, a fake Azure scope (`sub-prod-01`, `rg-finops-eastus`, `tenant-bizmetric-prod`), fake scope flags (`source_availability` all true, `data_freshness 2026-11-10`, `environment: Production`), `ConfigurationView` fake subscription/resource-group/workspace/Fabric hierarchy ("adb-lakehouse-eastus", "F64-FinOps-EastUS", "System Tables Live" badge on every workspace), a scripted fake discovery progress with a fixed success message, hardcoded "Retail Prices Verified", "Deterministic Engine Certified", "Verified System Tables Lineage", sidebar fallback workspace ID, `|| "TERMINATED"/"STOPPED"/"READY"` status defaults.
**Result:** `frontend/test/connection-state.test.ts` and `finops-live-data.test.ts` statically fail the build if any of these strings return.

## 3. Files changed (this milestone)

Backend: `schemas/databricks.py` (WorkspaceConnectionState, SqlWarehouseStatus, health fields), `schemas/billing_ingestion.py` (nullable), `schemas/finops.py` (`reason`), `services/databricks/workspace_service.py` (shared registry, cache-preserving discovery, refresh state, health), **new** `services/databricks/refresher.py`, `services/databricks/billing_ingestion_service.py`, `services/databricks/finops_analytics_service.py`, `api/routes/finops.py`, `api/routes/databricks.py`, `core/config.py`, `main.py`, tests (`test_m2_4_connection_state.py` new; M2.3/finops tests updated).
Frontend: **new** `lib/connectionState.ts`, `lib/refreshScheduler.ts`, `lib/useDatabricksConnection.ts`; changed `app/page.tsx`, `Sidebar.tsx`, `FinOpsCommandCenterView.tsx`, `DatabricksWorkspaceDetailView.tsx`, `ConnectCloudView.tsx`, `ConfigurationView.tsx`, `TopNav.tsx`, `FinOpsAiAnalysisSection.tsx`, `FinOpsProvenance.tsx`, `types/index.ts`, `next.config.mjs` (optional `NEXT_DIST_DIR`, used only for my isolated verification instance), tests.
Not touched: `fabric-integration/**` (the pre-existing `sync-agent/config.py` edit is preserved), `docs/ADR`, `schemas/domain.py`, auth logic.

## 4. Databricks connection: one source of truth

`GET /databricks/connections/{id}/health` now returns `connection_state` (`CONNECTED | DISCONNECTED | AUTHENTICATION_REQUIRED | ACCESS_DENIED | ERROR | NOT_CONFIGURED`), workspace id/name/url, environment, auth method, `last_connected_at`, `last_discovery_at`, `last_discovery_attempt_at`, `discovery_stale`, `refresh_interval_seconds`, last error, and a **separate** `sql_warehouse` block (`state`, `sql_available`, message). The SQL warehouse can be `STOPPED` while the workspace is `CONNECTED`. The frontend renders the single `ConnectionView` derived from it in the header, sidebar, workspace detail, and every FinOps module; a test forbids any component from computing its own badge.

Final live status (Dev): **CONNECTED** · environment **development** · SQL warehouse **STOPPED** (`sql_available=false`, "requires explicit approval") · not stale.

## 5. Inventory counts verified against live API responses

Discovery `completed`, 79 resources: 1 cluster (`1102-081455-7t3bqp3v`, TERMINATED), 1 cluster policy, 1 warehouse (`05ed10a52697a344`, STOPPED), **27 serving endpoints**, **3 apps**, 1 MLflow experiment, 35 runs, **9 catalogs** (108 schemas, 780 tables via Unity Catalog), 0 jobs/pipelines/pools/job-runs (confirmed empty by the API, `empty_confirmed=true`). All categories `has_more=false` (pagination complete). The browser rendered Clusters = 1 (TERMINATED) and Apps = 3, matching the API.

## 6. Billing source and ingestion

The runtime billing store is empty. Rows can only arrive via the approved read-only `system.billing.usage` ingestion (token-gated, unchanged). With no rows: `total_spend_verified`, `total_dbu`, `net_dbu`, reconciliation figures are `null`; status `NO_BILLING_ROWS` / `NO_DATA` (previously zeros with `BASELINE`/`RECONCILED`). The built-in rate card is labelled as such and never treated as expenditure. Unmatched-SKU usage is never shown as verified spend. Offline ingestion/pricing/mapping behaviour is covered by tests using test-only fixtures; **no live billing verification was possible** (needs SQL approval).

## 7. KPI source mapping (generated from the live backend, not hand-written)

Status distribution across all 13 KPI modules: **LIVE 4, CALCULATED 2, INSUFFICIENT_HISTORY 2, BLOCKED_PENDING_APPROVAL 27, NOT_AUTHORIZED 4 (network/Azure), UNAVAILABLE 24**: 63 KPIs, only 6 with values, because billing and telemetry SQL is not approved.

| Module | KPI (metric_id) | Source | Formula | Status | Value shown | Last updated (UTC) | Reason when unavailable |

|---|---|---|---|---|---|---|---|

| Executive Overview | total_spend | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. No billing rows ingested. Spend cannot be derived from Databric… |

| Executive Overview | databricks_spend | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. No billing rows ingested. Spend cannot be derived from Databric… |

| Executive Overview | ai_spend | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. No billing rows ingested. Spend cannot be derived from Databric… |

| Executive Overview | dbu_consumption | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. No billing rows ingested. Spend cannot be derived from Databric… |

| Executive Overview | savings_opportunity | Optimization Advisor | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Savings require billing and utilization telemetry; none is calculable ye… |

| Executive Overview | forecast_spend | system.billing.usage | - | INSUFFICIENT_HISTORY | - | 2026-11-13T09:55:06 | Insufficient history. No billing rows ingested. Spend cannot be derived from Databricks APIs alone; it requires a read-only SELEC… |

| Executive Overview | anomalies | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Needs >= 14 days of ingested billing history. |

| Cost Explorer | gross_consumption | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Cost Explorer | effective_rate | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Cost Explorer | unallocated_spend | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Cost Explorer | credits_discounts | Azure invoice / contract data | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Discounts and credits are not exposed by system.billing.usage. |

| Cost Allocation | allocated_spend | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Cost Allocation | unallocated_spend | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Cost Allocation | active_rules | Allocation engine configuration | - | LIVE | 2 rules | 2026-11-13T09:55:06 | - |

| Cost Allocation | shared_pool | Shared-cost configuration | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No shared-cost pools are configured. |

| Compute & Warehouses | compute_spend | system.billing.usage x list prices | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Needs ingested billing rows. |

| Compute & Warehouses | active_compute | Databricks clusters/warehouses API | count(state == RUNNING) | LIVE | 0 of 2 running | 2026-11-13T09:55:06 | - |

| Compute & Warehouses | idle_capacity | system.compute.node_timeline | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Utilization and uptime need system.compute tables (SQL on a sta… |

| Compute & Warehouses | potential_savings | Optimization Advisor | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Savings are not calculable without utilization and billing data. |

| AI Economics | ai_spend | system.billing.usage x list prices | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. DBU compute cost only; token-priced external models are not inc… |

| AI Economics | input_tokens | system.serving.endpoint_usage / system.ai_gateway.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Token counts, request counts and latency are only exposed throu… |

| AI Economics | output_tokens | system.serving.endpoint_usage / system.ai_gateway.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Token counts, request counts and latency are only exposed throu… |

| AI Economics | cached_tokens | system.serving.endpoint_usage / system.ai_gateway.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Token counts, request counts and latency are only exposed throu… |

| AI Economics | cost_per_1k_tokens | system.serving.endpoint_usage / system.ai_gateway.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Token counts, request counts and latency are only exposed throu… |

| AI Economics | cost_per_task | Agent evaluation telemetry | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No task/outcome telemetry source is connected. |

| Data & Storage | storage_spend | Azure Cost Management | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Storage charges are Azure resources, not in system.billing.usage. |

| Data & Storage | total_stored_data | DESCRIBE DETAIL / system.information_schema / Azure Storage… | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Unity Catalog REST metadata does not report table size, growth … |

| Data & Storage | cold_data | DESCRIBE DETAIL / system.information_schema / Azure Storage… | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Unity Catalog REST metadata does not report table size, growth … |

| Data & Storage | ingestion_spend | DESCRIBE DETAIL / system.information_schema / Azure Storage… | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Unity Catalog REST metadata does not report table size, growth … |

| Network & Cloud | network_infra_spend | Azure Cost Management / Azure Resource Graph | - | NOT_AUTHORIZED | - | 2026-11-13T09:55:06 | Permission required. Databricks exposes no network cost telemetry; this needs read-only Azure access. Required: Azure Reader and … |

| Network & Cloud | data_egress | Azure Cost Management / Azure Resource Graph | - | NOT_AUTHORIZED | - | 2026-11-13T09:55:06 | Permission required. Databricks exposes no network cost telemetry; this needs read-only Azure access. Required: Azure Reader and … |

| Network & Cloud | private_endpoints | Azure Cost Management / Azure Resource Graph | - | NOT_AUTHORIZED | - | 2026-11-13T09:55:06 | Permission required. Databricks exposes no network cost telemetry; this needs read-only Azure access. Required: Azure Reader and … |

| Network & Cloud | unmapped_resources | Azure Cost Management / Azure Resource Graph | - | NOT_AUTHORIZED | - | 2026-11-13T09:55:06 | Permission required. Databricks exposes no network cost telemetry; this needs read-only Azure access. Required: Azure Reader and … |

| Optimization Advisor | potential_savings | Optimization Advisor | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Savings are only reported when calculable from usage and billing telemet… |

| Optimization Advisor | estimated_savings | Optimization Advisor | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Savings are only reported when calculable from usage and billing telemet… |

| Optimization Advisor | approved_savings | Optimization Advisor | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Savings are only reported when calculable from usage and billing telemet… |

| Optimization Advisor | quick_wins | Optimization Advisor | count(configuration findings) | CALCULATED | 0 count | 2026-11-13T09:55:06 | - |

| Optimization Advisor | awaiting_approval | Optimization Advisor | - | CALCULATED | 0 count | 2026-11-13T09:55:06 | - |

| Optimization Advisor | implemented_savings | Post-change billing audit | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No change has been verified against post-change billing. |

| Optimization Advisor | realized_savings | Post-change billing audit | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Realized savings require a verified before/after billing comparison. |

| Forecast & Budgets | approved_budget | FINOPS_MONTHLY_BUDGET_USD setting | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Set finops_monthly_budget_usd to enable budget tracking. |

| Forecast & Budgets | actual_mtd | system.billing.usage x list prices | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Actual (list-price basis). |

| Forecast & Budgets | forecast_month_end | Run-rate projection | MTD + trailing-7-day average x remaining days | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. Needs >= 14 days of ingested billing history. |

| Forecast & Budgets | forecast_confidence | Forecast backtest | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No confidence interval is computed for the run-rate method. |

| Forecast & Budgets | forecast_accuracy | Forecast backtest | - | INSUFFICIENT_HISTORY | - | 2026-11-13T09:55:06 | Insufficient history. Requires >= 3 completed forecast cycles. |

| Forecast & Budgets | budget_utilization | Budget vs actual | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No budget configured. |

| Forecast & Budgets | projected_overrun | Forecast vs budget | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Requires both a forecast and a configured budget. |

| Anomaly Detection | open_anomalies | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Anomaly Detection | potential_exposure | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Anomaly Detection | mean_time_to_detect | Detection latency telemetry | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. Not measured. |

| Anomaly Detection | auto_triaged | Triage workflow | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No automated triage exists. |

| Governance & Policies | policy_compliance | Policy compliance scanner | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No compliance scanner data source exists. |

| Governance & Policies | policy_violations | Policy compliance scanner | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No violation data source exists. |

| Governance & Policies | resources_without_owner | Databricks resource APIs (creator field) | count(resources WHERE creator IS NULL) | LIVE | 27 resources | 2026-11-13T09:55:06 | - |

| Governance & Policies | expiring_exceptions | Exception registry | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No exception registry exists. |

| Showback / Chargeback | bu_billed | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Showback / Chargeback | shared_pool | Shared-cost configuration | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No shared-cost pools are configured; nothing is distributed artificially. |

| Showback / Chargeback | disputed_allocations | Dispute workflow | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No dispute workflow data source exists. |

| Showback / Chargeback | statement_readiness | system.billing.usage | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Workload Economics | tracked_workloads | Jobs / pipelines API + system.billing.usage | - | LIVE | 0 count | 2026-11-13T09:55:06 | - |

| Workload Economics | unit_metrics_coverage | Business volume metrics | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No business volume metric source is connected. |

| Workload Economics | avg_cost_workload | system.billing.usage x list prices | - | BLOCKED_PENDING_APPROVAL | - | 2026-11-13T09:55:06 | Blocked: requires approved read-only SQL access to system tables. |

| Workload Economics | value_positive | Business outcome metrics | - | UNAVAILABLE | - | 2026-11-13T09:55:06 | Not available: no connected source provides this metric. No outcome/value data is connected. |

**Every `-` has a reason** (tooltip on the card, and a provenance banner on the page): `reason` is returned by the API for each null KPI. Zero is shown only for confirmed zeros (for example "0 of 2 running", 0 jobs).

## 8. Refresh architecture

- **Backend:** `MetadataRefresher` (background task, started in app lifespan; off in the `testing` environment) keeps the process-shared discovery/Unity Catalog/system-table-metadata caches fresh for connections requested in the last 15 minutes: inventory every **60 s** (`DATABRICKS_INVENTORY_REFRESH_SECONDS`), slower metadata every **600 s** (`DATABRICKS_METADATA_REFRESH_SECONDS`). REST only — never SQL. Single-flight per connection; a failed refresh keeps the last good cache and sets `discovery_stale`. Request-time warm-up waits at most 25 s for a *first-ever* discovery and otherwise schedules a background refresh, so slow metadata never blocks a dashboard request.
- **Frontend:** `useDatabricksConnection` polls health+inventory every **60 s** (`NEXT_PUBLIC_REFRESH_INTERVAL_MS`, min 5 s) and the connection registry every **300 s**; `FinOpsCommandCenterView` re-fetches module data on the same interval; paused while the tab is hidden, refreshed on return and on manual **Refresh**; single-flight (no overlapping requests); module data is cleared immediately when the workspace/resource scope changes so another workspace's data is never shown. A "Updated …UTC" stamp and a "Stale data: last refresh failed" badge are always visible; no tokens are stored client-side.
- SQL-based metrics refresh only when billing rows exist; they are never polled.

## 9. Browser verification (real Chrome, `puppeteer-core`, against the current code)

Real Chrome (headless, `puppeteer-core`) against an **isolated** instance of the current code (backend :8003, frontend :3001 with an 8 s refresh interval), driving the real flow: Connections → Select Account → Configured Scope → every module.

- **21 of 21 modules visited** (11 Databricks operations + 10 FinOps). Final run: **0 console errors, 0 HTTP errors, 0 mock sentinels** (`$284,620`, `$176,840`, `88,420`, `$300,000`, "Azure Production Account", "adb-lakehouse-eastus" and others were all absent), no stale flags.
- **Connection state consistent everywhere:** sidebar badge **CONNECTED** and FinOps header **"Azure Databricks Dev Connected"** on all pages; environment chip **"Development"**; SQL warehouse chip **STOPPED** shown separately.
- **Inventory rendered equals the API:** Clusters lists 1 cluster (`1102-081455-7t3bqp3v`, TERMINATED); Databricks Apps shows 3 apps.
- **Unavailable values:** every blocked KPI renders `-` with its reason in a tooltip plus a provenance banner ("To unblock: explicit human approval to start the SQL warehouse … plus SELECT on system.billing.usage"). Executive Overview says "No billing data ingested yet: spend figures stay unavailable until an approved read-only ingestion runs."
- **Live refresh:** with an 8 s interval the "Updated" stamp advanced 09:44:25 to 09:44:57 UTC, with 4 health polls in 30 s.
- **Outage / stale test:** stopped the backend mid-session → sidebar became **"CONNECTED (STALE)"**, the FinOps header showed **"Stale data: last refresh failed"**, and the Updated stamp stayed frozen at 09:48:16. After restarting the backend the stamp advanced to 09:49:40 and the stale flag cleared.
- **Bugs the browser found and fixed:** (1) status stayed DISCONNECTED after a successful discovery (registry copy race); (2) the Connect page swallowed validation failures with a fake offline success; (3) **blocking discovery froze the event loop**, producing proxy 500s on health/discovery/billing every refresh cycle. Discovery and other SDK/CLI calls now run in worker threads; `/health` answers in about 10 ms during a refresh and the final run had zero 500s. Leftover `print("RUNNER …")` debug output was also removed.
- Evidence (screenshots, page text, API bodies per module) is in the verification scratch directory, not committed.


## 10. Test results

| Gate | Result |
|---|---|
| `ruff check backend/` | pass |
| `ruff format --check backend/` | 2 pre-existing findings in files not touched (`db/session.py`, `scripts/run_migrations.py`) |
| `mypy src` | pass (87 files) |
| `pytest backend/tests` | **443 passed, 3 skipped**; coverage 85% (`finops_analytics_service` 95%, `refresher` 89%, `workspace_service` 74%) |
| `npm run lint` / `typecheck` | pass / pass |
| `npm test` | **11 suites pass** (new: `connection-state.test.ts`, `finops-live-data.test.ts`) |
| `npm run build` | success (built into a separate dist dir so it cannot disturb a running dev server) |

New backend regression tests (`test_m2_4_connection_state.py`, 24 tests): a stopped warehouse never changes workspace state; all six states map correctly; permission failure is explicit; a failed refresh keeps the last good inventory and flags stale; an old success is flagged stale; registry status is shared across service instances (root cause of discrepancy 1); refresher single-flight / interval / activity window; warm-up is bounded and non-blocking; discovery runs off the event loop; `-` with a reason versus a real zero; empty billing summary and reconciliation are null; unmatched SKU is never verified spend; actual figures appear only when billing rows exist; budget utilization needs both a budget and actuals.
Frontend tests: single derivation of connection state; `-` versus real-zero counts; single-flight refresh controller; stale by age and on failure; static scans for hardcoded workspace/environment/mock-connection strings and retired mock figures.

Honesty note: tests that use fixtures use offline test data and make **no live claim**. Live claims come only from the browser and API runs in section 9.


## 11. Remaining approval requirements

1. **Start SQL warehouse `05ed10a52697a344` (compute cost) and approve read-only ingestion** — unlocks spend, DBU, trends, allocation, showback, workload cost, forecast, anomalies.
2. `SELECT` on `system.billing.usage`, `system.billing.list_prices`, then `system.compute.*`, `system.query.*`, `system.serving.*`/`ai_gateway`, `system.lakeflow.*`, `system.access.*` — utilization, tokens, job cost, table size (`DESCRIBE DETAIL`).
3. Azure `Reader` + `Cost Management Reader` on the workspace subscription — network, egress, storage spend, discounts/credits.
4. A configured budget (`FINOPS_MONTHLY_BUDGET_USD`) — budget utilization and overrun.
5. **Restart your running backend** (PID on :8000 is stale) so it serves current code.

## 12. Remaining limitations (honest list)

- Spend-dependent modules are `-` until item 1 above; their *calculation paths* are tested only with offline fixtures.
- `LandingView` (the `view=home` demo page) still contains a hardcoded demo subscription (`sub-prod-01`) and `handleSelectSubscription` has a `sub-prod-01 → rg-finops-eastus` mapping; it is not part of the Databricks dashboards but is a remaining hardcoded demo path.
- Azure Monitoring tabs (Overview & Trends … Cost & Waste) and the multi-cloud architect flow are outside the Databricks data path. For this subscription they were observed live (`data_source: live_authenticated`, 18 resources), but the backend still contains labelled `mock_fixture`/`simulation_benchmark` fallbacks that appear when ARM auth is absent; they were not audited line-by-line here.
- `GET /connections` and some ARM calls are slow (several seconds) and one transient 500 occurred on `/connections/validate` under two concurrent browser sessions; the UI now reports such failures instead of masking them.
- Resource-group, Fabric and VM discovery have no backend endpoint, so those Configuration sections are empty.
- Per-user (masked) query-history identities are as returned by the source layer.
- Git: an earlier whole-directory `ruff format tests` changed on-disk line endings (LF) of 26 unrelated test files; their content is identical to HEAD (verified with `git diff --quiet`). `db/session.py` and `scripts/run_migrations.py` still fail `ruff format --check` (pre-existing, untouched).

## Module matrix

| Module | Live data verified | Mock data removed | Unavailable values handled | Browser verified |
|---|---|---|---|---|
| Executive Overview | Inventory counts live; spend not available | Yes | `-` + reason + banner | Yes |
| Cost Explorer | No (needs billing) | Yes | `-`, empty-ledger message | Yes |
| Cost Allocation | Rule count only | Yes | `-`; untagged stays Unallocated | Yes |
| Cost & Billing (showback) | No (needs billing) | Yes | `-` | Yes |
| Forecast & Budgets | No (needs 14+ days of billing and a configured budget) | Yes | `-`, INSUFFICIENT_HISTORY | Yes |
| Anomaly Detection | No (needs 14+ days of billing) | Yes | `-` | Yes |
| Optimization Advisor | Yes (configuration findings; none on healthy config) | Yes | savings `-` | Yes |
| AI Economics | 27 endpoints live; usage blocked | Yes | `-` | Yes |
| Governance & Policies | Yes (policy and owner counts) | Yes | compliance `-` | Yes |
| Reports & Audit | Audit trail starts empty (real events only) | Yes | n/a | Yes |
| Databricks Overview / Clusters / Warehouses | Yes (1 cluster, 1 warehouse) | Yes | utilization `-` | Yes |
| Jobs & Pipelines | Yes (confirmed empty by API) | Yes | n/a | Yes |
| Model Serving / Apps | Yes (27 / 3) | Yes | usage `-` | Yes |
| Unity Catalog | Yes (9 catalogs / 108 schemas / 780 tables) | Yes | size `-` | Yes |
| System Tables | Metadata live (46 tables); rows blocked | Yes | no sample rows | Yes |
| Query History | Yes (live REST, paginated) | Yes | cost correlation `-` | Yes |
| Network & Cloud, Data & Storage, Workload Economics | Storage/catalog inventory live; network needs Azure Reader | Yes | `-` (NOT_AUTHORIZED / BLOCKED) | Not reachable from the sidebar; verified via API only |
| Connect Cloud / Configuration | Real ARM subscriptions (Azure subscription 1 shows **Disabled**) | Yes | RG/Fabric lists empty | Yes |
| Azure Monitoring tabs (8) | Live ARM for this subscription | Not audited line by line | labelled fixtures when no auth | Opened, no console errors |

