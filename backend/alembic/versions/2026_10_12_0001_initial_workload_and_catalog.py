"""Initial workload and catalog schema migration.

Revision ID: 2026_10_12_0001
Revises:
Create Date: 2026-10-12 14:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2026_10_12_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. Workload Profiles Table
    # --------------------------------------------------------------------------
    op.create_table(
        "workload_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("target_traffic_rps", sa.Integer(), nullable=True),
        sa.Column("monthly_active_users", sa.Integer(), nullable=True),
        sa.Column("peak_multiplier", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("target_sla_percentage", sa.Numeric(precision=5, scale=3), nullable=True),
        sa.Column(
            "high_availability", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("multi_region", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rpo_minutes", sa.Integer(), nullable=True),
        sa.Column("rto_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "compliance_frameworks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("data_classification", sa.String(length=100), nullable=True),
        sa.Column("storage_volume_gb", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("monthly_data_egress_gb", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("database_type", sa.String(length=50), nullable=True),
        sa.Column("primary_region", sa.String(length=100), nullable=True),
        sa.Column(
            "target_regions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("max_monthly_budget", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "cost_buffer_percentage",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="15.00",
        ),
        sa.Column(
            "estimation_assumptions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_workload_profiles_name", "workload_profiles", ["name"])
    op.create_index("ix_workload_profiles_category", "workload_profiles", ["category"])
    op.create_index("ix_workload_category_created", "workload_profiles", ["category", "created_at"])

    # --------------------------------------------------------------------------
    # 2. Cloud Service Catalog Table
    # --------------------------------------------------------------------------
    op.create_table(
        "cloud_service_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "supported_regions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "supported_compliance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sla_percentage", sa.Float(), nullable=True),
        sa.Column("is_serverless", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("pricing_unit", sa.String(length=100), nullable=True),
        sa.Column("measurement_metric", sa.String(length=100), nullable=True),
        sa.Column("documentation_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "pricing_source_type",
            sa.String(length=100),
            nullable=False,
            server_default="curated_fixture",
        ),
        sa.Column("pricing_reference_url", sa.String(length=1000), nullable=True),
        sa.Column("dataset_version", sa.String(length=50), nullable=False, server_default="1.0.0"),
        sa.Column(
            "retrieval_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("provenance", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="fixture"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("provider", "service_id", name="uq_provider_service_id"),
    )
    op.create_index("ix_cloud_service_catalog_provider", "cloud_service_catalog", ["provider"])
    op.create_index("ix_cloud_service_catalog_category", "cloud_service_catalog", ["category"])
    op.create_index("ix_cloud_service_catalog_status", "cloud_service_catalog", ["status"])
    op.create_index(
        "ix_catalog_provider_category", "cloud_service_catalog", ["provider", "category"]
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_provider_category", table_name="cloud_service_catalog")
    op.drop_index("ix_cloud_service_catalog_status", table_name="cloud_service_catalog")
    op.drop_index("ix_cloud_service_catalog_category", table_name="cloud_service_catalog")
    op.drop_index("ix_cloud_service_catalog_provider", table_name="cloud_service_catalog")
    op.drop_table("cloud_service_catalog")

    op.drop_index("ix_workload_category_created", table_name="workload_profiles")
    op.drop_index("ix_workload_profiles_category", table_name="workload_profiles")
    op.drop_index("ix_workload_profiles_name", table_name="workload_profiles")
    op.drop_table("workload_profiles")
