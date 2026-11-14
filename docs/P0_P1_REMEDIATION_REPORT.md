# P0 / P1 Remediation Report

Branch `feature/live-finops-kpi-integration`, HEAD `b199b0c` (unchanged). Nothing staged, committed or pushed.
Scope: P0 (M7.1 correctness and safety) and P1 (Azure simulation fallback) only. P2–P7 were not started.

> **STATUS CORRECTION (after `P0_P1_INDEPENDENT_CODE_REVIEW.md`).** This report originally marked several items "Fixed" and the whole change "ready for review". The independent review showed that was too strong. **P0/P1 is NOT fully accepted.** The statuses below are corrected; where this note and a table cell disagree, this note wins.
>
> | Item | Accurate status |
> |---|---|
> | D5 attribution | **Partially complete** as delivered (pool / notebook / serverless keys were missing from analytics). Addressed afterwards in `P0_P1_PRE_P2_CORRECTIONS_REPORT.md`; still awaiting re-review. |
> | Currency handling | **Incomplete** as delivered: correct in the billing service, but analytics KPIs and the FinOps frontend still assumed USD / `$` (the frontend also applied hardcoded FX rates). Addressed afterwards in the pre-P2 corrections; still awaiting re-review. |
> | Token scope | **Partially complete**: execution enforces `LIMIT` vs signed `max_rows`, the date window as claimed by the caller, SQL hash, warehouse, workspace, expiry and single use — but the signed dates are not bound to the SQL text and issuance does not tie scope to the statement. |
> | Approval-token authentication / route | **FAILED (open, not addressed)**: the route signs any allow-listed SELECT (incl. `ai_query`, `http_request`, `identity_metadata`, cross-workspace, cross joins); it echoes `request.workspace_id` instead of the signed one; and with `entra_auth_enabled=false` (default) any caller is an Admin. Blocks any live step. |
> | PostgreSQL integration tests | **Not executed.** Never run (no PostgreSQL available). Two defects found by review are still open: a `text()` query that ignores the private schema, and outage assertions that use a malformed token and so never reach the ledger. |
> | Statement-API behaviour (C1/C2) | **NOT VERIFIED** against real Databricks payloads; all evidence is hand-built fake responses. `spend_complete` also still ignores `price_card_complete`. |
> | Frontend run-result toast | **Open**: still reports `failed` / `incomplete` runs as "Ingestion completed". |
> | P1 Azure fallback removal | PASS per the review; demo fixtures are default-off but the whole test suite opts in globally. |
> | Overall | **Not accepted.** Do not claim P0/P1 acceptance. |

## 1. Findings and status

### P0

| Finding | Status | What was done |
|---|---|---|
| **D10** hardcoded preview dates | **Fixed** | `/ingestion/preview` now takes `start_date`/`end_date` as optional; defaults are derived from today (first of month → today, UTC). Test scans `api/routes/finops.py` for any date literal. Erratum appended to the M7.1 hardening report (its D10 claim was incomplete). |
| **D4** timestamp canonicalisation | **Fixed** | `canonical_timestamp()` (parsed UTC ISO) is used in `_row_identity_hash`; `sku_name` is stripped. `…00Z`, `…00.000+00:00`, naive and offset forms hash identically. Unparsable values are kept verbatim, never guessed. Cross-run corrections now counted in `shared_record_id_count` (review M2). **The production dedup key is still not finalised** — it remains PROVISIONAL pending evidence from a first approved extract. |
| **D5** attribution filters | **Partially complete** (see status correction) | Analytics `app` filter uses `app_id` only (`app_name` is not an ingested key); `_RESOURCE_META_KEYS` uses the same priority order as `billing_sql.ATTRIBUTION_RULES`; the generic resource-id filter uses exact `matches_resource` instead of "value in dict.values()". |
| **Mixed currencies** | **Incomplete** (billing service only; see status correction) | Price join keys on `(rate, currency)`: equal numbers in different currencies are `AMBIGUOUS`, never merged. Summary: `total_spend_verified`/`currency` are `null` when >1 currency, with `spend_by_currency`. Reconciliation: `gross/net_cost` `null` + `cost_by_currency`, `single_currency` check fails. Analytics: if priced rows in scope span >1 currency their costs are withheld (`MIXED_CURRENCY`), DBU quantities untouched, provenance says so. No conversion anywhere. |
| **C1** statement completeness | **Fixed offline; real-API evidence NOT VERIFIED** | `_collect_complete_rows`: polls PENDING/RUNNING until the query timeout then cancels and raises `STATEMENT_TIMEOUT`; FAILED/CANCELED/CLOSED → `STATEMENT_FAILED`; manifest `truncated` → `RESULT_TRUNCATED`; follows `next_chunk_index` to the end; checks collected rows against `total_row_count` and chunks against `total_chunk_count`; no manifest or external-link chunks → `RESULT_INCOMPLETE`. Sync wait capped at the API's 50 s. A run that reaches its row bound is `incomplete` / `ROW_LIMIT_REACHED`, never `completed`. A failed statement ingests nothing. |
| **C2** rate-card completeness | **Partially complete** (`spend_complete` ignores card completeness; no paging fallback) | `list_prices` is fetched with its own fixed bound (`PRICE_ROW_LIMIT` = 50 000), no longer the usage `limit` default of 1000. All chunks are followed; reaching the bound or failing marks `price_card_complete = False`, surfaced on the billing summary and the run (`result_complete`, `error_code`). |
| **Token scope** | **Partially complete** (see status correction) | Execution now requires a bounded statement: the SQL's `LIMIT` (parsed from the AST) must be ≤ the signed `max_rows`; the signed date window must equal the requested one; exact SQL-hash, warehouse, workspace and expiry checks are unchanged; un-scoped legacy tokens are refused outside offline/test mode. Single use: lock + in-flight set (exactly one winner under 16-way thread contention); the DB atomic UPDATE stays authoritative; a token is no longer burnt in memory on a ledger outage (review D7-3). |
| **PostgreSQL integration tests** | **Written, NOT executed, two known defects** | See §6. |
| **Migration 0004** | **Corrected, not applied** | Removed the placeholder `md5(record_id)` hashes and the stray no-op alter; upgrade refuses if `billing_usage_records` has rows; price identity is now a functional unique index on `COALESCE(account_id,'')` (NULL-safe; ORM updated to match); downgrade is guarded (refuses unless both tables are empty) and never fabricates a `0` price; adds `error_count`, `shared_record_id_count`, `result_complete`, `error_code` to `billing_ingestion_runs` (and the ORM). Offline-rendered only. |

### P1

| Finding | Status | What was done |
|---|---|---|
| **L-1** hardcoded Azure topology | **Fixed** | Removed from `_discover_azure_scopes`. No token ⇒ `status="authentication_required"`, `data_source="none"`, empty tree, message "run `az login`…". With `ALLOW_DEMO_FIXTURES=true` the fixture is returned from the new isolated module `services/configuration/demo_fixtures.py`, labelled `data_source="demo_fixture"` and "DEMO FIXTURE" in the message. Default of the flag remains `False`. |
| Failure classification | **Improved** | Live failures were all reported as `permission_denied`. Now: 401 / `AzureAuthenticationRequired` ⇒ `authentication_required`; 403 / `PermissionError` ⇒ `permission_denied`; anything else ⇒ `error`. |
| Authenticated discovery | **Preserved** | Live ARM branch untouched; covered by an existing and a new test. |

API additions (additive only): `ScopeDiscoveryResponse.status` gains `authentication_required`, `error`; new optional `data_source`; billing responses gain `result_complete`, `error_code`, `spend_by_currency`, `price_card_complete`, `cost_by_currency`; run `status` can be `incomplete`. No field or endpoint was removed.

## 2. Files changed (this phase)

Source: `services/databricks/sql_client.py` (C1, token scope, single use), `billing_sql.py` (`canonical_timestamp`, `PRICE_ROW_LIMIT`, `MIXED_CURRENCY`), `billing_ingestion_service.py` (completeness, currency, hash, evidence), `finops_analytics_service.py` (D5, currency guard), `schemas/billing_ingestion.py`, `schemas/configuration.py`, `api/routes/finops.py` (D10), `db/models.py` (price index, run columns), `services/configuration/configuration_service.py` (P1), new `services/configuration/demo_fixtures.py`, migration `2026_11_13_0004_…`, `frontend/src/types/index.ts` (union + optional field).
Tests: new `tests/test_p0_remediation.py` (59 tests: P0, P1 and offline migration checks), new `tests/test_p0_postgres_integration.py` (5, skipped without a disposable DB); adjusted `test_m7_1_billing_hardening.py` (realistic Statement-API response shape; tokens issued with a matching signed scope), `test_milestone_3j2_security.py`, `test_databricks_workspace.py` (unbounded `SELECT *` + token is now correctly refused), `test_configuration.py` (explicit demo opt-in).
Docs: this report; erratum appended to `M7_1_BILLING_INGESTION_HARDENING_REPORT.md`.

## 3. Tests executed

| Check | Result |
|---|---|
| Backend `pytest tests -q --cov` | **612 passed, 8 skipped, 0 failed**; coverage 86% (`billing_sql` 98%, `billing_ingestion_service` 90%, `sql_client` 88%, `demo_fixtures` 100%) |
| `ruff check .` | clean |
| `ruff format --check .` | clean except the pre-existing `scripts/run_migrations.py` (untouched) |
| `mypy src` | no issues, 91 files |
| Frontend `npm test` | 13 suites, 0 failures |
| Frontend `lint` / `typecheck` / `build` | pass |

Baseline was 553 passed / 3 skipped. Delta: +59 passed, +5 skipped (the PostgreSQL tests). The 3 original skips are unchanged. Seven existing tests failed after the stricter token/statement handling and were investigated rather than ignored: each issued a token without a signed row limit/date window or returned a statement response without a status/manifest, i.e. they encoded the exact laxness this work removes. They were updated to realistic inputs; the behaviour change is intentional.

## 4. Azure regression status

No live Azure call was made. Offline evidence: the existing Azure inventory, configuration, connection, auth, cost-management and monitoring suites all pass unchanged (apart from the one explicit demo opt-in in `test_configuration.py`); the authenticated discovery path is untouched and re-tested. **Live Azure regression is not verified** (live verification is P6).

## 5. Databricks regression status

No live Databricks call was made. Discovery, workspace, FinOps analytics/KPI, ingestion, enforcement and security suites pass. Billing failures remain isolated: a billing run error never touches discovery code, and analytics still shows resource metadata when billing is absent (`NO_DATA` / blocked-pending-approval states unchanged). **Live Databricks regression is not verified.**

## 6. PostgreSQL integration-test evidence and limitations

- **No PostgreSQL, Docker or `psql` exists on this machine**, and no disposable database URL was provided, so `tests/test_p0_postgres_integration.py` was **skipped, not run**. It has therefore never executed; the D7 ledger remains design-verified plus SQLite-stand-in evidence, **not** PostgreSQL-integration-verified.
- What the file covers once `TEST_POSTGRES_URL` points at a disposable DB: real `AsyncSession`/asyncpg issue→verify→consume→replay across service instances; 12-way concurrent consume with exactly one winner (separate service instances so the in-memory set cannot decide); unreachable DB and missing table fail closed; optional (`TEST_POSTGRES_MIGRATE=1`, empty database) migration upgrade, NUMERIC(38,18) round-trip, correction rows sharing a `record_id`, NULL-account price uniqueness, guarded downgrade.
- Safety guards (enforced in code before anything is created): URL must differ from the application's `database_url`; database name must contain `test`; ledger tests use a private uniquely-named schema that is dropped afterwards; the migration test requires an empty database. The application database is never used.
- Unverified details a real run may expose: the exact set of NOT NULL columns in the hand-written usage `INSERT` in the migration test.
- Also not proven: the SQLite stand-in tests prove the thread→loop bridge and error handling only, not asyncpg transaction or locking behaviour.

## 7. Remaining mock / hardcoded findings (not in P0/P1 scope; not touched)

- **L-2/L-3** `KNOWN_WAREHOUSES/CLUSTERS/SERVING_ENDPOINTS/APPS`, `HISTORICAL_FIXTURE_ENDPOINTS`, `AUTHORIZED_WORKSPACES` in `finops_analytics_service.py`; hardcoded default workspace id `642006393507276` in routes/services.
- **L-4/L-5** `/monitoring/sources` env-derived `simulation_fixture` and invented retention numbers; `mock_fixture` default label in `monitoring_service.py`.
- **T-1…T-6** discovery caps (500 per category, 25/10/5 detail caps) — disclosed by `has_more` but still truncation.
- Review items deliberately left: D7-5 `TEST-APPROVED-TOKEN` bypass still gated only on `auth_type=="mock"` or `app_env=="testing"`; the token route can still sign any validator-passing SELECT over the two allow-listed tables (L-5/M5 approver risk); `/billing/usage` `limit` lacks `ge=1` (L2); a few older weak tests (L3) were not rewritten; no foreign keys/lineage from usage rows to runs or prices.
- The dedup identity is **provisional**; D4 evidence must come from a first approved extract.

## 8. Prohibited live operations

None occurred. No SQL was executed, no warehouse was started or contacted, no billing ingestion ran, no cloud resource, permission or credential was changed, no Databricks authentication or Fabric code was touched, no migration was applied (0004 was only rendered offline with `--sql`), no PostgreSQL connection was made. All tests used the mock/offline providers and fakes. The frontend build and tests ran locally.

## 9. Git state

Branch `feature/live-finops-kpi-integration`, HEAD `b199b0c`, nothing staged. Working tree holds the earlier uncommitted M7.1 work plus this phase: modified (source) `finops.py`, `db/models.py`, `schemas/billing_ingestion.py`, `schemas/configuration.py`, `configuration_service.py`, `billing_ingestion_service.py`, `finops_analytics_service.py`, `sql_client.py`, `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`, plus modified tests; untracked: migration 0004, `billing_sql.py`, `demo_fixtures.py`, three test files (`test_m7_1_…`, `test_p0_remediation.py`, `test_p0_postgres_integration.py`), `frontend/src/lib/billing.ts`, `frontend/test/billing-contract.test.ts`, the M7/M7.1/V5.1/P0-P1 docs, and `docs/databricks_api_audit/` (raw tenant audit JSON — must **not** be committed). `frontend/tsconfig.json` shows modified with no content difference (line endings only) — do not stage. No `.env` files are modified or untracked-pending.

## 10. Ready for review?

**Not accepted.** P0/P1 was reviewed independently (`P0_P1_INDEPENDENT_CODE_REVIEW.md`): D5 and currency handling were incomplete, token scope is only partial, approval-token authentication **failed**, the PostgreSQL tests have **not been executed** (and contain two defects), and Statement-API behaviour is **NOT VERIFIED**. The D5 and currency gaps were then addressed in `P0_P1_PRE_P2_CORRECTIONS_REPORT.md`; the token route, the PostgreSQL evidence, the Statement-API evidence, `price_card_complete` handling and the run-result toast remain open and block any warehouse start, token mint or ingestion. Readiness of the wider live-data requirement is **not** claimed.
