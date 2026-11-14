# M7.1 — Pre-Commit Independent Code Review

| | |
|---|---|
| Reviewed | Complete working-tree diff of M7.1 against `b199b0c`, plus `docs/M7_DATABRICKS_BILLING_INTEGRATION_DESIGN.md` (D1–D11 definitions) and `docs/M7_1_BILLING_INGESTION_HARDENING_REPORT.md` |
| Mode | **Read-only.** Nothing staged, committed, pushed or migrated. No SQL, warehouse, ingestion, cloud, credential, Fabric or database action. The only things executed were `git`/`grep`/file reads and one scratch Python probe (in the session scratchpad, importing the code with the mock SQL service) |
| Method | Read the actual code and tests for every defect; did not rely on the implementation report. Where the report and code disagree, the code was treated as authoritative |
| Excluded | `docs/databricks_api_audit/*.json` (untracked, untouched), environment files (none modified) |

## 0. Verdict

**Commit readiness: NOT READY** — three small, in-scope items must be corrected first (§9). Nothing found is dangerous (no new execution path, no secret exposure, allowlist unchanged), but the implementation report contains one **inaccurate claim** (D10) and two defects are only half-fixed (D4 idempotency fragility, D5 analytics alignment). Separately, **one pre-existing critical flaw (C1) makes the first live billing query unsafe** and must be fixed before any A3/A4/A5 approval, whether or not M7.1 is committed.

---

## 1. Git verification

| Item | Result |
|---|---|
| HEAD / branch | `b199b0c` on `feature/live-finops-kpi-integration`; equals `origin/feature/live-finops-kpi-integration` |
| Staged | none |
| Modified application/test files (M7.1) | `api/routes/finops.py`, `db/models.py`, `schemas/billing_ingestion.py`, `services/databricks/{billing_ingestion_service,finops_analytics_service,sql_client}.py`; tests `fixtures/billing_baseline.py`, `test_live_finops_integration.py`, `test_m2_3_live_data.py`, `test_milestone_3j2_security.py`; frontend `lib/api.ts`, `types/index.ts` — 12 files, +1113/−466 |
| Untracked (M7.1) | `alembic/versions/2026_11_13_0004_*.py`, `services/databricks/billing_sql.py`, `tests/test_m7_1_billing_hardening.py`, `frontend/src/lib/billing.ts`, `frontend/test/billing-contract.test.ts`, the two M7 docs |
| Untracked, must stay uncommitted | `docs/databricks_api_audit/` |
| Pre-existing line-ending-only modifications | 25 backend test files (unchanged, unstaged). `test_ingestion_enforcement.py` is among them and **is not an M7.1 edit** |
| Environment files | none modified or untracked |
| `frontend/tsconfig.json` | shows ` M` in `git status` but `git diff --ignore-space-at-eol` is empty: no content change (stale stat/line-ending noise left by the build). Do not stage it |
| Reviewer note | The M7.1 report says "12 files modified"-style scope; the real set is as above plus the 25 untouched ones |

---

## 2. D1–D11 review matrix

PASS = original problem fixed in code and exercised by tests; PARTIAL = fixed in part, or fixed but with a material residual risk; OPEN = not fixed.

| # | Original problem | Code inspected | Tests | Remaining risk | Verdict |
|---|---|---|---|---|---|
| **D1** | Hardcoded rate card | `_CANONICAL_LIST_PRICES` and seeding removed; `_price_store` empty; `_apply_price_matching` joins SKU/cloud/unit/validity on ingested prices only; unmatched ⇒ `effective_cost=None` | `test_d1_*` (4) | **Mixed-currency collision**: two price rows with equal start/rate but different currency are silently collapsed to one (probe P4: `MATCHED`, currency `USD`, arbitrary). Not flagged `AMBIGUOUS`. Usage window straddling a price change is priced at the start-time rate. The report's test `test_recon_mixed_currency_is_flagged` is **vacuous** (asserts `currency in {USD, EUR, None}`) | **PASS** (finding M1) |
| **D2** | Nested `pricing` struct not parsed | `_row_to_price_record`: dict or JSON text; `default`, `promotional.default`, `effective_list.default`; promotional never used; no-rate row ⇒ malformed | `test_d2_*` (5) | Verified only against hand-written rows shaped from Unity Catalog column metadata, **not** a real Statement-API payload. Query default `LIMIT` for the price run is 1000 (C2) | **PASS** (shape) |
| **D3** | Precision loss | `Decimal` via `to_decimal`; full-precision cost; no per-row rounding; JSON as float + `usage_quantity_exact`; ORM `Numeric(38,18)` | `test_d3_*` (5) | DB column change **exists only in unapplied migration**; until A1 nothing persists, so there is no stored-precision evidence. Analytics converts to float at its display boundary (acceptable) | **PARTIAL** (code PASS, DB pending A1) |
| **D4** | `record_id`-only dedup | Provisional full-row identity hash; second distinct row stored as `record_id#hash12`; surrogate PK + `UNIQUE(workspace_id, source_row_hash)` in ORM | `test_d4_*` (4) | See §3: hash built from **raw timestamp strings** (P1), evidence counter is **per-batch only** (P3), field-identical legitimate rows collapse (P2). Final key correctly *not* invented | **PARTIAL** (deliberately non-final; fragility found) |
| **D5** | Attribution too narrow | `ATTRIBUTION_RULES` (10 keys), exact `resolve_resource`/`matches_resource`; used by summary, list, mapper | `test_d5_*` (3) | **Not propagated to analytics**: `FinOpsAnalyticsService._FILTER_META_KEYS` still has 4 filters/6 keys (`warehouse_id, cluster_id, endpoint_id, endpoint_name, app_id, app_name`) — no pipeline/job/pool/notebook, and `app_name` is no longer ingested (D11 drops it), so the analytics "app" filter can now only match `app_id` | **PARTIAL** (finding H3) |
| **D6** | Token consumed before state check | `execute_read_only_statement`: verify → warehouse check (STOPPED/AUTH/PERMISSION/CONNECTION raise before consume) → consume → execute | `test_d6_*` (5), `test_milestone_3j2` updated | If the ledger is unreachable at consume time, the **in-memory** set is already updated (L712 precedes the DB call) so the token is burnt in memory though nothing ran (fail-closed, but contradicts the D6 intent for that case). Token is also consumed *before* `execute_statement`; a network failure there burns it (single-use by design) | **PASS** (finding L1) |
| **D7** | Ledger bypassed on `AsyncSession` | `LedgerHandle` + `_ledger_call` (`run_coroutine_threadsafe(session.run_sync(fn), loop)`); raw `AsyncSession` and on-loop-thread calls rejected; issue raises, verify/consume fail closed | `test_d7_*` (6) | See §4. **No PostgreSQL/asyncpg evidence**; stand-in only; no concurrent test through the bridge; legacy tokens bypass the ledger | **PARTIAL** |
| **D8** | SQL by f-string | `billing_sql` validators + `IngestionRunCreateRequest` validators + `Literal` source table; run path builds only from validated values; builders pass the AST validator; tokens hash-bind the exact text | `test_d8_*` (12 incl. parametrised) | Run path: sound. **Token route** still accepts any allow-listed `SELECT` text; `max_rows`/dates in the token are **not enforced at execute** (§6) | **PARTIAL** (run path PASS) |
| **D9** | Envelope mismatch | `?envelope=true` + bare list default; `normalizeUsagePage/PricePage`; `api.ts` requests envelope | `test_d9_*` (4), `billing-contract.test.ts` (6) | `limit` on `/billing/usage` has no `ge=1` (negative limit slices wrongly; `/billing/pricing` has `ge=1`). **No UI component calls these functions** (grep: defined in `api.ts` only), so end-to-end use is unproven | **PASS** (finding L2) |
| **D10** | Stale defaults / copy | Approval text uses observed `auto_stop_mins`; fixed `$0.15…`, "10-minute" removed; request/validate defaults dynamic | `test_d10_*` (4) | **Inaccurate in the implementation report:** `/ingestion/preview` in `api/routes/finops.py` L610–619 **still defaults to `2026-10-01` / `2026-11-04`** (`Query(...)` and `_param(...)`). The "no stale literals" test scans only three files and misses it. Hardcoded default warehouse name/ID remain in schema defaults | **PARTIAL** (finding F1) |
| **D11** | `identity_metadata`/free text selected | Explicit column list + flat `usage_metadata.<id>` projections; mapper ignores identity, keeps allow-listed IDs; foreign-workspace rows rejected | `test_d11_*` (4) | `custom_tags` still stored (owner emails possible). Token route can still approve a `SELECT *`-style query including identity columns (not reachable via `run_ingestion`). `app_name` loss affects analytics (D5) | **PASS** (run path) |
| (req.) | Reconciliation correctness | Six real checks, `PARTIAL_PRICING` / `DISCREPANCY_DETECTED`, Decimal sums | `test_recon_*` (5) | Mixed-currency check is vacuous in test; check "cost_identity" is largely tautological (same data both sides) — it cannot detect source-side error | **PASS** (limited power) |
| (req.) | `CostBasis` labelling | Enum on records/summary/reconciliation/ORM/frontend; `AZURE_INVOICED` unproduced (source scan) | 2 backend + frontend | Frontend does not yet render the label | **PASS** |

Scorecard (D1–D11): **PASS 5** (D1, D2, D6, D9, D11) · **PARTIAL 6** (D3, D4, D5, D7, D8, D10) · **OPEN 0**.

---

## 3. Deep review — D4 (deduplication)

What the code does (`ingest_records`, `_row_identity_hash`): the first row with a given `record_id` is stored under that key; a later row with the same `record_id` but a different identity hash is stored under `record_id#<hash12>`; identical hash ⇒ duplicate. Identity = (workspace_id, record_id, sku_name, record_type, usage_start_time, usage_end_time, usage_unit, normalised quantity). `ingestion_date` is deliberately excluded.

Behaviours verified (real code, scratch probe):

| Scenario | Observed | Assessment |
|---|---|---|
| Original + retraction + restatement sharing `record_id` (test) | all 3 inserted; net DBU correct | Good — corrections never discarded |
| Retraction arrives **before** its original (P6) | both stored (`z`, `z#…`) | Good — order independent |
| Identical re-extract in a later run | skipped as duplicate | Good — idempotent for byte-identical rows |
| **Same source row, different timestamp text** (`…00Z` vs `…00.000+00:00`) (P1) | **inserted again** | **Defect.** The hash uses raw strings. The Statement API and the SDK may format timestamps differently between calls/versions/paths, silently double-counting a whole backfill. Normalise to parsed UTC before hashing |
| Two field-identical rows in one batch (P2) | 1 inserted, 1 "duplicate" | Inherent to any identity that lacks a source-unique discriminator. If Databricks can emit two legitimate rows that are identical in all these fields, spend is under-counted. Only an approved extract can show whether that occurs; **the code cannot prove it never does** |
| Corrections spread over **different runs** (P3) | `shared_record_id_count = 0` | The evidence counter is per extracted batch, so the exact situation it exists to detect (a correction landing in a later run) is invisible. Count against the store, not only the batch |
| `ingestion_date` excluded | stored but ignored for identity | Reasonable; but then a **restatement with identical type/window/quantity** (a pure re-publication) is dropped as a duplicate — correct only if that is semantically a no-op |

Further risks: (a) any `sku_name` case/whitespace difference changes the hash; (b) `record_type` is lower-cased on ingest, so `RETRACTION`/`retraction` are consistent — good; (c) the ORM unique constraint `(workspace_id, source_row_hash)` is only as stable as the hash (see P1); (d) hash values are not persisted anywhere yet.

**Conclusion:** the provisional identity is a defensible *safe-side* choice (it prefers keeping rows) and the report honestly leaves the final key open. But the P1 fragility makes its "idempotent across repeated runs" claim weaker than stated, and P3 weakens the evidence-gathering plan. Verdict stays **PARTIAL**. No production key is proposed here.

---

## 4. Deep review — D7 (durable approval-token ledger)

### 4.1 What is correct (code reading)

- Root cause correctly identified: calling `AsyncSession.execute()` synchronously returns an un-awaited coroutine; the old `try/except` hid the failure.
- `_ledger_call` runs `fn(sync_session)` on the owning loop via `run_sync`, from a worker thread, and rejects (a) raw `AsyncSession`, (b) calls made on the loop's own thread (would deadlock). Both are tested.
- Consume is a single atomic `UPDATE … WHERE token_id=:id AND is_consumed=false RETURNING id`, then commit; zero rows ⇒ rollback + `False`. On PostgreSQL the row lock serialises concurrent updaters; the loser re-evaluates the predicate and updates zero rows. The SQL is portable to asyncpg (`returning`, boolean comparison, `run_sync` with `commit()` inside is supported).
- Fail-closed: issue ⇒ `ApprovalLedgerError` (route ⇒ 503); verify ⇒ `False`; consume ⇒ `False`. A signed token with **no ledger row** can verify but cannot be consumed (UPDATE matches 0 rows) ⇒ refused. Good.
- `get_billing_ledger` yields `None` in mock/testing and a `LedgerHandle` in live mode; one `AsyncSession` per request (no cross-request sharing).

### 4.2 Findings

| ID | Severity | Finding |
|---|---|---|
| D7-1 | **High (evidence gap)** | **No PostgreSQL/asyncpg evidence exists.** The tests use `_FakeAsyncSession` (an object with an `async run_sync` that calls a **sync SQLite** `Session`, `StaticPool`, `check_same_thread=False`). `aiosqlite` is not installed, so not even a real `AsyncSession` over SQLite was exercised. What it proves: the thread→loop bridge, error propagation, rejection rules. What it does **not** prove: asyncpg behaviour, real `AsyncSession.run_sync` + `commit()` semantics, connection-pool/transaction state across the 3–4 sequential `run_sync` calls of one request, PostgreSQL locking, JSONB/UUID types in `BillingApprovalTokenModel`, behaviour when the table is absent |
| D7-2 | **High** | **Concurrent consumption is not tested through the bridge**, and the existing concurrency test (`test_milestone_3j3_security::test_concurrent_token_consumption`) does **not isolate DB atomicity**: all threads share one service whose in-memory `_consumed_tokens` check-then-add (L710–712) runs first, so threads are mostly rejected by the in-memory set. That set has **no lock**, so two threads can both pass `if token in set` before either adds; then only the DB atomic UPDATE protects single use — and **without a ledger (direct service use / offline) nothing does** |
| D7-3 | Medium | **In-memory marking precedes the DB result** (`consume_approval_token`): on ledger outage the token is marked consumed in memory (burnt for the process lifetime) though it never ran |
| D7-4 | Medium | **Legacy tokens bypass the ledger**: 4-part tokens (no workspace/max_rows/ledger id) and 7-part tokens are still accepted by `verify_approval_token`; for 4-part, `consume` returns `True` without a ledger row. Single-use for those is in-memory only. Pre-existing, but the report's "durable single-use" statement should be qualified |
| D7-5 | Medium | **`TEST-APPROVED-TOKEN` bypass** remains gated on `auth_type == "mock"` **or** `app_env == "testing"`; a production misconfiguration of either re-opens an unauthenticated execution path. Pre-existing; worth a startup guard |
| D7-6 | Medium (operational) | In live mode the **token-issue and run routes now require PostgreSQL and the migrated `billing_approval_tokens` table** (migration `0003`, whose applied state was never checked). Until then, issuing a token returns 503. That is the intended fail-closed outcome but makes A1/0003 a **hard prerequisite for any live approval**, including A4 |
| D7-7 | Low | Timeout path: `future.result(timeout=15)` raising leaves the coroutine running; a late commit can succeed after the caller already failed (issue ⇒ orphan ledger row; consume ⇒ token consumed in DB while the run reports failure). Direction is safe (never double-spend) |
| D7-8 | Low | A read (`_ledger_allows`) opens a transaction that stays open until the consume `commit` or request end; not harmful in this flow, but an idle-in-transaction connection is held across the warehouse check |
| D7-9 | Low | `get_billing_ledger` runs for the **un-approved plan call too** (`is_approved=false`); a session-factory configuration error would 500 a request that needs no ledger |

### 4.3 PostgreSQL compatibility assessment

**Likely compatible, unproven.** Nothing in the code is dialect-specific except `UPDATE … RETURNING`, which PostgreSQL supports. The main unverified risks are (1) real `AsyncSession.run_sync` + explicit `commit()`/`rollback()` inside the callback under asyncpg, (2) pool/transaction interaction across multiple `run_sync` calls, (3) whether `0003` is applied. **Required evidence before A4:** an integration test against a disposable PostgreSQL (not the customer DB) with a real `AsyncSession(asyncpg)` covering issue → verify → consume → replay, N-way concurrent consume (exactly one winner), outage (stop DB) ⇒ fail-closed, and missing-table ⇒ fail-closed.

---

## 5. Migration `0004` review (offline only; no DB connection)

Verified by reading the file, importing the module, and rendering `alembic upgrade 2026_11_07_0003:2026_11_13_0004 --sql` and the downgrade SQL offline.

| Check | Result |
|---|---|
| Revision / chain | `revision = 2026_11_13_0004`, `down_revision = 2026_11_07_0003` ✔; offline range upgrade rendered successfully ✔ |
| Numeric precision | `usage_quantity`, `effective_cost` → `NUMERIC(38,18)`; price columns `NUMERIC(38,18)` ✔ (matches source `decimal(38,18)`) |
| Constraints / indexes | PK moved to surrogate `id`; `UNIQUE(workspace_id, source_row_hash)`; `UNIQUE` price identity; `ix_billing_usage_records_record_id`, `ix_billing_usage_ws_resource` ✔. Names match the ORM. **Caveat:** the price UNIQUE includes nullable `account_id`; PostgreSQL treats NULLs as distinct (needs `NULLS NOT DISTINCT`, PG 15+) so duplicates with a NULL account are not prevented |
| Foreign keys | **None added.** The design proposed `run_id`/price FKs; M7.1 adds neither (no lineage from usage rows to runs or to the price row used). Acceptable for M7.1, but state it |
| ORM ↔ migration parity | Column names/types/constraint names agree for the changed tables. Pre-existing drift unchanged: `0002` has `account_id VARCHAR(64)` vs ORM `String(100)`. **`BillingIngestionRunModel` has no `error_count` or `shared_record_id_count` columns**, although both are in the run schema/response — persisting runs later would lose them. No automated ORM-vs-migration comparison test exists |
| Existing-data compatibility | `id` backfilled with `gen_random_uuid()` (**PostgreSQL ≥ 13**, documented). `source_row_hash` backfilled with `md5(record_id)` — a placeholder that will **never equal an application-computed hash**, so re-ingesting the same rows would insert **duplicates beside the legacy rows**. Moot if the tables are empty (expected: storage was in-memory), but the migration does not assert emptiness |
| Upgrade safety | `ALTER … TYPE NUMERIC(38,18)` rewrites the table (lock) — fine when empty; the stray `alter_column("record_id", existing_type=…)` is a no-op |
| Downgrade / reversibility | **Not safely reversible with data.** (a) restoring `PRIMARY KEY(record_id)` **fails** if any correction rows share a `record_id` — the very case the migration exists for; (b) `price_per_unit = COALESCE(price_effective_list, price_default, 0)` **fabricates a `0` price** for unpriced rows (violates null≠0); (c) precision narrowing truncates. Fine as a dev-only rollback on an empty schema; document that it is destructive |
| Whether applied | Not applied; `0002`/`0003` state unknown |

Migration verdict: **structurally sound for a greenfield/empty schema; needs the NULL-account and downgrade caveats documented, and an emptiness guard or an explicit "empty tables only" note.** It is correctly gated behind A1.

---

## 6. SQL security review

| Question | Finding |
|---|---|
| All request inputs validated? | `IngestionRunCreateRequest` (workspace id `^[0-9]{1,20}$`, ISO date, window order, limit 1–50 000, `source_table` `Literal`) → 422 on violation; `billing_sql` repeats the checks as defence in depth. ASCII-only digit classes; whitespace stripped then re-validated. ✔ |
| Identifiers/values manipulable? | Run path: no. The only interpolated values are validated; identifiers (columns, tables) are constants. ✔ |
| Token binds to exact query? | Yes — SHA-256 of the exact built text, plus warehouse and workspace id; verified before execution. Test `test_milestone_3j2` had to be updated to prove it. ✔ |
| Token `max_rows` / dates enforced? | **No.** `execute_read_only_statement` calls `verify_approval_token(token, sql, warehouse, session=…)` without `max_rows`/`date_start`/`date_end`, so those signed fields are not compared (the query hash indirectly pins the literal `LIMIT`/dates, but a token minted with `max_rows=10` still authorises a `LIMIT 50000` statement whose *hash* it was issued for). Pre-existing; low practical risk because the hash is the real binding, but the fields are misleading |
| Unrestricted execution path introduced? | No. `execute_read_only_statement` has one caller (`run_ingestion`), which builds the SQL itself; request-supplied SQL still cannot reach it. ✔ |
| Allowlist still restrictive? | `ALLOWED_SYSTEM_TABLES` unchanged (`system.billing.usage`, `system.billing.list_prices`). Both new builders were asserted to pass the AST validator. ✔ |
| Weak spots | (1) `POST /ingestion/approval-token` will still sign **any** validator-passing `SELECT` over the two tables (e.g. `SELECT *`, other workspaces, `identity_metadata`) — approver risk, not an automatic path; the validator does not require a `workspace_id` predicate or a `LIMIT`. (2) Statement-Execution bind parameters unused (acceptable given validation). (3) Legacy-token and `TEST-APPROVED-TOKEN` paths (D7-4/5) |

**SQL security verdict:** no new injection or unrestricted-execution path; token binding is sound on the run path. Hardening opportunities are listed, none blocking commit.

---

## 7. Findings register

### Critical

| ID | Finding | Scope |
|---|---|---|
| **C1** | **Statement-execution results are handled unsafely.** `execute_read_only_statement` reads only `response.result.data_array` and `manifest.schema`; it **never checks `response.status.state`** (PENDING/RUNNING after `wait_timeout`, FAILED, CANCELED), `manifest.truncated`, `result.next_chunk_index` (additional result chunks), or `row_count`. Consequences: a statement that has not finished returns `result=None` ⇒ **zero rows, reported as `completed`**; a large result silently ingests only the first chunk; hitting `LIMIT` is not surfaced. With idempotent loading this produces **silent partial ingestion that looks successful**. Pre-existing code, not a D1–D11 item, but it is exactly the code the first approved query will run through | **Block A3/A4/A5** until fixed and tested |
| **C2** | **Rate-card run is truncated by the usage default.** `_build_statement` passes `request.limit` (default 1000) to the `list_prices` query, ordered by `sku_name, price_start_time`. Azure `list_prices` can exceed that, so later SKUs are silently unpriced (costs stay `None`, no error). Combine with C1 (no truncation signal) | Fix before A4 |

### High

| ID | Finding |
|---|---|
| **H1** | D4: hash uses raw timestamp strings (P1) ⇒ re-extract with different formatting double-counts. |
| **H2** | D7-1/D7-2: no PostgreSQL evidence; concurrency through the bridge untested; in-memory race. |
| **H3** | D5/D11: analytics `_FILTER_META_KEYS` not aligned with the new attribution set; `app_name` no longer ingested, so the analytics "app" filter lost a key. |
| **H4** | D10: implementation report states stale defaults were removed; `/ingestion/preview` still defaults to `2026-10-01`/`2026-11-04` (and the source-scan test misses it). |

### Medium / Low

| ID | Finding |
|---|---|
| M1 | Equal-rate, different-currency prices silently collapse (P4); test is vacuous. |
| M2 | D4 evidence counter blind across runs (P3). |
| M3 | Migration: downgrade not reversible with data; fabricates `0` prices; placeholder `md5(record_id)` hashes; NULL-account uniqueness. |
| M4 | Run ORM lacks `error_count`/`shared_record_id_count`; no FKs; no ORM↔migration parity test. |
| M5 | Token `max_rows`/dates not enforced at execute; token route can sign broad SELECTs. |
| M6 | Legacy-token / `TEST-APPROVED-TOKEN` paths weaken "durable single-use". |
| M7 | Live approvals now hard-depend on PostgreSQL + migration `0003`. |
| L1 | Token burnt in memory on ledger outage (D6/D7-3). |
| L2 | `/billing/usage` `limit` lacks `ge=1`. |
| L3 | Weak/vacuous tests: `test_recon_mixed_currency_is_flagged`; `test_d10_defaults_are_dynamic…` (loose date assertion); `test_d6_auth_failure…` uses a bare `pytest.raises(Exception)`; `test_d1…` literal list contains an odd fragment. |
| L4 | `frontend/tsconfig.json` shows ` M` with no content change; do not stage. |
| L5 | Price join ignores account id (a price row from another account can price usage); acceptable if list prices are account-independent — confirm. |

---

## 8. Test evidence and limitations

| Evidence | Value |
|---|---|
| Backend full suite (as reported earlier this session) | 553 passed, 3 skipped, 0 failed; coverage 86%; `billing_sql.py` 95%, `billing_ingestion_service.py` 89%, `sql_client.py` 82% |
| New file | `tests/test_m7_1_billing_hardening.py`: 75 tests, passing when last run during implementation (not re-run in this read-only review) |
| Static analysis | `ruff check` clean; `mypy src` clean (90 files); `ruff format --check` flags only the pre-existing `scripts/run_migrations.py` |
| Frontend | 13 suites, lint, typecheck, production build pass |
| Migration | rendered offline only |
| Probes (this review) | P1–P6 above, run against the real code with the mock SQL service |

**Limitations — what this evidence does *not* show**
1. **No PostgreSQL, no asyncpg, no real `AsyncSession`** anywhere in the M7.1 evidence (SQLite stand-in only; `aiosqlite` absent). D7 is therefore *design-verified*, not *integration-verified*.
2. **No real Statement-API payload shapes** (struct/map columns as JSON text, timestamp formats, truncation/chunking). All price/usage rows in tests are hand-built from Unity Catalog column metadata.
3. **No live Databricks or Azure** interaction of any kind (by design).
4. Concurrency evidence is a SQLite threaded test whose outcome is dominated by the in-memory set.
5. Several tests assert weakly (L3), so a green suite overstates coverage of mixed-currency, default-date and auth-failure behaviours.
6. The frontend billing functions have no UI consumer, so the envelope fix is contract-tested only.
7. During implementation, one early test run used the real router and its `warm_live_metadata` dependency (read-only metadata calls possible, no SQL); it was subsequently overridden. Not re-verifiable from here.

---

## 9. Required before commit vs before first live query

**Before committing M7.1 (small, in-scope):**
1. **F1 (H4):** change `/ingestion/preview` defaults to dynamic/`None`, extend the stale-literal test to scan `api/routes/finops.py`, and **correct the D10 statement** in the implementation report (do not rewrite that report in this review — amend it in the fix commit or add an erratum).
2. **F2 (H1):** normalise timestamps (parsed UTC ISO) before hashing, with a regression test for P1.
3. **F3 (H3):** align `_FILTER_META_KEYS` (or route analytics through `matches_resource`) and decide how the analytics "app" filter should work without `app_name`; add a test.

Optional in the same pass (cheap): M1 (mark differing currencies `AMBIGUOUS` + real test), L2 (`ge=1`), L3 (tighten weak tests), D7-3 ordering (add DB result before in-memory mark), M2 (count shared ids against the store).

**Before any live query (A3–A5), separate from the commit:**
- **C1** and **C2** (statement state/truncation/chunk handling; price-run limit), with offline tests using a fake Statement-API response (PENDING, FAILED, truncated, multi-chunk).
- **D7 PostgreSQL integration test** (§4.3) on a disposable database.
- **D4 evidence** from the first approved extract before fixing the final key.
- Migration notes (M3) and the `0003` applied-state check under A1.

---

## 10. Remaining approval requirements

Unchanged from the design and implementation reports; **none has been requested or performed**:

| # | Approval | Additional precondition found by this review |
|---|---|---|
| A1 | Apply migration `0004` (and confirm `0002`/`0003`) | Also: decide empty-table assertion / downgrade policy; PG ≥ 13 |
| A2 | Metadata-only grants check | — |
| A3 | Warehouse start (human operator) | **C1 fixed first** |
| A4 | `list_prices` query + token | **C1, C2 fixed; ledger integration evidence (D7-1)** |
| A5 | Each `usage` chunk + token | C1 fixed; chunk sizing below `LIMIT`/result caps; P1 fix in place |
| A6 | Allow-list expansion | — |
| A7 | Any production / service-principal run | — |

---

## 11. Commit readiness

**NOT READY.**

Reasons: (1) the implementation report's D10 claim is not true of the code (stale defaults remain in `/ingestion/preview`); (2) D4's "idempotent" property can be defeated by timestamp formatting; (3) D5 attribution is not aligned in the analytics layer, with a small regression for the app filter. All three are quick, offline, in-scope fixes. After they are made and the suite/lint/type checks are re-run, M7.1 can be committed as **code-level hardening only** — with the explicit understanding that it is **not sufficient to begin live ingestion** (C1, C2, D7 PostgreSQL evidence and the approvals in §10 remain).

*Read-only review: no code, test, migration or existing report was modified; nothing was staged, committed or pushed.*
