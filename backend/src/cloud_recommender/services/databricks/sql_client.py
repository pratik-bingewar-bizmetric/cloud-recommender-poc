"""Secure, read-only Databricks SQL & Warehouse Service.

Implements Milestone 3H Phase B requirements:
1. Environment-driven configuration (DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID, DATABRICKS_AUTH_TYPE, etc.).
2. Zero-mutation warehouse status check (identifies STOPPED warehouse without starting compute).
3. Non-negotiable Warehouse Execution Approval Gate:
   Generates structured 8-point approval requests and prevents unapproved live SQL execution.
4. Read-only SQL safety guards (strictly enforces SELECT statements; rejects all DDL/DML mutations).
5. Comprehensive error classification: WAREHOUSE_STOPPED, APPROVAL_REQUIRED, PERMISSION_DENIED, AUTH_ERROR.
6. Secret redaction on all error messages.
"""

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from databricks.sdk import WorkspaceClient
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.services.databricks.auth import (
    DatabricksAuthError,
    DatabricksAuthService,
    classify_databricks_error,
)

logger = structlog.get_logger(__name__)


class ApprovalRequiredError(Exception):
    """Raised when an unapproved live SQL execution attempt occurs."""

    def __init__(self, approval_request: dict[str, Any]) -> None:
        super().__init__(
            "Live SQL execution requires explicit human approval before compute resume."
        )
        self.approval_request = approval_request


class WarehouseStoppedError(Exception):
    """Raised when query execution is attempted against a stopped warehouse without startup authorization."""

    def __init__(self, warehouse_id: str, warehouse_name: str) -> None:
        super().__init__(
            f"Warehouse '{warehouse_name}' ({warehouse_id}) is STOPPED. Compute startup prohibited without approval."
        )
        self.warehouse_id = warehouse_id
        self.warehouse_name = warehouse_name


class MutationProhibitedError(Exception):
    """Raised if any non-SELECT or mutation statement is passed to the read-only query engine."""

    pass


class ApprovalLedgerError(Exception):
    """Raised when the durable approval-token ledger cannot be read or written (fail closed)."""


class StatementIncompleteError(Exception):
    """A statement failed, timed out, or returned only part of its result.

    Never swallowed into an empty/short row list: callers must treat the run as failed.
    ``code`` is one of STATEMENT_FAILED, STATEMENT_TIMEOUT, RESULT_TRUNCATED,
    RESULT_INCOMPLETE.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.reason = message


def _state_name(value: Any) -> str:
    """Upper-case name of a StatementState enum/str (``StatementState.X`` -> ``X``)."""
    raw = getattr(value, "value", value)
    return str(raw).rsplit(".", 1)[-1].upper()


def statement_row_limit(sql_statement: str) -> int | None:
    """The literal ``LIMIT n`` of the outermost SELECT, or ``None`` when unbounded."""
    import sqlglot
    from sqlglot import exp

    try:
        tree = sqlglot.parse_one(sql_statement, read="databricks")
    except sqlglot.errors.SqlglotError:
        return None
    limit = tree.args.get("limit")
    if not isinstance(limit, exp.Limit):
        return None
    node = limit.args.get("expression")
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return int(node.name)
        except ValueError:
            return None
    return None


_LEDGER_TIMEOUT_SECONDS = 15.0
# The Statement Execution API accepts a synchronous wait of 0 or 5-50 s; anything longer
# is polled until the configured query timeout.
_STATEMENT_MAX_SYNC_WAIT_SECONDS = 50
_STATEMENT_POLL_SECONDS = 2.0


@dataclass
class LedgerHandle:
    """An AsyncSession plus the event loop that owns it.

    Token methods are synchronous and run in worker threads (sync FastAPI routes). A handle lets
    them execute ledger work on the owning loop without blocking it:
    ``asyncio.run_coroutine_threadsafe(session.run_sync(fn), loop)``.
    """

    session: AsyncSession
    loop: asyncio.AbstractEventLoop


def _ledger_call[T](handle: Any, fn: Callable[[Any], T]) -> T:
    """Run ``fn(sync_session)`` against a sync Session or a LedgerHandle-wrapped AsyncSession.

    A raw AsyncSession is rejected: calling its coroutine API synchronously silently does
    nothing, which is how the ledger was previously bypassed.
    """
    if isinstance(handle, LedgerHandle):
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is handle.loop:
            raise ApprovalLedgerError("Ledger call attempted on the event loop thread.")
        future = asyncio.run_coroutine_threadsafe(handle.session.run_sync(fn), handle.loop)
        return future.result(timeout=_LEDGER_TIMEOUT_SECONDS)
    if isinstance(handle, AsyncSession):
        raise ApprovalLedgerError("AsyncSession must be wrapped in a LedgerHandle.")
    return fn(handle)


@dataclass
class WarehouseHealthResult:
    """Structured result of warehouse connection and status diagnostic."""

    status: str  # AVAILABLE, WAREHOUSE_STOPPED, PERMISSION_DENIED, AUTH_ERROR, APPROVAL_REQUIRED
    warehouse_id: str
    warehouse_name: str
    warehouse_state: str  # STOPPED, RUNNING, STARTING, STOPPING, UNKNOWN
    can_execute: bool
    authenticated_user: str | None = None
    message: str = ""
    last_checked: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    auto_stop_mins: int | None = None  # observed from warehouse metadata; None = not observed
    cluster_size: str | None = None


class DatabricksSqlService:
    """Service managing read-only Databricks SQL execution, warehouse status checks, and approval gates."""

    def __init__(
        self,
        settings: Settings | None = None,
        auth_service: DatabricksAuthService | None = None,
        workspace_client: WorkspaceClient | None = None,
        host: str | None = None,
        warehouse_id: str | None = None,
        workspace_id: str | None = None,
        auth_type: str | None = None,
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.auth_service = auth_service or DatabricksAuthService()
        self._client = workspace_client

        # Direct overrides if supplied
        self.host = host or self.settings.databricks_host
        self.warehouse_id = (
            warehouse_id if warehouse_id is not None else self.settings.databricks_warehouse_id
        )
        self.workspace_id = (
            workspace_id
            or getattr(self.settings, "databricks_workspace_id", None)
            or "642006393507276"
        )
        self.auth_type = auth_type or self.settings.databricks_auth_type
        self.profile = profile or self.settings.databricks_profile
        self.client_id = client_id or self.settings.databricks_client_id
        self.client_secret = client_secret or self.settings.databricks_client_secret
        self._consumed_tokens: set[str] = set()
        self._inflight_tokens: set[str] = set()
        self._token_lock = threading.Lock()

    def __repr__(self) -> str:
        secret_mask = "[REDACTED]" if self.client_secret else "None"
        return (
            f"<DatabricksSqlService host={self.host!r} "
            f"warehouse_id={self.warehouse_id!r} "
            f"auth_type={self.auth_type!r} "
            f"client_secret={secret_mask}>"
        )

    def get_client(self) -> WorkspaceClient:
        """Resolve authenticated WorkspaceClient using environment settings and auth service."""
        if self._client is not None:
            return self._client

        return self.auth_service.create_workspace_client(
            host=self.host,
            cloud="azure",
            profile=self.profile,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

    def check_warehouse_status(self) -> WarehouseHealthResult:
        """Inspect warehouse state without starting compute or executing SQL.

        Complies with the Zero-Mutation policy: reads warehouse metadata only.
        Never uses llm_provider to suppress real warehouse checks, and never masks
        403 / auth / connection failures as STOPPED.
        """
        warehouse_id = (self.warehouse_id or "").strip()
        default_name = "Serverless Starter Warehouse"

        if self._client is None and (
            self.auth_type == "mock" or self.settings.databricks_auth_type == "mock"
        ):
            return WarehouseHealthResult(
                status="WAREHOUSE_STOPPED",
                warehouse_id=warehouse_id,
                warehouse_name=default_name,
                warehouse_state="STOPPED",
                can_execute=False,
                authenticated_user="offline_test_user@domain.com",
                message=f"Zero-execution policy active. Warehouse '{warehouse_id}' observed STOPPED in offline/mock mode.",
            )

        status_map = {
            "auth_failed": "AUTH_ERROR",
            "permission_denied": "PERMISSION_DENIED",
            "connection_error": "CONNECTION_ERROR",
        }

        try:
            client = self.get_client()

            # Test basic authentication and workspace membership
            me = client.current_user.me()
            username = me.user_name or me.display_name or "authenticated_user"

            if not warehouse_id:
                return WarehouseHealthResult(
                    status="CONNECTION_ERROR",
                    warehouse_id="",
                    warehouse_name="Unconfigured SQL Warehouse",
                    warehouse_state="UNCONFIGURED",
                    can_execute=False,
                    authenticated_user=username,
                    message="No SQL Warehouse ID is configured for this workspace.",
                )

            # Query warehouse metadata (READ-ONLY metadata inspection via SDK)
            try:
                wh_info = client.warehouses.get(id=warehouse_id)
                wh_name = wh_info.name or default_name
                state_val = getattr(wh_info.state, "value", None) or str(wh_info.state or "")
                state_str = str(state_val).upper()
                raw_auto_stop = getattr(wh_info, "auto_stop_mins", None)
                observed_auto_stop = (
                    raw_auto_stop
                    if isinstance(raw_auto_stop, int) and not isinstance(raw_auto_stop, bool)
                    else None
                )
                raw_size = getattr(wh_info, "cluster_size", None)
                observed_size = raw_size if isinstance(raw_size, str) else None

                if "STOPPED" in state_str:
                    return WarehouseHealthResult(
                        status="WAREHOUSE_STOPPED",
                        warehouse_id=warehouse_id,
                        warehouse_name=wh_name,
                        warehouse_state="STOPPED",
                        can_execute=False,
                        auto_stop_mins=observed_auto_stop,
                        cluster_size=observed_size,
                        authenticated_user=username,
                        message=(
                            f"Warehouse '{wh_name}' ({warehouse_id}) is STOPPED. "
                            "Approval required before resuming compute for live ingestion."
                        ),
                    )
                elif "RUNNING" in state_str:
                    return WarehouseHealthResult(
                        status="AVAILABLE",
                        warehouse_id=warehouse_id,
                        warehouse_name=wh_name,
                        warehouse_state="RUNNING",
                        can_execute=True,
                        auto_stop_mins=observed_auto_stop,
                        cluster_size=observed_size,
                        authenticated_user=username,
                        message=f"Warehouse '{wh_name}' is active and ready for read-only queries.",
                    )
                else:
                    return WarehouseHealthResult(
                        status="WAREHOUSE_STOPPED",
                        warehouse_id=warehouse_id,
                        warehouse_name=wh_name,
                        warehouse_state=state_str or "UNKNOWN",
                        can_execute=False,
                        authenticated_user=username,
                        message=f"Warehouse '{wh_name}' is in '{state_str}' state. Live execution gated.",
                    )

            except Exception as wh_exc:
                scrubbed = self.auth_service.scrub_sensitive(str(wh_exc))
                err_kind = classify_databricks_error(wh_exc)
                health_status = status_map[err_kind]
                logger.warning(
                    "databricks_warehouse_metadata_failed",
                    warehouse_id=warehouse_id,
                    classified_status=health_status,
                    error=scrubbed,
                )
                return WarehouseHealthResult(
                    status=health_status,
                    warehouse_id=warehouse_id,
                    warehouse_name=default_name,
                    warehouse_state="UNKNOWN",
                    can_execute=False,
                    authenticated_user=username,
                    message=f"{health_status}: Failed to inspect warehouse '{warehouse_id}' metadata ({scrubbed}).",
                )

        except Exception as auth_exc:
            scrubbed = self.auth_service.scrub_sensitive(str(auth_exc))
            err_kind = classify_databricks_error(auth_exc)
            health_status = status_map[err_kind]
            logger.warning(
                "databricks_sql_auth_check_failed",
                warehouse_id=warehouse_id,
                classified_status=health_status,
                error=scrubbed,
            )
            return WarehouseHealthResult(
                status=health_status,
                warehouse_id=warehouse_id,
                warehouse_name=default_name,
                warehouse_state="UNKNOWN",
                can_execute=False,
                authenticated_user=None,
                message=f"{health_status}: Unable to authenticate or connect to Databricks workspace ({scrubbed}).",
            )

    def generate_approval_request(
        self,
        sql_statement: str,
        system_tables: list[str],
        execution_purpose: str = "Ingest verified billing usage and price records into FinOps Command Center",
        estimated_scope: str = "Not specified",
    ) -> dict[str, Any]:
        """Generate the structured 8-point approval request for live SQL execution.

        Every operational figure shown to the approver is *observed* warehouse metadata or an
        explicit "not estimated"; nothing here is a hardcoded guess.
        """
        wh_health = self.check_warehouse_status()
        if wh_health.auto_stop_mins is None:
            auto_stop_text = "Auto-stop setting not observed (warehouse metadata unavailable)"
        elif wh_health.auto_stop_mins == 0:
            auto_stop_text = "Auto-stop is DISABLED on the target warehouse"
        else:
            auto_stop_text = (
                f"{wh_health.auto_stop_mins}-minute auto-stop observed on the target warehouse"
            )
        size_text = wh_health.cluster_size or "size not observed"
        return {
            "warehouse_name": wh_health.warehouse_name,
            "warehouse_id": wh_health.warehouse_id,
            "status": wh_health.warehouse_state,
            "current_observed_state": wh_health.warehouse_state,
            "exact_read_only_sql": sql_statement.strip(),
            "system_tables_accessed": system_tables,
            "execution_purpose": execution_purpose,
            "estimated_scope_and_window": estimated_scope,
            "warehouse_startup_necessary": wh_health.warehouse_state == "STOPPED",
            "expected_compute_charges": (
                "Not estimated: depends on warehouse size and runtime "
                f"({size_text}; {auto_stop_text})."
            ),
            "observed_auto_stop_mins": wh_health.auto_stop_mins,
            "observed_cluster_size": wh_health.cluster_size,
            "approval_status": "APPROVAL_REQUIRED",
            "timestamp": datetime.now(UTC).isoformat(),
            "explicit_approval_required": {
                "action": "Read-only SELECT query against system tables",
                "target_compute": f"Databricks SQL Warehouse {wh_health.warehouse_name} ({wh_health.warehouse_id})",
                "state_transition": "Warehouse state will transition from STOPPED to RUNNING",
                "auto_stop_configured": auto_stop_text,
                "estimated_cost": "Not estimated: depends on warehouse size and runtime",
                "data_mutation": "Zero mutations permitted: query strictly restricted to read-only projection",
                "rollback_procedure": "Warehouse compute is stopped immediately upon ingestion completion",
                "local_fixture_fallback": "Deterministic offline fixtures remain active if execution is unapproved",
            },
        }

    ALLOWED_SYSTEM_TABLES: set[str] = {
        "system.billing.usage",
        "system.billing.list_prices",
    }

    ALLOWED_APPROVER_ROLES: set[str] = {
        "Admin",
        "FinOpsAdministrator",
        "PlatformAdministrator",
    }

    def _get_signing_keys(self) -> dict[str, bytes]:
        """Retrieve active and rotated cryptographic HMAC signing keys mapped by kid.

        Fail-closed: If finops_signing_secret is not configured, raises RuntimeError.
        """
        import json

        primary = getattr(self.settings, "finops_signing_secret", None)
        if not primary or not str(primary).strip():
            raise RuntimeError(
                "Cryptographic signing secret 'finops_signing_secret' is not configured. "
                "Token issuance is disabled to enforce fail-closed security."
            )
        active_kid = getattr(self.settings, "finops_signing_kid", "k1-2026") or "k1-2026"
        key_ring: dict[str, bytes] = {active_kid: primary.strip().encode("utf-8")}

        # Load any additional verification keys for rotation support
        verification_keys_raw = getattr(self.settings, "finops_verification_keys", None)
        if verification_keys_raw:
            try:
                parsed = json.loads(verification_keys_raw)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if k and v:
                            key_ring[str(k).strip()] = str(v).strip().encode("utf-8")
            except Exception:
                for item in str(verification_keys_raw).split(","):
                    if ":" in item:
                        k, v = item.split(":", 1)
                        if k.strip() and v.strip():
                            key_ring[k.strip()] = v.strip().encode("utf-8")

        return key_ring

    def issue_approval_token(
        self,
        query: str,
        warehouse_id: str,
        start_date: str = "",
        end_date: str = "",
        ttl_seconds: int = 300,
        approver_sub: str = "operator@bizmetric.com",
        approver_roles: list[str] | None = None,
        max_rows: int = 1000,
        approval_purpose: str = "Live System Tables Billing Ingestion",
        session: Any | None = None,
    ) -> str:
        """Issue a cryptographically signed approval token binding query, warehouse, and scope."""
        import base64
        import hashlib
        import hmac
        import json
        import secrets
        import time

        # 1. Enforce RBAC for approver: strictly reject missing/unauthorized roles
        roles = approver_roles if approver_roles is not None else []
        if not roles or not any(r in self.ALLOWED_APPROVER_ROLES for r in roles):
            raise PermissionError(
                f"Approver '{approver_sub}' with roles {roles} is not authorized to issue approval tokens. "
                f"Requires one of: {sorted(self.ALLOWED_APPROVER_ROLES)}"
            )

        # 2. Enforce query safety check before issuing token
        self.validate_read_only_statement(query)

        # 3. Retrieve active signing key (fails closed if unconfigured)
        key_ring = self._get_signing_keys()
        active_kid = getattr(self.settings, "finops_signing_kid", "k1-2026") or "k1-2026"
        secret = key_ring.get(active_kid)
        if not secret:
            secret = next(iter(key_ring.values()))

        nonce = secrets.token_hex(16)
        issued_ts = int(time.time())
        expiry_ts = issued_ts + ttl_seconds
        issued_iso = datetime.fromtimestamp(issued_ts, UTC).isoformat()
        expiry_iso = datetime.fromtimestamp(expiry_ts, UTC).isoformat()
        qhash = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()
        token_id = f"tok-{nonce[:12]}-{qhash[:12]}"

        # 4. Canonical 15-parameter payload binding
        canonical_payload = {
            "allowed_tables": sorted(self.ALLOWED_SYSTEM_TABLES),
            "approval_purpose": approval_purpose,
            "approver_roles": sorted(roles),
            "approver_sub": approver_sub,
            "date_end": end_date or None,
            "date_start": start_date or None,
            "expires_at": expiry_iso,
            "issued_at": issued_iso,
            "kid": active_kid,
            "max_rows": max_rows,
            "nonce": nonce,
            "query_hash": qhash,
            "requested_operation": "READ_ONLY_SYSTEM_TABLES_SELECT",
            "token_id": token_id,
            "warehouse_id": warehouse_id,
            "workspace_id": self.workspace_id,
        }

        canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
        sig = hmac.new(secret, canonical_json.encode("utf-8"), hashlib.sha256).hexdigest()
        b64_payload = (
            base64.urlsafe_b64encode(canonical_json.encode("utf-8")).decode("ascii").rstrip("=")
        )
        token = f"v2:{active_kid}:{b64_payload}:{sig}"

        # 5. Durable persistence in PostgreSQL if a ledger session is provided.
        # Fail closed: a token that cannot be recorded is never returned.
        if session is not None:
            from cloud_recommender.db.models import BillingApprovalTokenModel

            def _persist(sync_session: Any) -> None:
                sync_session.add(
                    BillingApprovalTokenModel(
                        token_id=token_id,
                        kid=active_kid,
                        approver_sub=approver_sub,
                        approver_roles=roles,
                        workspace_id=self.workspace_id,
                        warehouse_id=warehouse_id,
                        query_hash=qhash,
                        date_start=start_date or None,
                        date_end=end_date or None,
                        allowed_tables=sorted(self.ALLOWED_SYSTEM_TABLES),
                        requested_operation="READ_ONLY_SYSTEM_TABLES_SELECT",
                        max_rows=max_rows,
                        nonce=nonce,
                        issued_at=datetime.fromtimestamp(issued_ts, UTC),
                        expires_at=datetime.fromtimestamp(expiry_ts, UTC),
                        is_consumed=False,
                        approval_purpose=approval_purpose,
                    )
                )
                try:
                    sync_session.commit()
                except Exception:
                    sync_session.rollback()
                    raise

            try:
                _ledger_call(session, _persist)
            except Exception as e:
                logger.warning("approval_token_persistence_failed", error=type(e).__name__)
                raise ApprovalLedgerError(
                    "Approval token could not be recorded in the durable ledger; token not issued."
                ) from e

        return token

    def verify_approval_token(
        self,
        token: str | None,
        query: str,
        warehouse_id: str,
        session: Any | None = None,
        max_rows: int | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        enforce_scope: bool = False,
    ) -> bool:
        """Verify that the approval token is valid, unexpired, unconsumed, and matches query and warehouse.

        With ``enforce_scope`` (used for execution) the signed scope must match exactly: the
        statement's row limit may not exceed the token's ``max_rows`` (and must exist), the
        signed date window must equal the requested one, and un-scoped legacy tokens are not
        accepted outside offline/test mode.
        """
        if not token:
            return False

        # Enforce one-time-use / server-side replay prevention in memory
        if token in self._consumed_tokens:
            logger.warning("approval_token_memory_replay_rejected", token_prefix=token[:16])
            return False

        if token == "TEST-APPROVED-TOKEN" and (
            self.auth_type == "mock" or self.settings.app_env == "testing"
        ):
            return True

        import base64
        import hashlib
        import hmac
        import json
        import time

        current_qhash = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()

        # Handle v2 canonical token
        if token.startswith("v2:"):
            parts = token.split(":")
            if len(parts) != 4:
                return False
            _, t_kid, b64_payload, t_sig = parts

            try:
                key_ring = self._get_signing_keys()
            except Exception:
                return False

            secret = key_ring.get(t_kid)
            if not secret:
                logger.warning("approval_token_unknown_kid_rejected", kid=t_kid)
                return False

            pad = -len(b64_payload) % 4
            try:
                payload_bytes = base64.urlsafe_b64decode(b64_payload + ("=" * pad))
                expected_sig = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(t_sig, expected_sig):
                    logger.warning("approval_token_invalid_signature_rejected")
                    return False

                payload = json.loads(payload_bytes.decode("utf-8"))
            except Exception as e:
                logger.warning("approval_token_payload_decode_failed", error=str(e))
                return False

            if payload.get("warehouse_id") != warehouse_id:
                logger.warning("approval_token_warehouse_mismatch")
                return False
            if payload.get("query_hash") != current_qhash:
                logger.warning("approval_token_query_hash_mismatch")
                return False
            if payload.get("workspace_id") != self.workspace_id:
                logger.warning("approval_token_workspace_mismatch")
                return False

            exp_str = payload.get("expires_at")
            if not exp_str:
                return False
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                if datetime.now(UTC) > exp_dt:
                    logger.warning("approval_token_expired", expires_at=exp_str)
                    return False
            except Exception:
                return False

            if enforce_scope:
                token_rows = payload.get("max_rows")
                if (
                    max_rows is None
                    or isinstance(token_rows, bool)
                    or not isinstance(token_rows, int)
                    or max_rows > token_rows
                ):
                    logger.warning("approval_token_max_rows_exceeded")
                    return False
                if (date_start or None) != payload.get("date_start"):
                    logger.warning("approval_token_date_start_mismatch")
                    return False
                if (date_end or None) != payload.get("date_end"):
                    logger.warning("approval_token_date_end_mismatch")
                    return False
            else:
                if max_rows is not None:
                    token_max = payload.get("max_rows", 1000)
                    if max_rows > token_max:
                        logger.warning("approval_token_max_rows_exceeded")
                        return False
                if (
                    date_start
                    and payload.get("date_start")
                    and date_start != payload.get("date_start")
                ):
                    logger.warning("approval_token_date_start_mismatch")
                    return False
                if date_end and payload.get("date_end") and date_end != payload.get("date_end"):
                    logger.warning("approval_token_date_end_mismatch")
                    return False

            token_id = payload.get("token_id")
            if session is not None and token_id:
                if not self._ledger_allows(session, token_id):
                    return False

            return True

        # Backward compatibility with legacy 7-part token and 4-part token. Legacy tokens carry
        # no signed row limit or date window, so they cannot satisfy scope enforcement.
        if enforce_scope and not (self.auth_type == "mock" or self.settings.app_env == "testing"):
            logger.warning("approval_token_legacy_format_rejected_for_execution")
            return False
        parts = token.split(":")
        if len(parts) == 7:
            t_wh, t_qhash, _, _, nonce_part, t_exp_str, t_sig = parts
            payload = ":".join(parts[:6])
            token_id = f"tok-{nonce_part}-{t_sig[:16]}"
        elif len(parts) == 4:
            t_wh, t_qhash, t_exp_str, t_sig = parts
            payload = f"{t_wh}:{t_qhash}:{t_exp_str}"
            token_id = None
        else:
            return False

        if t_wh != warehouse_id or t_qhash != current_qhash:
            return False

        try:
            exp = int(t_exp_str)
            if time.time() > exp:
                return False
        except ValueError:
            return False

        # Verify signature against key ring
        sig_valid = False
        try:
            keys = list(self._get_signing_keys().values())
        except Exception:
            keys = []
        for secret in keys:
            expected_sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
            if hmac.compare_digest(t_sig, expected_sig):
                sig_valid = True
                break

        if not sig_valid:
            return False

        if session is not None and token_id:
            if not self._ledger_allows(session, token_id):
                return False

        return True

    def _ledger_allows(self, session: Any, token_id: str) -> bool:
        """True when the durable ledger shows the token as not consumed.

        Fail closed: if the ledger cannot be read the token is NOT accepted.
        """
        from sqlalchemy import select

        from cloud_recommender.db.models import BillingApprovalTokenModel

        def _lookup(sync_session: Any) -> bool:
            rec = sync_session.execute(
                select(BillingApprovalTokenModel).where(
                    BillingApprovalTokenModel.token_id == token_id
                )
            ).scalar_one_or_none()
            return bool(rec is not None and rec.is_consumed)

        try:
            consumed = _ledger_call(session, _lookup)
        except Exception as e:
            logger.warning("approval_token_db_check_failed", error=type(e).__name__)
            return False
        if consumed:
            logger.warning("approval_token_db_replay_rejected", token_id=token_id)
            return False
        return True

    def consume_approval_token(
        self,
        token: str,
        session: Any | None = None,
    ) -> bool:
        """Mark approval token as consumed atomically in database and in memory to enforce single-use.

        The durable atomic UPDATE is authoritative. The in-memory set is only marked after a
        successful consume, so a ledger outage does not burn a token that never ran; an
        in-flight set under a lock stops two threads racing through the check.
        """
        if not token or token == "TEST-APPROVED-TOKEN":
            return True
        with self._token_lock:
            if token in self._consumed_tokens or token in self._inflight_tokens:
                return False
            self._inflight_tokens.add(token)
        won = False
        try:
            won = self._consume_durable(token, session)
        finally:
            with self._token_lock:
                self._inflight_tokens.discard(token)
                if won:
                    self._consumed_tokens.add(token)
        return won

    def _consume_durable(self, token: str, session: Any | None) -> bool:
        """Atomically consume ``token`` in the durable ledger (when one is supplied)."""
        if session is not None:
            token_id = None
            if token.startswith("v2:"):
                import base64
                import json

                parts = token.split(":")
                if len(parts) == 4:
                    b64_payload = parts[2]
                    pad = -len(b64_payload) % 4
                    try:
                        p_bytes = base64.urlsafe_b64decode(b64_payload + ("=" * pad))
                        payload_data = json.loads(p_bytes.decode("utf-8"))
                        token_id = payload_data.get("token_id")
                    except Exception:
                        token_id = None
            else:
                parts = token.split(":")
                if len(parts) == 7:
                    nonce_part, t_sig = parts[4], parts[6]
                    token_id = f"tok-{nonce_part}-{t_sig[:16]}"

            if token_id:
                from sqlalchemy import update

                from cloud_recommender.db.models import BillingApprovalTokenModel

                def _consume(sync_session: Any) -> bool:
                    stmt = (
                        update(BillingApprovalTokenModel)
                        .where(
                            BillingApprovalTokenModel.token_id == token_id,
                            BillingApprovalTokenModel.is_consumed == False,  # noqa: E712
                        )
                        .values(is_consumed=True, consumed_at=datetime.now(UTC))
                        .returning(BillingApprovalTokenModel.id)
                    )
                    updated_row = sync_session.execute(stmt).scalar_one_or_none()
                    if updated_row is None:
                        sync_session.rollback()
                        return False
                    sync_session.commit()
                    return True

                try:
                    won = _ledger_call(session, _consume)
                except Exception as e:
                    logger.warning("approval_token_consume_db_failed", error=type(e).__name__)
                    return False
                if not won:
                    logger.warning(
                        "approval_token_atomic_consume_failed_already_consumed",
                        token_id=token_id,
                    )
                return won
            # v2 tokens must be recorded in the ledger; legacy tokens stay in-memory single-use.
            if token.startswith("v2:"):
                return False
        return True

    def validate_read_only_statement(self, sql_statement: str) -> None:
        """Validate statement using Databricks SQL AST parser and fail-closed security rules."""
        import sqlglot
        from sqlglot import exp

        cleaned_sql = sql_statement.strip()
        if not cleaned_sql:
            raise MutationProhibitedError("Empty SQL statement is not permitted.")

        # 1. Block SQL comments to prevent comment-hiding evasion
        if "--" in cleaned_sql or "/*" in cleaned_sql or "*/" in cleaned_sql:
            raise MutationProhibitedError(
                "Comments ('--' or '/*') are prohibited in certified queries to prevent comment-hiding evasion."
            )

        # 2. Block multiple statements (semicolon check)
        if ";" in cleaned_sql:
            raise MutationProhibitedError(
                "Semicolons are prohibited to prevent chained statement injection."
            )

        # 3. Parse AST using Databricks dialect
        try:
            expressions = sqlglot.parse(cleaned_sql, read="databricks")
        except Exception as pe:
            raise MutationProhibitedError(f"SQL statement could not be parsed: {pe}") from pe

        if len(expressions) != 1 or expressions[0] is None:
            raise MutationProhibitedError("Exactly one read-only statement must be provided.")

        ast = expressions[0]

        # 4. Root expression must be a read-only query (Select or Union)
        if not isinstance(ast, (exp.Select, exp.Union)):
            raise MutationProhibitedError(
                f"Only read-only SELECT or WITH statements are permitted. Found AST node: {type(ast).__name__}"
            )

        # 5. Prohibited AST mutation nodes
        prohibited_nodes = (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Drop,
            exp.Create,
            exp.Alter,
            exp.Merge,
            exp.TruncateTable,
            exp.Command,
            exp.Pragma,
            exp.Kill,
        )
        for node in ast.walk():
            if isinstance(node, prohibited_nodes):
                raise MutationProhibitedError(
                    f"Statement contains prohibited mutation AST node: {type(node).__name__}"
                )

        # 6. CTE and physical table resolution against strict allowlist
        cte_names = {
            cte.alias.lower()
            for cte in ast.find_all(exp.CTE)
            if hasattr(cte, "alias") and cte.alias
        }

        allowed_table_refs = 0
        for table in ast.find_all(exp.Table):
            catalog_part = (table.catalog or "").lower().strip('`"')
            db_part = (table.db or "").lower().strip('`"')
            name_part = (table.name or "").lower().strip('`"')

            parts = [p for p in [catalog_part, db_part, name_part] if p]
            full_table_name = ".".join(parts)

            # If referencing an in-query CTE name without external catalog/schema
            if name_part in cte_names and not catalog_part and not db_part:
                continue

            if full_table_name in self.ALLOWED_SYSTEM_TABLES:
                allowed_table_refs += 1
                continue

            raise MutationProhibitedError(
                f"Access to table '{full_table_name or name_part}' is not permitted by allowlist. "
                f"Allowed: {sorted(self.ALLOWED_SYSTEM_TABLES)}"
            )

        if allowed_table_refs == 0:
            raise MutationProhibitedError(
                f"Query must reference at least one allowed system table: {sorted(self.ALLOWED_SYSTEM_TABLES)}"
            )

        # 7. Unsafe functions and reflection checks
        prohibited_func_names = {
            "secret",
            "reflect",
            "java_method",
            "javamethod",
            "stack",
            "current_user",
            "currentuser",
            "password",
            "user",
            "session_user",
            "sessionuser",
            "version",
            "input_file_name",
            "inputfilename",
            "execute_immediate",
            "executeimmediate",
        }

        for node in ast.walk():
            # Check function invocations
            if isinstance(node, (exp.Func, exp.Anonymous)):
                if isinstance(node, exp.Anonymous):
                    fn_name = str(node.this).lower()
                else:
                    fn_name = (node.key or node.sql_name() or "").lower()
                if fn_name in prohibited_func_names:
                    raise MutationProhibitedError(
                        f"Statement contains unsafe function or call: {fn_name}"
                    )

            # Check Dot expressions for dbutils or sys.*
            if isinstance(node, exp.Dot):
                dot_text = node.sql().lower()
                if dot_text.startswith("dbutils.") or dot_text.startswith("sys."):
                    raise MutationProhibitedError(
                        f"Statement contains unsafe function or call: {dot_text}"
                    )

    def execute_read_only_statement(
        self,
        sql_statement: str,
        system_tables: list[str] | None = None,
        is_approved: bool = False,
        approval_token: str | None = None,
        parameters: dict[str, Any] | None = None,
        session: Any | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> list[dict[str, Any]]:
        """Safely execute a read-only SQL statement against Databricks System Tables.

        Strict Safety Rules:
        1. Statement must start strictly with SELECT or WITH.
        2. If is_approved is False, raises ApprovalRequiredError immediately.
        3. If approval_token is invalid or missing, raises ApprovalRequiredError (server-enforced).
        4. If warehouse is STOPPED and startup is not permitted, raises WarehouseStoppedError.
        5. Zero-execution decoupling: never auto-starts or resumes stopped warehouse compute.
        6. The token's signed scope is enforced: exact SQL hash, warehouse, workspace, expiry,
           statement LIMIT <= signed max_rows and the signed date window.
        7. The result must be COMPLETE: a statement that is still running, failed, was
           truncated, or returned fewer rows than its manifest states raises
           StatementIncompleteError instead of returning a short list.
        """
        _ = parameters
        cleaned_sql = sql_statement.strip()

        # Enforce read-only policy
        self.validate_read_only_statement(cleaned_sql)

        # Enforce human approval gate
        is_token_valid = self.verify_approval_token(
            approval_token,
            cleaned_sql,
            self.warehouse_id,
            session=session,
            max_rows=statement_row_limit(cleaned_sql),
            date_start=date_start,
            date_end=date_end,
            enforce_scope=True,
        )
        # Allow testing bypass only when running unit tests under mock auth with explicit is_approved flag
        test_bypass = (
            is_approved
            and (self.auth_type == "mock" or self.settings.app_env == "testing")
            and (approval_token is None or approval_token == "TEST-APPROVED-TOKEN")
        )

        if not (is_approved and (is_token_valid or test_bypass)):
            tables = system_tables or ["system.billing.usage"]
            approval_req = self.generate_approval_request(
                sql_statement=cleaned_sql,
                system_tables=tables,
            )
            approval_req["approval_instructions"] = (
                "Request a cryptographically signed authorization token via "
                "POST /api/v1/finops/ingestion/approval-token using an authenticated "
                "principal with FinOpsAdministrator, Admin, or PlatformAdministrator role."
            )
            logger.info(
                "databricks_sql_gated_approval_required",
                warehouse_id=self.warehouse_id,
            )
            raise ApprovalRequiredError(approval_req)

        uses_real_token = bool(approval_token and approval_token != "TEST-APPROVED-TOKEN")
        offline_mode = self.auth_type == "mock" or self.settings.app_env == "testing"
        if uses_real_token and session is None and not offline_mode:
            # No durable ledger was supplied (e.g. direct service use). Single-use is still
            # enforced in memory, but does not survive a restart. API routes always supply the
            # ledger in live mode and fail closed if it is unavailable.
            logger.warning("approval_token_ledger_not_configured", warehouse_id=self.warehouse_id)

        # Check warehouse state FIRST (zero-execution decoupling). A stopped warehouse or a
        # failed health check must not consume the single-use approval.
        wh_health = self.check_warehouse_status()
        if wh_health.warehouse_state == "STOPPED":
            raise WarehouseStoppedError(wh_health.warehouse_id, wh_health.warehouse_name)
        if wh_health.status in ("AUTH_ERROR", "PERMISSION_DENIED", "CONNECTION_ERROR"):
            raise DatabricksAuthError(wh_health.message)

        # Warehouse is usable: now consume the token (one-time use, in memory and durable ledger)
        if uses_real_token:
            assert approval_token is not None
            consumed = self.consume_approval_token(approval_token, session=session)
            if not consumed:
                raise ApprovalRequiredError(
                    {"error": "Token has already been consumed or replay was detected."}
                )

        # Live execution (when approved and warehouse is running)
        client = self.get_client()
        logger.info(
            "databricks_executing_approved_sql",
            warehouse_id=self.warehouse_id,
            timeout=self.settings.databricks_query_timeout_seconds,
        )
        sync_wait = min(
            int(self.settings.databricks_query_timeout_seconds),
            _STATEMENT_MAX_SYNC_WAIT_SECONDS,
        )
        response = client.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            statement=cleaned_sql,
            wait_timeout=f"{sync_wait}s",
        )
        return self._collect_complete_rows(client, response)

    def _collect_complete_rows(self, client: Any, response: Any) -> list[dict[str, Any]]:
        """Return every row of a finished statement, or raise StatementIncompleteError.

        Waits (bounded by the query timeout, cancelling on expiry) for PENDING/RUNNING
        statements, rejects FAILED/CANCELED/CLOSED, rejects a manifest flagged ``truncated``,
        follows ``next_chunk_index`` until exhausted and cross-checks the collected row count
        against the manifest.
        """
        api = client.statement_execution
        statement_id = getattr(response, "statement_id", None)
        deadline = time.monotonic() + float(self.settings.databricks_query_timeout_seconds)
        state = _state_name(getattr(getattr(response, "status", None), "state", None))
        while state in ("PENDING", "RUNNING"):
            if statement_id is None or time.monotonic() >= deadline:
                if statement_id is not None:
                    try:
                        api.cancel_execution(statement_id)
                    except Exception as exc:  # best effort: never mask the timeout
                        logger.warning(
                            "databricks_statement_cancel_failed", error=type(exc).__name__
                        )
                raise StatementIncompleteError(
                    "STATEMENT_TIMEOUT",
                    "The statement did not finish within the query timeout; no rows were used.",
                )
            time.sleep(_STATEMENT_POLL_SECONDS)
            response = api.get_statement(statement_id)
            state = _state_name(getattr(getattr(response, "status", None), "state", None))

        if state != "SUCCEEDED":
            err = getattr(getattr(response, "status", None), "error", None)
            detail = self.auth_service.scrub_sensitive(str(getattr(err, "message", "") or ""))
            raise StatementIncompleteError(
                "STATEMENT_FAILED",
                f"The statement ended in state {state}." + (f" {detail}" if detail else ""),
            )

        manifest = getattr(response, "manifest", None)
        if manifest is None:
            raise StatementIncompleteError(
                "RESULT_INCOMPLETE",
                "The result has no manifest, so its completeness cannot be verified.",
            )
        if getattr(manifest, "truncated", None):
            raise StatementIncompleteError(
                "RESULT_TRUNCATED", "Databricks truncated the result; rows were not used."
            )
        schema = getattr(manifest, "schema", None)
        schema_cols = getattr(schema, "columns", None) or []
        columns = [str(col.name or "") for col in schema_cols]

        rows: list[dict[str, Any]] = []
        result = getattr(response, "result", None)
        chunks_read = 0
        while result is not None:
            if getattr(result, "external_links", None):
                raise StatementIncompleteError(
                    "RESULT_INCOMPLETE", "External-link result chunks are not supported."
                )
            for row_vals in result.data_array or []:
                rows.append(dict(zip(columns, row_vals, strict=False)))
            chunks_read += 1
            next_index = result.next_chunk_index
            if next_index is None:
                break
            if statement_id is None or chunks_read > 100_000:
                raise StatementIncompleteError(
                    "RESULT_INCOMPLETE", "Further result chunks exist but cannot be fetched."
                )
            result = api.get_statement_result_chunk_n(statement_id, next_index)

        expected_rows = manifest.total_row_count
        if expected_rows is not None and len(rows) != expected_rows:
            raise StatementIncompleteError(
                "RESULT_INCOMPLETE",
                f"Collected {len(rows)} rows but the manifest reports {expected_rows}.",
            )
        expected_chunks = manifest.total_chunk_count
        if expected_chunks and chunks_read < expected_chunks:
            raise StatementIncompleteError(
                "RESULT_INCOMPLETE",
                f"Read {chunks_read} of {expected_chunks} result chunks.",
            )
        return rows
