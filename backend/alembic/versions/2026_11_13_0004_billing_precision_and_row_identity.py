"""M7.1 billing hardening: source precision, real list_prices shape, row identity.

PREPARED, NOT APPLIED. Applying this revision requires explicit A1 (schema change) approval.

Revision ID: 2026_11_13_0004
Revises: 2026_11_07_0003
Create Date: 2026-11-13 12:00:00.000000

Changes
-------
billing_usage_records
  * usage_quantity / effective_cost widened to NUMERIC(38,18) (source is decimal(38,18)).
  * surrogate ``id`` UUID primary key; ``record_id`` becomes a plain indexed column
    (record_id alone is not assumed unique across retractions/restatements).
  * ``source_row_hash`` + UNIQUE (workspace_id, source_row_hash) = PROVISIONAL row identity.
  * cost_basis, match_status, price_tier, resource_type, resource_id added.
  * ``currency`` default removed (an unpriced row has no currency).
billing_price_records
  * flat ``price_per_unit`` replaced by price_default / price_promotional / price_effective_list
    (source ``pricing`` struct); ``pricing_unit`` renamed ``usage_unit``; ``account_id`` added.
  * UNIQUE price identity.

billing_price_records identity
  * UNIQUE is a functional unique INDEX over ``COALESCE(account_id, '')`` so rows with a NULL
    account cannot duplicate each other (PostgreSQL treats NULLs as distinct in a plain UNIQUE
    constraint; ``NULLS NOT DISTINCT`` would need PostgreSQL 15+).
billing_ingestion_runs
  * adds ``error_count``, ``shared_record_id_count``, ``result_complete`` and ``error_code``
    (present in the run schema/response, previously not persistable).

Requirements / notes
  * PostgreSQL 13+ (``gen_random_uuid()`` for the surrogate-key backfill).
  * EMPTY-TABLE GUARD: ``billing_usage_records`` must be empty on upgrade. Legacy rows cannot be
    given a trustworthy ``source_row_hash`` (it is computed by the application from the full
    row identity), and a placeholder would later insert duplicates beside them. Billing storage
    was in-memory before this revision, so no rows are expected; the migration refuses rather
    than guessing.
  * No foreign keys are added (usage rows carry no run/price lineage yet).
  * DOWNGRADE is destructive-by-design and therefore GUARDED: it refuses to run unless both
    billing tables are empty (precision narrowing truncates, restoring ``PRIMARY KEY(record_id)``
    fails once correction rows share a record_id, and an unpriced row has no price to restore;
    no ``0`` price is ever fabricated).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2026_11_13_0004"
down_revision: str | None = "2026_11_07_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _require_empty(table: str, *, direction: str) -> None:
    """Abort unless ``table`` has no rows (skipped for offline ``--sql`` rendering)."""
    if op.get_context().as_sql:
        return
    count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
    if count:
        raise RuntimeError(
            f"Refusing to {direction}: {table} holds {count} row(s). "
            "This revision is only safe on an empty billing schema (see the module docstring)."
        )


def upgrade() -> None:
    _require_empty("billing_usage_records", direction="upgrade")
    # ------------------------------------------------------------------ usage records
    op.alter_column(
        "billing_usage_records",
        "usage_quantity",
        existing_type=sa.Numeric(precision=18, scale=4),
        type_=sa.Numeric(precision=38, scale=18),
        existing_nullable=False,
    )
    op.alter_column(
        "billing_usage_records",
        "effective_cost",
        existing_type=sa.Numeric(precision=18, scale=4),
        type_=sa.Numeric(precision=38, scale=18),
        existing_nullable=True,
    )
    op.alter_column(
        "billing_usage_records",
        "currency",
        existing_type=sa.String(length=10),
        existing_nullable=True,
        server_default=None,
    )

    op.add_column(
        "billing_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE billing_usage_records SET id = gen_random_uuid() WHERE id IS NULL")
    op.add_column(
        "billing_usage_records",
        sa.Column("source_row_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "billing_usage_records",
        sa.Column(
            "cost_basis", sa.String(length=32), nullable=False, server_default="METERED_USAGE"
        ),
    )
    op.add_column(
        "billing_usage_records",
        sa.Column("match_status", sa.String(length=32), nullable=False, server_default="NO_PRICE"),
    )
    op.add_column(
        "billing_usage_records", sa.Column("price_tier", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "billing_usage_records", sa.Column("resource_type", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "billing_usage_records", sa.Column("resource_id", sa.String(length=200), nullable=True)
    )

    # Swap primary key: record_id -> surrogate id
    op.drop_constraint("billing_usage_records_pkey", "billing_usage_records", type_="primary")
    op.alter_column("billing_usage_records", "id", nullable=False)
    op.alter_column("billing_usage_records", "source_row_hash", nullable=False)
    op.create_primary_key("billing_usage_records_pkey", "billing_usage_records", ["id"])
    op.create_index("ix_billing_usage_records_record_id", "billing_usage_records", ["record_id"])
    op.create_index(
        "ix_billing_usage_ws_resource",
        "billing_usage_records",
        ["workspace_id", "resource_type", "resource_id"],
    )
    op.create_unique_constraint(
        "uq_billing_usage_row_identity",
        "billing_usage_records",
        ["workspace_id", "source_row_hash"],
    )

    # ------------------------------------------------------------------ price records
    op.add_column(
        "billing_price_records", sa.Column("account_id", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "billing_price_records",
        sa.Column("price_default", sa.Numeric(precision=38, scale=18), nullable=True),
    )
    op.add_column(
        "billing_price_records",
        sa.Column("price_promotional", sa.Numeric(precision=38, scale=18), nullable=True),
    )
    op.add_column(
        "billing_price_records",
        sa.Column("price_effective_list", sa.Numeric(precision=38, scale=18), nullable=True),
    )
    op.execute("UPDATE billing_price_records SET price_default = price_per_unit")
    op.drop_column("billing_price_records", "price_per_unit")
    op.alter_column("billing_price_records", "pricing_unit", new_column_name="usage_unit")
    op.create_index(
        "uq_billing_price_identity",
        "billing_price_records",
        [
            sa.text("COALESCE(account_id, '')"),
            "sku_name",
            "cloud",
            "currency_code",
            "usage_unit",
            "price_start_time",
        ],
        unique=True,
    )

    # ------------------------------------------------------------------ run records
    op.add_column(
        "billing_ingestion_runs",
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "billing_ingestion_runs",
        sa.Column("shared_record_id_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "billing_ingestion_runs", sa.Column("result_complete", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "billing_ingestion_runs", sa.Column("error_code", sa.String(length=40), nullable=True)
    )


def downgrade() -> None:
    _require_empty("billing_usage_records", direction="downgrade")
    _require_empty("billing_price_records", direction="downgrade")
    op.drop_column("billing_ingestion_runs", "error_code")
    op.drop_column("billing_ingestion_runs", "result_complete")
    op.drop_column("billing_ingestion_runs", "shared_record_id_count")
    op.drop_column("billing_ingestion_runs", "error_count")
    # ------------------------------------------------------------------ price records
    op.drop_index("uq_billing_price_identity", table_name="billing_price_records")
    op.alter_column("billing_price_records", "usage_unit", new_column_name="pricing_unit")
    # Table is empty (guarded above): no value is invented for the restored NOT NULL column.
    op.add_column(
        "billing_price_records",
        sa.Column("price_per_unit", sa.Numeric(precision=18, scale=6), nullable=False),
    )
    op.drop_column("billing_price_records", "price_effective_list")
    op.drop_column("billing_price_records", "price_promotional")
    op.drop_column("billing_price_records", "price_default")
    op.drop_column("billing_price_records", "account_id")

    # ------------------------------------------------------------------ usage records
    op.drop_constraint("uq_billing_usage_row_identity", "billing_usage_records", type_="unique")
    op.drop_index("ix_billing_usage_ws_resource", table_name="billing_usage_records")
    op.drop_index("ix_billing_usage_records_record_id", table_name="billing_usage_records")
    op.drop_constraint("billing_usage_records_pkey", "billing_usage_records", type_="primary")
    op.create_primary_key("billing_usage_records_pkey", "billing_usage_records", ["record_id"])
    op.drop_column("billing_usage_records", "resource_id")
    op.drop_column("billing_usage_records", "resource_type")
    op.drop_column("billing_usage_records", "price_tier")
    op.drop_column("billing_usage_records", "match_status")
    op.drop_column("billing_usage_records", "cost_basis")
    op.drop_column("billing_usage_records", "source_row_hash")
    op.drop_column("billing_usage_records", "id")
    op.alter_column(
        "billing_usage_records",
        "currency",
        existing_type=sa.String(length=10),
        existing_nullable=True,
        server_default="USD",
    )
    op.alter_column(
        "billing_usage_records",
        "effective_cost",
        existing_type=sa.Numeric(precision=38, scale=18),
        type_=sa.Numeric(precision=18, scale=4),
        existing_nullable=True,
    )
    op.alter_column(
        "billing_usage_records",
        "usage_quantity",
        existing_type=sa.Numeric(precision=38, scale=18),
        type_=sa.Numeric(precision=18, scale=4),
        existing_nullable=False,
    )
