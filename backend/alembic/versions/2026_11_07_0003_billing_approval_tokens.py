"""Billing approval tokens schema migration for replay prevention and RBAC.

Revision ID: 2026_11_07_0003
Revises: 2026_11_07_0002
Create Date: 2026-11-07 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2026_11_07_0003"
down_revision: str | None = "2026_11_07_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. Billing Approval Tokens Table (Replay Prevention & RBAC Audit)
    # --------------------------------------------------------------------------
    op.create_table(
        "billing_approval_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("token_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("approver_sub", sa.String(length=256), nullable=False),
        sa.Column(
            "approver_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("warehouse_id", sa.String(length=64), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("date_start", sa.String(length=32), nullable=True),
        sa.Column("date_end", sa.String(length=32), nullable=True),
        sa.Column(
            "allowed_tables",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "requested_operation",
            sa.String(length=128),
            nullable=False,
            server_default="READ_ONLY_SYSTEM_TABLES_SELECT",
        ),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("kid", sa.String(length=64), nullable=False, server_default="k1-2026"),
        sa.Column("max_rows", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_consumed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "approval_purpose",
            sa.String(length=256),
            nullable=False,
            server_default="Ingest verified billing usage and price records into FinOps Command Center",
        ),
    )
    op.create_index(
        "ix_billing_approval_tokens_token_id",
        "billing_approval_tokens",
        ["token_id"],
        unique=True,
    )
    op.create_index(
        "ix_billing_approval_token_status",
        "billing_approval_tokens",
        ["is_consumed", "expires_at"],
    )
    op.create_index(
        "ix_billing_approval_token_wh_qhash",
        "billing_approval_tokens",
        ["warehouse_id", "query_hash"],
    )


def downgrade() -> None:
    op.drop_table("billing_approval_tokens")
