# P0 / P1 Independent Code Review

Read-only review of the P0/P1 remediation (branch `feature/live-finops-kpi-integration`, HEAD `b199b0c`, nothing staged or committed).
Method: read the changed source, tests, migration and frontend code against the findings in `M7_1_PRECOMMIT_REVIEW_REPORT.md`, `V5_1_LIVE_DATA_READINESS_AUDIT.md` and `P0_P1_REMEDIATION_REPORT.md`; ran **in-process, offline probes** (mock auth, no network, no SQL executed) against the validator, token signer and row-limit parser.
Not done in this review: the full backend/frontend suites were **not re-run** (the tree is unchanged since the 612-passed run reported earlier); no live call, no SQL, no warehouse, no migration, no DB connection, no code change.

Classification: **PASS** = defect fixed and evidenced; **PARTIAL** = fixed for the stated case but a gap remains; **FAIL** = defect or false claim; **NOT VERIFIED** = cannot be proven offline.

## 0. Verdict

P0/P1 is **not accepted as written**. The core mechanics are sound (D4, D10, C1, P1 fallback removal), but the review found one security finding the remediation report glosses over (the approval-token route, §3), two claims in the report that the code does not support (currency and D5 in the analytics layer), a UI that contradicts the new `incomplete` status, and bugs in the PostgreSQL tests. None of these is a technical dependency of P2, but several must be settled before any warehouse start.

## 1. Finding matrix

| # | Area | Class | Summary |
|---|---|---|---|
| 1 | D4 timestamp canonicalisation | **PASS** | `canonical_timestamp()` is used for both timestamps in `_row_identity_hash`; the four formats hash identically and a re-extract is a duplicate. Production key still provisional (correct). Residual: two field-identical rows in one batch still collapse (P2 from the earlier review); real Statement-API timestamp formats **NOT VERIFIED**. |
| 2 | D5 attribution | **PARTIAL** | App filter now `app_id`-only and exact matching is used. But analytics `_RESOURCE_META_KEYS` still omits `instance_pool_id`, `notebook_id`, `serverless_compute_id`, which `billing_sql.ATTRIBUTION_RULES` attributes. Rows carrying only those keys resolve in billing but have no resource in analytics. `_FILTER_META_KEYS` still has only four filters (no job/pipeline). The report's "same priority order" claim holds only for the shared subset. |
| 3 | D10 preview dates | **PASS** | Route defaults are `None` → today-derived; the test scans `finops.py`. Other stale date defaults exist outside this scope: `cost_management_service.query_subscription_costs` defaults `2026-11-01`/`2026-11-30` and subscription `sub-finops-enterprise-01`; `services/ingestion/providers/*` embed `2026-11-05` cost records (whether gated is **NOT VERIFIED**). |
| 4 | C1 statement completeness | **PARTIAL** | Logic is correct and well tested against fakes: polling, cancel on timeout, FAILED/CANCELED/CLOSED, `truncated`, chunk following, row-count and chunk-count cross-checks, no manifest, external links. SDK field names were confirmed against the installed SDK. Gaps: (a) the poll deadline starts after the initial ≤50 s synchronous wait, so worst case is ~timeout + 50 s; (b) `cancel_execution` is a write-type API call (cancels only our statement, best-effort) — acceptable but should be a stated, approved behaviour; (c) `len(rows) >= bound` marks an exactly-full result incomplete (conservative, correct, but cannot distinguish "exactly N"); (d) the token is consumed before execution, so a timed-out or failed statement burns the approval (by design; needs a new approval to retry); (e) all evidence is hand-built response objects — real SDK payloads **NOT VERIFIED**. |
| 5 | C2 rate-card completeness | **PARTIAL** | Own fixed bound (50 000), chunks followed, truncation/limit flagged on the run and on the summary. Gaps: `spend_complete` ignores `price_card_complete`, and no analytics provenance or KPI reads it (grep: only the schema and the service set it), so a partial card does not degrade a displayed spend. There is no keyset pagination: if the card exceeds Databricks' inline-result size cap the statement fails and there is no smaller-page fallback. Order is `sku_name, price_start_time`, so a truncated card drops alphabetically-late SKUs. |
| 6 | Currency handling | **PARTIAL / FAIL for analytics** | Billing service: **PASS** — `(rate, currency)` ambiguity, `spend_by_currency`, `cost_by_currency`, nulled totals, failing `single_currency` check, all tested. Analytics: **FAIL** — the mixed-currency guard exists, but every KPI is built with `currency="USD"` and formatted by `_usd()` (`$`); a rate card in a single non-USD currency is displayed as dollars. The remediation report's "no conversion anywhere" is true, but "currency handling fixed" is not. |
| 7 | Token scope | **PARTIAL** | Execution enforces SQL-hash, warehouse, workspace, expiry, LIMIT ≤ signed `max_rows` (parsed from the AST), single use, and rejects legacy tokens live. The signed **dates are not bound to the SQL**: they are metadata the caller echoes; verification compares the caller's claimed dates with the signed dates, and the hash is the only real binding. Issuance does not check that `max_rows` or the dates correspond to the statement. See §3 for the route. |
| 8 | Approval-token route | **FAIL** | See §3. |
| 9 | Migration 0004 | **PARTIAL** | Static review: empty-table guard, no placeholder hash, no fabricated `0`, NULL-safe functional unique index, run columns added, downgrade guarded; offline render succeeds. Caveats: the guard is skipped in `--sql` mode by design; the functional index is skipped by SQLAlchemy reflection (warning), so Alembic autogenerate will not see it; the earlier `account_id VARCHAR(64)` vs ORM 100 drift remains; no whole-schema ORM↔migration parity test. Applying it is **NOT VERIFIED** (no database). |
| 10 | Azure fallback removal (P1) | **PASS** | `_discover_azure_scopes` has no fabricated topology; identifiers exist only in `demo_fixtures.py` (test asserts this). No token and no flag → `authentication_required`, `data_source="none"`, empty tree. Live branch untouched. 401/403/other now classified. Limit: only the *configuration* path was changed; other fixture paths (`azure_inventory`) were already gated. |
| 11 | Demo fixtures default-off / not shown as live | **PARTIAL** | `allow_demo_fixtures` field default is `False`, and no `.env` file in the repo sets it. But `tests/conftest.py` sets `ALLOW_DEMO_FIXTURES=true` for the whole suite, so most API tests cannot detect a leak (the new tests pass explicit `Settings`). The fixture response is flagged (`data_source="demo_fixture"`, "DEMO FIXTURE" message) yet reports `status="ready"` and its nodes carry no per-node label; the route is a public GET and no frontend code reads `data_source`. Any consumer that reads only `tree` would show plausible-looking tenant data. |
| 12 | Backward compatibility — API | **PASS** | Changes are additive: new status literals, new optional fields, `incomplete` run status, preview params became optional. `verify_approval_token` defaults (`enforce_scope=False`) preserve old behaviour for non-execution callers. Strict clients validating the old `status` enum would reject the new values. |
| 13 | Backward compatibility — frontend | **FAIL (one defect)** | `FinOpsCommandCenterView.handleExecuteIngestionRun` shows "Ingestion completed: N records inserted." for **any** status other than `approval_required` — including `failed` and the new `incomplete`. P0 introduced `incomplete` precisely so partial data is never reported as success; the only UI consumer contradicts it. (Pre-existing for `failed`.) Typecheck/lint/build/tests pass; types were widened correctly. |
| 14 | PostgreSQL tests | **FAIL (test defects), NOT VERIFIED (execution)** | See §4. |
| 15 | Tests cannot touch the application DB | **PARTIAL** | See §5. |

## 2. Original findings versus implementation

| Original | Status after P0/P1 |
|---|---|
| H1 / F2 (D4) | Fixed (row 1) |
| H3 / F3 (D5) | Partly fixed (row 2) |
| H4 / F1 (D10) | Fixed (row 3) |
| C1 | Fixed offline (row 4) |
| C2 | Partly fixed (row 5) |
| M1 mixed currency | Fixed in billing service; not in analytics display (row 6) |
| M2 evidence counter | Fixed (cross-run ids counted) |
| M3 migration | Fixed statically (row 9) |
| M4 run columns | Fixed in ORM and migration; no FKs/lineage (acknowledged) |
| M5 token `max_rows`/dates not enforced | `max_rows` and dates enforced at execution; token route still too permissive (row 8) |
| M6 legacy / `TEST-APPROVED-TOKEN` | Legacy refused live; `TEST-APPROVED-TOKEN` bypass still gated only on `auth_type=="mock"` or `app_env=="testing"` |
| L1 token burnt on outage | Fixed |
| L2 `/billing/usage` limit `ge=1` | Not done |
| L3 weak tests | Mixed-currency and default-date tests were replaced with real ones; other weak tests remain |
| D7-1/D7-2 PostgreSQL evidence | **Still open** — tests written, never executed |

## 3. Approval-token route investigation (`POST /ingestion/approval-token`)

Probe results (validator and signer run in-process; "ACCEPTED" means it would be signed):

| Statement | Result |
|---|---|
| `SELECT * … usage LIMIT 50000` (all workspaces, all columns) | ACCEPTED |
| `SELECT identity_metadata, usage_metadata …` | ACCEPTED (identity data, previously excluded by D11 only because the builder omits it) |
| Another workspace's rows (`workspace_id='999'`) | ACCEPTED |
| `CROSS JOIN usage a, usage b LIMIT 50000` | ACCEPTED (warehouse-cost amplification) |
| `ai_query('endpoint', …)` over usage rows | ACCEPTED (invokes a model-serving endpoint: cost and data leaving the table) |
| `http_request(conn => …)` | ACCEPTED (external call through a connection) |
| `UNION`, `OFFSET`, nested sub-queries | ACCEPTED |
| No `LIMIT` | ACCEPTED at issue (refused only later, at execution) |
| `read_files(…)`, `system.access.audit`, table-valued `explode` | rejected |

Findings:

1. **The validator is an allow-list of tables, not of statements.** Function allow-listing is a small deny-list (`secret`, `reflect`, `current_user`, …); `ai_query`, `http_request` and similar functions with side effects or egress are not denied. A token for such a statement is validly signed. This is read-only in the SQL sense but not side-effect-free.
2. **The signed approval is not scoped to what the product actually runs.** The only code path that executes a token is `run_ingestion`, which rebuilds fixed SQL, so a token for an ad-hoc statement is **currently inert** through the API (the SQL hash would not match). That is a mitigation by accident, not by design; any future caller of `execute_read_only_statement` inherits the full exposure.
3. **Issuance does not bind scope to SQL.** `max_rows`, `start_date`, `end_date` are free-form; the signed dates need not appear in the SQL; `max_rows` need not match the `LIMIT`; no `workspace_id` predicate or `LIMIT` is required.
4. **Workspace mismatch in the response.** The token signs the *service's* workspace id, but `BillingApprovalTokenResponse.workspace_id` echoes `request.workspace_id` (verified in `finops.py`; the signed payload in the probe was workspace `111` regardless of any request value). An approver can be told a token covers a workspace it does not.
5. **The approver is not authenticated by default.** `entra_auth_enabled` defaults to `False`; in that mode `get_current_user` returns a built-in identity with roles `Admin, Reader, CostManagementReader` for **any** caller, so any anonymous caller can mint a token, and `/ingestion/run` has no auth dependency. The human-approval gate is therefore self-service unless Entra is enabled. Only the stopped warehouse currently stops execution; once a warehouse runs, a caller who can reach the API can approve and run the fixed ingestion queries (bounded to the two allow-listed tables, the validated builder SQL and the signed limits). Nothing in this change introduced it, but P0 claimed token scope was enforced.
6. Minor: token-issue errors are returned as `400` with `str(e)`; the direct-call branch honours client-supplied `approver_roles` (unreachable under FastAPI DI, but worth removing).

**Answer:** yes, the route can sign allow-listed `SELECT`s that were never intended (broad, cross-workspace, identity-bearing, function-invoking), and the signed approval is **not** sufficiently restricted. Execution today is bounded only because the run route rebuilds its own SQL.

## 4. The five PostgreSQL integration tests

All five were reviewed by reading; **none has executed**. Defects found:

| Test | Assessment |
|---|---|
| `test_pg_issue_verify_consume_replay_across_service_instances` | **Bug:** the final assertion uses `session.execute(text('SELECT … FROM billing_approval_tokens'))`. `schema_translate_map` rewrites `Table` objects, not `text()`, so the query targets the default schema, not the private one. It will raise "relation does not exist" — or, if a `billing_approval_tokens` table exists in `public`, read someone else's table. The ORM-based calls above it are correct. |
| `test_pg_concurrent_consume_has_exactly_one_winner` | Sound: 12 sessions, separate service instances, thread→loop bridge, expects one `True`. Concurrency is bounded by the default thread-pool size (fine on typical machines). |
| `test_pg_unreachable_database_fails_closed` | **Partly vacuous:** `issue` is genuinely exercised, but `verify_approval_token(…"v2:x:y:z"…)` and `consume_approval_token("v2:x:y:z")` return `False` for a malformed token **before** touching the ledger, so they do not prove outage fail-closed. Needs a really-issued token. |
| `test_pg_missing_ledger_table_fails_closed` | Sound for issue; same gap for verify/consume (not asserted). |
| `test_pg_migration_0004_…` (needs `TEST_POSTGRES_MIGRATE=1`) | Plausible, unverified: the hand-written usage `INSERT` supplies the ORM's NOT NULL columns (`record_id, source_row_hash, workspace_id, sku_name, usage_start_time, usage_end_time, usage_date, usage_quantity`) but the real 0002 table's column types and NOT NULL set are **NOT VERIFIED** (e.g. timestamp literals into a text column, `cloud`/`usage_unit` columns); asserts the guarded-downgrade message by regex. |

**How to execute them against a disposable PostgreSQL (13+ because of `gen_random_uuid()`):**

1. Start a throw-away server, never the application's: e.g. `docker run --rm -d --name cr-pg-it -e POSTGRES_PASSWORD=<throwaway> -p 55432:5432 postgres:16`, then create two empty databases (`cr_ledger_test`, `cr_migrate_test`) with `docker exec cr-pg-it createdb -U postgres …`. Without Docker, use a locally installed PostgreSQL's `initdb` on a temp directory and a non-default port.
2. Ledger tests: `set TEST_POSTGRES_URL=postgresql+asyncpg://postgres:<throwaway>@127.0.0.1:55432/cr_ledger_test` then `pytest backend/tests/test_p0_postgres_integration.py -v` from `backend/`. They create and drop a uniquely named schema.
3. Migration test: point `TEST_POSTGRES_URL` at `cr_migrate_test` (must hold no tables), also set `TEST_POSTGRES_MIGRATE=1`, and run `-k migration_0004`.
4. Remove the container afterwards. Fix the two defects above first, or the first and third tests will mislead.

Even once green, results are evidence for **PostgreSQL 16 + asyncpg on that host** only.

## 5. Can the tests reach or modify the application database?

- Every engine in the file is built from `TEST_POSTGRES_URL`; nothing imports `get_session_factory` or the application engine; the migration test sets `sqlalchemy.url` explicitly, so `alembic/env.py` does not fall back to `settings.database_url`. Without the env var all five tests skip before any connection. **No path to the application DB through the code itself — PASS.**
- The guard is **weaker than it looks**: it compares only `(host, port, database)` with `Settings().database_url`, so `localhost` vs `127.0.0.1` vs a hostname alias of the same server is not recognised, and it accepts any database whose name merely *contains* `test` (including the project's own `cloud_recommender_test` used by `conftest`, and names like `latest_prod`). If `TEST_POSTGRES_URL` is set carelessly to a shared server, the ledger tests (private schema, dropped after) are low-risk, but the migration test runs `upgrade head`, `TRUNCATE` and `downgrade base` on whatever empty database it is given. The empty-database precondition is the real protection.
- The `text()` query noted in §4 is the only statement that can touch objects outside the private schema (read only).
- Class: **PARTIAL** — safe by construction in the code, safe in practice only if the operator supplies a genuinely disposable, empty database.

## 6. Backward compatibility summary

- **Azure:** no existing route or field removed; `ScopeDiscoveryResponse` gains values/fields (additive); the authenticated discovery path is untouched. In a default (flag-off) deployment the only behavioural change is the intended one: an unauthenticated discovery no longer returns fabricated resources. `/scopes/discover` is not consumed by any UI component (only `api.ts`), so no screen changes. Live regression **NOT VERIFIED** (no live calls).
- **Databricks:** discovery and KPI code paths are unchanged apart from attribution keys and the currency guard; billing failures do not reach discovery code. Execution is stricter by design: tokens must now carry matching `max_rows`/dates, and unbounded statements are refused — any external script that minted loose tokens will now be refused.
- **Frontend:** types widened; build/lint/typecheck/13 suites passed; the run-result toast defect (row 13) is the one behavioural conflict.

## 7. Blockers

**Hard blockers to starting P2 (code):** none. P2 (live registries instead of `KNOWN_*` lists) does not depend on the token path.

**Conditions I recommend before P2 is authorised** (small, and they touch the file P2 will edit):
1. Correct `P0_P1_REMEDIATION_REPORT.md`: currency and D5 are **partial**, the token route finding is open, and the PostgreSQL tests are defective as well as unexecuted.
2. In `finops_analytics_service.py` (P2's target): align `_RESOURCE_META_KEYS`/filters with `ATTRIBUTION_RULES`, and stop hardcoding USD/`$` in KPIs (derive the currency from the priced rows or show it as unknown).

**Blockers to any warehouse start, token mint or ingestion (P6/P7), independent of P2:**
- B1 Harden the approval-token route: deny side-effect/egress functions (`ai_query`, `http_request`, …) or switch to allowing only the two builder statements; require a `workspace_id` predicate and `LIMIT`; bind `max_rows`/dates to the SQL at issuance; stop echoing `request.workspace_id`; require authentication (Entra) for token issue **and** run, or refuse to run in live mode when `entra_auth_enabled` is false.
- B2 Fix the two PostgreSQL-test defects, then execute all five on a disposable database and record the result.
- B3 Make `price_card_complete` degrade `spend_complete` and the analytics provenance; decide the price-card paging strategy for oversized results.
- B4 Fix the UI toast so `failed` and `incomplete` are never shown as "completed".
- B5 Obtain evidence of real Statement-API payload shapes (timestamps, struct columns, chunking) under the approved A3–A5 steps; keep the dedup key provisional until then.

**Lower priority / track:** poll-deadline accounting and the `cancel_execution` call (C1 a/b); `/billing/usage` `limit` `ge=1`; `TEST-APPROVED-TOKEN` startup guard; stale defaults in `cost_management_service` and ingestion providers; per-node labelling of demo fixture nodes and removing the global `ALLOW_DEMO_FIXTURES=true` from `conftest` for tests that should prove default-off behaviour.

## 8. Confirmation of constraints

No code, test, migration or existing report was modified; the only file created is this review. No live cloud call, Databricks SQL, warehouse start, migration, credential or permission change, Fabric change, commit or push occurred. The probes ran in-process with the mock auth type and the test signing secret; no network access was needed. Working-tree changes and untracked files (including `docs/databricks_api_audit/`, which must not be committed) are preserved.
