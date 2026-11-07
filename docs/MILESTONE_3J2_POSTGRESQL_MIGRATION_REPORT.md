# Milestone 3J.2 — PostgreSQL Migration & Schema Integrity Report
## Durable Persistence Architecture for FinOps Governance & Approval Tokens

| Parameter | Specification |
| :--- | :--- |
| **Database Engine** | PostgreSQL 16 (Local Port 5432) / SQLite (Unit Test In-Memory) |
| **Migration Tool** | Alembic 1.14+ / SQLAlchemy 2.0 |
| **New Migration Revision** | `2026_11_07_0003` |
| **Down Revision** | `2026_11_07_0002` |
| **Target Head Revision** | `2026_11_07_0003_billing_approval_tokens.py` |
| **Data Preservation** | 100% Non-Destructive / Zero Data Loss |

---

## 1. Migration History & Lineage

The database schema evolution has progressed through three clean, sequential revisions:

```
2026_10_12_0001 (initial_workload_and_catalog)
        │
        ▼
2026_11_07_0002 (billing_ingestion_and_reconciliation)
        │
        ▼
2026_11_07_0003 (billing_approval_tokens) [MILESTONE 3J.2]
```

### 1.1 Revision Lineage Details

1. **`2026_10_12_0001_initial_workload_and_catalog.py`**:
   - `workload_profiles`: Application intake profiles and architecture recommendations.
   - `cloud_service_catalog`: Multi-cloud SKU and service pricing catalog.
   - `resource_configurations`: Cloud resource selections.
   - `configured_scope_items`: Ingested cloud resources.
   - `ingestion_runs`: General Azure/GCP ingestion logs.
   - `ingestion_resource_records`: Raw resource records.

2. **`2026_11_07_0002_billing_ingestion_and_reconciliation.py`**:
   - `billing_usage_records`: Normalized Databricks usage records from `system.billing.usage`.
   - `billing_price_records`: Rate card list prices from `system.billing.list_prices`.
   - `billing_ingestion_runs`: Detailed audit logs of Databricks ingestion runs.
   - `billing_reconciliation_results`: Financial reconciliation results between usage and pricing.
   - `billing_source_checkpoints`: High-watermark checkpoints for incremental ingestion.
   - `billing_scope_snapshots`: Periodic snapshots of active cluster/warehouse inventory.
   - `billing_calculation_versions`: Audit registry of pricing formulas and rounding policies.

3. **`2026_11_07_0003_billing_approval_tokens.py`** *(Introduced in Milestone 3J.2)*:
   - `billing_approval_tokens`: Durable ledger for cryptographic execution approval tokens, approver identities, role snapshots, and atomic consumption flags.

---

## 2. Table Definition: `billing_approval_tokens`

```sql
CREATE TABLE billing_approval_tokens (
    id UUID PRIMARY KEY,
    token_id VARCHAR(128) NOT NULL UNIQUE,
    approver_sub VARCHAR(256) NOT NULL,
    approver_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    workspace_id VARCHAR(64) NOT NULL,
    warehouse_id VARCHAR(64) NOT NULL,
    query_hash VARCHAR(64) NOT NULL,
    date_start VARCHAR(32),
    date_end VARCHAR(32),
    allowed_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    requested_operation VARCHAR(128) NOT NULL DEFAULT 'READ_ONLY_SYSTEM_TABLES_SELECT',
    nonce VARCHAR(64) NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    is_consumed BOOLEAN NOT NULL DEFAULT false,
    approval_purpose VARCHAR(256) NOT NULL DEFAULT 'Ingest verified billing usage and price records into FinOps Command Center'
);

-- Indexes for performance and replay query optimization
CREATE UNIQUE INDEX ix_billing_approval_tokens_token_id ON billing_approval_tokens (token_id);
CREATE INDEX ix_billing_approval_token_status ON billing_approval_tokens (is_consumed, expires_at);
CREATE INDEX ix_billing_approval_token_wh_qhash ON billing_approval_tokens (warehouse_id, query_hash);
CREATE INDEX ix_billing_approval_tokens_workspace_id ON billing_approval_tokens (workspace_id);
```

---

## 3. ORM Model Mapping & Declarative Metadata

The ORM entity is mapped in `backend/src/cloud_recommender/db/models.py`:
- Class: `BillingApprovalTokenModel`
- Subclass of: `Base` (DeclarativeBase)
- Cross-dialect JSON compatibility: uses `JSONType` (evaluates to `JSONB` on PostgreSQL and `JSON` on SQLite for offline test suites).
- Platform-independent UUID: uses `GUID` decorator (native UUID on PostgreSQL, CHAR(36) on SQLite).
- Registration in `Base.metadata.tables`: verified by automated tests in `test_alembic_migration.py`.

---

## 4. Verification Evidence

The migration script and database metadata were verified across both unit and integration tests:
1. `test_alembic_migration.py::test_billing_approval_tokens_migration_module_structure` — **PASSED**
2. `test_alembic_migration.py::test_billing_ingestion_migration_module_structure` — **PASSED** (verifies all 8 tables in `Base.metadata`)
3. `test_milestone_3j2_security.py::test_durable_token_persistence_and_cross_restart_replay` — **PASSED** (verifies live CRUD, table creation, and single-use consumption)
4. Non-destructive migration verification in `startup.bat`:
   - `alembic current` -> reports active revision
   - `alembic heads` -> targets `2026_11_07_0003`
   - `alembic upgrade head` -> applies only pending migrations without dropping existing data.

