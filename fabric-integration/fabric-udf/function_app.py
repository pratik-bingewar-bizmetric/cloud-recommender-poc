"""Microsoft Fabric Python User Data Functions (UDF) - Production Bundle.

Provides serverless FinOps RPC endpoints callable via Microsoft Fabric REST API:
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/userDataFunctions/{udfId}/functions/{functionName}/invoke

Strict Operational Principles:
1. Real Data Only - Zero synthetic curves or mock generators.
2. Least-Privilege Read-Only permissions on customer cloud tenants.
3. Offline & local determinism via Lakehouse / SQLite persistent store.
"""

import asyncio
import base64
import concurrent.futures
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import ssl
import subprocess
import tempfile
from typing import Any, Literal
import urllib.error
import urllib.parse
import urllib.request
import uuid

import fabric.functions as fn
udf = fn.UserDataFunctions()

from cryptography.fernet import Fernet
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("finops_udf")


def run_sync(coro: Any) -> Any:
    """Execute coroutine synchronously even when invoked inside an existing event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


# --- SECTION: SCHEMAS & MODELS ---

"""Domain schemas and API contracts for Microsoft Fabric User Data Functions.

Strict adherence to:
1. Real Data Only - Zero mock / synthetic fallbacks in production.
2. Least-Privilege Read-Only permissions on customer clouds.
3. Explicit typing with Pydantic v2.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class UdfResponse(BaseModel, Generic[T]):
    """Standard RPC response envelope for Microsoft Fabric User Data Functions."""

    status: Literal["success", "error"] = Field(
        ..., description="Execution status: success or error."
    )
    data: T | None = Field(default=None, description="Typed payload if successful.")
    error_code: str | None = Field(
        default=None, description="Machine-readable error identifier if failed."
    )
    error_message: str | None = Field(
        default=None, description="Human-actionable diagnostic message if failed."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of response generation.",
    )


class CloudConnection(BaseModel):
    """Metadata representing an authorized cloud subscription or project."""

    id: str = Field(..., description="Unique connection ID (e.g. azure-sub-11223344).")
    name: str = Field(..., description="Display name for the connection.")
    provider: Literal["azure", "aws", "gcp"] = Field(
        ..., description="Target cloud provider."
    )
    scope_id: str = Field(
        ..., description="Azure Subscription ID, AWS Account ID, or GCP Project ID."
    )
    tenant_or_org_id: str | None = Field(
        default=None, description="Entra ID Tenant ID or GCP Org ID."
    )
    client_id: str | None = Field(
        default=None,
        description="Client ID / App ID for Service Principal authentication.",
    )
    secret_vault_ref: str | None = Field(
        default=None,
        description="Secure vault reference or encrypted key identifier for secret.",
    )
    auth_method: str = Field(
        ...,
        description="Safe description of auth method (e.g. service_principal, cli_token).",
    )
    status: Literal["connected", "auth_failed", "permission_denied", "disconnected"] = (
        Field(default="connected", description="Current verified status.")
    )
    last_verified_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of last successful probe.",
    )
    is_live: bool = Field(
        default=True, description="True if backed by verified live provider APIs."
    )
    capabilities: list[str] = Field(
        default_factory=lambda: [
            "inventory",
            "waste_detection",
            "metrics",
            "token_economics",
        ],
        description="Enabled telemetry and scan capabilities.",
    )
    access_limitations: list[str] = Field(
        default_factory=lambda: [
            "Strictly read-only access (Reader, Cost Management Reader, Monitoring Reader).",
            "Zero automated infrastructure mutations permitted.",
        ],
        description="Bound security constraints.",
    )


class DiscoveredResource(BaseModel):
    """Normalized snapshot of a cloud resource discovered via live provider APIs."""

    resource_id: str = Field(..., description="Canonical ARM Resource ID or cloud URI.")
    name: str = Field(..., description="Resource name.")
    resource_type: str = Field(
        ...,
        description="Normalized resource type (e.g. Microsoft.Compute/virtualMachines).",
    )
    resource_group: str | None = Field(
        default=None, description="Azure Resource Group name if applicable."
    )
    location: str = Field(..., description="Cloud region / datacenter location.")
    sku_name: str | None = Field(
        default=None, description="Assigned hardware/tier SKU."
    )
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags.")
    power_state: str | None = Field(
        default=None,
        description="Power / runtime state (running, stopped, deallocated).",
    )
    monthly_cost_usd: Decimal | None = Field(
        default=None, description="Deterministic monthly cost based on official rates."
    )


class WasteItem(BaseModel):
    """Identified FinOps cloud waste candidate with deterministic cost leakage calculation."""

    resource_id: str = Field(
        ..., description="ARM ID or URI of the resource generating waste."
    )
    name: str = Field(..., description="Resource name.")
    resource_type: str = Field(
        ..., description="Type of resource (VirtualMachine, Disk, PublicIP)."
    )
    waste_category: Literal[
        "unattached_disk", "idle_compute", "unassociated_ip", "oversized_compute"
    ] = Field(..., description="FinOps classification of the waste.")
    evidence: str = Field(
        ..., description="Objective telemetry rationale (e.g. CPU < 5% over 7 days)."
    )
    current_sku: str | None = Field(default=None, description="Current assigned SKU.")
    recommended_sku: str | None = Field(
        default=None, description="Target rightsized SKU if applicable."
    )
    monthly_cost_leakage_usd: Decimal = Field(
        ..., description="Deterministic monthly cost currently being wasted."
    )
    projected_monthly_savings_usd: Decimal = Field(
        ..., description="Monthly financial savings achieved upon manual remediation."
    )
    cost_status: Literal[
        "verified_rate", "estimated_sku_rate", "pricing_unavailable"
    ] = Field(
        default="verified_rate", description="Provenance of monthly cost figure."
    )


class WasteSummary(BaseModel):
    """Aggregated FinOps waste detection findings for a cloud scope."""

    connection_id: str = Field(..., description="Connection ID evaluated.")
    scan_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC time of waste evaluation.",
    )
    total_monthly_waste_usd: Decimal = Field(
        default=Decimal("0.00"),
        description="Sum of monthly waste across all categories.",
    )
    total_annual_waste_usd: Decimal = Field(
        default=Decimal("0.00"), description="12-month projected waste."
    )
    waste_count_by_category: dict[str, int] = Field(
        default_factory=dict, description="Count of candidate resources per category."
    )
    items: list[WasteItem] = Field(
        default_factory=list, description="Detailed list of detected waste candidates."
    )


class MetricPoint(BaseModel):
    """Single timestamped observation point from Azure Monitor."""

    timestamp: datetime = Field(..., description="UTC observation timestamp.")
    average: float | None = Field(
        default=None, description="Average metric value in interval."
    )
    maximum: float | None = Field(
        default=None, description="Peak metric value in interval."
    )
    minimum: float | None = Field(
        default=None, description="Minimum metric value in interval."
    )


class MetricSeries(BaseModel):
    """Timeseries for a specific resource metric."""

    metric_name: str = Field(
        ..., description="Metric identifier (e.g. Percentage CPU)."
    )
    unit: str = Field(..., description="Measurement unit (Percent, Bytes, Count).")
    points: list[MetricPoint] = Field(
        default_factory=list, description="Ordered time series."
    )


class ResourceMetricsResponse(BaseModel):
    """Container for monitoring metrics retrieved for a given resource."""

    resource_id: str = Field(..., description="ARM ID evaluated.")
    time_grain: str = Field(..., description="Aggregation grain (e.g. PT1H, P1D).")
    start_time: datetime = Field(..., description="Start of window.")
    end_time: datetime = Field(..., description="End of window.")
    series: list[MetricSeries] = Field(
        default_factory=list, description="Metric series collected."
    )


class TokenUsageRecord(BaseModel):
    """Canonical log of real GenAI token consumption and deterministic cost."""

    event_id: str = Field(..., description="Unique event identifier.")
    connection_id: str = Field(..., description="Associated connection ID.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the model inference event.",
    )
    model_name: str = Field(
        ..., description="Model identifier (e.g. gpt-4o, gpt-4o-mini)."
    )
    deployment_name: str | None = Field(
        default=None, description="Azure OpenAI deployment name."
    )
    prompt_tokens: int = Field(
        default=0, ge=0, description="Actual prompt tokens consumed."
    )
    completion_tokens: int = Field(
        default=0, ge=0, description="Actual completion tokens generated."
    )
    total_tokens: int = Field(
        default=0, ge=0, description="Sum of prompt and completion tokens."
    )
    latency_ms: int | None = Field(
        default=None, ge=0, description="Inference response duration in ms."
    )
    estimated_cost_usd: Decimal = Field(
        default=Decimal("0.0000"),
        description="Deterministic cost calculated via official provider unit rate.",
    )
    source: Literal["direct_inference_intercept", "azure_monitor_metric"] = Field(
        default="direct_inference_intercept",
        description="Source of the token telemetry.",
    )
    pricing_status: Literal["published_rate", "unknown_model_rate"] = Field(
        default="published_rate",
        description="Provenance of model rate pricing.",
    )


class TokenEconomicsSummary(BaseModel):
    """Aggregated token economics summary across models."""

    connection_id: str = Field(..., description="Target connection ID.")
    window_days: int = Field(default=30, description="Days covered in summary.")
    total_prompt_tokens: int = Field(default=0, ge=0)
    total_completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_cost_usd: Decimal = Field(default=Decimal("0.0000"))
    token_efficiency_ratio: float = Field(
        default=0.0, description="Ratio of completion tokens to prompt tokens."
    )
    models_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    daily_timeseries: list[dict[str, Any]] = Field(default_factory=list)


# --- UDF Function Argument Schemas ---


class ListConnectionsArgs(BaseModel):
    provider_filter: Literal["azure", "aws", "gcp"] | None = None


class CreateConnectionArgs(BaseModel):
    provider: Literal["azure", "aws", "gcp"] = "azure"
    name: str = Field(..., min_length=1, max_length=120)
    tenant_id: str = Field(..., min_length=1)
    subscription_id: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)


class ValidateConnectionArgs(BaseModel):
    connection_id: str | None = None
    provider: Literal["azure", "aws", "gcp"] = "azure"
    tenant_id: str | None = None
    subscription_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class GetInventoryArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    resource_type_filter: str | None = None


class GetWasteArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    force_refresh: bool = False


class GetMetricsArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    resource_id: str = Field(..., min_length=1)
    metric_names: list[str] = Field(default_factory=lambda: ["Percentage CPU"])
    time_grain: str = "PT1H"
    days: int = 7


class GetTokenEconomicsArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    days: int = 30


class RecordTokenArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    deployment_name: str | None = None
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    latency_ms: int | None = None


class PricingCalculationArgs(BaseModel):
    arm_sku_name: str = Field(..., min_length=1)
    region: str = "northcentralus"
    hours_per_month: Decimal = Decimal("730.0")

# --- SECTION: LAKEHOUSE STORE ---

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

# --- SECTION: AZURE REAL CLIENT ---

"""Azure Real Read-Only API Client.

Directly queries official Azure management endpoints:
1. Azure Resource Graph REST API (Resource discovery, inventory, state)
2. Azure Monitor Metrics REST API (CPU, Memory, Network, Disk IOPS)
3. Azure Retail Prices API (Public consumption rates for SKUs)

Security Guardrails:
- 100% read-only operations (strictly HTTP GET or Resource Graph POST queries).
- Zero resource creation, modification, or deletion against customer subscriptions.
- Never prints, logs, or returns bearer tokens or client secrets.
- Surfaces honest error states if credentials fail or are revoked.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
import shutil
import ssl
import subprocess
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)


def _sync_http_request(
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, Any]:
    """Execute synchronous HTTP request using standard library urllib."""
    target_url = url
    if params:
        query_string = urllib.parse.urlencode(params)
        sep = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{sep}{query_string}"

    req_headers = headers.copy() if headers else {}
    req_headers.setdefault("User-Agent", "FinOps-UDF-Client/1.0")

    body_bytes: bytes | None = None
    if json_body is not None:
        body_bytes = json.dumps(json_body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    elif data is not None:
        body_bytes = urllib.parse.urlencode(data).encode("utf-8")
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(
        target_url,
        data=body_bytes,
        headers=req_headers,
        method=method,
    )

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            resp_bytes = resp.read()
            raw_text = resp_bytes.decode("utf-8", errors="replace")
            status_code = resp.status
            try:
                return status_code, json.loads(raw_text)
            except Exception:
                return status_code, raw_text
    except urllib.error.HTTPError as http_err:
        raw_text = http_err.read().decode("utf-8", errors="replace")
        try:
            return http_err.code, json.loads(raw_text)
        except Exception:
            return http_err.code, raw_text
    except Exception as exc:
        logger.warning(f"HTTP request to {target_url} failed: {exc}")
        return 0, str(exc)


class AzureRealClient:
    """Client for authentic read-only interactions with Azure cloud services."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def get_access_token(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> tuple[str | None, str]:
        """Acquire an ARM bearer token via OAuth2 Client Credentials or host Azure CLI session.

        Returns (token, auth_method_description).
        """
        # 1. Service Principal OAuth2 Client Credentials
        if tenant_id and client_id and client_secret:
            token_url = (
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            )
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://management.azure.com/.default",
            }
            status, payload = await asyncio.to_thread(
                _sync_http_request,
                "POST",
                token_url,
                data=data,
                timeout=self.timeout,
            )
            if status == 200 and isinstance(payload, dict):
                token = payload.get("access_token")
                if token:
                    return token, "service_principal_oauth2"
            logger.warning(f"azure_real_sp_token_failed status_code={status}")
            # Explicit credentials were provided and rejected - do not mask with CLI fallback
            return None, "unauthenticated"

        # 2. Host Azure CLI session fallback (used only when no explicit SP secrets were provided)
        az_path = shutil.which("az") or shutil.which("az.cmd")
        if az_path:
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    [
                        az_path,
                        "account",
                        "get-access-token",
                        "--resource",
                        "https://management.azure.com/",
                        "--output",
                        "json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if proc.returncode == 0:
                    data_obj = json.loads(proc.stdout)
                    token = data_obj.get("accessToken") or data_obj.get("token")
                    if token:
                        return token, "azure_cli_session"
            except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
                logger.debug(f"azure_real_cli_token_attempt_failed error={exc}")

        return None, "unauthenticated"

    async def query_resource_graph(
        self, token: str, subscription_id: str, query: str | None = None
    ) -> list[DiscoveredResource]:
        """Execute a read-only KQL query against Azure Resource Graph for a subscription."""
        url = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2021-03-01"
        kql = query or (
            f"Resources | where subscriptionId =~ '{subscription_id}' "
            "| project id, name, type, resourceGroup, location, sku, tags, properties"
        )
        payload = {
            "subscriptions": [subscription_id],
            "query": kql,
            "options": {"resultFormat": "objectArray"},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "POST",
            url,
            json_body=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200:
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"Azure Resource Graph query failed (status {status}): {err_msg}"
            )

        rows: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
        resources: list[DiscoveredResource] = []

        for row in rows:
            sku_obj = row.get("sku")
            sku_name = (
                sku_obj.get("name")
                if isinstance(sku_obj, dict)
                else (sku_obj or None)
            )
            props = row.get("properties") or {}
            power_state = None
            if isinstance(props, dict):
                power_state = (
                    props.get("extended", {})
                    .get("instanceView", {})
                    .get("powerState", {})
                    .get("code")
                    or props.get("diskState")
                    or props.get("provisioningState")
                )

            raw_tags = row.get("tags") or {}
            tags = (
                {str(k): str(v) for k, v in raw_tags.items()}
                if isinstance(raw_tags, dict)
                else {}
            )

            resources.append(
                DiscoveredResource(
                    resource_id=row["id"],
                    name=row.get("name", row["id"].split("/")[-1]),
                    resource_type=row.get("type", "Unknown"),
                    resource_group=row.get("resourceGroup"),
                    location=row.get("location", "unknown"),
                    sku_name=sku_name,
                    tags=tags,
                    power_state=power_state,
                )
            )

        return resources

    async def query_monitor_metrics(
        self,
        token: str,
        resource_id: str,
        metric_names: list[str],
        time_grain: str = "PT1H",
        days: int = 7,
    ) -> ResourceMetricsResponse:
        """Query Azure Monitor metrics for a specific ARM resource."""
        clean_id = resource_id.lstrip("/")
        url = f"https://management.azure.com/{clean_id}/providers/Microsoft.Insights/metrics"

        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)
        timespan = f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"

        params = {
            "api-version": "2018-01-01",
            "metricnames": ",".join(metric_names),
            "interval": time_grain,
            "aggregation": "Average,Maximum,Minimum",
            "timespan": timespan,
        }
        headers = {"Authorization": f"Bearer {token}"}

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200 or not isinstance(data, dict):
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"Azure Monitor metrics query failed (status {status}): {err_msg}"
            )

        series_list: list[MetricSeries] = []
        start_str = data.get("timespan", "").split("/")[0]
        end_str = (
            data.get("timespan", "").split("/")[-1]
            if "/" in data.get("timespan", "")
            else ""
        )

        for value_obj in data.get("value", []):
            metric_name = value_obj.get("name", {}).get("value", "UnknownMetric")
            unit = value_obj.get("unit", "Count")
            points: list[MetricPoint] = []

            for ts in value_obj.get("timeseries", []):
                for d in ts.get("data", []):
                    if "timeStamp" in d:
                        points.append(
                            MetricPoint(
                                timestamp=d["timeStamp"],
                                average=d.get("average"),
                                maximum=d.get("maximum"),
                                minimum=d.get("minimum"),
                            )
                        )

            series_list.append(
                MetricSeries(metric_name=metric_name, unit=unit, points=points)
            )

        return ResourceMetricsResponse(
            resource_id=resource_id,
            time_grain=time_grain,
            start_time=start_str or "2026-01-01T00:00:00Z",
            end_time=end_str or "2026-01-01T00:00:00Z",
            series=series_list,
        )

    async def fetch_retail_price(
        self, arm_sku_name: str, region: str = "northcentralus"
    ) -> Decimal | None:
        """Fetch consumption hourly rate from public Azure Retail Prices API."""
        url = "https://prices.azure.com/api/retail/prices"
        filter_expr = f"armSkuName eq '{arm_sku_name}' and armRegionName eq '{region}' and priceType eq 'Consumption'"
        params = {"$filter": filter_expr}

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            url,
            params=params,
            timeout=10.0,
        )

        if status == 200 and isinstance(data, dict):
            items = data.get("Items", [])
            if items:
                for item in items:
                    if not item.get("isPrimaryMeterRegion") and len(items) > 1:
                        continue
                    unit_price = item.get("unitPrice")
                    if unit_price is not None:
                        return Decimal(str(unit_price))

        return None

    async def validate_arm_connection(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        subscription_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate live credentials and RBAC roles against Azure Resource Manager and Cost Management."""
        token, auth_method = await self.get_access_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

        if not token:
            return {
                "valid": False,
                "error_code": "AUTHENTICATION_FAILED",
                "error_message": (
                    "Could not acquire Azure Resource Manager token. "
                    "Verify Tenant ID, Client ID, and Client Secret."
                ),
                "auth_method": auth_method,
            }

        result: dict[str, Any] = {
            "valid": True,
            "auth_method": auth_method,
            "provider": "azure",
            "scope_id": subscription_id,
            "roles": {
                "reader": False,
                "cost_management_reader": False,
                "resource_graph": False,
            },
            "subscription_name": None,
            "subscription_state": None,
            "resource_groups_count": 0,
            "discovered_resources_count": 0,
            "message": "Connection authenticated successfully.",
        }

        if not subscription_id:
            return result

        # 1. Probe Subscription Metadata (Reader Role)
        sub_url = f"https://management.azure.com/subscriptions/{subscription_id}?api-version=2022-12-01"
        sub_status, sub_data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            sub_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )

        if sub_status == 200 and isinstance(sub_data, dict):
            result["roles"]["reader"] = True
            result["subscription_name"] = sub_data.get("displayName")
            result["subscription_state"] = sub_data.get("state")
            result["message"] = (
                f"Verified Reader access on subscription '{result['subscription_name']}' "
                f"({result['subscription_state']})."
            )
        elif sub_status in (401, 403):
            result["valid"] = False
            result["error_code"] = "AUTHORIZATION_FAILED"
            result["error_message"] = (
                f"Authorization failed on subscription '{subscription_id}'. "
                "Ensure the Service Principal has the 'Reader' role assigned."
            )
            return result
        elif sub_status == 404:
            result["valid"] = False
            result["error_code"] = "SUBSCRIPTION_NOT_FOUND"
            result["error_message"] = (
                f"Subscription '{subscription_id}' was not found in tenant."
            )
            return result
        else:
            err_str = sub_data if isinstance(sub_data, str) else json.dumps(sub_data)
            logger.warning(f"Subscription probe returned HTTP {sub_status}: {err_str}")
            result["valid"] = False
            result["error_code"] = "INVALID_SUBSCRIPTION"
            result["error_message"] = (
                f"Subscription '{subscription_id}' probe failed (HTTP {sub_status}): {err_str}"
            )
            return result

        # 2. Probe Resource Groups
        rg_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups?api-version=2021-04-01"
        rg_status, rg_data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            rg_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if rg_status == 200 and isinstance(rg_data, dict):
            rgs = rg_data.get("value", [])
            result["resource_groups_count"] = len(rgs)

        # 3. Probe Azure Resource Graph
        try:
            resources = await self.query_resource_graph(token, subscription_id)
            result["roles"]["resource_graph"] = True
            result["discovered_resources_count"] = len(resources)
        except Exception as exc:
            logger.debug(f"Resource graph probe failed: {exc}")

        # 4. Probe Azure Cost Management
        cm_url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            "/providers/Microsoft.CostManagement/query?api-version=2021-10-01"
        )
        cm_payload = {
            "type": "ActualCost",
            "timeframe": "MonthToDate",
            "dataset": {
                "granularity": "None",
                "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            },
        }
        cm_status, _ = await asyncio.to_thread(
            _sync_http_request,
            "POST",
            cm_url,
            json_body=cm_payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if cm_status == 200:
            result["roles"]["cost_management_reader"] = True
        else:
            logger.debug(f"Cost Management probe returned HTTP {cm_status}")

        return result

    async def query_cost_management(
        self,
        token: str,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict[str, Any]:
        """Query Azure Cost Management for aggregated actual expenditure by service and resource group."""
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            "/providers/Microsoft.CostManagement/query?api-version=2021-10-01"
        )
        payload = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": {
                "granularity": "None",
                "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"},
                },
                "grouping": [
                    {"type": "Dimension", "name": "ServiceName"},
                    {"type": "Dimension", "name": "ResourceGroupName"},
                ],
            },
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "POST",
            url,
            json_body=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200 or not isinstance(data, dict):
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"Azure Cost Management query failed (status {status}): {err_msg}"
            )

        rows = data.get("properties", {}).get("rows", [])
        columns = [
            c.get("name") for c in data.get("properties", {}).get("columns", [])
        ]

        service_breakdown: dict[str, float] = {}
        rg_breakdown: dict[str, float] = {}
        total_usd = Decimal("0.00")
        currency = "USD"

        for row in rows:
            row_dict = dict(zip(columns, row))
            cost_val = Decimal(str(row_dict.get("Cost", 0)))
            total_usd += cost_val
            srv = str(row_dict.get("ServiceName", "Other"))
            rg = str(row_dict.get("ResourceGroupName", "Unassigned"))
            if "Currency" in row_dict:
                currency = str(row_dict["Currency"])

            service_breakdown[srv] = round(
                service_breakdown.get(srv, 0.0) + float(cost_val), 2
            )
            rg_breakdown[rg] = round(
                rg_breakdown.get(rg, 0.0) + float(cost_val), 2
            )

        return {
            "timeframe": timeframe,
            "total_cost": float(total_usd),
            "currency": currency,
            "service_breakdown": service_breakdown,
            "resource_group_breakdown": rg_breakdown,
            "row_count": len(rows),
        }

    async def query_arm_resources_direct(
        self, token: str, subscription_id: str
    ) -> list[DiscoveredResource]:
        """Direct ARM resource enumeration fallback if Resource Graph is unavailable."""
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            "/resources?api-version=2021-04-01"
        )
        headers = {"Authorization": f"Bearer {token}"}

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            url,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200 or not isinstance(data, dict):
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"ARM direct resources query failed (status {status}): {err_msg}"
            )

        items = data.get("value", [])
        resources: list[DiscoveredResource] = []
        for item in items:
            raw_tags = item.get("tags") or {}
            tags = (
                {str(k): str(v) for k, v in raw_tags.items()}
                if isinstance(raw_tags, dict)
                else {}
            )
            sku_obj = item.get("sku")
            sku_name = (
                sku_obj.get("name")
                if isinstance(sku_obj, dict)
                else (sku_obj or None)
            )

            res_id = item.get("id", "")
            rg_name = None
            if "/resourcegroups/" in res_id.lower():
                parts = res_id.split("/")
                for i, p in enumerate(parts):
                    if p.lower() == "resourcegroups" and i + 1 < len(parts):
                        rg_name = parts[i + 1]
                        break

            resources.append(
                DiscoveredResource(
                    resource_id=res_id,
                    name=item.get("name", res_id.split("/")[-1]),
                    resource_type=item.get("type", "Unknown"),
                    resource_group=rg_name,
                    location=item.get("location", "unknown"),
                    sku_name=sku_name,
                    tags=tags,
                )
            )
        return resources

# --- SECTION: WASTE DETECTOR ---

"""Pure deterministic FinOps cloud waste detection algorithms.

Evaluates discovered resources and live telemetry:
- Unattached managed disks (no attached VM / managedBy is null)
- Idle virtual machines (power_state=running, but 7-day max CPU < 5%)
- Unassociated Public IP addresses
- Oversized compute instances with rightsizing candidates

Strict Real-Data Policy:
Returns strictly real detected items or an empty list with count 0.
Never injects synthetic or hardcoded placeholder items.
"""

from decimal import Decimal



class FinOpsWasteDetector:
    """Deterministic analyzer identifying cloud waste across discovered resources."""

    def analyze_waste(
        self,
        connection_id: str,
        resources: list[DiscoveredResource],
        vm_cpu_metrics: dict[str, float] | None = None,
    ) -> WasteSummary:
        """Analyze a list of discovered resources and metrics to generate a WasteSummary."""
        items: list[WasteItem] = []
        metrics = vm_cpu_metrics or {}

        for res in resources:
            r_type = res.resource_type.lower()

            # 1. Detect Unattached Managed Disks
            if "microsoft.compute/disks" in r_type:
                # Check tags or power_state (used as diskState representation)
                state = (res.power_state or res.tags.get("diskState") or "").lower()
                is_unattached = (
                    state == "unattached"
                    or res.tags.get("managedBy") in (None, "", "null")
                    and state != "attached"
                )
                if is_unattached:
                    cost = res.monthly_cost_usd
                    cost_status = "verified_rate" if cost is not None else "pricing_unavailable"
                    cost_val = cost if cost is not None else Decimal("0.00")
                    items.append(
                        WasteItem(
                            resource_id=res.resource_id,
                            name=res.name,
                            resource_type="Disk",
                            waste_category="unattached_disk",
                            evidence="Disk state is Unattached (no compute instance attached).",
                            current_sku=res.sku_name or "Standard_SSD",
                            monthly_cost_leakage_usd=cost_val,
                            projected_monthly_savings_usd=cost_val,
                            cost_status=cost_status,
                        )
                    )

            # 2. Detect Idle Virtual Machines
            elif "microsoft.compute/virtualmachines" in r_type:
                # Only running VMs can generate idle compute waste
                is_running = (res.power_state or "").lower() in (
                    "running",
                    "powerstate/running",
                )
                if is_running:
                    # Check CPU telemetry if available
                    max_cpu = metrics.get(res.resource_id)
                    if max_cpu is not None and max_cpu < 5.0:
                        vm_cost = res.monthly_cost_usd
                        cost_status = "verified_rate" if vm_cost is not None else "pricing_unavailable"
                        cost_val = vm_cost if vm_cost is not None else Decimal("0.00")
                        items.append(
                            WasteItem(
                                resource_id=res.resource_id,
                                name=res.name,
                                resource_type="VirtualMachine",
                                waste_category="idle_compute",
                                evidence=f"7-day maximum CPU utilization was {max_cpu:.1f}% (threshold < 5.0%).",
                                current_sku=res.sku_name or "Standard_D2s_v5",
                                monthly_cost_leakage_usd=cost_val,
                                projected_monthly_savings_usd=cost_val,
                                cost_status=cost_status,
                            )
                        )

            # 3. Detect Unassociated Public IPs
            elif "microsoft.network/publicipaddresses" in r_type:
                state = (
                    res.power_state or res.tags.get("ipConfiguration") or ""
                ).lower()
                is_unassociated = (
                    state in ("unassociated", "", "none")
                    or "ipconfiguration" not in res.tags
                )
                if is_unassociated:
                    ip_cost = res.monthly_cost_usd
                    cost_status = "verified_rate" if ip_cost is not None else "pricing_unavailable"
                    cost_val = ip_cost if ip_cost is not None else Decimal("0.00")
                    items.append(
                        WasteItem(
                            resource_id=res.resource_id,
                            name=res.name,
                            resource_type="PublicIP",
                            waste_category="unassociated_ip",
                            evidence="Public IP is not associated with any Network Interface (NIC) or Load Balancer.",
                            current_sku=res.sku_name or "Standard_IPv4",
                            monthly_cost_leakage_usd=cost_val,
                            projected_monthly_savings_usd=cost_val,
                            cost_status=cost_status,
                        )
                    )

        # Compute totals
        total_monthly = sum(
            (item.monthly_cost_leakage_usd for item in items), Decimal("0.00")
        )
        total_annual = total_monthly * Decimal("12.0")

        category_counts: dict[str, int] = {}
        for item in items:
            category_counts[item.waste_category] = (
                category_counts.get(item.waste_category, 0) + 1
            )

        return WasteSummary(
            connection_id=connection_id,
            total_monthly_waste_usd=total_monthly,
            total_annual_waste_usd=total_annual,
            waste_count_by_category=category_counts,
            items=items,
        )

# --- SECTION: TOKEN TELEMETRY SERVICE ---

"""Real GenAI Token Telemetry & FinOps Economics Ingestion Engine.

Calculates deterministic unit economics for LLM calls based on official published rates:
- Ingests actual `usage` metadata from completions (Azure OpenAI, Azure AI Foundry, etc.)
- Calculates precise monetary cost ($/1k tokens) without generative estimation
- Aggregates genuine historical consumption without synthetic curve generation
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any



# Official published rates per 1,000,000 tokens (USD)
# Source: Azure OpenAI Retail Prices / OpenAI Official Pricing Catalog
MODEL_RATES_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # model: (prompt_rate_per_1M, completion_rate_per_1M)
    "gpt-4o": (Decimal("2.5000"), Decimal("10.0000")),
    "gpt-4o-mini": (Decimal("0.1500"), Decimal("0.6000")),
    "gpt-4-turbo": (Decimal("10.0000"), Decimal("30.0000")),
    "gpt-4": (Decimal("30.0000"), Decimal("60.0000")),
    "gpt-35-turbo": (Decimal("0.5000"), Decimal("1.5000")),
    "text-embedding-3-small": (Decimal("0.0200"), Decimal("0.0200")),
    "text-embedding-3-large": (Decimal("0.1300"), Decimal("0.1300")),
}

MILLION = Decimal(1000000)


def get_model_rates(model_name: str) -> tuple[tuple[Decimal, Decimal] | None, str]:
    """Retrieve published rates for a model or return None and 'unknown_model_rate'."""
    normalized_name = model_name.lower().strip()
    for known_model, rates in sorted(
        MODEL_RATES_PER_MILLION.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if known_model in normalized_name:
            return rates, "published_rate"
    return None, "unknown_model_rate"


def compute_token_cost(
    model_name: str, prompt_tokens: int, completion_tokens: int
) -> tuple[Decimal, str]:
    """Deterministically compute USD cost for prompt and completion tokens.

    If model rate is unknown, returns (Decimal('0.0000'), 'unknown_model_rate').
    Never uses synthetic or guessed rates.
    """
    rates, pricing_status = get_model_rates(model_name)
    if rates is None:
        return Decimal("0.0000"), pricing_status

    rate_prompt, rate_comp = rates
    cost_prompt = (Decimal(prompt_tokens) * rate_prompt) / MILLION
    cost_comp = (Decimal(completion_tokens) * rate_comp) / MILLION
    total_cost = (cost_prompt + cost_comp).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return total_cost, pricing_status


class TokenTelemetryService:
    """Service managing real GenAI token consumption telemetry and economics."""

    def __init__(self, store: FabricLakehouseStore) -> None:
        self.store = store

    def record_usage(
        self,
        connection_id: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        deployment_name: str | None = None,
        latency_ms: int | None = None,
    ) -> TokenUsageRecord:
        """Record real model invocation telemetry into Lakehouse persistence."""
        cost, pricing_status = compute_token_cost(
            model_name, prompt_tokens, completion_tokens
        )
        record = TokenUsageRecord(
            event_id=f"evt-{uuid.uuid4()}",
            connection_id=connection_id,
            timestamp=datetime.now(UTC),
            model_name=model_name,
            deployment_name=deployment_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=cost,
            source="direct_inference_intercept",
            pricing_status=pricing_status,  # type: ignore[arg-type]
        )
        self.store.append_token_telemetry(record)
        return record

    def get_summary(self, connection_id: str, days: int = 30) -> TokenEconomicsSummary:
        """Aggregate actual telemetry records over the window into a TokenEconomicsSummary."""
        records = self.store.get_token_telemetry(connection_id=connection_id, days=days)
        cutoff = datetime.now(UTC) - timedelta(days=days)
        filtered_records = [r for r in records if r.timestamp >= cutoff]

        total_prompt = sum(r.prompt_tokens for r in filtered_records)
        total_completion = sum(r.completion_tokens for r in filtered_records)
        total_tokens = sum(r.total_tokens for r in filtered_records)
        total_cost = sum(
            (r.estimated_cost_usd for r in filtered_records), Decimal("0.0000")
        )

        efficiency_ratio = (
            round(total_completion / total_prompt, 3) if total_prompt > 0 else 0.0
        )

        # Breakdown by Model
        model_map: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": Decimal("0.0000"),
                "invocations": 0,
            }
        )
        # Breakdown by Day
        daily_map: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "promptTokens": 0,
                "completionTokens": 0,
                "totalTokens": 0,
                "costUsd": Decimal("0.00"),
                "requests": 0,
            }
        )

        for r in filtered_records:
            # Model stats
            m = model_map[r.model_name]
            m["prompt_tokens"] += r.prompt_tokens
            m["completion_tokens"] += r.completion_tokens
            m["total_tokens"] += r.total_tokens
            m["cost_usd"] += r.estimated_cost_usd
            m["invocations"] += 1

            # Day stats
            day_str = r.timestamp.strftime("%Y-%m-%d")
            d = daily_map[day_str]
            d["promptTokens"] += r.prompt_tokens
            d["completionTokens"] += r.completion_tokens
            d["totalTokens"] += r.total_tokens
            d["costUsd"] += r.estimated_cost_usd
            d["requests"] += 1

        models_list = [
            {
                "model_name": k,
                "prompt_tokens": v["prompt_tokens"],
                "completion_tokens": v["completion_tokens"],
                "total_tokens": v["total_tokens"],
                "cost_usd": float(v["cost_usd"]),
                "invocations": v["invocations"],
            }
            for k, v in model_map.items()
        ]

        timeseries_list = [
            {
                "timestamp": k,
                "promptTokens": v["promptTokens"],
                "completionTokens": v["completionTokens"],
                "totalTokens": v["totalTokens"],
                "costUsd": float(v["costUsd"]),
                "requests": v["requests"],
            }
            for k, v in sorted(daily_map.items(), key=lambda x: x[0])
        ]

        return TokenEconomicsSummary(
            connection_id=connection_id,
            window_days=days,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            token_efficiency_ratio=efficiency_ratio,
            models_breakdown=models_list,
            daily_timeseries=timeseries_list,
        )

# --- SECTION: CONNECTION HANDLERS ---

"""Connection management RPC handlers for Microsoft Fabric UDF."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError


async def handle_list_connections(
    store: FabricLakehouseStore,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """List all registered cloud connections from Lakehouse persistent store."""
    parsed = ListConnectionsArgs(**(args or {}))
    connections = store.list_connections(provider_filter=parsed.provider_filter)
    resp = UdfResponse(
        status="success",
        data=[c.model_dump(mode="json") for c in connections],
    )
    return resp.model_dump(mode="json")


async def handle_create_connection(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Register and validate a new cloud provider connection with real server-side verification."""
    try:
        parsed = CreateConnectionArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    if parsed.provider != "azure":
        return UdfResponse(
            status="error",
            error_code="PROVIDER_NOT_SUPPORTED",
            error_message=f"Provider '{parsed.provider}' is deferred for this Fabric POC. Please select Azure.",
        ).model_dump(mode="json")

    # Real authentication and RBAC validation check
    val_result = await azure_client.validate_arm_connection(
        tenant_id=parsed.tenant_id,
        client_id=parsed.client_id,
        client_secret=parsed.client_secret,
        subscription_id=parsed.subscription_id,
    )

    if not val_result.get("valid"):
        return UdfResponse(
            status="error",
            error_code=val_result.get("error_code", "AUTHENTICATION_FAILED"),
            error_message=val_result.get("error_message", (
                f"Failed to authenticate against Microsoft Entra tenant {parsed.tenant_id}. "
                "Verify Client ID, Client Secret, and required role assignments (Reader, Cost Management Reader)."
            )),
        ).model_dump(mode="json")

    conn_id = f"{parsed.provider}-{parsed.subscription_id[:8]}-{uuid.uuid4().hex[:4]}"
    display_name = parsed.name
    if not display_name or display_name.strip() == "":
        display_name = val_result.get("subscription_name") or f"Azure Subscription {parsed.subscription_id[:8]}"

    verified_caps = ["inventory", "waste_detection", "metrics", "token_economics"]
    if val_result.get("roles", {}).get("cost_management_reader"):
        verified_caps.append("cost_management")

    connection = CloudConnection(
        id=conn_id,
        name=display_name,
        provider=parsed.provider,
        scope_id=parsed.subscription_id,
        tenant_or_org_id=parsed.tenant_id,
        client_id=parsed.client_id,
        auth_method=val_result.get("auth_method", "service_principal"),
        status="connected",
        last_verified_at=datetime.now(UTC),
        is_live=True,
        capabilities=verified_caps,
    )

    store.save_connection(connection, secret=parsed.client_secret)
    return UdfResponse(
        status="success",
        data=connection.model_dump(mode="json"),
    ).model_dump(mode="json")


async def handle_validate_connection(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Test connectivity and permissions for an existing or newly submitted connection."""
    try:
        parsed = ValidateConnectionArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    if parsed.provider != "azure":
        return UdfResponse(
            status="error",
            error_code="PROVIDER_NOT_SUPPORTED",
            error_message=f"Provider '{parsed.provider}' is deferred for this Fabric POC. Please select Azure.",
        ).model_dump(mode="json")

    tenant_id = parsed.tenant_id
    sub_id = parsed.subscription_id
    secret = parsed.client_secret
    client_id = parsed.client_id

    if parsed.connection_id:
        existing = store.get_connection(parsed.connection_id)
        if not existing:
            return UdfResponse(
                status="error",
                error_code="CONNECTION_NOT_FOUND",
                error_message=f"Connection '{parsed.connection_id}' does not exist.",
            ).model_dump(mode="json")
        tenant_id = tenant_id or existing.tenant_or_org_id
        sub_id = sub_id or existing.scope_id
        client_id = client_id or existing.client_id
        secret = secret or store.get_connection_secret(parsed.connection_id)

    val_result = await azure_client.validate_arm_connection(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=secret,
        subscription_id=sub_id,
    )

    if not val_result.get("valid"):
        return UdfResponse(
            status="error",
            error_code=val_result.get("error_code", "AUTHENTICATION_FAILED"),
            error_message=val_result.get(
                "error_message",
                "Authentication check failed. Could not acquire Azure Resource Manager token.",
            ),
        ).model_dump(mode="json")

    return UdfResponse(
        status="success",
        data=val_result,
    ).model_dump(mode="json")


async def handle_delete_connection(
    store: FabricLakehouseStore,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Delete a connection and cascading records from Lakehouse storage."""
    conn_id = args.get("connection_id")
    if not conn_id:
        return UdfResponse(
            status="error",
            error_code="MISSING_CONNECTION_ID",
            error_message="connection_id parameter is required.",
        ).model_dump(mode="json")

    deleted = store.delete_connection(conn_id)
    if not deleted:
        return UdfResponse(
            status="error",
            error_code="CONNECTION_NOT_FOUND",
            error_message=f"Connection '{conn_id}' was not found.",
        ).model_dump(mode="json")

    return UdfResponse(
        status="success",
        data={"deleted": True, "connection_id": conn_id},
    ).model_dump(mode="json")

# --- SECTION: INVENTORY HANDLERS ---

"""Inventory discovery RPC handlers for Microsoft Fabric UDF."""

from typing import Any
import urllib.error

from pydantic import ValidationError


async def handle_get_inventory(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve discovered resources for a connection from live Azure Resource Graph or Lakehouse snapshot."""
    try:
        parsed = GetInventoryArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    conn = store.get_connection(parsed.connection_id)
    if not conn:
        return UdfResponse(
            status="error",
            error_code="CONNECTION_NOT_FOUND",
            error_message=f"Connection '{parsed.connection_id}' not found.",
        ).model_dump(mode="json")

    secret = store.get_connection_secret(parsed.connection_id)
    token, _ = await azure_client.get_access_token(
        tenant_id=conn.tenant_or_org_id,
        client_id=conn.client_id,
        client_secret=secret,
    )

    resources: list[DiscoveredResource] = []
    if token:
        try:
            resources = await azure_client.query_resource_graph(
                token=token,
                subscription_id=conn.scope_id,
            )
            # Persist live snapshot in Lakehouse
            store.save_inventory(parsed.connection_id, resources)
        except (RuntimeError, urllib.error.URLError, OSError) as arg_exc:
            # Fall back to direct ARM resources list API
            try:
                resources = await azure_client.query_arm_resources_direct(
                    token=token,
                    subscription_id=conn.scope_id,
                )
                store.save_inventory(parsed.connection_id, resources)
            except Exception:
                # Fall back to persisted Lakehouse snapshot if live ARM/ARG calls failed
                resources = store.get_inventory(
                    parsed.connection_id,
                    resource_type_filter=parsed.resource_type_filter,
                )
                if not resources:
                    return UdfResponse(
                        status="error",
                        error_code="LIVE_QUERY_FAILED",
                        error_message=f"Failed to query Azure Resource Graph/ARM and no snapshot exists: {arg_exc}",
                    ).model_dump(mode="json")
    else:
        # Load persisted Lakehouse snapshot
        resources = store.get_inventory(
            parsed.connection_id,
            resource_type_filter=parsed.resource_type_filter,
        )
        if not resources:
            return UdfResponse(
                status="error",
                error_code="UNAUTHENTICATED",
                error_message="Could not authenticate with Azure and no persisted inventory exists.",
            ).model_dump(mode="json")

    if parsed.resource_type_filter:
        resources = [
            r
            for r in resources
            if parsed.resource_type_filter.lower() in r.resource_type.lower()
        ]

    return UdfResponse(
        status="success",
        data=[r.model_dump(mode="json") for r in resources],
    ).model_dump(mode="json")

# --- SECTION: PRICING HANDLERS ---

"""Deterministic pricing calculation RPC handlers for Microsoft Fabric UDF."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import ValidationError


async def handle_calculate_pricing(
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Deterministically calculate monthly cost using live official Azure Retail Prices API."""
    try:
        parsed = PricingCalculationArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    hourly_rate = await azure_client.fetch_retail_price(
        arm_sku_name=parsed.arm_sku_name,
        region=parsed.region,
    )

    if hourly_rate is None:
        return UdfResponse(
            status="error",
            error_code="SKU_NOT_FOUND",
            error_message=(
                f"SKU '{parsed.arm_sku_name}' in region '{parsed.region}' not found in "
                "Azure Retail Prices API catalog."
            ),
        ).model_dump(mode="json")

    monthly_cost = (hourly_rate * parsed.hours_per_month).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return UdfResponse(
        status="success",
        data={
            "arm_sku_name": parsed.arm_sku_name,
            "region": parsed.region,
            "hourly_rate_usd": float(hourly_rate),
            "monthly_cost_usd": float(monthly_cost),
            "annual_cost_usd": float(monthly_cost * Decimal("12.0")),
            "currency": "USD",
            "source": "Azure Retail Prices API (Public Consumption Tier)",
        },
    ).model_dump(mode="json")

# --- SECTION: TELEMETRY HANDLERS ---

"""Azure Monitor telemetry RPC handlers for Microsoft Fabric UDF."""

from typing import Any
import urllib.error

from pydantic import ValidationError


async def handle_get_metrics(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve actual Azure Monitor metrics for a specific ARM resource."""
    try:
        parsed = GetMetricsArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    conn = store.get_connection(parsed.connection_id)
    if not conn:
        return UdfResponse(
            status="error",
            error_code="CONNECTION_NOT_FOUND",
            error_message=f"Connection '{parsed.connection_id}' not found.",
        ).model_dump(mode="json")

    secret = store.get_connection_secret(parsed.connection_id)
    token, _ = await azure_client.get_access_token(
        tenant_id=conn.tenant_or_org_id,
        client_id=conn.client_id,
        client_secret=secret,
    )

    if not token:
        return UdfResponse(
            status="error",
            error_code="UNAUTHENTICATED",
            error_message="Azure credentials unavailable or expired to query Azure Monitor.",
        ).model_dump(mode="json")

    try:
        metrics_resp = await azure_client.query_monitor_metrics(
            token=token,
            resource_id=parsed.resource_id,
            metric_names=parsed.metric_names,
            time_grain=parsed.time_grain,
            days=parsed.days,
        )
        return UdfResponse(
            status="success",
            data=metrics_resp.model_dump(mode="json"),
        ).model_dump(mode="json")
    except (RuntimeError, urllib.error.URLError, OSError) as exc:
        return UdfResponse(
            status="error",
            error_code="METRICS_QUERY_FAILED",
            error_message=f"Azure Monitor metrics query failed: {exc}",
        ).model_dump(mode="json")

# --- SECTION: TOKEN HANDLERS ---

"""Token Economics and AI FinOps RPC handlers for Microsoft Fabric UDF."""

from typing import Any

from pydantic import ValidationError


async def handle_get_token_economics(
    token_service: TokenTelemetryService,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve aggregated real token consumption and unit economics for a connection."""
    try:
        parsed = GetTokenEconomicsArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    summary = token_service.get_summary(
        connection_id=parsed.connection_id,
        days=parsed.days,
    )
    return UdfResponse(
        status="success",
        data=summary.model_dump(mode="json"),
    ).model_dump(mode="json")


async def handle_record_token_usage(
    token_service: TokenTelemetryService,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Record an authentic model inference event with actual token counts."""
    try:
        parsed = RecordTokenArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    record = token_service.record_usage(
        connection_id=parsed.connection_id,
        model_name=parsed.model_name,
        prompt_tokens=parsed.prompt_tokens,
        completion_tokens=parsed.completion_tokens,
        deployment_name=parsed.deployment_name,
        latency_ms=parsed.latency_ms,
    )
    return UdfResponse(
        status="success",
        data=record.model_dump(mode="json"),
    ).model_dump(mode="json")

# --- SECTION: WASTE HANDLERS ---

"""FinOps cost waste analysis RPC handlers for Microsoft Fabric UDF."""

import logging
import urllib.error
from typing import Any

from pydantic import ValidationError

logger = logging.getLogger(__name__)


async def handle_get_waste(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    waste_detector: FinOpsWasteDetector,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Execute deterministic FinOps waste detection on actual discovered resources."""
    try:
        parsed = GetWasteArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    conn = store.get_connection(parsed.connection_id)
    if not conn:
        return UdfResponse(
            status="error",
            error_code="CONNECTION_NOT_FOUND",
            error_message=f"Connection '{parsed.connection_id}' not found.",
        ).model_dump(mode="json")

    # Fetch resources
    resources = store.get_inventory(parsed.connection_id)
    secret = store.get_connection_secret(parsed.connection_id)
    token, _ = await azure_client.get_access_token(
        tenant_id=conn.tenant_or_org_id,
        client_id=conn.client_id,
        client_secret=secret,
    )

    if (parsed.force_refresh or not resources) and token:
        try:
            resources = await azure_client.query_resource_graph(
                token=token,
                subscription_id=conn.scope_id,
            )
            store.save_inventory(parsed.connection_id, resources)
        except (RuntimeError, urllib.error.URLError, OSError) as exc:
            logger.debug(f"live_arg_waste_query_failed: {exc}")

    if not resources:
        # Return empty waste summary with honest zero counts
        empty_summary = WasteSummary(connection_id=parsed.connection_id)
        return UdfResponse(
            status="success",
            data=empty_summary.model_dump(mode="json"),
        ).model_dump(mode="json")

    # Collect CPU metrics for running VMs if token is available
    vm_cpu_metrics: dict[str, float] = {}
    if token:
        running_vms = [
            r
            for r in resources
            if "microsoft.compute/virtualmachines" in r.resource_type.lower()
            and (r.power_state or "").lower() in ("running", "powerstate/running")
        ]
        for vm in running_vms[:10]:  # Limit to 10 for latency bounds
            try:
                metrics_resp = await azure_client.query_monitor_metrics(
                    token=token,
                    resource_id=vm.resource_id,
                    metric_names=["Percentage CPU"],
                    time_grain="PT1H",
                    days=7,
                )
                # Find max CPU across series
                for s in metrics_resp.series:
                    max_val = max(
                        (p.maximum for p in s.points if p.maximum is not None),
                        default=None,
                    )
                    if max_val is not None:
                        vm_cpu_metrics[vm.resource_id] = float(max_val)
            except (RuntimeError, urllib.error.URLError, OSError) as exc:
                logger.debug(
                    f"vm_cpu_metric_query_failed vm_id={vm.resource_id} error={exc}"
                )

    summary = waste_detector.analyze_waste(
        connection_id=parsed.connection_id,
        resources=resources,
        vm_cpu_metrics=vm_cpu_metrics,
    )

    return UdfResponse(
        status="success",
        data=summary.model_dump(mode="json"),
    ).model_dump(mode="json")


# ==============================================================================
# LAZY SINGLETON SERVICE ACCESSORS
# ==============================================================================
_store = None
_azure_client = None
_waste_detector = None
_token_service = None


def get_store() -> FabricLakehouseStore:
    global _store
    if _store is None:
        _store = FabricLakehouseStore()
    return _store


def get_azure_client() -> AzureRealClient:
    global _azure_client
    if _azure_client is None:
        _azure_client = AzureRealClient()
    return _azure_client


def get_waste_detector() -> FinOpsWasteDetector:
    global _waste_detector
    if _waste_detector is None:
        _waste_detector = FinOpsWasteDetector()
    return _waste_detector


def get_token_service() -> TokenTelemetryService:
    global _token_service
    if _token_service is None:
        _token_service = TokenTelemetryService(store=get_store())
    return _token_service


# ==============================================================================
# REGISTERED FABRIC UDF RPC FUNCTIONS (Compliant with Fabric Python Engine Rules)
# Enforced rules:
# 1. Parameter names must be camelCase (zero underscores).
# 2. Parameter types must be primitive: str, int, float, bool.
# 3. No complex union types (no | None).
# 4. No **kwargs in function signature (Fabric runtime parameter binder rejects kwargs).
# 5. Functions return dict.
# 6. Synchronous def functions executing async coroutines via run_sync().
# ==============================================================================

@udf.function()
def hello_fabric(name: str = "FinOps") -> dict:
    """Health check ping for Fabric UDF runtime verification."""
    return {
        "status": "success",
        "message": f"Hello, {name}! Microsoft Fabric FinOps UDF backend is live.",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@udf.function()
def list_connections(providerFilter: str = "") -> dict:
    """List registered cloud connections with safe metadata."""
    args = {"provider_filter": providerFilter} if providerFilter else {}
    return run_sync(handle_list_connections(get_store(), args))


@udf.function()
def create_connection(
    name: str = "",
    tenantId: str = "",
    subscriptionId: str = "",
    clientId: str = "",
    clientSecret: str = "",
    provider: str = "azure",
) -> dict:
    """Validate credentials and register cloud connection."""
    args = {
        "name": name,
        "tenant_id": tenantId,
        "subscription_id": subscriptionId,
        "client_id": clientId,
        "client_secret": clientSecret,
        "provider": provider,
    }
    return run_sync(handle_create_connection(get_store(), get_azure_client(), args))


@udf.function()
def validate_connection(
    connectionId: str = "",
    tenantId: str = "",
    subscriptionId: str = "",
    clientId: str = "",
    clientSecret: str = "",
    provider: str = "azure",
) -> dict:
    """Verify live connectivity and permissions against cloud provider."""
    args = {
        "connection_id": connectionId or None,
        "tenant_id": tenantId or None,
        "subscription_id": subscriptionId or None,
        "client_id": clientId or None,
        "client_secret": clientSecret or None,
        "provider": provider,
    }
    return run_sync(
        handle_validate_connection(get_store(), get_azure_client(), args)
    )


@udf.function()
def delete_connection(connectionId: str = "") -> dict:
    """Delete connection and associated telemetry."""
    args = {"connection_id": connectionId}
    return run_sync(handle_delete_connection(get_store(), args))


@udf.function()
def get_inventory(
    connectionId: str = "",
    resourceTypeFilter: str = "",
) -> dict:
    """Fetch discovered resources from Azure Resource Graph or Lakehouse snapshot."""
    args = {
        "connection_id": connectionId,
        "resource_type_filter": resourceTypeFilter or None,
    }
    return run_sync(handle_get_inventory(get_store(), get_azure_client(), args))


@udf.function()
def get_cost_waste(
    connectionId: str = "",
    forceRefresh: bool = False,
) -> dict:
    """Detect cloud waste across compute, disks, and IPs using deterministic algorithms."""
    args = {
        "connection_id": connectionId,
        "force_refresh": bool(forceRefresh),
    }
    return run_sync(
        handle_get_waste(
            get_store(),
            get_azure_client(),
            get_waste_detector(),
            args,
        )
    )


@udf.function()
def get_metrics(
    connectionId: str = "",
    resourceId: str = "",
    metricNames: str = "Percentage CPU",
    timeGrain: str = "PT1H",
    days: int = 7,
) -> dict:
    """Retrieve actual Azure Monitor performance metrics for a resource."""
    if isinstance(metricNames, str):
        names = [n.strip() for n in metricNames.split(",") if n.strip()]
    elif isinstance(metricNames, list):
        names = metricNames
    else:
        names = ["Percentage CPU"]

    args = {
        "connection_id": connectionId,
        "resource_id": resourceId,
        "metric_names": names,
        "time_grain": timeGrain,
        "days": days,
    }
    return run_sync(handle_get_metrics(get_store(), get_azure_client(), args))


@udf.function()
def get_token_economics(
    connectionId: str = "",
    days: int = 30,
) -> dict:
    """Aggregate actual GenAI token consumption and unit costs."""
    args = {
        "connection_id": connectionId,
        "days": days,
    }
    return run_sync(handle_get_token_economics(get_token_service(), args))


@udf.function()
def record_token_usage(
    connectionId: str = "",
    modelName: str = "",
    promptTokens: int = 0,
    completionTokens: int = 0,
    deploymentName: str = "",
    latencyMs: int = 0,
) -> dict:
    """Log an authentic GenAI inference event with exact token counts."""
    args = {
        "connection_id": connectionId,
        "model_name": modelName,
        "prompt_tokens": promptTokens,
        "completion_tokens": completionTokens,
        "deployment_name": deploymentName or None,
        "latency_ms": latencyMs or None,
    }
    return run_sync(handle_record_token_usage(get_token_service(), args))


@udf.function()
def calculate_pricing(
    armSkuName: str = "",
    region: str = "northcentralus",
    hoursPerMonth: float = 730.0,
) -> dict:
    """Calculate monthly cost deterministically from official Azure Retail Prices API."""
    args = {
        "arm_sku_name": armSkuName,
        "region": region,
        "hours_per_month": hoursPerMonth,
    }
    return run_sync(handle_calculate_pricing(get_azure_client(), args))


# Unified RPC dispatcher
FUNCTION_REGISTRY = {
    "hello_fabric": hello_fabric,
    "list_connections": list_connections,
    "create_connection": create_connection,
    "validate_connection": validate_connection,
    "delete_connection": delete_connection,
    "get_inventory": get_inventory,
    "get_cost_waste": get_cost_waste,
    "get_metrics": get_metrics,
    "get_token_economics": get_token_economics,
    "record_token_usage": record_token_usage,
    "calculate_pricing": calculate_pricing,
}


def dispatch_udf_function(
    function_name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Route function name and argument payload to registered handler."""
    fn_handler = FUNCTION_REGISTRY.get(function_name)
    if not fn_handler:
        return {
            "status": "error",
            "error_code": "FUNCTION_NOT_FOUND",
            "error_message": f"Fabric User Data Function '{function_name}' is not registered.",
        }
    mapped = {}
    for k, v in payload.items():
        camel_k = re.sub(r"_([a-z0-9])", lambda m: m.group(1).upper(), k)
        mapped[camel_k] = v
    try:
        return fn_handler(**mapped)
    except (TypeError, ValueError, RuntimeError, KeyError) as exc:
        return {
            "status": "error",
            "error_code": "FUNCTION_EXECUTION_ERROR",
            "error_message": str(exc),
        }
