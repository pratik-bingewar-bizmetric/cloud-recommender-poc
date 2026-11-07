# Milestone 3J.3: PostgreSQL 16 Integration Report
## Database Schema Architecture, Alembic Migration 2026_11_07_0003 & Durable Governance

### 1. Architectural Role of PostgreSQL 16

In `cloud-recommender-poc`, PostgreSQL 16 serves as the authoritative, durable persistence engine for:
1. Operational configurations and integration credentials (stored without secrets).
2. The normalized FinOps billing usage and pricing rate card cache (`billing_usage_records`, `billing_price_records`).
3. Ingestion telemetry, run history, and reconciliation logs (`billing_ingestion_runs`, `billing_reconciliation_logs`).
4. Cryptographic authorization ledger and replay tracking (`billing_approval_tokens`).

---

### 2. Schema Structure of `billing_approval_tokens`

Alembic revision `2026_11_07_0003` establishes the immutable approval token ledger. In Milestone 3J.3, the schema was enhanced with `kid`, `max_rows`, and a database-level unique constraint on `nonce`:

```sql
CREATE TABLE billing_approval_tokens (
    id SERIAL PRIMARY KEY,
    token_id VARCHAR(128) NOT NULL UNIQUE,
    kid VARCHAR(64) NOT NULL DEFAULT 'k1-2026',
    approver_sub VARCHAR(256) NOT NULL,
    approver_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    workspace_id VARCHAR(64) NOT NULL,
    warehouse_id VARCHAR(64) NOT NULL,
    query_hash VARCHAR(64) NOT NULL,
    date_start VARCHAR(32),
    date_end VARCHAR(32),
    allowed_tables JSONB NOT NULL DEFAULT '["system.billing.usage", "system.billing.list_prices"]'::jsonb,
    requested_operation VARCHAR(64) NOT NULL DEFAULT 'READ_ONLY_SYSTEM_TABLES_SELECT',
    max_rows INTEGER NOT NULL DEFAULT 1000,
    nonce VARCHAR(64) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    is_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at TIMESTAMPTZ,
    approval_purpose VARCHAR(512) NOT NULL DEFAULT 'Live System Tables Billing Ingestion',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_billing_approval_tokens_nonce UNIQUE (nonce)
);

CREATE INDEX ix_billing_approval_tokens_token_id ON billing_approval_tokens (token_id);
CREATE INDEX ix_billing_approval_tokens_warehouse_hash ON billing_approval_tokens (warehouse_id, query_hash);
CREATE INDEX ix_billing_approval_tokens_expires_consumed ON billing_approval_tokens (expires_at, is_consumed);
```

---

### 3. Alembic Migration Lineage

The Alembic migration chain is linear, deterministic, and preserves all historical data structures:

| Revision ID | Description | Created At | Status |
| :--- | :--- | :--- | :--- |
| `2026_10_28_0001` | Initial core recommender and catalog schemas | 2026-10-28 | **APPLIED** |
| `2026_11_07_0002` | FinOps normalized billing tables & governance | 2026-11-07 | **APPLIED** |
| `2026_11_07_0003` | `billing_approval_tokens` ledger & concurrency constraints | 2026-11-07 | **HEAD** |

---

### 4. Decoupled Migration Operations in `startup.bat`

Per the operational hardening guidelines of Milestone 3J.3:
- Default startup (`startup.bat start`) **does not run schema migrations automatically**. Instead, it inspects `alembic current` and informs the operator of the current state.
- A dedicated subcommand (`startup.bat migrate`) was added to handle migrations explicitly.
- Prior to executing `alembic upgrade head`, `startup.bat migrate`:
  1. Validates TCP connectivity on `127.0.0.1:5432`.
  2. Clearly displays the target database host, port, database name (`cloud_recommender`), and user (`postgres`).
  3. Displays current revision and target head before applying changes.

