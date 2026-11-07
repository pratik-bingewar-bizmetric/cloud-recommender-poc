# MILESTONE 3J.1 — Defect Register & Resolution Log

> **Repository:** `cloud-recommender-poc`  
> **Milestone:** 3J.1  
> **Status:** AUDITED & RESOLVED  
> **Date:** November 7, 2026

---

## 1. Summary of Defects

This register tracks all defects discovered during the Milestone 3J.1 release candidate verification, their root causes, and their exact remediation.

| Defect ID | Severity | Area | Description | Resolution State |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-3J1-01** | High | Backend / Models | Missing ORM registrations for 7 billing entities in `models.py` and `__init__.py` | **RESOLVED** |
| **DEF-3J1-02** | High | Database / Migrations | Missing Alembic migration for FinOps billing tables | **RESOLVED** |
| **DEF-3J1-03** | High | Security / Ingestion | Ingestion approval tokens lacked single-use replay prevention | **RESOLVED** |
| **DEF-3J1-04** | High | Security / SQL | Statement validator did not strip comments or block unsafe functions | **RESOLVED** |
| **DEF-3J1-05** | Medium | Frontend / UI | 6 FinOps Command Center modules rendered fallback placeholder card | **RESOLVED** |
| **DEF-3J1-06** | Medium | Backend / SDK Client | `DatabricksDiscoveryService` assumed `create_workspace_client` returns single object | **RESOLVED** |
| **DEF-3J1-07** | Low | Code Quality / Lint | Unformatted lines in `test_milestone_3h_ingestion.py` | **RESOLVED** |

---

## 2. Detailed Defect Analysis & Fix Evidence

### DEF-3J1-01: Missing ORM Entity Registrations
- **Discovered In:** `backend/src/cloud_recommender/db/models.py`
- **Impact:** Alembic and SQLAlchemy could not map `billing_usage_records`, `billing_price_records`, `billing_ingestion_runs`, `billing_reconciliation_results`, `billing_source_checkpoints`, `billing_scope_snapshots`, or `billing_calculation_versions`.
- **Root Cause:** Entities were previously prototyped in schemas but omitted from database models.
- **Remediation:** Added 7 strongly-typed SQLAlchemy 2.0 ORM models using `Mapped[]` and `mapped_column()` with comprehensive indexes and constraints. Exported all models from `backend/src/cloud_recommender/db/__init__.py`.
- **Verification:** `test_alembic_env_target_metadata_has_models` PASSED.

---

### DEF-3J1-02: Missing Alembic Migration Script
- **Discovered In:** `backend/alembic/versions/`
- **Impact:** Applying migrations to a clean database would fail to provision billing ingestion tables.
- **Root Cause:** Migration was not generated or checked in during Milestone 3H.
- **Remediation:** Authored migration `2026_11_07_0002_billing_ingestion_and_reconciliation.py` containing complete `upgrade()` and `downgrade()` methods covering all 7 tables, columns, constraints, and indexes.
- **Verification:** `test_billing_ingestion_migration_module_structure` PASSED.

---

### DEF-3J1-03: Ingestion Approval Token Replay Vulnerability
- **Discovered In:** `backend/src/cloud_recommender/services/databricks/sql_client.py`
- **Impact:** A previously verified approval token could potentially be re-submitted multiple times within its 15-minute validity window.
- **Root Cause:** Stateless HMAC verification checked expiration and signature, but did not maintain server-side token consumption state.
- **Remediation:** Implemented server-side token registry `_consumed_tokens: set[str]`. When `verify_approval_token` succeeds, the token signature is recorded as consumed; subsequent verification attempts are rejected.
- **Verification:** `test_hmac_approval_token_and_replay_prevention` PASSED.

---

### DEF-3J1-04: SQL Statement Sanitization & Comment Injections
- **Discovered In:** `backend/src/cloud_recommender/services/databricks/sql_client.py`
- **Impact:** Attackers could hide prohibited mutations or functions inside SQL comments (e.g., `SELECT /* comment */ 1; DROP TABLE`).
- **Root Cause:** Regex validation did not strip comments before keyword checks, and did not check for unsafe reflection functions.
- **Remediation:** Added regex pass to strip `-- ...` and `/* ... */` comments. Added semicolon check to reject multi-statement injection. Added check for prohibited functions (`SECRET(`, `DBUTILS.`, `REFLECT(`, `JAVA_METHOD(`, etc.). Enforced table allowlist against `ALLOWED_SYSTEM_TABLES`.
- **Verification:** `test_read_only_statement_validation` PASSED with adversarial inputs.

---

### DEF-3J1-05: Frontend Fallback Placeholder Card
- **Discovered In:** `frontend/src/components/FinOpsCommandCenterView.tsx`
- **Impact:** Modules 6, 7, 11, 12, 13, and 14 rendered generic placeholder text rather than domain-specific FinOps visualizations.
- **Root Cause:** Phased implementation deferred secondary module visualizations.
- **Remediation:** Replaced fallback card with tailored, data-bound UI layouts for each module:
  - Data & Storage: Storage tiers distribution, lifecycle rules, Delta catalogs table.
  - Network & Infra: NAT gateways, private endpoints, inter-zone transit breakdown table.
  - Governance & Policies: Cluster policies catalogue, governance verification checklist, approval workflow.
  - Showback & Chargeback: Business unit showback statements, attribution ledgers.
  - Workload Economics: Unit costs per query/pipeline, efficiency scores.
  - Reports & Audit: Report pack download cards, immutable governance audit log table.
- **Verification:** Frontend compiles cleanly with `tsc` and `next build`.

---

### DEF-3J1-06: Discovery Service Client Unpacking
- **Discovered In:** `backend/src/cloud_recommender/services/databricks/discovery_service.py`
- **Impact:** In unit tests or mock strategies returning `(client, error)` tuples, discovery failed with `AttributeError`.
- **Root Cause:** `discover_workspace` assumed `create_workspace_client` always returned a bare `WorkspaceClient`.
- **Remediation:** Added tuple detection: `if isinstance(client_res, tuple): client = client_res[0] else: client = client_res`.
- **Verification:** `test_discovery_service_all_categories_success` and `test_discovery_service_permission_denied_isolation` PASSED.

---

### DEF-3J1-07: Code Formatting Drift
- **Discovered In:** `backend/tests/test_milestone_3h_ingestion.py`
- **Impact:** Ruff check reported 1 unformatted file.
- **Root Cause:** Minor line-length overflow in test assertions.
- **Remediation:** Executed `ruff format backend/tests/test_milestone_3h_ingestion.py`.
- **Verification:** `ruff format --check backend/src backend/tests` returns 0 errors (120 files already formatted).

