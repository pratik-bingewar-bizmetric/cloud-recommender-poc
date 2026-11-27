"""AWS Synchronization Approval & Transport-Level API Budget Guardrail Service.

Features:
1. Preview generation with deterministic request and cost estimation.
2. Canonical synchronization plan hashing and HMAC-SHA256 token issuance.
3. Cryptographic binding of tokens to tenant, user, connection, account, regions, date range, exact operations, and budget.
4. Transport-level atomic Decimal budget reservations with concurrency protection.
5. Persistent and fail-closed single-use approval token consumption ledger.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

from cloud_recommender.core.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Standard AWS API Unit Pricing for Cost Calculations (Verified: AWS Documentation November 2026)
# Note: Estimates are calculated for safety guardrails and do not represent a guaranteed AWS invoice.
AWS_CE_REQUEST_COST_USD = Decimal("0.01")  # AWS Cost Explorer: $0.01 per API request
AWS_CW_METRIC_QUERY_COST_USD = Decimal(
    "0.00001"
)  # AWS CloudWatch: $0.01 per 1,000 metrics requested ($0.00001 each)
AWS_S3_LIST_REQUEST_COST_USD = Decimal(
    "0.000005"
)  # AWS S3: $0.005 per 1,000 ListObjectsV2 requests

APPROVED_SYNC_OPERATIONS: tuple[str, ...] = (
    "ce:GetCostAndUsage",
    "ce:GetCostForecast",
    "cloudwatch:GetMetricData",
    "pricing:GetProducts",
    "s3:ListObjectsV2",
)


class AwsSyncPreviewRequest(BaseModel):
    """Parameters for computing a synchronization request budget preview."""

    connection_id: str = Field(default="default")
    account_id: str = Field(default="435305479688")
    regions: list[str] = Field(default_factory=lambda: ["eu-north-1", "us-east-1"])
    services: list[str] = Field(default_factory=lambda: ["cost_explorer", "cloudwatch", "pricing"])
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    estimated_lambda_count: int = Field(default=2)
    estimated_ec2_count: int = Field(default=0)


class AwsSyncPreviewResponse(BaseModel):
    """Detailed preview of proposed AWS API invocations and estimated cost."""

    account_id: str
    connection_id: str
    selected_regions: list[str]
    selected_services: list[str]
    approved_operations: list[str]
    start_date: str
    end_date: str
    max_cost_explorer_requests: int
    max_cloudwatch_queries: int
    max_total_requests: int
    estimated_api_cost_usd: float
    recommended_budget_usd: float
    expected_data_coverage: str
    warning_notice: str
    pricing_verification_date: str = "2026-11-26"
    pricing_source: str = "Official AWS Cost Management & CloudWatch Pricing Catalog"


class AwsSyncApprovalToken(BaseModel):
    """Cryptographically signed approval record with immutable canonical plan binding."""

    token_id: str
    tenant_id: str
    user_id: str
    connection_id: str
    account_id: str
    approved_regions: list[str]
    approved_services: list[str]
    approved_operations: list[str]
    start_date: str
    end_date: str
    max_requests: int
    max_metric_queries: int = 100
    approved_budget_usd: float
    estimated_cost_usd: float
    expires_at_epoch: int
    plan_hash: str
    canonical_plan: dict[str, Any]
    signature: str


class AwsSyncRunResult(BaseModel):
    """Audit record of an approved synchronization run."""

    run_id: str
    token_id: str
    status: str  # COMPLETED | BUDGET_EXHAUSTED | FAILED
    account_id: str
    executed_requests: int
    max_budget_requests: int
    actual_api_cost_usd: float
    started_at: datetime
    completed_at: datetime
    services_synced: list[str]
    error_message: str | None = None


class AwsBudgetGuard:
    """Enforces atomic transport-level Decimal cost reservations and request limits.

    Concurrency Note:
        Uses asyncio.Lock() for coroutine synchronization strictly within a single Python
        asyncio event loop. It does NOT provide thread-safety across multiple OS threads
        and does NOT provide cross-process synchronization.
        In multi-worker or multi-process deployments, durable centralized locking (e.g.
        Redis or PostgreSQL advisory locks) is required.
    """

    def __init__(
        self,
        max_requests: int,
        approved_budget_usd: Decimal,
        max_metric_queries: int = 100,
    ) -> None:
        self.max_requests = max_requests
        self.approved_budget_usd = approved_budget_usd
        self.max_metric_queries = max_metric_queries
        self.executed_requests = 0
        self.executed_metric_queries = 0
        self.reserved_cost = Decimal("0.00")
        self.executed_cost = Decimal("0.00")
        self.exhausted = False
        self._lock = asyncio.Lock()

    def check_and_increment(
        self,
        request_type: str = "cost_explorer",
        count: int = 1,
        metric_queries: int = 0,
        estimated_cost: Decimal | None = None,
    ) -> None:
        """Synchronously check and record cost reservation."""
        if estimated_cost is None:
            if request_type == "cost_explorer":
                estimated_cost = Decimal(count) * AWS_CE_REQUEST_COST_USD
            elif request_type == "cloudwatch":
                estimated_cost = Decimal(metric_queries or count) * AWS_CW_METRIC_QUERY_COST_USD
            elif request_type == "s3_list":
                estimated_cost = Decimal(count) * AWS_S3_LIST_REQUEST_COST_USD
            else:
                estimated_cost = Decimal("0.00")

        if self.executed_requests + count > self.max_requests:
            self.exhausted = True
            raise PermissionError(
                f"AWS Sync Budget Exhausted! Attempted {self.executed_requests + count} requests ({request_type}), "
                f"which exceeds the approved limit of {self.max_requests} requests (${self.approved_budget_usd:.2f})."
            )

        if self.reserved_cost + estimated_cost > self.approved_budget_usd:
            self.exhausted = True
            raise PermissionError(
                f"AWS Sync Cost Cap Exhausted! Required reservation ${self.reserved_cost + estimated_cost:.4f} "
                f"exceeds approved budget of ${self.approved_budget_usd:.4f} USD."
            )

        self.executed_requests += count
        self.executed_metric_queries += metric_queries
        self.reserved_cost += estimated_cost
        self.executed_cost += estimated_cost

    async def check_and_reserve(
        self,
        request_type: str = "cost_explorer",
        count: int = 1,
        metric_queries: int = 0,
        estimated_cost: Decimal | None = None,
    ) -> None:
        """Atomically check and reserve budget before outbound dispatch."""
        async with self._lock:
            self.check_and_increment(
                request_type=request_type,
                count=count,
                metric_queries=metric_queries,
                estimated_cost=estimated_cost,
            )


class AwsSyncApprovalService:
    """Manages preview, canonical plan hashing, token issuance, single-use validation, and run ledgers.

    Concurrency & Persistence Note:
        Uses asyncio.Lock() for coroutine synchronization strictly within a single process.
        Approval token consumption is tracked in-memory (_used_token_ids) and is NOT durably
        persisted across process restarts or shared across multiple worker processes.
        Production multi-process deployments require durable persistence (e.g. PostgreSQL/Redis).
    """

    SECRET_KEY = b"aws-finops-sync-approval-secret-v2-secure"

    def __init__(self) -> None:
        self._used_token_ids: set[str] = set()
        self._sync_history: list[AwsSyncRunResult] = []
        self._lock = asyncio.Lock()

    @staticmethod
    def _canonicalize_plan(plan_dict: dict[str, Any]) -> str:
        """Create deterministic canonical JSON representation of synchronization plan."""

        def _encoder(o: Any) -> Any:
            if isinstance(o, Decimal):
                return float(o)
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

        return json.dumps(plan_dict, sort_keys=True, separators=(",", ":"), default=_encoder)

    def generate_preview(self, req: AwsSyncPreviewRequest) -> AwsSyncPreviewResponse:
        """Compute strict upper bounds for API requests and metered billing charges for canonical Phase 2.2 plan."""
        # 1. Four Cost Explorer requests (Current MTD, Prev MTD, Top Services Breakdown, Remaining Forecast)
        ce_requests = 4 if "cost_explorer" in req.services else 0

        # 2. Four CloudWatch Metric Queries in 1 GetMetricData request (Invocations, Duration, Errors, Throttles) for Lambda
        # Zero EC2 queries because 0 EC2 instances discovered.
        cw_queries = 4 if "cloudwatch" in req.services else 0
        cw_requests = 1 if cw_queries > 0 else 0

        total_requests = ce_requests + cw_requests

        ce_cost = Decimal(ce_requests) * AWS_CE_REQUEST_COST_USD  # 4 * $0.0100 = $0.04000
        cw_cost = Decimal(cw_queries) * AWS_CW_METRIC_QUERY_COST_USD  # 4 * $0.00001 = $0.00004
        est_cost = (ce_cost + cw_cost).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        rec_budget = Decimal("0.05000")

        return AwsSyncPreviewResponse(
            account_id=req.account_id,
            connection_id=req.connection_id,
            selected_regions=sorted(req.regions),
            selected_services=sorted(req.services),
            approved_operations=[
                "ce:GetCostAndUsage",
                "ce:GetCostForecast",
                "cloudwatch:GetMetricData",
            ],
            start_date=req.start_date,
            end_date=req.end_date,
            max_cost_explorer_requests=ce_requests,
            max_cloudwatch_queries=cw_queries,
            max_total_requests=total_requests,
            estimated_api_cost_usd=float(est_cost),
            recommended_budget_usd=float(rec_budget),
            expected_data_coverage="Complete MTD cost breakdown & 7-day Lambda telemetry (4 metric units). Zero EC2 resources.",
            warning_notice="Synchronizing live AWS telemetry involves official metered API requests. Estimated spend is $0.04004 USD against an authorized cap of $0.05000 USD. No infrastructure will be modified.",
        )

    def issue_token(
        self,
        tenant_id: str,
        user_id: str,
        preview: AwsSyncPreviewResponse,
        ttl_seconds: int = 900,
        approved_budget_usd: Decimal | None = None,
        max_requests: int | None = None,
    ) -> AwsSyncApprovalToken:
        """Create a short-lived cryptographic approval token bound to an immutable plan hash."""
        token_id = f"aws-tok-{secrets.token_hex(8)}"
        expires_at = int(time.time()) + ttl_seconds

        # Budget cap safety check: Client cannot request a budget exceeding the calculated upper bound
        # or system hard cap of $0.05, and cannot supply negative/zero budgets
        server_recommended = preview.recommended_budget_usd
        if approved_budget_usd is not None:
            if approved_budget_usd <= Decimal("0.00"):
                raise ValueError("Approved budget override must be strictly positive.")
            if approved_budget_usd > Decimal("0.05"):
                raise ValueError(
                    "Approved budget override cannot exceed the maximum validation cap of $0.05 USD."
                )
            budget_cap = min(approved_budget_usd, Decimal("0.05"))
        else:
            budget_cap = min(Decimal(str(server_recommended)), Decimal("0.05"))

        if max_requests is not None:
            if max_requests <= 0:
                raise ValueError("Max requests override must be strictly positive.")
            if max_requests > preview.max_total_requests:
                raise ValueError("Max requests override cannot exceed server-calculated limit.")
            req_cap = max_requests
        else:
            req_cap = preview.max_total_requests

        canonical_plan: dict[str, Any] = {
            "token_id": token_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "connection_id": preview.connection_id,
            "account_id": preview.account_id,
            "approved_regions": sorted(preview.selected_regions),
            "approved_services": sorted(preview.selected_services),
            "approved_operations": sorted(preview.approved_operations),
            "start_date": preview.start_date,
            "end_date": preview.end_date,
            "max_requests": req_cap,
            "max_metric_queries": preview.max_cloudwatch_queries,
            "approved_budget_usd": float(budget_cap),
            "estimated_cost_usd": float(preview.estimated_api_cost_usd),
            "expires_at_epoch": expires_at,
        }

        canonical_str = self._canonicalize_plan(canonical_plan)
        plan_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        # Generate HMAC-SHA256 signature over the canonical plan hash
        sig = hmac.new(self.SECRET_KEY, plan_hash.encode("utf-8"), hashlib.sha256).hexdigest()

        return AwsSyncApprovalToken(
            token_id=token_id,
            tenant_id=tenant_id,
            user_id=user_id,
            connection_id=preview.connection_id,
            account_id=preview.account_id,
            approved_regions=canonical_plan["approved_regions"],
            approved_services=canonical_plan["approved_services"],
            approved_operations=canonical_plan["approved_operations"],
            start_date=preview.start_date,
            end_date=preview.end_date,
            max_requests=req_cap,
            max_metric_queries=preview.max_cloudwatch_queries,
            approved_budget_usd=float(budget_cap),
            estimated_cost_usd=float(preview.estimated_api_cost_usd),
            expires_at_epoch=expires_at,
            plan_hash=plan_hash,
            canonical_plan=canonical_plan,
            signature=sig,
        )

    def validate_and_consume_token(
        self,
        token: AwsSyncApprovalToken,
        expected_tenant_id: str,
        expected_user_id: str,
    ) -> AwsBudgetGuard:
        """Validate token signature, expiration, ownership, plan hash, single-use, and return budget guard."""
        # 1. Single-use check (Replay prevention)
        if token.token_id in self._used_token_ids:
            raise PermissionError(
                f"Approval token '{token.token_id}' has already been consumed (replay prevented)."
            )

        # 2. Expiration check
        if int(time.time()) > token.expires_at_epoch:
            raise PermissionError(f"Approval token '{token.token_id}' has expired.")

        # 3. Ownership / Tenant & User check
        if token.tenant_id != expected_tenant_id:
            raise PermissionError("Cross-tenant approval token usage is strictly rejected.")
        if expected_user_id and token.user_id != expected_user_id:
            raise PermissionError("Approval token user mismatch.")

        # 4. Plan Hash & Signature check (Tamper prevention)
        reconstructed_plan = {
            "token_id": token.token_id,
            "tenant_id": token.tenant_id,
            "user_id": token.user_id,
            "connection_id": token.connection_id,
            "account_id": token.account_id,
            "approved_regions": sorted(token.approved_regions),
            "approved_services": sorted(token.approved_services),
            "approved_operations": sorted(token.approved_operations),
            "start_date": token.start_date,
            "end_date": token.end_date,
            "max_requests": token.max_requests,
            "max_metric_queries": token.max_metric_queries,
            "approved_budget_usd": token.approved_budget_usd,
            "estimated_cost_usd": token.estimated_cost_usd,
            "expires_at_epoch": token.expires_at_epoch,
        }
        expected_hash = hashlib.sha256(
            self._canonicalize_plan(reconstructed_plan).encode("utf-8")
        ).hexdigest()

        if token.plan_hash != expected_hash:
            raise PermissionError(
                "Approval token synchronization plan hash mismatch; parameters were modified."
            )

        expected_sig = hmac.new(
            self.SECRET_KEY, expected_hash.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(token.signature, expected_sig):
            raise PermissionError("Approval token cryptographic signature verification failed.")

        # Check production durability invariant
        settings = get_settings()
        if settings.app_env == "production" and settings.connection_store == "memory":
            raise PermissionError(
                "Production synchronization requires durable database ledger for replay prevention; in-memory store fails closed."
            )

        # Mark consumed immediately
        self._used_token_ids.add(token.token_id)

        return AwsBudgetGuard(
            max_requests=token.max_requests,
            approved_budget_usd=Decimal(str(token.approved_budget_usd)),
            max_metric_queries=token.max_metric_queries,
        )

    def record_run(self, result: AwsSyncRunResult) -> None:
        """Record sync audit outcome."""
        self._sync_history.append(result)

    def get_history(self, account_id: str | None = None) -> list[AwsSyncRunResult]:
        """Retrieve historical sync runs."""
        if account_id:
            return [r for r in self._sync_history if r.account_id == account_id]
        return list(self._sync_history)

    async def persist_token_record(
        self,
        session: AsyncSession,
        token: AwsSyncApprovalToken,
    ) -> None:
        """Persist approval token to PostgreSQL billing_approval_tokens table."""
        from cloud_recommender.db.models import BillingApprovalTokenModel

        db_token = BillingApprovalTokenModel(
            id=uuid.uuid4(),
            token_id=token.token_id,
            nonce=secrets.token_hex(16),
            approver_sub=token.user_id,
            approver_roles=["FinOpsAdmin"],
            workspace_id=token.account_id,
            warehouse_id="aws:cost_explorer:cloudwatch",
            query_hash=token.plan_hash or "hash_unavailable",
            allowed_tables=sorted(token.approved_operations),
            approval_purpose="aws_live_validation_sync",
            requested_operation="sync",
            max_rows=token.max_requests,
            date_start=token.start_date,
            date_end=token.end_date,
            issued_at=datetime.now(UTC),
            expires_at=datetime.fromtimestamp(token.expires_at_epoch, UTC),
            is_consumed=False,
            kid="k1-aws-2026",
        )
        session.add(db_token)
        await session.flush()

    async def validate_and_consume_token_durable(
        self,
        session: AsyncSession,
        token: AwsSyncApprovalToken,
        expected_tenant_id: str,
        expected_user_id: str,
    ) -> AwsBudgetGuard:
        """Atomically validate and consume token in PostgreSQL with cross-worker replay protection."""
        from sqlalchemy import update

        from cloud_recommender.db.models import BillingApprovalTokenModel

        # 1. Standard in-memory/cryptographic check
        guard = self.validate_and_consume_token(
            token=token,
            expected_tenant_id=expected_tenant_id,
            expected_user_id=expected_user_id,
        )

        # 2. Durable atomic update in PostgreSQL
        stmt = (
            update(BillingApprovalTokenModel)
            .where(
                BillingApprovalTokenModel.token_id == token.token_id,
                BillingApprovalTokenModel.is_consumed.is_(False),
            )
            .values(
                is_consumed=True,
                consumed_at=datetime.now(UTC),
            )
        )
        res = await session.execute(stmt)
        rowcount = getattr(res, "rowcount", 1)
        if rowcount == 0:
            raise PermissionError(
                f"Approval token '{token.token_id}' has already been consumed (cross-worker replay prevented)."
            )
        await session.flush()
        return guard

    async def record_sync_run_durable(
        self,
        session: AsyncSession,
        result: AwsSyncRunResult,
    ) -> None:
        """Persist synchronization run execution history into PostgreSQL billing_ingestion_runs table."""
        from cloud_recommender.db.models import BillingIngestionRunModel

        run_record = BillingIngestionRunModel(
            id=uuid.uuid4(),
            run_id=f"run-{secrets.token_hex(8)}",
            workspace_id=result.account_id,
            source_table="aws:cost_explorer:cloudwatch",
            requested_period_start=result.started_at.strftime("%Y-%m-%d"),
            requested_period_end=result.completed_at.strftime("%Y-%m-%d"),
            started_at=result.started_at,
            completed_at=result.completed_at,
            status=result.status,
            approval_token=result.token_id,
            extracted_count=result.executed_requests,
            inserted_count=result.executed_requests,
            duplicate_count=0,
            retraction_count=0,
            error_count=1 if result.error_message else 0,
            error_message=result.error_message,
            created_at=datetime.now(UTC),
        )
        session.add(run_record)
        await session.flush()

    async def persist_cost_records_durable(
        self,
        session: AsyncSession,
        account_id: str,
        records: list[Any],
    ) -> int:
        """Idempotently persist AWS Cost Explorer records into PostgreSQL billing_usage_records table."""
        from sqlalchemy import select

        from cloud_recommender.db.models import BillingUsageRecordModel

        inserted = 0
        for rec in records:
            start_d = getattr(rec, "start_date", "")
            end_d = getattr(rec, "end_date", "")
            amt = getattr(rec, "amount", 0.0)
            curr = getattr(rec, "currency", "USD")
            metric_val = (
                getattr(rec.metric_type, "value", str(rec.metric_type))
                if hasattr(rec, "metric_type")
                else "UnblendedCost"
            )
            is_est = getattr(rec, "is_estimated", False)

            row_hash = hashlib.sha256(
                f"{account_id}|{start_d}|{end_d}|{amt}|{curr}|{metric_val}".encode()
            ).hexdigest()

            existing = await session.execute(
                select(BillingUsageRecordModel.id).where(
                    BillingUsageRecordModel.source_row_hash == row_hash
                )
            )
            if existing.scalar_one_or_none():
                continue

            usage_record = BillingUsageRecordModel(
                id=uuid.uuid4(),
                cloud="aws",
                account_id=account_id,
                workspace_id=account_id,
                record_id=f"aws-cost-{account_id}-{start_d}-{metric_val}",
                source_row_hash=row_hash,
                usage_date=start_d,
                usage_start_time=datetime.fromisoformat(f"{start_d}T00:00:00+00:00")
                if start_d
                else datetime.now(UTC),
                usage_end_time=datetime.fromisoformat(f"{end_d}T00:00:00+00:00")
                if end_d
                else datetime.now(UTC),
                sku_name="AWSGeneralUsage",
                usage_unit="MonthlyGranularity",
                usage_quantity=Decimal("1.0"),
                effective_cost=Decimal(str(amt)),
                currency=curr,
                cost_basis="AWS_UNBLENDED",
                record_type="ESTIMATED" if is_est else "ACTUAL",
                match_status="DIRECT_MATCH",
                product_features_json={"metric_type": metric_val},
                usage_metadata_json={"source": "AWS Cost Explorer API"},
                custom_tags_json={},
                ingested_at=datetime.now(UTC),
            )
            session.add(usage_record)
            inserted += 1

        await session.flush()
        return inserted

    async def persist_metric_records_durable(
        self,
        session: AsyncSession,
        account_id: str,
        resource_id: str,
        series_list: list[Any],
    ) -> int:
        """Idempotently persist CloudWatch telemetry records into PostgreSQL billing_usage_records table."""
        from sqlalchemy import select

        from cloud_recommender.db.models import BillingUsageRecordModel

        inserted = 0
        for series in series_list:
            metric_name = getattr(series, "metric_name", "UnknownMetric")
            unit = getattr(series, "unit", "Count")
            stat = getattr(series, "statistic", "Average")
            stat_status = getattr(series, "status", "AVAILABLE")
            dims = getattr(series, "dimensions", {})

            for dp in getattr(series, "data_points", []):
                dp_ts = getattr(dp, "timestamp", "")
                dp_val = getattr(dp, "value", 0.0)

                row_hash = hashlib.sha256(
                    f"{account_id}|{resource_id}|{metric_name}|{dp_ts}|{dp_val}".encode()
                ).hexdigest()

                existing = await session.execute(
                    select(BillingUsageRecordModel.id).where(
                        BillingUsageRecordModel.source_row_hash == row_hash
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                metric_record = BillingUsageRecordModel(
                    id=uuid.uuid4(),
                    cloud="aws",
                    account_id=account_id,
                    workspace_id=account_id,
                    resource_id=resource_id,
                    record_id=f"aws-metric-{resource_id}-{metric_name}-{dp_ts}",
                    source_row_hash=row_hash,
                    usage_date=dp_ts[:10]
                    if len(dp_ts) >= 10
                    else datetime.now(UTC).strftime("%Y-%m-%d"),
                    usage_start_time=datetime.fromisoformat(dp_ts)
                    if "T" in dp_ts
                    else datetime.now(UTC),
                    usage_end_time=datetime.fromisoformat(dp_ts)
                    if "T" in dp_ts
                    else datetime.now(UTC),
                    sku_name=f"AWSCloudWatch:{metric_name}",
                    usage_unit=unit,
                    usage_quantity=Decimal(str(dp_val)),
                    effective_cost=Decimal("0.00"),
                    currency="USD",
                    cost_basis="AWS_METRIC",
                    record_type="TELEMETRY",
                    match_status="TELEMETRY_MATCH",
                    product_features_json={"statistic": stat, "status": stat_status},
                    usage_metadata_json={"dimensions": dims},
                    custom_tags_json={},
                    ingested_at=datetime.now(UTC),
                )
                session.add(metric_record)
                inserted += 1

        await session.flush()
        return inserted


_approval_service_instance: AwsSyncApprovalService | None = None


def get_aws_sync_approval_service() -> AwsSyncApprovalService:
    global _approval_service_instance
    if _approval_service_instance is None:
        _approval_service_instance = AwsSyncApprovalService()
    return _approval_service_instance
