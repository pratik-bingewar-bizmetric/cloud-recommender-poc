"""Owner-bound persistent cloud connections with encrypted credentials.

PREPARED, NOT APPLIED. Applying this revision requires explicit schema-change approval.

Revision ID: 2026_11_16_0005
Revises: 2026_11_13_0004
Create Date: 2026-11-16 12:00:00.000000

Creates ``cloud_connections``:
  * ``owner_tid`` / ``owner_oid``: owner taken from the validated application token.
  * ``secret_ciphertext`` (AES-256-GCM, AAD = id|owner) + ``secret_kid`` (key id for rotation).
  * ``integration_config`` / ``last_validation``: non-secret integration settings and the latest
    per-integration validation result.
  * UNIQUE (owner_tid, owner_oid, provider, scope_id, credential_client_id): duplicate connection
    detection (HTTP 409).
No existing table is touched. DOWNGRADE drops the table, including all stored (encrypted)
credentials, and is therefore guarded: it refuses to run unless the table is empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2026_11_16_0005"
down_revision: str | None = "2026_11_13_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_tid", sa.String(64), nullable=False),
        sa.Column("owner_oid", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("auth_method", sa.String(40), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scope_id", sa.String(150), nullable=False),
        sa.Column("credential_tenant_id", sa.String(64), nullable=True),
        sa.Column("credential_client_id", sa.String(64), nullable=True),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("secret_kid", sa.String(100), nullable=True),
        sa.Column(
            "integration_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_validation", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="connected"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "owner_tid",
            "owner_oid",
            "provider",
            "scope_id",
            "credential_client_id",
            name="uq_cloud_connection_owner_scope",
        ),
    )
    op.create_index("ix_cloud_connections_owner", "cloud_connections", ["owner_tid", "owner_oid"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM cloud_connections)")).scalar():
        raise RuntimeError(
            "Refusing to drop cloud_connections: it contains stored connections and encrypted "
            "credentials. Export or delete them deliberately first."
        )
    op.drop_index("ix_cloud_connections_owner", table_name="cloud_connections")
    op.drop_table("cloud_connections")
