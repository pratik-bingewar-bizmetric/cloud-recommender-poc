# M7.1 — Databricks Billing Ingestion Hardening Report

| | |
|---|---|
| Branch / baseline | `feature/live-finops-kpi-integration` @ `b199b0c` (verified equal to `origin/feature/live-finops-kpi-integration` before starting) |
| Reference | `docs/M7_DATABRICKS_BILLING_INTEGRATION_DESIGN.md` (D1–D11 used verbatim) |
| Status | **Code-level corrections implemented and tested offline. Not committed, not pushed.** Migration `0004` is prepared and **not applied**. |
| Executed against Databricks / Azure / Postgres | **Nothing.** No SQL, no warehouse start, no ingestion, no migration, no credential/permission/auth/Fabric change, no cloud change. |

---

## 1. D1–D11 status

Definitions are the ones in §1.3 of the design report.

| # | Defect (design report) | Status | What changed | Proven by |
|---|---|---|---|---|
| **D1** | Hardcoded rate card (`_CANONICAL_LIST_PRICES`) | **Fixed** | Constant and seeding removed. `_price_store` starts empty; rates enter only via an approved `system.billing.list_prices` run (`run_ingestion(source_table="system.billing.list_prices")`) or `ingest_price_records`. Join is SKU + cloud + usage unit + `usage_start_time ∈ [price_start, price_end)`; unmatched/ambiguous/expired/non-DBU rows keep `effective_cost = None` (never 0) with `match_status`. | `test_d1_*` (4) |
| **D2** | `list_prices` nested `pricing` struct not parsed | **Fixed** | `_row_to_price_record` maps `pricing.default`, `pricing.promotional.default`, `pricing.effective_list.default` (dict or JSON text) to `price_default / price_promotional / price_effective_list`; `pricing_unit` → `usage_unit`. Estimate uses `effective_list`, else `default`; **promotional is never used**. A row with no usable rate is malformed, not free. Legacy flat `price_per_unit` / `pricing_unit` inputs and outputs remain (computed fields) so existing consumers don't break. | `test_d2_*` (5) |
| **D3** | `usage_quantity` precision loss (`decimal(38,18)` → `Numeric(18,4)` / float) | **Fixed in code; DB column change prepared, not applied** | `Decimal` end-to-end (`to_decimal`, no float noise, NaN/∞/bool/None rejected). Cost is the full-precision product; the old per-row cent rounding (which turns sub-cent hourly rows into `0.00`) is removed. Rounding only at presentation totals. JSON stays numeric (`float`) for consumers, plus lossless `usage_quantity_exact`. ORM columns are `Numeric(38,18)`; migration `0004` alters the DB. | `test_d3_*` (5) |
| **D4** | `record_id` alone as PK / dedup key | **Mitigated — final key deliberately NOT chosen** | No evidence is available offline: the captured Unity Catalog comments for `record_id`/`record_type` do not state whether a retraction/restatement reuses the original `record_id`. Implemented a **PROVISIONAL full-row identity** (workspace, record_id, sku, record_type, metering window, unit, exact quantity) that removes only genuine re-extracts and **cannot discard a correction row**. Runs report `shared_record_id_count` — the evidence needed to finalise the key after the first approved extract. ORM: surrogate `id` PK + `UNIQUE(workspace_id, source_row_hash)`. See §6. | `test_d4_*` (4) |
| **D5** | Attribution limited to 5 keys | **Fixed** | `billing_sql.ATTRIBUTION_RULES` (10 ID keys, ordered); `resolve_resource` / `matches_resource` are **exact** (no substring); `resource_type`/`resource_id` stored per row; summaries/lists/analytics filter through the same helper. | `test_d5_*` (3) |
| **D6** | Token consumed before warehouse-state check | **Fixed** | Order is now verify → check warehouse (STOPPED / AUTH / PERMISSION / CONNECTION raise **without consuming**) → consume (single-use) → execute. The failed-run message states the token was not consumed. Single-use after execution is unchanged (replay rejected). | `test_d6_*` (5) |
| **D7** | Durable token ledger bypassed with `AsyncSession` | **Fixed** | Root cause: sync `session.execute(...)` on an `AsyncSession` returned a coroutine; errors were swallowed. Now `LedgerHandle(session, loop)` + `_ledger_call` run the work as `asyncio.run_coroutine_threadsafe(session.run_sync(fn), loop)` from the sync worker thread (sync `Session` still works). A raw `AsyncSession`, or a call made on the event-loop thread, is **rejected**. Fail-closed: issue raises `ApprovalLedgerError` (HTTP 503), verify/consume return False when the ledger can't be read/written. The routes get the handle from a new `get_billing_ledger` dependency (live mode only; offline/mock keeps the in-memory set). | `test_d7_*` (6) |
| **D8** | SQL built by f-string from request fields | **Fixed** | New `services/databricks/billing_sql.py`: `validate_workspace_id` (`^\d{1,20}$`), `validate_iso_date`, `validate_limit` (1–50 000), window order, cloud allowlist; `IngestionRunCreateRequest` validates the same (HTTP 422), `source_table` is a `Literal` of the two allow-listed tables. Query text is built only from validated values, with fixed projections and `ORDER BY … LIMIT`. Both builders are asserted to pass the AST validator. Tokens bind to the exact built query. *Not done:* Statement-Execution bind parameters (the service ignores `parameters`; validated literals are the control). | `test_d8_*` (12 incl. parametrised) |
| **D9** | Frontend/backend billing envelope mismatch | **Fixed, compatible** | Backend: `GET /billing/usage` and `/billing/pricing` keep returning bare lists by default; `?envelope=true` returns `{total, offset, limit, records}` / `{total, records}` (`total` = pre-pagination count). Added `record_type`, `sku_name`, `limit` filters the frontend already sent. Frontend: `lib/billing.ts` `normalizeUsagePage/PricePage` accept either shape; `api.ts` requests `envelope=true`. | `test_d9_*` (4), `billing-contract.test.ts` (6) |
| **D10** | Stale defaults / copy | **Fixed** | Approval payload uses **observed** warehouse `auto_stop_mins` / `cluster_size` (`WarehouseHealthResult` new fields) — "N-minute auto-stop observed", "not observed", or "DISABLED"; fixed "10-minute", "$0.15–$0.35", "10–15 minutes" removed; cost/result size are "Not estimated". Request/validation default dates are now dynamic (last 30 days) instead of `2026-10-01…2026-11-04`. A source-scan test prevents the stale literals returning. | `test_d10_*` (4) |
| **D11** | `identity_metadata` / free-text selected | **Fixed** | Usage query selects an explicit column list + individually projected ID sub-fields of `usage_metadata`; never `identity_metadata`, `notebook_path`, `run_name`, `job_name`, `app_name`, nor `SELECT *`. Mapper ignores identity and keeps only allow-listed ID keys. Rows whose `workspace_id` ≠ the requested workspace are rejected at load. `custom_tags` is still stored (FinOps allocation needs it) — see §6. | `test_d11_*` (4) |
| (item 10) | Reconciliation correctness | **Fixed** | Previously always `RECONCILED`. Now six real checks (net-DBU identity, pricing partition, cost identity, unit separation, retraction sign, single currency) → `RECONCILED` / `PARTIAL_PRICING` (unpriced DBU rows) / `DISCREPANCY_DETECTED`; `checks[]` returned; Decimal arithmetic; `cost_basis`, `spend_complete`, `pricing_coverage_pct` on the summary so a partial estimate is never presented as complete. | `test_recon_*` (5) |
| (requirement) | Distinguish METERED_USAGE / LIST_PRICE_ESTIMATE / AZURE_INVOICED | **Done** | `CostBasis` enum on records, summary, reconciliation, ORM and frontend types/labels. `AZURE_INVOICED` is **reserved and never produced** (source scan test); the frontend label helper can't read anything else as "Billed". | `test_cost_basis_*` (2), frontend test |

---

## 2. Files changed

**New**

| File | Purpose |
|---|---|
| `backend/src/cloud_recommender/services/databricks/billing_sql.py` | Validated query builders, `CostBasis`/`MatchStatus`, attribution resolver, Decimal/timestamp helpers (pure, no I/O) |
| `backend/alembic/versions/2026_11_13_0004_billing_precision_and_row_identity.py` | **Prepared, not applied** migration (see §5) |
| `backend/tests/test_m7_1_billing_hardening.py` | 75 regression tests (D1–D11, reconciliation, cost basis, migration shape) |
| `frontend/src/lib/billing.ts` | Envelope normalisers, cost-basis labels |
| `frontend/test/billing-contract.test.ts` | 6 frontend contract tests |

**Modified (backend source)**

`services/databricks/billing_ingestion_service.py` (rewritten: no rate card, price join, dedup, price ingestion, summary, reconciliation, validated SQL, ledger pass-through) · `schemas/billing_ingestion.py` (Decimal types, price shape, envelopes, `cost_basis`, validators, dynamic dates) · `services/databricks/sql_client.py` (ledger bridge, D6 ordering, observed warehouse metadata, honest approval text) · `api/routes/finops.py` (`get_billing_ledger`, envelope, 503 on ledger failure, filters) · `db/models.py` (usage/price models) · `services/databricks/finops_analytics_service.py` (Decimal→float at the display boundary only).

**Modified (frontend)** `src/lib/api.ts`, `src/types/index.ts`.

**Modified (tests, to remove the dependency on the deleted rate card / old behaviour)** `tests/fixtures/billing_baseline.py` (TEST-ONLY `BASELINE_PRICES` in the real nested shape, `load_baseline_prices`; expectations no longer round per row), `test_m2_3_live_data.py`, `test_live_finops_integration.py`, `test_milestone_3j2_security.py` (token now bound to the exact builder query).

**Untouched by design** `docs/ADR/*`, `backend/schemas/domain.py`, Fabric, auth, `.env` files, `docs/databricks_api_audit/`. The 25 line-ending-only files remain unstaged.

---

## 3. Tests and results (all actually executed)

| Check | Result |
|---|---|
| New backend regression file `tests/test_m7_1_billing_hardening.py` | **75 passed** |
| Previously existing billing/token/analytics suites (3h, 3j2, 3j3, live finops, m2_3, finops analytics, ingestion enforcement, workspace) | pass after the intentional test updates listed above |
| Full backend `pytest tests` | **553 passed, 3 skipped, 0 failed** (478 before; +75 new). Total coverage 86%; `billing_sql.py` 95%, `billing_ingestion_service.py` 89%, `sql_client.py` 82% |
| `ruff check backend/` | **All checks passed** |
| `ruff format --check backend/` | All files formatted **except** `backend/scripts/run_migrations.py`, which is unmodified by this work (pre-existing) |
| `mypy src` | **Success: no issues found in 90 source files** |
| Frontend `npm test` | **13 suites, 0 failures** (incl. new `billing-contract`, 6 tests) |
| Frontend `npm run lint` | No ESLint warnings or errors |
| Frontend `npm run typecheck` | Pass |
| Frontend production build | Pass (isolated `NEXT_DIST_DIR`; output and the transient `tsconfig.json` include were removed afterwards, `tsconfig.json` unchanged) |
| Migration SQL (offline `alembic … --sql`, no DB connection) | Upgrade and downgrade both render; generated upgrade SQL reviewed |

Notes for honesty:
- The migration was **rendered** offline only; it has never run against PostgreSQL. `gen_random_uuid()` needs PostgreSQL ≥ 13.
- My first run of the four new API tests (D9) used the real router, whose `warm_live_metadata` dependency may attempt read-only Databricks metadata calls (it took ~70 s). I then overrode that dependency in the test fixture (now 1.6 s, fully offline). The earlier calls were metadata reads only — no SQL, no mutation, no warehouse interaction was possible from that code path — but I cannot show from here exactly what, if anything, left the machine during those first runs.
- Async-session ledger tests use a faithful `run_sync` stand-in over SQLite because `aiosqlite` is not installed; they exercise the real thread→event-loop bridge, not a live asyncpg session.

---

## 4. Behaviour changes to be aware of

1. **No prices ship with the app.** Until a `list_prices` ingestion is approved and run, every cost is `None` / "No data", and summaries say `cost_basis = METERED_USAGE`. This is intended (Golden Rule 2) but is visible in demos.
2. **Costs no longer round per row.** Totals can differ by cents from the old per-row-rounded values; the baseline test expectations were updated to round once at the end.
3. **Tokens bind to the exact built query.** A token issued for an arbitrary `SELECT *` no longer authorises the service's run (it now builds a fixed projection). Approvers must request tokens for the query shown in the plan/approval payload.
4. **Live mode requires the durable ledger on API routes.** If PostgreSQL or the migrated `billing_approval_tokens` table is unreachable, token issue returns **503** and execution fails closed. Direct service use without a ledger keeps in-memory single-use and logs `approval_token_ledger_not_configured`.
5. **Approval text** reports observed warehouse settings; where unobserved it says so.

---

## 5. Migration requirements (A1 — not applied)

`backend/alembic/versions/2026_11_13_0004_billing_precision_and_row_identity.py` (revises `2026_11_07_0003`):

- `billing_usage_records`: `usage_quantity`, `effective_cost` → `NUMERIC(38,18)`; add surrogate `id` (UUID PK, backfilled), `source_row_hash` (+ `UNIQUE(workspace_id, source_row_hash)`), `cost_basis`, `match_status`, `price_tier`, `resource_type`, `resource_id`; `record_id` becomes a plain indexed column; `currency` default `USD` dropped; new index `(workspace_id, resource_type, resource_id)`.
- `billing_price_records`: `price_per_unit` → `price_default` / `price_promotional` / `price_effective_list`; `pricing_unit` → `usage_unit`; `account_id` added; `UNIQUE` price identity (note: PostgreSQL treats NULL `account_id` values as distinct unless `NULLS NOT DISTINCT`, PG 15+, is added).
- Prerequisites: PostgreSQL ≥ 13; revisions `0002` and `0003` must already be applied (their state was **not** checked); the ledger table (`0003`) must exist before live approvals can work.
- Downgrade narrows precision and may truncate/fail if high-precision data exists.
- Until applied, nothing persists billing data: the service is still in-memory (the repository/persistence layer is Phase 1 of the design, not part of M7.1).

---

## 6. Remaining blockers and open items

| # | Item | Why it remains |
|---|---|---|
| B1 | **Final dedup key (D4)** | Needs evidence from an approved extract: check `shared_record_id_count` and whether correction rows reuse `record_id`; then replace the provisional identity and its DB constraint if needed. Not invented here, per instructions. |
| B2 | Persistence not wired | The service still uses in-memory stores; no billing repository exists. Planned Phase 1 after A1. |
| B3 | `SELECT` on `system.billing.*` and `CAN_USE` on warehouse `05ed10a52697a344` unverified | Needs the no-SQL grants check (A2) — not run in this milestone. |
| B4 | Price tier policy | `effective_list`, else `default` is implemented; the owner has not confirmed it (design open question 1). |
| B5 | `custom_tags` may contain personal identifiers (e.g. owner emails) | Stored for allocation; redaction policy is an owner decision. |
| B6 | Statement-Execution bind parameters not used | Validated literals + AST validator are the controls; parameters could be added later. |
| B7 | Frontend does not yet display `cost_basis` / freshness badges | Helpers and types exist (`costBasisLabel`); UI wiring is Phase 6. |
| B8 | Statement API limits (wait timeout window, inline result size) | Unchanged; chunking/`max_rows` handling belongs to the backfill phase. |
| B9 | No Azure invoiced cost source | `AZURE_INVOICED` is reserved only; reconciliation against Azure Cost Management is a later phase. |
| B10 | `backend/scripts/run_migrations.py` fails `ruff format --check` | Pre-existing at the baseline; untouched. |

---

## 7. Explicit approval requirements before any SQL execution

Nothing below has been requested or performed. All still apply exactly as in design §10.

| # | Approval | Gate |
|---|---|---|
| **A1** | Apply migration `0004` (and confirm `0002`/`0003` state) | DBA/owner approval; run via Alembic only after review |
| **A2** | Metadata-only grants check (`grants.get_effective`) | Read-only REST; no SQL |
| **A3** | Start warehouse `05ed10a52697a344` | Separate human operator action; the app never starts compute. A stopped warehouse no longer burns the token (D6). |
| **A4** | `list_prices` query | Signed single-use token bound to the exact query shown by the plan |
| **A5** | Each `usage` chunk | One token per statement; workspace-scoped, bounded `max_rows`, no identity columns |
| **A6** | Allow-list expansion (e.g. `attributed_usage`) | Code change + security review |
| **A7** | Any production / service-principal run | Separate scope and approval |

Hard stops unchanged: no `SELECT *`, no tables outside the allow-list, no statement without a valid token and a human-started warehouse, no fixture shown as live, no list-price estimate presented as an invoice.

---

*No commit or push was made. Review the diff and results above before committing.*

---

## Erratum (added during P0 remediation)

The D10 statement above ("stale default dates removed") was incomplete: `POST /ingestion/preview` in `api/routes/finops.py` still defaulted to `2026-10-01` / `2026-11-04`. This was found by the independent pre-commit review (finding H4) and corrected in the P0 remediation; see `docs/P0_P1_REMEDIATION_REPORT.md`. The pre-existing literal-scan test did not cover the routes module; `tests/test_p0_remediation.py::test_d10_preview_route_has_no_hardcoded_dates` now does.
