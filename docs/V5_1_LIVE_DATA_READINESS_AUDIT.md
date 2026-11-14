# V5.1 Live-Data Readiness — Phase 0 Baseline and Static Audit

| | |
|---|---|
| Branch / HEAD | `feature/live-finops-kpi-integration` @ `b199b0c` (= `origin/...`) |
| Working tree | M7.1 changes uncommitted (12 modified + 5 untracked code/test files, 3 M7 docs); 25 pre-existing line-ending-only test files; `docs/databricks_api_audit/` untracked (never to be committed) |
| This phase | Inspection and documentation **only**. No code changed, nothing staged/committed, no SQL, no warehouse start, no migration, no credential/Fabric change, **no live API call was made in this phase** |
| Verdict | **NOT READY.** Items 1, 2, 3, 5 and 6 of the Definition of Ready are unverified or unmet; items 4, 7, 8 are only partly evidenced (§6) |

The readiness criteria cannot honestly be declared met from static inspection. This document records what was inspected, what is already known from earlier read-only verification, and the concrete gaps found.

---

## 1. Regression baseline

| Evidence | Status |
|---|---|
| Backend `pytest tests` on the current (M7.1-modified) tree | 553 passed, 3 skipped, 0 failed (run earlier this session; tree unchanged by this phase). Not re-run now |
| `ruff check`, `mypy src` | clean (earlier this session) |
| Frontend `npm test` (13 suites), lint, typecheck, production build | pass (earlier this session) |
| Last live verification (committed baseline `b199b0c`) | Databricks Dev discovery `LIVE`/`connected`: 1 cluster, 1 warehouse, 27 serving endpoints, 9 catalogs, 3 apps; Azure Resource Groups live (6 and 1) via Azure CLI session; GCP returns explicit 401 (no credentials). **Not repeated on the current tree** |
| Known pending review items | `docs/M7_1_PRECOMMIT_REVIEW_REPORT.md`: 3 pre-commit fixes (F1 stale preview defaults, F2 hash normalisation, F3 analytics filter keys) and critical C1/C2 (Statement API result handling, price-run limit) |

**Rule for every later change:** re-run the backend/frontend suites plus a live read-only discovery smoke before and after; Fabric code is not touched.

---

## 2. Findings — mock, hardcoded or fallback cloud data still reachable

| ID | Severity | Location | Finding | Requirement violated |
|---|---|---|---|---|
| **L-1** | **Critical** | `services/configuration/configuration_service.py` `_discover_azure_scopes` (≈L85–): `if not token:` returns a **hardcoded "simulation fixture"** topology — fixed subscription ID `f718c261-…`, tenant ID `fe82a67c-…`, resource group `rg-analytics-databricks`, workspace `adb-lakehouse-prod`, and more. It is **not** gated by `allow_demo_fixtures` and is not labelled in the response status as a fixture by that flag. The GCP twin was fixed in V5.1; the Azure branch was missed | §4 (no fixture on auth failure), §5 (honest states) |
| **L-2** | High | `services/databricks/finops_analytics_service.py` L104–146: `KNOWN_WAREHOUSES`, `KNOWN_CLUSTERS`, `KNOWN_SERVING_ENDPOINTS` (11 names), `KNOWN_APPS` are **hardcoded snapshots of one workspace's live resources**, used as a fallback to classify a resource when the live discovery cache is empty. Resources created later are not recognised; resources deleted are still "recognised". `HISTORICAL_FIXTURE_ENDPOINTS` (labelled non-live) is also in the production class | §4 |
| **L-3** | High | Hardcoded workspace identifiers in production paths: `AUTHORIZED_WORKSPACES` (three workspace IDs), default `642006393507276` in `validate_scope` and in ~10 route/service defaults. Works for the single Dev workspace; not a general live-data design | §4, §2/§3 completeness |
| **L-4** | Medium | `api/routes/monitoring.py` `/monitoring/sources`: status `simulation_fixture`, `retention_days` 90/30 and capabilities are **derived from env-var presence** (`azure_subscription_id/tenant_id/client_id`), not from a real auth/capability probe. An Azure CLI session (the supported path) is reported as `simulation_fixture` / not live; retention values are invented | §5 (status honesty) |
| **L-5** | Medium | `services/monitoring/monitoring_service.py`: initial `data_source = "mock_fixture"` and telemetry label "Azure Monitor Simulation…"; overwritten for Azure from `analyze_subscription` (which now fails closed), but the default label can surface in limitation text; retention/limitation strings need audit | §4, §5 |
| **L-6** | Medium | `/ingestion/preview` defaults `2026-10-01`/`2026-11-04` (M7.1 F1) | §4 |
| **L-7** | Medium | `services/configuration/…` and connection service still contain labelled demo/reference fixtures behind `allow_demo_fixtures` (default off) — acceptable per §4 if the flag is never enabled outside tests/demos; needs a startup guard/visible banner when enabled | §4 |
| **L-8** | Low | `services/ai/foundry_provider.py` mock fallback (`mock_fallback_fixture`) and catalog curated fixtures — these are **application-architecture (Phase A) data, not cloud telemetry**; out of scope here but must stay labelled | §4 |
| **L-9** | Low | Frontend: `isFixtureDataSource` and `[Demo Fixture]` labels exist and fixture sources are not shown as live (V5.1 tests). No hardcoded cloud figures found by grep in `frontend/src` this phase | §4 |

---

## 3. Findings — completeness (arbitrary truncation) and provenance

| ID | Severity | Finding |
|---|---|---|
| **T-1** | High | **Databricks discovery caps results** via `_collect_sdk_iterable(max_items=500)` (and smaller caps: UC tables per schema 50, schemas 100, MLflow runs 50, artifacts 25, experiments' runs `exp_ids[:10]`, artifact paths `[:10]`, metrics `[:5]`, up to 25 per-table detail fetches). A `has_more` flag is returned, which is honest, but the cap itself contradicts "no arbitrary truncation"; the UI's treatment of `has_more` was not verified in this phase |
| **T-2** | Medium | Presentation caps in analytics (`tables[:500]`, top-N lists `[:5]`, `[:500]` ledger rows). Fine for charts if totals are computed pre-cap and the cap is stated; needs per-module verification |
| **T-3** | Medium | **Azure**: `discovery_service` and `azure_inventory` follow `nextLink`, and `cost_management_service` follows `nextLink`. No cap was found in the pagination loops, but error text is cut at 200–300 chars (acceptable). **Completeness metadata** (pages fetched, total, `stale`) exists for the RG/resource discovery added in M2.5; it was not verified for the other Azure modules (monitoring metrics, Cost Management, service-specific metadata) |
| **T-4** | High | **Statement execution (C1)**: results are not checked for completion/truncation/chunking — the first billing query would risk silent partial data (see M7.1 review). Directly relevant to "billing figures with valid provenance" |
| **T-5** | Medium | Per-module provenance (source, LIVE/NO_DATA/…, last successful sync, completeness, missing permission, error detail, financial basis) is implemented unevenly: KPI provenance exists for the 15 FinOps modules; the Azure inventory/monitoring modules and the Databricks discovery categories carry statuses but not the uniform set required in §5 (notably `last successful synchronization` and `financial basis` on every module) |
| **T-6** | Medium | Billing rows are in-memory only and empty until an approved ingestion; billing failure isolation from discovery was established in V5.1 (discovery returns without billing), but is not covered by a dedicated regression test for each module |

---

## 4. Access matrix — known unavailable sources (from earlier read-only audits; **not re-tested now**)

| Service / endpoint | Result observed | Class | Needed to resolve (request, not performed) |
|---|---|---|---|
| Databricks account API `GET /api/2.0/accounts/{id}/workspaces/{ws}` | HTTP 403 "API disabled for users without account admin status" | authorization | Account-admin read access, or accept that workspace-level APIs are used instead |
| Databricks `GET …/sql/permissions` and warehouse config (`get_warehouse_permissions`, `get_warehouse_config`) | HTTP 403 (no `CAN_MANAGE` on the warehouse) | authorization | `CAN_MANAGE` (or admin) **only if** permission/config display is required; `CAN_USE` is enough to run approved queries |
| `GET /api/2.0/preview/permissionassignments/principals/{id}` | HTTP 404 | endpoint availability | Different endpoint/API version; not an access issue |
| Table/column lineage (`POST` variants) | HTTP 404; GET variants return empty | endpoint / source data | Lineage may not be populated; use the documented GET API |
| `system.tags.*`, `system.alert.*` metadata | HTTP 404 | endpoint availability (schema not enabled) | Metastore admin enabling the system schema (only if needed) |
| `system.billing.usage` / `list_prices` **data** (SELECT) | **Unknown** — metadata visible; grants not captured | authorization (probable) | Metastore/account admin to grant `USE SCHEMA` + `SELECT` on `system.billing.*`; `CAN_USE` on the warehouse |
| SQL warehouse `05ed10a52697a344` | `STOPPED`; start not permitted without approval | policy | Human-approved start (A3) |
| Databricks service principal (OAuth M2M) | HTTP 403 "workspace inaccessible" | authorization | Workspace assignment of the SP (production path only; Dev uses Azure CLI) |
| Azure `AZURE_CLIENT_SECRET` | `AADSTS7000215` invalid secret | authentication | Valid secret/credential **only if** the SP path is required; ARM currently falls back to the Azure CLI session |
| Azure subscription 1 | state `Disabled` | source state | Not a permission problem; resource operations on a disabled subscription are limited |
| Azure Cost Management / Monitor for the Enabled subscription | **Not re-verified in this phase** | unknown | Run a live read-only check; required roles: `Reader`, `Cost Management Reader`, `Monitoring Reader` |
| GCP (all) | HTTP 401 on this host (no credentials) | authentication | Out of scope for the Azure/Databricks target |

No permission has been requested or modified.

---

## 5. Module inventory to be verified against live APIs (not yet verified in this phase)

**Azure:** subscriptions/state · resource groups · resources (paged) · resource detail/config/metadata · Azure Monitor metrics/utilisation · Cost Management usage · resource health/activity · service-specific metadata (e.g. Databricks workspace resource) · diagnostics settings.

**Databricks (Dev workspace):** workspace info · clusters · cluster policies · instance pools · SQL warehouses · jobs · job runs · pipelines · Model Serving · MLflow experiments/runs · Unity Catalog (catalogs/schemas/tables/columns/grants) · Apps · system-table metadata · query history · FinOps modules (15).

For each: record endpoint, HTTP result, record count vs source total, `has_more`, status label, and whether billing absence leaves it intact.

---

## 6. Definition of Ready — current status

| # | Criterion | Status | Basis |
|---|---|---|---|
| 1 | All existing Azure modules verified against live APIs | **Not verified** | Only RG/resource discovery verified live (V5.1); Monitor, Cost Management and service metadata not re-verified |
| 2 | All existing Databricks modules verified against live APIs | **Not verified on the current tree** | Dev discovery verified at `b199b0c`; per-module and completeness verification not repeated |
| 3 | All accessible data visible without arbitrary truncation | **Not met** | T-1…T-3 |
| 4 | No mock/hardcoded cloud data in normal operation | **Not met** | L-1 (critical), L-2, L-3, L-4 |
| 5 | Missing access documented with exact IT/API requirements | **Partial** | §4 covers known items; Azure Monitor/Cost Management and system-table SELECT unknown |
| 6 | Billing figures have valid source provenance | **Not met** | No ingested billing; C1/C2 unresolved; `cost_basis` not yet shown in the UI |
| 7 | All previous functionality continues to work | **Evidenced (tests), not live** | 553 backend / 13 frontend suites pass on the uncommitted tree |
| 8 | Regression, frontend and backend checks pass | **Evidenced** | Earlier this session; must be re-run after each change |

**Readiness is not claimed.**

---

## 7. Proposed work plan (needs go-ahead; each step ends with the full regression + live read-only smoke)

| Step | Scope | Live calls | Risk |
|---|---|---|---|
| P0 | Resolve M7.1 pre-commit items (F1–F3), commit M7.1 as code-level hardening | none | low |
| P1 | **L-1**: gate/remove the Azure scope fixture; unauthenticated ⇒ explicit `AUTHENTICATION_REQUIRED` state (mirrors the GCP fix) + regression tests | none | low |
| P2 | **L-2/L-3**: replace `KNOWN_*` and fixed workspace allowlists with live-discovery-derived registries and the workspace registry; keep behaviour when discovery is empty = `UNAVAILABLE`, not a guess | none | medium (classification code) |
| P3 | **L-4/L-5**: real capability/auth probes for `/monitoring/sources`; remove invented retention numbers | read-only Azure | low |
| P4 | **T-1/T-2**: remove or raise discovery caps with real pagination to completion (bounded by time, not count), surface `result_complete`, totals and `has_more` in every module and in the UI | read-only Databricks | medium |
| P5 | **T-5**: uniform module provenance block (source, status, last sync, completeness, missing permission, error, financial basis) in schemas + UI badges | none | medium |
| P6 | **Live verification pass** (read-only): every Azure and Databricks module; produce an evidence table (endpoint, HTTP, counts vs totals) and update §4 with exact errors | read-only Azure + Databricks; **no SQL, no warehouse start** | low |
| P7 | Billing: M7.1 C1/C2 fixes, PostgreSQL ledger evidence, persistence — all gated by A1–A5 | SQL only after approval | high |

Nothing here has been started. Steps P1, P2 and P5 change production behaviour and should be reviewed before merging; P6 needs your confirmation that read-only live calls against the Dev workspace and the Azure subscription(s) are acceptable in this session.

---

## 8. Constraints observed

No change to Fabric integration, Databricks authentication (Azure CLI retained), credentials, permissions, databases or schemas; no destructive Git command; no secrets, environment files or raw audit JSON handled or committed.
