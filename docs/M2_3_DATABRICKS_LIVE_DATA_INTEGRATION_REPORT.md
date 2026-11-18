# M2.3 Databricks Live Data Integration Report

> **Branch:** `feature/live-finops-kpi-integration` · **Workspace:** `adb-deaccelerator-dev` (`642006393507276`)
> **Auth:** Azure CLI delegated (unchanged M2.2A) · **Date:** 2026-11-13
> **Safety:** no SQL executed, SQL warehouse `05ed10a52697a344` never started (verified `STOPPED` after live run), no cluster/permission/cloud mutation.

## 1. Mock-data inventory (found)

| # | Location | Mock content |
|---|---|---|
| 1 | `billing_ingestion_service.py` `_CANONICAL_BASELINE_USAGE` + seeded run `run-baseline-001` | 11 fabricated `system.billing.usage` rows (88,420 DBU) presented as ingested billing |
| 2 | `finops_analytics_service.py` (5,889 lines) | Hardcoded ledger ($176,840 / 24 rows), $42,180 MTD, trends, product families, budgets ($300,000), forecast ($319,500, "26.7236-day velocity"), anomalies, 5 decisions ($24,530), cluster/warehouse runtime & utilization, heatmap, jobs, token counts (10.28B), Genie/agent tables, storage tiers, network components, departmental chargeback, governance policies/exceptions, seeded audit events, settings sources, AI narratives for every module, 10 system tables with fake `sample_records`, 7 fake query-history rows |
| 3 | `FinOpsCommandCenterView.tsx` | Hardcoded KPI cards on 6 modules, SVG chart paths, fallback composition/cost-driver rows, `createFallbackKpi` demo KPIs, local scenario formula, demo ingestion banner/modal numbers, export CSV/PDF numbers |
| 4 | `KpiDetailDrawer.tsx` (740 lines), `ResourceDetailDrawer.tsx` (1,318 lines), `AnomalyDetailDrawer.tsx` | Fabricated lineage, breakdowns, narratives, per-resource telemetry |
| 5 | `DatabricksWorkspaceDetailView.tsx` | Query History fallbacks (7 / 5 / 1 / "1,432 ms") |

## 2. Mock data removed
All of the above from active paths. The synthetic billing rows now live **only** in `backend/tests/fixtures/billing_baseline.py` (test-only, with an independent expectations calculator). The runtime billing store starts empty. The rate card is kept, relabelled "Built-in rate card", and is never presented as billing data.

## 3. Actual Databricks sources integrated
| Source | Used for | Access |
|---|---|---|
| Workspace discovery (clusters, warehouses, jobs/runs, serving endpoints, apps, MLflow, policies, catalogs) | Compute, AI inventory, governance, workloads, recommendations | REST/SDK, read-only |
| Unity Catalog metadata (catalogs/schemas/tables) | Data & Storage inventory | REST, read-only |
| System-table **metadata** (schemas, columns, SELECT grants) | System Tables explorer, readiness | REST, read-only (no row reads) |
| **Query History API** | Query History (pagination, status, warehouse, date window) | REST, read-only, no SQL, no warehouse start |
| `system.billing.usage` rows (once ingested) | Overview, Cost Explorer, Allocation, Showback, Workloads, Forecast, Anomaly | **BLOCKED_PENDING_APPROVAL** (SQL) |

`run_ingestion` previously discarded approved-run rows; it now maps `system.billing.usage` rows (`_row_to_usage_record`), prices them, de-duplicates by `record_id`, and preserves retractions. It remains behind the existing human-approval token gate.

## 4. Dashboard modules updated
All 15 modules plus Query History and System Tables. New response contract: every module returns a `provenance` map (`LIVE`, `CALCULATED`, `ESTIMATED`, `UNAVAILABLE`, `NO_DATA`, `BLOCKED_PENDING_APPROVAL`, `INSUFFICIENT_HISTORY`, `NOT_AUTHORIZED`) with message and unblock requirement; the UI renders a provenance banner and a status badge on every KPI. A null value renders its reason ("Awaiting billing data"), never `$0`. Nullable schema fields replaced fabricated zeros.

## 5. KPI calculation methodology
- **Spend** = Σ(`usage_quantity` × list price) over ingested DBU rows, per usage month (CALCULATED; excludes discounts, credits, Azure infra — stated in caveats). Retractions (negative quantity) net out.
- **AI spend** = rows whose `billing_origin_product` is model-serving/AI; subset of total, never added.
- **Allocation/Showback** = owner-type tag (`owner/team/business_unit/cost_center/department`); untagged spend stays **Unallocated**, never distributed; shared pool/disputes UNAVAILABLE.
- **Forecast (ESTIMATED)** = MTD + trailing-7-day mean × remaining days; requires ≥ 14 usage days. Budget only from `FINOPS_MONTHLY_BUDGET_USD` (new optional setting); accuracy needs ≥ 3 cycles.
- **Anomalies** = trailing ≤28-day z-score ≥ 3 (SD floored at 5% of mean); requires ≥ 14 days.
- **Recommendations** = rule checks on live configuration (warehouse auto-stop > 10 min/disabled, cluster auto-termination missing/> 60 min, serving scale-to-zero off) with evidence, methodology, confidence, source timestamp. **Savings are never claimed** (`null`, UNAVAILABLE) without usage + billing data; realized savings UNAVAILABLE.
- **Module AI analysis** is now a deterministic summary of the module's own KPIs/provenance (no authored numbers).

## 6. Live verification evidence (read-only, Dev, 2026-11-13)
Run via the service layer with Azure CLI auth (no tokens printed):
- Discovery `completed`: 79 resources — 1 cluster, 1 policy, 1 warehouse, **27 serving endpoints**, 1 MLflow experiment, 35 runs, **9 catalogs**, **3 apps**, 0 jobs.
- Unity Catalog: 9 catalogs / **108 schemas / 780 tables**, state LIVE. System-table metadata: 46 tables, `sql_executed=false`, `compute_started=false`.
- Overview spend: `BLOCKED_PENDING_APPROVAL` / "Awaiting billing data" (no fabricated spend). Token KPIs BLOCKED. Savings UNAVAILABLE.
- Cluster `1102-081455-7t3bqp3v` TERMINATED, auto-termination 10 min (healthy → no recommendation). Warehouse `05ed10a52697a344` STOPPED, auto-stop 5 min → no recommendation. (Rules correctly stay silent on healthy config.)
- **Query History API: LIVE**, 10 records returned, `has_next_page=true`.
- Warehouse state after run: **STOPPED**.
Not live-verified in a browser; the UI was verified by typecheck/lint/build and tests only.

## 7. Still unavailable and why
| Feature | Required source | State |
|---|---|---|
| Spend, trends, composition, cost explorer ledger, allocation, showback, workload cost, forecast, anomalies | `system.billing.usage`, `system.billing.list_prices` | BLOCKED_PENDING_APPROVAL |
| Utilization, uptime, idle %, heatmap, job cost | `system.compute.*`, `system.lakeflow.*` | BLOCKED_PENDING_APPROVAL |
| Token counts, latency, requests, Genie/agent economics | `system.serving.endpoint_usage`, `system.ai_gateway.usage` | BLOCKED_PENDING_APPROVAL |
| Table size, growth, last access, storage tiers/cost | `DESCRIBE DETAIL` / `system.information_schema` or Azure Monitor | BLOCKED_PENDING_APPROVAL |
| Network/egress/private endpoints, storage & infra spend, discounts/credits | Azure Cost Management Reader (Reader on subscription) | BLOCKED (Azure access not granted) |
| Policy compliance/violations/exceptions, shared pools, disputes, cost-per-task | no source connected | UNAVAILABLE |
| Query `cost_correlation_dbu`, bytes written | not in Query History API | UNAVAILABLE (null) |

## 8. SQL / compute approval requirements
To unlock the billing-derived modules: (1) explicit human approval to start warehouse `05ed10a52697a344` (or another approved warehouse) — compute cost is incurred; (2) `SELECT` on `system.billing.usage`, `system.billing.list_prices` (later `system.compute`, `system.serving`, `system.query`, `system.lakeflow`, `system.access`); (3) a server-issued approval token via the existing gate, then `POST /api/v1/finops/ingestion/run` with `is_approved=true`. Nothing in this milestone requested or used these. Azure modules additionally need `Reader` / `Cost Management Reader` (read-only).

## 9. Backend results
- `ruff check backend/`: pass. `mypy src`: **pass (86 files)**.
- `pytest backend/tests`: **419 passed, 3 skipped**; coverage 84% overall, `finops_analytics_service.py` 95%, `billing_ingestion_service.py` 84%.
- `ruff format --check backend/`: **2 pre-existing findings in files not touched by this work** (`db/session.py`, `scripts/run_migrations.py`); left unchanged to avoid unrelated edits.
- New suite `tests/test_m2_3_live_data.py` (20 tests): no-money-without-billing for all 13 modules, mock-sentinel scan of every response, row mapping + approved-run ingestion + idempotency + retractions, unallocated handling, anomaly/forecast history gates, rule negatives/thresholds, UC cache mapping, Query History error states and the ASGI route (pagination, date filters, bounds).
- **Existing tests:** 48 tests asserted the retired modelled numbers. None were deleted; each was rewritten in place to assert the same invariant against the new behaviour using values recomputed independently from the fixture (e.g. the real fixture total is $168,834.25, not the old $176,840, confirming the old figures were never consistent with the rows). 11 ingestion tests now load the test fixture explicitly. Mock-labelled tests use offline fixtures and make no live claims.

## 10. Frontend results
`npm run lint`: pass · `typecheck`: pass · `npm test`: **10 suites pass** (new `finops-live-data.test.ts` including a static scan that fails if retired mock figures return) · two label assertions in `finops-navigation.test.ts` updated for renamed UI text ("Budget burn", "Configuration findings").

## 11. Production build
`npm run build`: **success** (Next.js, static pages 4/4).

## 12. Git integrity
Branch `feature/live-finops-kpi-integration`, HEAD `df6868b` unchanged; no commit, reset, clean, stash or checkout run. Existing modifications preserved, including `fabric-integration/sync-agent/config.py` (untouched by this work); no file under `fabric-integration/` edited. `auth.py` auth logic unchanged (only a return-type annotation on `require_roles`). `schemas/domain.py` and ADRs untouched. One unintended formatter edit to `db/session.py` was reverted. `ruff format` over `src` did reformat whitespace in other already-modified files.

## Final module matrix
| Dashboard Module | Previous | Final | Live Data Source | Verification |
|---|---|---|---|---|
| Executive Overview | Hybrid | Live inventory + BLOCKED spend (computes from ingested rows) | Discovery; `system.billing.usage` (blocked) | Live run + tests |
| Cost Explorer | Mock | BLOCKED (real ledger once ingested) | `system.billing.usage` | Fixture tests; blocked state live |
| Cost Allocation | Mock | BLOCKED; tag-based, explicit Unallocated | billing tags | Fixture tests |
| Compute & Warehouses | Hybrid | **Live inventory/config**; utilization BLOCKED | Clusters/Warehouses/Jobs APIs | **Live** |
| AI Economics | Hybrid | **Live 27 endpoints**; usage BLOCKED | Serving API; `system.serving` (blocked) | **Live** |
| Data & Storage | Hybrid | **Live UC catalogs/tables**; size BLOCKED | Unity Catalog API | **Live** (780 tables) |
| Optimization Advisor | Hybrid | **Config-based, evidence + timestamp**; savings UNAVAILABLE | Live configuration | **Live** (0 findings on healthy config) + tests |
| Anomaly Detection | Hybrid | INSUFFICIENT_HISTORY / BLOCKED (z-score once ≥14 days) | billing rows | Fixture tests |
| Forecast & Budgets | Mock | INSUFFICIENT_HISTORY; ESTIMATED once ≥14 days; config budget | billing rows + setting | Fixture tests |
| Showback / Chargeback | Mock | BLOCKED; tag-based, nothing distributed | billing tags | Fixture tests |
| Workload Economics | Mock | Live job/pipeline list; cost BLOCKED | Jobs API; billing rows | Fixture tests |
| Network & Cloud | Mock | BLOCKED (needs Azure Cost Mgmt Reader) | none accessible | Live (blocked state) |
| Query History | Mock | **LIVE** with pagination + date filter | Query History REST API | **Live** (10 rows, paged) |
| System Tables & Billing | Partial | **Live metadata (46 tables)**; rows BLOCKED | Unity Catalog API | **Live** |
