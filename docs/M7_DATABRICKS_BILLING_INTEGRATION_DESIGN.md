# Milestone 7 — Databricks Real Billing Integration: Architecture Discovery & Design

| | |
|---|---|
| Repository / branch | `cloud-recommender-poc` / `feature/live-finops-kpi-integration` |
| Baseline | `b199b0c` |
| Status | **Design only.** No SQL executed, no warehouse started, no ingestion run, no schema/credential/auth/Fabric change, no commit. |
| Evidence | Source code in `backend/src`, `backend/alembic`, `frontend/src`, and the already-captured read-only Unity Catalog API audit (`docs/databricks_api_audit/`, untracked, not quoted for identities). No live call was made for this report. |
| Scope target | Dev workspace `642006393507276`, SQL warehouse `05ed10a52697a344` (observed `STOPPED` in the audit). |

---

## Executive summary

1. **The billing sources exist and are visible.** `system.billing.usage`, `system.billing.list_prices` (and `system.billing.attributed_usage`) are reachable through the Unity Catalog metadata API in the Dev workspace; their full column lists were captured without SQL (§2).
2. **Most of the ingestion skeleton already exists** — approval gate, signed single-use tokens, read-only SQL validator, run/checkpoint/usage/price ORM models and Alembic migrations, summary/reconciliation endpoints, KPI provenance. The gap is that **none of it is persisted or wired to Postgres**: the billing store is in-memory and the ORM tables are never read or written (§1.2).
3. **Several existing assumptions don't match the real source schema** and must be fixed before the first approved query, otherwise the first real ingestion would produce wrong numbers (§1.3). The most important: the price table has a nested `pricing` struct, not a flat `price_per_unit`; `usage_quantity` is `decimal(38,18)` but is stored as `Numeric(18,4)`; the single-column `record_id` primary key would treat retractions/restatements as duplicates; and the service ships a **hardcoded rate card** (violates Golden Rule 2).
4. **"Actual billed" cannot come from Databricks system tables alone.** They give metered DBU and list price. DBU × list price is a *calculated estimate*, not an invoice; VM/storage charges for classic compute are not in these tables at all. The data model therefore carries an explicit `cost_basis` (§3.3).
5. **Permissions are not yet proven sufficient.** The Dev Azure-CLI identity can read table metadata and has the `databricks-sql-access` entitlement, but `SELECT` on `system.billing.*` and `CAN_USE` on the warehouse were **not verifiable without SQL / with the audit's 403s** (§5). A no-SQL verification step is proposed.
6. **Every live query needs approval** (token + a separately authorised warehouse start). Seven approval points are listed in §10.

---

## 1. Current architecture

### 1.1 Components that already exist (reuse before building)

| Concern | Existing component | Notes |
|---|---|---|
| Read-only SQL gate | `services/databricks/sql_client.py` — `DatabricksSqlService` | AST validator (sqlglot, Databricks dialect): single `SELECT`/`WITH`, no comments/semicolons, table allowlist (`ALLOWED_SYSTEM_TABLES` = `usage`, `list_prices`), blocked functions. Never starts a warehouse; raises `WarehouseStoppedError`. |
| Approval tokens | same file + `BillingApprovalTokenModel` + `POST /finops/ingestion/approval-token` | HMAC-signed `v2:` token binding query hash, warehouse, workspace, date range, `max_rows`, TTL; RBAC (`Admin`/`FinOpsAdministrator`/`PlatformAdministrator`); fail-closed without `finops_signing_secret`. |
| Ingestion service | `services/databricks/billing_ingestion_service.py` — `BillingIngestionService` | status / validate / preview / run, row→record mapping, `record_id` dedupe, price join, summary, reconciliation. |
| Schemas | `schemas/billing_ingestion.py` | Usage, price, run, summary, reconciliation, token contracts. |
| ORM + migrations | `db/models.py` (`BillingUsageRecordModel`, `BillingPriceRecordModel`, `BillingIngestionRunModel`, `BillingReconciliationResultModel`, `BillingSourceCheckpointModel`, `BillingScopeSnapshotModel`, `BillingCalculationVersionModel`, `BillingApprovalTokenModel`); `alembic/versions/2026_11_07_0002_*`, `…_0003_*` | Tables already designed, incl. checkpoints and calculation versions. |
| System-table discovery (no SQL) | `services/databricks/discovery_service.py::discover_system_tables_metadata` | `schemas.list` / `tables.list` / `tables.get` / `grants.get_effective` via REST SDK; produces `billing_ingestion_ready_tables` only when columns **and** SELECT are verified **and** a warehouse is configured. |
| FinOps analytics | `services/databricks/finops_analytics_service.py` | 15 modules; reads `billing_service._usage_store` via `_billing_rows()`; KPI statuses `LIVE`, `BLOCKED_PENDING_APPROVAL`, `UNAVAILABLE`, `INSUFFICIENT_HISTORY`, `NO_BILLING_ROWS`; `_billing_provenance()`. |
| Auth | `services/databricks/auth.py` | Azure CLI delegated identity for Dev (unchanged by this design). |
| Azure cost source | `services/azure/cost_management_service.py` | Read-only; candidate reconciliation target (§3.5). |
| Persistence | `db/session.py` (async SQLAlchemy 2.0 / asyncpg), `db/repositories/*` (catalog, workload, configuration, ingestion repos) | Repository pattern to follow. |
| Frontend | `lib/api.ts` (`getFinOpsBillingSummary/Usage/Pricing/Reconciliation`, ingestion status/run), `lib/financials.ts` (null-safe, `NO_DATA_LABEL`, `periodSuffix`), `FinOpsCommandCenterView.tsx`, KPI drawer | Fail-closed null handling from V5.1 is reusable as-is. |
| Pre-existing tests | `tests/test_milestone_3h_ingestion.py`, `tests/test_ingestion_enforcement.py` | Cover gate/dedupe/pricing join against the mock provider. |

### 1.2 What is *not* in place

- `BillingIngestionService._usage_store`, `_price_store`, `_runs_store` are **process-memory dicts**. The singleton is created in `api/routes/finops.py::get_billing_service`. A restart loses all ingested data and the run audit trail.
- No code imports the billing ORM models outside `db/models.py` / `db/__init__.py`; there is no billing repository.
- `finops_analytics_service` reaches into the private `billing_service._usage_store` rather than a repository interface.
- No checkpoint/watermark logic, no retry, no scheduler, no freshness API. `BillingSourceCheckpointModel` is unused.
- Whether Alembic revisions `0002/0003` have been applied to any Postgres instance was **not checked** (would require a DB connection; out of scope).

### 1.3 Defects / mismatches found (must be resolved before any live query)

| # | Finding | Evidence | Impact | Proposed resolution |
|---|---|---|---|---|
| D1 | **Hardcoded rate card** (`_CANONICAL_LIST_PRICES`: e.g. SKU → 2.20 / 4.00 / 1.45047 USD per DBU, start 2026‑01‑01) seeds `_price_store` and is used to price usage. | `billing_ingestion_service.py:51-97, 148` | Violates Golden Rule 2 (no invented prices); results look "verified" while resting on guessed rates. | Remove. Price only from ingested `system.billing.list_prices` rows; unpriced rows stay `cost = NULL` (already the contract). |
| D2 | **Price schema mismatch.** Real `list_prices` columns: `account_id, price_start_time, price_end_time, sku_name, cloud, currency_code, usage_unit, pricing` where `pricing` is `struct<default, promotional.default, effective_list.default>`. Code/ORM expect flat `price_per_unit` + `pricing_unit`. | Captured UC metadata (§2.2) | A literal `SELECT *` mapping would fail or drop prices. | Map `pricing.default`, `pricing.promotional.default`, `pricing.effective_list.default` to three nullable columns; rename `pricing_unit`→`usage_unit`; define which tier is used (§3.3). |
| D3 | **Numeric precision.** Source `usage_quantity decimal(38,18)`; ORM/Alembic `Numeric(18,4)`; Pydantic `float`. | UC metadata vs `models.py:623`, schema `float` | Silent rounding/truncation; float accumulation error vs the "Decimal" claim in reconciliation. | Store `Numeric(38,18)`; carry `Decimal` end-to-end; round only at presentation. |
| D4 | **Idempotency key.** `record_id` alone is the PK and the dedupe key; retractions/restatements are *additional* records for the same usage. | `BillingUsageRecordModel.record_id` PK; `ingest_records` `if rec.record_id in store: duplicates += 1` | If retraction/restatement rows share the original `record_id` (verify against current Databricks docs at the first approved query — see Risk R2), they would be **discarded as duplicates**, corrupting net DBU/cost. | Natural key `(workspace_id, record_id, record_type, usage_start_time, usage_end_time, ingestion_date)` + surrogate PK; `INSERT … ON CONFLICT DO NOTHING`. |
| D5 | **Resource attribution too narrow.** Matches only `cluster_id, warehouse_id, endpoint_id, job_id, app_id`. `usage_metadata` actually has many more (`dlt_pipeline_id`, `endpoint_name`, `instance_pool_id`, `notebook_id`, `job_run_id`, `ai_gateway.*`, `serverless_compute_id`, `uc_table_*`, …). | UC metadata (§2.1) | Serverless/AI/DLT spend would be unattributed → `NO_DATA` for valid resources. | Attribution resolver (§3.4). |
| D6 | **Token consumed before warehouse-state check.** | `sql_client.py` consumes at ~L876, checks `STOPPED` at ~L884 | A stopped warehouse "burns" the single-use approval. | Check state first; consume only when about to submit. |
| D7 | **DB replay ledger appears non-functional.** Token persistence/consume use sync `session.execute(...).scalar_one_or_none()` while the app session is `AsyncSession`; the issue route never passes a session. Errors are swallowed by `try/except`. | `sql_client.py` token methods; `finops.py::issue_approval_token`; `db/session.py` | Replay protection is in-memory only (lost on restart); audit rows never written. | Async repository for the token ledger; pass session; fail closed if the ledger is unavailable. |
| D8 | **Query values interpolated by f-string.** `workspace_id`, `start_date`, `end_date`, `limit` inserted into SQL text; `parameters` argument is ignored. AST validation does not constrain literal values. | `run_ingestion`, `preview/validate` | Injection surface if request fields are ever user-controlled. | Strict validators (`^\d{1,20}$`, ISO `YYYY-MM-DD`, bounded int) before string build; Statement Execution API parameters where supported. |
| D9 | **Frontend/backend shape drift.** `api.ts` types `billing/usage` and `billing/pricing` as `{total, offset, limit, records}` / `{total, records}`; the routes return bare lists. | `api.ts:1097-1131` vs `finops.py:737-767` | Likely runtime mismatch once data exists. (Not exercised today because stores are empty — **verify**.) | Align in implementation phase with a paginated envelope. |
| D10 | **Stale defaults / copy.** Request defaults `2026-10-01…2026-11-04`; approval text says "10-minute auto-termination" and "$0.15–$0.35" while the warehouse reports `auto_stop_mins = 5`; `expected_operational_cost` is a fixed string. | `schemas/billing_ingestion.py`, `sql_client.py`, audit | Misleading approval screens (approver relies on these). | Derive from observed warehouse metadata; show "unknown" for cost instead of a fixed range. |
| D11 | **`identity_metadata` and free-text fields are selected.** The ingestion `SELECT` pulls `identity_metadata` (user/service-principal identifiers) and `usage_metadata` (names, notebook paths). | `run_ingestion` SQL | PII / sensitive naming persisted to Postgres. | Minimise: omit or pseudonymise (§7). |

---

## 2. Billing source availability (from existing metadata only)

All below was obtained from Unity Catalog REST metadata (`GET /api/2.1/unity-catalog/tables/…`, HTTP 200) captured in the earlier read-only audit. No SQL, no warehouse.

### 2.1 `system.billing.usage` (MANAGED, `DELTASHARING`) — 18 columns

| Pos | Column | Type | Meaning / use |
|---|---|---|---|
| 0 | `account_id` | string | Account the report belongs to. |
| 1 | `workspace_id` | string | **Workspace attribution; mandatory filter** (the table is account-wide). |
| 2 | `record_id` | string | Unique usage record ID. |
| 3 | `sku_name` | string | Commercial SKU; **join key to prices**. |
| 4 | `cloud` | string | `AWS`/`AZURE`/`GCP`. |
| 5–6 | `usage_start_time`, `usage_end_time` | timestamp | Metering window (UTC). |
| 7 | `usage_date` | date | Partition-friendly date; billing-period bucketing. |
| 8 | `custom_tags` | map<string,string> | User/compute/job tags (cost allocation). |
| 9 | `usage_unit` | string | DBU, Gbps-hours, … — **never mix units**. |
| 10 | `usage_quantity` | decimal(38,18) | Metered quantity (negative on retractions). |
| 11 | `usage_metadata` | struct (≈60 fields) | Resource attribution: `cluster_id, job_id, job_run_id, warehouse_id, instance_pool_id, notebook_id, dlt_pipeline_id, endpoint_name, endpoint_id, app_id, app_name, metastore_id, node_type, ai_gateway{…}, genie{…}, serverless_compute_id, uc_table_*, budget_policy_id, usage_policy_id, …`. |
| 12 | `identity_metadata` | struct | `run_as, created_by, owned_by, run_by` (sensitive). |
| 13 | `record_type` | string | Original / retraction / restatement. |
| 14 | `ingestion_date` | date | Date the record landed — **incremental watermark candidate**. |
| 15 | `billing_origin_product` | string | Product family (JOBS, SQL, MODEL_SERVING, …). |
| 16 | `product_features` | struct | Tier, serverless, photon, serving type, … |
| 17 | `usage_type` | string | Usage type attribution. |

### 2.2 `system.billing.list_prices` (MANAGED, `DELTASHARING`) — 8 columns

`account_id`, `price_start_time`, `price_end_time` (validity interval, UTC), `sku_name`, `cloud`, `currency_code`, `usage_unit`, `pricing struct<default, promotional.default, effective_list.default>` (all `decimal(38,18)`).

### 2.3 `system.billing.attributed_usage` (visible; **not** on the allowlist)

16 columns incl. `usage_record_ids array<string>` (links back to `usage.record_id`), `active_usage_quantity`, `usage_metadata{dbsql_statement_id, warehouse_id, client_application}`, `identity_metadata{executed_by}`, `granular_tags{query_tags}`. Useful for per-query/per-user DBSQL cost; adding it requires changing `ALLOWED_SYSTEM_TABLES` (a code change + threat review; **deferred**, §8 phase 7).

### 2.4 Related system tables visible via metadata (for attribution/enrichment, not for billing facts)

`system.compute.clusters/warehouses/node_timeline`, `system.lakeflow.jobs/job_run_timeline/pipelines`, `system.serving.endpoint_usage/served_entities`, `system.ai_gateway.usage`, `system.query.history` (all HTTP 200). `system.tags.*` and `system.alert.*` returned 404 (not enabled) — irrelevant to billing. None of these are on the SQL allowlist today.

### 2.5 What the sources do **not** provide

- No monetary column in `usage`; cost must be derived from `list_prices`.
- `list_prices` are **list/published prices**, not contractual/negotiated or invoiced amounts.
- Cloud-side charges for classic compute (VMs, disks, networking, storage) are **outside** system tables → Azure Cost Management territory.

### 2.6 Timestamps and pricing dimensions available

Usage: `usage_start_time`/`usage_end_time` (window), `usage_date` (day bucket), `ingestion_date` (arrival). Price: `price_start_time`/`price_end_time` (validity), `currency_code`, `usage_unit`, `sku_name`, `cloud`. Join: `sku_name + cloud + usage_unit + currency` with `usage_start_time ∈ [price_start_time, price_end_time)` (an open `price_end_time` = currently effective).

---

## 3. Proposed data model

Principle: **facts, rate card, and calculations are separate tables.** Metered facts are immutable source copies; cost is a *derived, versioned* layer that always states its basis.

### 3.1 Tables (evolution of the existing models — requires an approved migration; none is applied now)

**`billing_usage_records`** (fact; revise existing)
- `id` (uuid PK), natural unique key `(workspace_id, record_id, record_type, usage_start_time, usage_end_time, ingestion_date)`.
- Source columns: `account_id, workspace_id, record_id, sku_name, cloud, usage_start_time, usage_end_time, usage_date (date), usage_unit, usage_quantity Numeric(38,18), record_type, ingestion_date (date), billing_origin_product, usage_type`.
- JSON: `custom_tags`, `product_features`, `usage_metadata` (minimised subset, §7).
- Attribution (denormalised from resolver): `resource_type`, `resource_id`, `resource_name`.
- Lineage: `source_table`, `run_id` (FK), `source_row_hash` (sha256 of canonical row), `ingested_at`.
- Indexes: `(workspace_id, usage_date)`, `(workspace_id, resource_type, resource_id, usage_date)`, `(sku_name, usage_unit)`, `(ingestion_date)`.

**`billing_list_prices`** (rate card; revise existing `billing_price_records`)
- `account_id, sku_name, cloud, currency_code, usage_unit, price_start_time, price_end_time`,
  `price_default`, `price_promotional`, `price_effective_list` (`Numeric(38,18)`, nullable), `source_row_hash`, `run_id`, `ingested_at`.
- Unique `(account_id, sku_name, cloud, currency_code, usage_unit, price_start_time)`.

**`billing_usage_costs`** (derived; **new** — the only place a monetary value lives)
- `usage_record_id` (FK), `price_id` (FK, nullable), `cost_amount Numeric(38,18)` (nullable), `currency`, `cost_basis`, `price_tier`, `calculation_version` (FK to existing `billing_calculation_versions`), `computed_at`, `match_status` (`MATCHED`, `NO_PRICE`, `UNIT_MISMATCH`, `AMBIGUOUS`).
- Recomputable at any time; never overwrites facts. Fixes D1/D2: no price ⇒ `cost_amount = NULL`, never zero.

**`billing_daily_rollups`** (derived; **new**, for KPI speed)
- `workspace_id, usage_date, sku_name, billing_origin_product, resource_type, resource_id, usage_unit, net_quantity, gross_quantity, retraction_quantity, cost_list_estimate, currency, record_count, has_restatement, calculation_version, refreshed_at`.

**`billing_ingestion_runs`** (existing; extend)
- Add `chunk_start/chunk_end`, `attempt`, `parent_run_id`, `token_id`, `query_hash`, `warehouse_id`, `rows_received`, `error_class`, `status` incl. `partial`, `watermark_before/after`.

**`billing_source_checkpoints`** (existing; extend)
- Per `(workspace_id, table_name)`: `high_watermark_ingestion_date`, `lookback_days`, `latest_usage_date`, `last_success_run_id`, `last_attempt_at`, `consecutive_failures`.

**`billing_approval_tokens`** (existing; unchanged contract; ledger must actually be written, D7).

### 3.2 Attribution resolver (replaces the five-key match, D5)

Ordered, first non-null wins; each rule yields `(resource_type, resource_id)`:
`warehouse_id → SQL_WAREHOUSE`, `endpoint_id|endpoint_name|ai_gateway.endpoint_* → SERVING_ENDPOINT`, `app_id → APP`, `job_id → JOB`, `dlt_pipeline_id → PIPELINE`, `cluster_id → CLUSTER`, `instance_pool_id → POOL`, `notebook_id → NOTEBOOK`, `serverless_compute_id → SERVERLESS`, else `UNATTRIBUTED`. Matching stays **exact** (existing policy: no substring/partial); unknown IDs return `NO_DATA`, never `0`. Optional enrichment from the existing inventory (names) is a join at read time, not stored authoritative data.

### 3.3 Actual vs calculated — explicit labelling

| `cost_basis` | Meaning | UI label | Allowed to be called "actual billed"? |
|---|---|---|---|
| `METERED_USAGE` | Quantity only (DBU, etc.), no money | "DBU consumed (metered)" | n/a (not a cost) |
| `LIST_PRICE_ESTIMATE` | metered qty × `list_prices` (effective_list/default), matched by SKU/cloud/unit/date | "Estimated at list price" | **No** |
| `AZURE_INVOICED` (future, via Cost Management Reader) | Azure-billed Databricks meter amounts | "Billed (Azure)" | **Yes** (only this one) |

Rules: a KPI shows a currency figure only with its basis; mixing bases in one total is forbidden; `NULL` cost renders `NO_DATA_LABEL` (existing V5.1 behaviour). Price tier policy (default vs promotional vs effective_list) is a decision recorded in `billing_calculation_versions.formula_definition` — **open question for the owner**, default proposal: `effective_list` when present else `default`.

### 3.4 Time semantics

- Billing period = calendar month of `usage_date` (UTC); stored as a derived `billing_month` in rollups.
- `usage_date` buckets reporting; `usage_start_time` drives price validity; `ingestion_date` drives incremental extraction and freshness; `ingested_at` is the app-side timestamp.
- Month-to-date and forecasts use only complete days; the current day is flagged partial (feeds existing `INSUFFICIENT_HISTORY` logic).

### 3.5 Provenance (reuses `canonical_financial` / KPI provenance)

Each KPI payload carries: `source` (`system.billing.usage` + `list_prices`), `cost_basis`, `workspace_id`, `run_id` range, `data_through` (max `usage_date`), `last_ingested_at`, `calculation_version`, and status ∈ existing set (`LIVE` only when rows came from an approved run). Fixture rows are never `LIVE` (V5.1 policy retained).

---

## 4. Ingestion architecture (design only — not implemented)

### 4.1 Pipeline stages

`PLAN → APPROVE → (OPERATOR STARTS WAREHOUSE) → EXTRACT → VALIDATE → LOAD → DERIVE → CHECKPOINT → STOP-CONFIRM`

1. **PLAN** (no SQL): compute windows from the checkpoint, render exact SQL per chunk, validate through `validate_read_only_statement`, produce the existing 8-point approval payload (corrected per D10). Reuses `validate`/`preview`/`run(is_approved=false)`.
2. **APPROVE**: human requests a token per chunk (query hash + warehouse + workspace + dates + `max_rows` bound). Roles enforced server-side from the authenticated identity.
3. **Warehouse start**: separate, explicit operator action (the app never starts compute — unchanged).
4. **EXTRACT**: one bounded statement per chunk via Statement Execution API; fixed column projection (no `SELECT *`, D11).
5. **VALIDATE**: per-row schema/type checks (required columns, units in a known set, `usage_end ≥ usage_start`, `usage_date` consistent with `usage_start_time`, finite decimals, `workspace_id` equals the requested one, `cloud = AZURE` for Dev). Bad rows → quarantine count + reason, never silently dropped; abort the run if error rate > threshold (proposal: 1%).
6. **LOAD**: single DB transaction per chunk: `INSERT … ON CONFLICT (natural key) DO NOTHING`; counts inserted/duplicate/retraction/restatement.
7. **DERIVE**: recompute `billing_usage_costs` and rollups for affected `(workspace, usage_date)` only.
8. **CHECKPOINT**: advance watermark **only after** the chunk commits and validation passes.
9. **STOP-CONFIRM**: report observed warehouse state; the app does not stop it (read-only), operator relies on `auto_stop_mins` (observed 5).

### 4.2 Initial historical backfill

- Order: `list_prices` first (small, whole history for the account's Azure SKUs), then `usage`.
- Usage in **monthly (or smaller) chunks**, newest → oldest, each its own approval token; stop at the first month with zero rows beyond a configurable retention (system tables retain ~365 days).
- Prefer **bounded projections with no per-row identity data**; if row counts per chunk approach `max_rows` (≤ 50 000), split by week.
- Backfill is resumable: chunk status persisted; re-running a completed chunk is a no-op due to the natural key.

### 4.3 Incremental ingestion

- Watermark = `max(ingestion_date)` successfully loaded per `(workspace, table)`.
- Query window = `ingestion_date >= watermark − lookback` (proposal: **3 days**) to absorb late arrivals and retractions/restatements; the natural key makes the overlap harmless.
- Cadence: daily (billing data is not real-time). Because each live query needs approval, the scheduler **creates a PLAN and notifies**; it never self-approves.
- `list_prices`: refresh weekly or when an unmatched-SKU rate crosses a threshold.

### 4.4 Duplicate prevention and idempotency

- DB-level unique natural key + `ON CONFLICT DO NOTHING` (D4); `source_row_hash` detects "same key, different content" (flag as `CONTENT_CONFLICT`, do not overwrite).
- Run idempotency: `(workspace, table, chunk_start, chunk_end, query_hash)` unique among `completed` runs; repeated POSTs return the existing result.
- Token single-use stays server-enforced (in-memory **and** durable ledger, D7).

### 4.5 Data validation & reconciliation

- Row-level checks above; run-level: `extracted == inserted + duplicate + quarantined`.
- Internal reconciliation (existing endpoint, corrected): Σ gross − Σ retraction = Σ net per day; matched + unmatched = total.
- Pricing coverage KPI: % of DBU with a matched price (target 100% for DBU units); unmatched SKUs listed explicitly.
- External reconciliation (later phase): compare monthly list-price estimate to Azure Cost Management Databricks meter totals; publish variance; **do not auto-adjust**.

### 4.6 Failure handling and retry

| Failure | Class | Handling |
|---|---|---|
| 401/auth expired | `AUTH` | No retry; surface "Authentication required — run az login."; run → `failed`. |
| 403 / no SELECT / no `CAN_USE` | `PERMISSION` | No retry; actionable message naming the missing grant. |
| Warehouse `STOPPED` | `WAREHOUSE_STOPPED` | No retry, **no token consumed** (D6); run → `blocked`. |
| 429 / 5xx / timeout / transient network | `TRANSIENT` | Exponential backoff with jitter, max 3 attempts, respecting `Retry-After`. A retry that needs a new token is **not** automatic — returns to `approval_required`. |
| Statement still `PENDING/RUNNING` after timeout | `TIMEOUT` | Poll existing statement id; never resubmit blindly (avoid double charge). |
| Row validation failure | `DATA_QUALITY` | Quarantine; abort above threshold; checkpoint not advanced. |
| DB failure mid-chunk | `PERSISTENCE` | Transaction rollback; checkpoint not advanced; safe to re-run. |

All error text passes through the existing secret scrubber before storage/return.

### 4.7 Data freshness tracking

Per workspace expose: `data_through` (max `usage_date` loaded), `last_successful_ingestion`, `last_attempt`, `watermark`, `lag_days`, `freshness_state` ∈ {`FRESH` (lag ≤ 2d), `STALE`, `NEVER_INGESTED`, `FAILING`}. Dashboards show state + age; stale data keeps the last good values **labelled stale** (mirrors the Azure discovery `stale` cache pattern), never silently current.

### 4.8 PostgreSQL persistence

Async repository (`BillingRepository`) following `db/repositories/*`; analytics reads through repository interfaces instead of `_usage_store`. Offline/mock mode keeps an in-memory implementation of the same interface (Golden Rule 4); the test suite stays runnable with no Postgres/Databricks. Writes use one transaction per chunk; bulk inserts via `executemany`/`COPY`-style batches of ≤ 5 000 rows.

---

## 5. Permissions and dependencies

### 5.1 Required, by layer

| Layer | Requirement | Where it comes from |
|---|---|---|
| Unity Catalog metadata | `USE CATALOG`/`USE SCHEMA` (browse) on `system` / `system.billing` to see tables & columns | Already effective (metadata calls returned 200). |
| Billing table data | **`SELECT` on `system.billing.usage` and `system.billing.list_prices`** (+ `USE CATALOG system`, `USE SCHEMA system.billing`) | System schemas must be *enabled* on the metastore (they are: tables visible) and **access granted by a metastore admin / account admin** — by default only admins can read them. |
| SQL compute | `CAN_USE` on warehouse `05ed10a52697a344` (or run on another warehouse the identity can use); **`CAN_MANAGE` not required** | Workspace admin / warehouse owner. |
| Workspace access | `workspace-access` + `databricks-sql-access` entitlements | Present on the Dev identity (audit). |
| Auth transport | Azure CLI delegated token (Dev); service principal OAuth only for production/explicit | Unchanged; SP currently 403 "workspace inaccessible" (not assigned). |
| Azure (reconciliation, later) | `Cost Management Reader` (+ `Reader`) | Already the project's read-only role set. |
| PostgreSQL | Role with `CONNECT`, `USAGE` on schema, `SELECT/INSERT/UPDATE` on billing tables; `CREATE` only for the migration role (separate from runtime role) | DBA. Runtime role gets **no** `DELETE/DROP/TRUNCATE`. |
| App | `finops_signing_secret` configured (otherwise tokens are disabled); approver holds `Admin`/`FinOpsAdministrator`/`PlatformAdministrator` | Existing config/RBAC. |

### 5.2 Is the current Dev identity (Azure CLI) sufficient?

| Need | Evidence | Verdict |
|---|---|---|
| Authenticate to Dev workspace | `current_user.me()` works; audit SUCCESS | **Yes** |
| See billing tables & columns | UC `tables.get` 200 for `usage`, `list_prices`, `attributed_usage` | **Yes** |
| `databricks-sql-access` entitlement | Present (also `workspace-access`, `workspace-consume`) | **Yes** |
| `SELECT` on `system.billing.*` | Not captured in the audit; metadata visibility ≠ SELECT. System tables are admin-only by default. | **Unknown — likely needs a grant** |
| `CAN_USE` on the warehouse | Warehouse visible/listable; permissions endpoint 403 ("no Manage permission"), which says nothing about `CAN_USE`. | **Unknown** |
| Start a stopped warehouse | Not tested (and prohibited); with `CAN_USE` a serverless warehouse can auto-start on a statement, which is why the app pre-checks state. | **Not needed by the app; operator action** |
| Account-level billing APIs | Account API returned 403 (not an account admin) | **Not available** (and not required for system tables) |

**Conclusion:** the current Dev workspace and Azure CLI identity are sufficient for everything *up to* querying; whether they are sufficient to *query* `system.billing.*` is unproven. **No permission was requested or changed.** A no-SQL check is proposed (Phase 2): run the existing `discover_system_tables_metadata`, whose `grants.get_effective` call populates `select_grant_verified`; if it is `false/None`, the finding to hand to a metastore admin is exactly: "grant `SELECT` on `system.billing.usage` and `system.billing.list_prices` (and `USE SCHEMA` on `system.billing`) to the Dev operator identity", plus confirm `CAN_USE` on the warehouse.

### 5.3 Dependencies

Databricks SDK (already used), `sqlglot` (validator), SQLAlchemy 2 + asyncpg + Alembic (present), a reachable PostgreSQL instance for persistence, a running Dev warehouse at approval time, and `finops_signing_secret`.

---

## 6. API design

Existing routes under `/api/v1/finops` are kept (backward compatible) and corrected; new ones are additive. All read endpoints are fail-closed: no rows ⇒ `NO_BILLING_ROWS`/`NO_DATA`, never zero.

| Method & path | Purpose | Change |
|---|---|---|
| `GET /ingestion/status` | Warehouse/auth/system-table readiness + freshness block | extend (adds freshness, watermark) |
| `GET /ingestion/runs` | Run audit (from Postgres) | now durable |
| `POST /ingestion/validate` | Preflight, no SQL | derive text from live metadata (D10) |
| `POST /ingestion/plan` | **New.** Returns the chunk plan + exact SQL + approval payloads; executes nothing | new |
| `POST /ingestion/preview` | Preview from stored rows | unchanged semantics |
| `POST /ingestion/approval-token` | Per-chunk signed token | persist ledger (D7) |
| `POST /ingestion/run` | Execute one approved chunk (idempotent) | token-per-chunk, D6/D8 fixes |
| `GET /billing/summary` | DBU + cost summary | add `cost_basis`, `period`, `data_through`, `freshness` |
| `GET /billing/usage` | Paginated facts | envelope `{total, offset, limit, records}` (D9) |
| `GET /billing/pricing` | Ingested rate card (empty until ingested) | no hardcoded rows (D1) |
| `GET /billing/daily` | **New.** Rollups by day/SKU/product | new |
| `GET /billing/by-resource` | **New.** Exact-ID attribution | new |
| `GET /billing/coverage` | **New.** Pricing-match %, unattributed %, quarantined rows | new |
| `GET /billing/reconciliation` | Internal reconciliation (+ later external) | correct decimal handling |
| `GET /billing/freshness` | **New.** `data_through`, lag, state | new |

Contracts: Pydantic v2, `Decimal` in storage / string-or-float at the edge as decided with the frontend; schema changes touch `schemas/billing_ingestion.py` (not the protected `domain.py`). Frontend consumes via existing `lib/api.ts` + `lib/financials.ts` (`NO_DATA_LABEL`, `periodSuffix`, `financialErrorFromStatus`), adding a basis badge ("Estimated at list price") and a freshness chip.

---

## 7. Security controls

| Control | Detail |
|---|---|
| Zero-execution / human approval | Unchanged: no SQL without a valid signed token **and** an operator-started warehouse. The app never starts or stops compute. |
| Read-only SQL | AST validator (single SELECT, allowlist, no comments/semicolons, unsafe functions blocked). New SQL builders must pass it in unit tests before any run. |
| Allowlist discipline | Only `usage` and `list_prices` initially. `attributed_usage` and others require a separate reviewed change. |
| Input validation | Strict patterns for `workspace_id`, dates, limits before SQL assembly (D8). |
| Token security | HMAC-signed, query-hash/warehouse/workspace/date/`max_rows` bound, short TTL, single-use (memory + durable ledger), key rotation via `kid`; fail closed without secret. |
| Server-derived identity | Approver identity and roles from the authenticated principal only; client-supplied values ignored (existing). |
| Least privilege | Databricks: `SELECT` on two tables + `CAN_USE`; Azure: read-only roles; Postgres runtime role without DDL/DELETE. |
| Data minimisation / PII | Do not select `identity_metadata` by default; store only needed `usage_metadata` keys; hash or drop `notebook_path`/`run_name`/user identifiers; never log row contents. |
| Tenant scoping | Every query filters `workspace_id` (the table is account-wide); loader asserts every row's `workspace_id` equals the request. |
| Secret hygiene | Existing scrubber on all error paths; no tokens/emails in logs, run records or the raw audit files (which stay uncommitted). |
| Offline/mock | Fixtures labelled `mock_fixture`, never `LIVE`; allowed only with the existing explicit opt-in (V5.1 policy). |
| Auditability | Every plan, approval, run, chunk and token consumption recorded durably with approver, query hash, rows, outcome. |
| Backups / retention | Raw facts retained per policy; derived tables rebuildable from facts + calculation version. |

---

## 8. Implementation phases (proposed; each ends with the AGENTS.md validation checklist)

| Phase | Scope | SQL? | Needs approval |
|---|---|---|---|
| **0 — Defect fixes (offline)** | D1–D11: remove rate card, price-struct mapping, `Decimal` pipeline, composite key, token ordering, validators, text corrections, frontend envelope. Tests with the `mock` provider. | No | Code review only. |
| **1 — Persistence layer** | Alembic migration (new/changed tables above), `BillingRepository` (async + in-memory impl), analytics reads via repository. | No | **Schema-change approval** (A1). |
| **2 — Permission verification (no SQL)** | Run existing metadata discovery to populate `select_grant_verified`; document missing grants for the admin. | No | Read-only metadata call (A2). |
| **3 — Rate-card ingestion** | One small `list_prices` statement (Azure SKUs only). | **Yes** | **Warehouse start + token (A3, A4).** |
| **4 — Usage backfill** | Chunked monthly `usage` extraction, validate/load/derive, coverage report. | **Yes** | **Token per chunk (A5).** |
| **5 — Incremental + freshness** | Checkpoint/lookback, plan scheduler (notify-only), freshness API/UI. | Yes (approved) | A5 per run. |
| **6 — Frontend & KPI wiring** | Basis badges, freshness chips, new endpoints, remove "blocked" states when `LIVE`. | No | — |
| **7 — Reconciliation & extensions** | Azure Cost Management comparison; optional `attributed_usage` allowlist change. | Maybe | Separate design/approval (A6, A7). |

---

## 9. Risks and dependencies

| ID | Risk / dependency | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | No `SELECT` on `system.billing.*` for the Dev identity | Medium–High | Blocks phases 3+ | Phase 2 check; request grant through the owner (no change made here). |
| R2 | Retraction/restatement keying differs from assumption (D4) | Medium | Wrong net totals | Natural key + `source_row_hash`; verify with the first approved `list_prices`/small usage chunk and Databricks' current billing-correction docs before enabling totals. |
| R3 | List-price estimate mistaken for invoice | Medium | Financial misstatement | `cost_basis` everywhere; only `AZURE_INVOICED` may be labelled billed. |
| R4 | Classic-compute VM/storage cost absent from system tables | Certain | Under-reports TCO | State scope in UI; Azure Cost Management reconciliation phase. |
| R5 | Per-chunk single-use tokens make large backfills operationally heavy | High | Slow rollout | Aggregate-first projections, month-sized chunks, plan/approve in batches by the same approver. |
| R6 | Warehouse cost and cold start unknown (approval text is estimated) | Medium | Surprise charge | Show observed size/auto-stop; remove fixed cost claims (D10); small first query. |
| R7 | Statement API limits (wait timeout window, inline result size) | Medium | Truncated/aborted chunks | Cap `max_rows`, chunk by week, poll by statement id, assert `row_count` vs manifest. |
| R8 | In-memory → Postgres cutover changes KPI behaviour | Medium | Regression | Repository interface with in-memory twin; keep existing tests; add parity tests. |
| R9 | Migration state of `0002/0003` unknown | Unknown | Deployment failure | Check `alembic current` in Phase 1 with approval. |
| R10 | Frontend/back-end shape drift (D9) | Medium | UI errors on first live data | Contract tests in Phase 0/6. |
| R11 | Sensitive identifiers in `identity_metadata`/`usage_metadata` | Certain if selected | Privacy/compliance | Minimise per §7. |
| R12 | Dev-only evidence; Production workspace/SP not assessed (SP currently unassigned) | Known | Scope limit | Separate production readiness review. |
| Dependencies | Postgres instance, `finops_signing_secret`, approver with an allowed role, Dev warehouse reachable, metastore-admin cooperation for grants. | | | |

### Open questions for the owner

1. Which price tier defines the headline estimate (`effective_list` vs `default` vs promotional)?
2. Retention/backfill depth (e.g., 12 months vs current quarter)?
3. Is a PII-free `usage_metadata` subset acceptable, or are job/notebook names required for allocation?
4. Is Azure Cost Management reconciliation in scope for M7 or a follow-up?
5. Who is the standing approver, and is per-chunk approval acceptable for daily incrementals?

---

## 10. Explicit approval points before any SQL execution

Nothing below has been requested or performed.

| # | Approval point | Approver | What is approved | Gate in the system |
|---|---|---|---|---|
| **A1** | Database schema change | Owner/DBA | Alembic revision creating/altering billing tables | Migration review; Zero-schema-change rule until then. |
| **A2** | Read-only metadata/grants verification | Owner | Run existing metadata-only discovery (`grants.get_effective`), no SQL | No SQL; REST read-only. |
| **A3** | Warehouse start | Operator with `CAN_USE` | Starting `05ed10a52697a344` for a stated window; stated size (2X-Small PRO serverless) and observed auto-stop (5 min) | Separate human action — the app never starts compute. |
| **A4** | Rate-card query | `FinOpsAdministrator`/`Admin`/`PlatformAdministrator` | Exact `list_prices` SELECT (columns, filter, `max_rows`) | Signed single-use token bound to query hash + warehouse + workspace + dates. |
| **A5** | Each usage chunk | Same roles | Exact `usage` SELECT per window, `workspace_id` filter, bounded `max_rows`, no identity columns | One token per statement; expires ≤ 1 h; replay rejected. |
| **A6** | Allowlist expansion (e.g. `attributed_usage`, `compute.*`) | Owner + security review | Change to `ALLOWED_SYSTEM_TABLES` and new column projections | Code change + threat review + tests. |
| **A7** | Any production/service-principal run | Owner | Separate scope, identity, workspace assignment | Out of scope for this design. |

**Approval payload must show:** exact SQL, tables, workspace, window, `max_rows`, current warehouse state, whether startup is needed, observed (not guessed) size/auto-stop, that data is read-only, and the rollback/stop procedure (let auto-stop expire; no write path exists).

**Hard stops (unchanged):** no `SELECT *`; no tables outside the allowlist; no statement without a valid token; no warehouse start by the application; no fixture data presented as live; no list-price estimate presented as an invoice.

---

*This is a read-only architecture document. No code, schema, credentials, authentication, Fabric integration or cloud resources were modified, and no Git commit was created.*
