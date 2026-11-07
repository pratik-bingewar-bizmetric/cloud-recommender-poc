"""Billing ingestion, rate card, and reconciliation schema migration.

Revision ID: 2026_11_07_0002
Revises: 2026_10_12_0001
Create Date: 2026-11-07 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2026_11_07_0002"
down_revision: str | None = "2026_10_12_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. Billing Usage Records Table
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_usage_records",
        sa.Column("record_id", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("sku_name", sa.String(length=200), nullable=False),
        sa.Column("cloud", sa.String(length=50), nullable=False, server_default="azure"),
        sa.Column("usage_start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_date", sa.String(length=20), nullable=False),
        sa.Column("usage_unit", sa.String(length=50), nullable=False, server_default="DBU"),
        sa.Column("usage_quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False, server_default="original"),
        sa.Column("ingestion_date", sa.String(length=20), nullable=True),
        sa.Column("billing_origin_product", sa.String(length=100), nullable=True),
        sa.Column(
            "product_features_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "usage_metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "custom_tags_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("effective_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("pricing_matched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("currency", sa.String(length=10), nullable=True, server_default="USD"),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_billing_usage_ws_date", "billing_usage_records", ["workspace_id", "usage_date"]
    )
    op.create_index(
        "ix_billing_usage_sku_unit", "billing_usage_records", ["sku_name", "usage_unit"]
    )

    # --------------------------------------------------------------------------
    # 2. Billing Price Records Table
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_price_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sku_name", sa.String(length=200), nullable=False),
        sa.Column("cloud", sa.String(length=50), nullable=False, server_default="azure"),
        sa.Column("currency_code", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column("price_per_unit", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("pricing_unit", sa.String(length=50), nullable=False, server_default="DBU"),
        sa.Column("price_start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_billing_price_sku_cloud",
        "billing_price_records",
        ["sku_name", "cloud", "currency_code"],
    )

    # --------------------------------------------------------------------------
    # 3. Billing Ingestion Runs Table
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "source_table",
            sa.String(length=128),
            nullable=False,
            server_default="system.billing.usage",
        ),
        sa.Column("requested_period_start", sa.String(length=20), nullable=False),
        sa.Column("requested_period_end", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("extracted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retraction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("approval_token", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_billing_runs_ws_status", "billing_ingestion_runs", ["workspace_id", "status"]
    )

    # --------------------------------------------------------------------------
    # 4. Billing Reconciliation Results Table
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_reconciliation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "reconciliation_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "reconciliation_status",
            sa.String(length=32),
            nullable=False,
            server_default="RECONCILED",
        ),
        sa.Column("usage_record_count", sa.Integer(), nullable=False),
        sa.Column("price_record_count", sa.Integer(), nullable=False),
        sa.Column("matched_records_count", sa.Integer(), nullable=False),
        sa.Column("unmatched_records_count", sa.Integer(), nullable=False),
        sa.Column("retraction_records_count", sa.Integer(), nullable=False),
        sa.Column("gross_dbu", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("retraction_dbu", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("net_dbu", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("gross_cost", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("net_cost", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column(
            "audit_notes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.create_index(
        "ix_billing_recon_ws_time",
        "billing_reconciliation_results",
        ["workspace_id", "reconciliation_timestamp"],
    )

    # --------------------------------------------------------------------------
    # 5. Billing Source Checkpoints Table
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_source_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("table_name", sa.String(length=128), nullable=False),
        sa.Column("high_watermark_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_usage_date", sa.String(length=20), nullable=True),
        sa.Column("records_ingested_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_checkpoint_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("workspace_id", "table_name", name="uq_billing_checkpoint_ws_tbl"),
    )

    # --------------------------------------------------------------------------
    # 6. Billing Scope Snapshots Table
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_scope_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "snapshot_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resource_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_clusters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_warehouses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_endpoints", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "snapshot_data_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    # --------------------------------------------------------------------------
    # 7. Billing Calculation Versions Table
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_calculation_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("version_tag", sa.String(length=64), nullable=False, unique=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("formula_definition", sa.Text(), nullable=False),
        sa.Column(
            "rounding_policy",
            sa.String(length=64),
            nullable=False,
            server_default="ROUND_HALF_UP_2DP",
        ),
        sa.Column(
            "currency_conversion_method",
            sa.String(length=64),
            nullable=False,
            server_default="EXACT_SOURCE_CURRENCY",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_table("billing_calculation_versions")
    op.drop_table("billing_scope_snapshots")
    op.drop_table("billing_source_checkpoints")
    op.drop_table("billing_reconciliation_results")
    op.drop_table("billing_ingestion_runs")
    op.drop_table("billing_price_records")
    op.drop_table("billing_usage_records")
