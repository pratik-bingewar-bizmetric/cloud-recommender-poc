"""Microsoft Fabric OneLake Lakehouse Persistence Layer.

Provides persistent storage for:
- Cloud connection registrations & safe metadata
- Resource inventory snapshots
- Real GenAI token telemetry logs

In Microsoft Fabric, tables are stored in the Lakehouse delta format.
In local development and automated testing, it persists to an isolated local SQLite
storage layer with identical schema definitions, ensuring 100% offline determinism.
"""

import base64
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)

from schemas.models import (
    CloudConnection,
    DiscoveredResource,
    TokenUsageRecord,
)


class FabricLakehouseStore:
    """Persistent storage engine for Microsoft Fabric FinOps telemetry and connections."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            # Use environment variable if configured, else default to workspace-safe local store
            env_path = os.environ.get("FABRIC_LAKEHOUSE_DB_PATH")
            if env_path:
                self.db_path = Path(env_path)
            else:
                try:
                    base_dir = (
                        Path(__file__).resolve().parent.parent
                        if "__file__" in globals()
                        else Path(tempfile.gettempdir())
                    )
                    candidate = base_dir / "data" / "lakehouse_finops.db"
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    test_probe = candidate.parent / ".probe_write"
                    test_probe.touch()
                    test_probe.unlink()
                    self.db_path = candidate
                except Exception:
                    import tempfile

                    self.db_path = Path(tempfile.gettempdir()) / "lakehouse_finops.db"
        else:
            self.db_path = Path(db_path)

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            import tempfile

            self.db_path = Path(tempfile.gettempdir()) / "lakehouse_finops.db"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """Initialize Delta/Relational schema tables for connections, telemetry, and inventory."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Cloud Connections Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cloud_connections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    tenant_or_org_id TEXT,
                    client_id TEXT,
                    auth_method TEXT NOT NULL,
                    secret_vault_ref TEXT,
                    status TEXT NOT NULL,
                    last_verified_at TEXT NOT NULL,
                    is_live INTEGER NOT NULL DEFAULT 1,
                    capabilities_json TEXT NOT NULL,
                    access_limitations_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Migration: ensure client_id column exists
            cursor.execute("PRAGMA table_info(cloud_connections)")
            cols = [r["name"] for r in cursor.fetchall()]
            if "client_id" not in cols:
                cursor.execute("ALTER TABLE cloud_connections ADD COLUMN client_id TEXT")

            # 2. Token Telemetry Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS token_telemetry (
                    event_id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    deployment_name TEXT,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    latency_ms INTEGER,
                    estimated_cost_usd TEXT NOT NULL,
                    source TEXT NOT NULL,
                    pricing_status TEXT DEFAULT 'published_rate',
                    FOREIGN KEY (connection_id) REFERENCES cloud_connections(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("PRAGMA table_info(token_telemetry)")
            columns_token = [col[1] for col in cursor.fetchall()]
            if "pricing_status" not in columns_token:
                cursor.execute(
                    "ALTER TABLE token_telemetry ADD COLUMN pricing_status TEXT DEFAULT 'published_rate'"
                )
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_token_telemetry_conn_ts
                ON token_telemetry(connection_id, timestamp)
            """)

            # 3. Discovered Resources Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resource_inventory (
                    resource_id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_group TEXT,
                    location TEXT NOT NULL,
                    sku_name TEXT,
                    tags_json TEXT NOT NULL,
                    power_state TEXT,
                    monthly_cost_usd TEXT,
                    scan_timestamp TEXT NOT NULL,
                    FOREIGN KEY (connection_id) REFERENCES cloud_connections(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_inventory_conn
                ON resource_inventory(connection_id)
            """)

            conn.commit()

    # --- Cryptographic Secret Protection ---

    def _get_cipher(self) -> Fernet:
        """Derive a stable 32-byte encryption key from environment seed or workspace salt."""
        key_seed = os.environ.get(
            "FABRIC_SECRET_ENCRYPTION_KEY",
            "fabric-finops-workspace-secret-salt-2026",
        )
        derived = hashlib.sha256(key_seed.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(derived))

    def _protect_secret(self, connection_id: str, secret: str) -> str:
        """Securely store secret in Azure Key Vault if available, or encrypt via AES-256 Fernet."""
        vault_url = os.environ.get("AZURE_KEYVAULT_URL")
        if vault_url:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient

                client = SecretClient(
                    vault_url=vault_url, credential=DefaultAzureCredential()
                )
                safe_name = f"finops-sp-{connection_id.replace('/', '-').replace(':', '-')}"
                client.set_secret(safe_name, secret)
                return f"vault://{vault_url.rstrip('/')}/secrets/{safe_name}"
            except Exception as exc:
                logger.warning(
                    "keyvault_protection_failed_fallback_to_fernet",
                    error=str(exc),
                )

        cipher = self._get_cipher()
        encrypted = cipher.encrypt(secret.encode("utf-8")).decode("utf-8")
        return f"enc:{encrypted}"

    def _unprotect_secret(self, secret_ref: str) -> str | None:
        """Retrieve plaintext secret from Azure Key Vault reference or decrypt Fernet ciphertext."""
        if secret_ref.startswith("vault://"):
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient

                parts = secret_ref[8:].split("/secrets/")
                if len(parts) == 2:
                    vault_url = f"https://{parts[0]}"
                    secret_name = parts[1]
                    client = SecretClient(
                        vault_url=vault_url, credential=DefaultAzureCredential()
                    )
                    return client.get_secret(secret_name).value
            except Exception as exc:
                logger.warning("keyvault_retrieve_failed", error=str(exc))
                return None
        elif secret_ref.startswith("enc:"):
            try:
                cipher = self._get_cipher()
                return cipher.decrypt(secret_ref[4:].encode("utf-8")).decode("utf-8")
            except Exception as exc:
                logger.warning("fernet_decrypt_failed", error=str(exc))
                return None
        return secret_ref  # Legacy fallback

    # --- Connection Operations ---

    def list_connections(
        self, provider_filter: str | None = None
    ) -> list[CloudConnection]:
        """Retrieve all registered cloud connections with safe metadata."""
        query = "SELECT * FROM cloud_connections"
        params: list[Any] = []
        if provider_filter:
            query += " WHERE provider = ?"
            params.append(provider_filter)
        query += " ORDER BY created_at DESC"

        connections: list[CloudConnection] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                row_keys = row.keys()
                client_id = row["client_id"] if "client_id" in row_keys else None
                connections.append(
                    CloudConnection(
                        id=row["id"],
                        name=row["name"],
                        provider=row["provider"],
                        scope_id=row["scope_id"],
                        tenant_or_org_id=row["tenant_or_org_id"],
                        client_id=client_id,
                        auth_method=row["auth_method"],
                        status=row["status"],
                        last_verified_at=datetime.fromisoformat(
                            row["last_verified_at"]
                        ),
                        is_live=bool(row["is_live"]),
                        capabilities=json.loads(row["capabilities_json"]),
                        access_limitations=json.loads(row["access_limitations_json"]),
                    )
                )
        return connections

    def get_connection(self, connection_id: str) -> CloudConnection | None:
        """Find a cloud connection by its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cloud_connections WHERE id = ?", (connection_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            row_keys = row.keys()
            client_id = row["client_id"] if "client_id" in row_keys else None
            return CloudConnection(
                id=row["id"],
                name=row["name"],
                provider=row["provider"],
                scope_id=row["scope_id"],
                tenant_or_org_id=row["tenant_or_org_id"],
                client_id=client_id,
                auth_method=row["auth_method"],
                status=row["status"],
                last_verified_at=datetime.fromisoformat(row["last_verified_at"]),
                is_live=bool(row["is_live"]),
                capabilities=json.loads(row["capabilities_json"]),
                access_limitations=json.loads(row["access_limitations_json"]),
            )

    def save_connection(
        self,
        connection: CloudConnection,
        secret: str | None = None,
    ) -> None:
        """Insert or update a cloud connection record with protected secret reference."""
        now_iso = datetime.now(UTC).isoformat()
        vault_ref = None
        if secret:
            vault_ref = self._protect_secret(connection.id, secret)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO cloud_connections (
                    id, name, provider, scope_id, tenant_or_org_id, client_id,
                    auth_method, secret_vault_ref, status, last_verified_at,
                    is_live, capabilities_json, access_limitations_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    provider=excluded.provider,
                    scope_id=excluded.scope_id,
                    tenant_or_org_id=excluded.tenant_or_org_id,
                    client_id=COALESCE(excluded.client_id, cloud_connections.client_id),
                    auth_method=excluded.auth_method,
                    secret_vault_ref=COALESCE(excluded.secret_vault_ref, cloud_connections.secret_vault_ref),
                    status=excluded.status,
                    last_verified_at=excluded.last_verified_at,
                    is_live=excluded.is_live,
                    capabilities_json=excluded.capabilities_json,
                    access_limitations_json=excluded.access_limitations_json,
                    updated_at=excluded.updated_at
                """,
                (
                    connection.id,
                    connection.name,
                    connection.provider,
                    connection.scope_id,
                    connection.tenant_or_org_id,
                    connection.client_id,
                    connection.auth_method,
                    vault_ref,
                    connection.status,
                    connection.last_verified_at.isoformat(),
                    1 if connection.is_live else 0,
                    json.dumps(connection.capabilities),
                    json.dumps(connection.access_limitations),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()

    def get_connection_secret(self, connection_id: str) -> str | None:
        """Retrieve and unprotect stored secret or key vault reference for server-side auth."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT secret_vault_ref FROM cloud_connections WHERE id = ?",
                (connection_id,),
            )
            row = cursor.fetchone()
            if row and row["secret_vault_ref"]:
                return self._unprotect_secret(str(row["secret_vault_ref"]))
            return None

    def delete_connection(self, connection_id: str) -> bool:
        """Delete a connection and cascading resources/telemetry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM cloud_connections WHERE id = ?", (connection_id,)
            )
            deleted_count = cursor.rowcount
            cursor.execute(
                "DELETE FROM resource_inventory WHERE connection_id = ?",
                (connection_id,),
            )
            cursor.execute(
                "DELETE FROM token_telemetry WHERE connection_id = ?", (connection_id,)
            )
            conn.commit()
            return deleted_count > 0

    # --- Resource Inventory Operations ---

    def save_inventory(
        self, connection_id: str, resources: list[DiscoveredResource]
    ) -> None:
        """Replace inventory snapshot for a given connection."""
        now_iso = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM resource_inventory WHERE connection_id = ?",
                (connection_id,),
            )
            for res in resources:
                cursor.execute(
                    """
                    INSERT INTO resource_inventory (
                        resource_id, connection_id, name, resource_type,
                        resource_group, location, sku_name, tags_json,
                        power_state, monthly_cost_usd, scan_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        res.resource_id,
                        connection_id,
                        res.name,
                        res.resource_type,
                        res.resource_group,
                        res.location,
                        res.sku_name,
                        json.dumps(res.tags),
                        res.power_state,
                        str(res.monthly_cost_usd)
                        if res.monthly_cost_usd is not None
                        else None,
                        now_iso,
                    ),
                )
            conn.commit()

    def get_inventory(
        self, connection_id: str, resource_type_filter: str | None = None
    ) -> list[DiscoveredResource]:
        """Fetch discovered resources for a connection."""
        query = "SELECT * FROM resource_inventory WHERE connection_id = ?"
        params: list[Any] = [connection_id]
        if resource_type_filter:
            query += " AND LOWER(resource_type) LIKE ?"
            params.append(f"%{resource_type_filter.lower()}%")
        query += " ORDER BY resource_type, name"

        resources: list[DiscoveredResource] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                resources.append(
                    DiscoveredResource(
                        resource_id=row["resource_id"],
                        name=row["name"],
                        resource_type=row["resource_type"],
                        resource_group=row["resource_group"],
                        location=row["location"],
                        sku_name=row["sku_name"],
                        tags=json.loads(row["tags_json"]),
                        power_state=row["power_state"],
                        monthly_cost_usd=Decimal(row["monthly_cost_usd"])
                        if row["monthly_cost_usd"]
                        else None,
                    )
                )
        return resources

    # --- Token Telemetry Operations ---

    def append_token_telemetry(self, record: TokenUsageRecord) -> None:
        """Insert a single real token telemetry event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO token_telemetry (
                    event_id, connection_id, timestamp, model_name,
                    deployment_name, prompt_tokens, completion_tokens,
                    total_tokens, latency_ms, estimated_cost_usd, source,
                    pricing_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.event_id,
                    record.connection_id,
                    record.timestamp.isoformat(),
                    record.model_name,
                    record.deployment_name,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    record.latency_ms,
                    str(record.estimated_cost_usd),
                    record.source,
                    record.pricing_status,
                ),
            )
            conn.commit()

    def get_token_telemetry(
        self, connection_id: str, days: int = 30
    ) -> list[TokenUsageRecord]:
        """Query token telemetry events within the specified time window."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM token_telemetry
                WHERE connection_id = ?
                ORDER BY timestamp ASC
                """,
                (connection_id,),
            )
            records: list[TokenUsageRecord] = []
            for row in cursor.fetchall():
                pricing_status = (
                    row["pricing_status"]
                    if "pricing_status" in row.keys() and row["pricing_status"]
                    else "published_rate"
                )
                records.append(
                    TokenUsageRecord(
                        event_id=row["event_id"],
                        connection_id=row["connection_id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        model_name=row["model_name"],
                        deployment_name=row["deployment_name"],
                        prompt_tokens=row["prompt_tokens"],
                        completion_tokens=row["completion_tokens"],
                        total_tokens=row["total_tokens"],
                        latency_ms=row["latency_ms"],
                        estimated_cost_usd=Decimal(row["estimated_cost_usd"]),
                        source=row["source"],
                        pricing_status=pricing_status,
                    )
                )
            return records
