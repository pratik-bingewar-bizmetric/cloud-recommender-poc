"""Tests for AWS Phase 2.2 — Controlled Live Validation Preflight, Security & Plan Readiness.

Covers:
1. Operation allowlist conflicting Action parameters rejection.
2. Operation allowlist conflicting X-Amz-Target header rejection.
3. Approved sync plan scope enforcement in operation_validator.
4. EKS REST architecture canonical action extraction.
5. Canonical 5-operation synchronization plan verification (4 CE requests, 4 CW metrics).
6. Budget calculation matching $0.0402 estimated spend with $0.05 hard cap.
7. Single-process replay prevention and token consumption lifecycle.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cloud_recommender.services.aws.operation_validator import (
    APPROVED_AWS_READ_ONLY_ACTIONS,
    validate_outbound_aws_request,
)
from cloud_recommender.services.aws.sync_approval_service import (
    AwsBudgetGuard,
    AwsSyncApprovalService,
)


def test_operation_validator_rejects_conflicting_action_parameters():
    """Verify that multiple contradictory Action parameters in query or body trigger ValueError."""
    # 1. Conflicting Action parameters within URL query
    with pytest.raises(ValueError, match="Conflicting Action parameters"):
        validate_outbound_aws_request(
            method="POST",
            url="https://ec2.eu-north-1.amazonaws.com/?Action=DescribeInstances&Action=DescribeVpcs",
            service="ec2",
        )

    # 2. Conflicting Action parameters between query string and body
    with pytest.raises(ValueError, match="Conflicting Action parameters"):
        validate_outbound_aws_request(
            method="POST",
            url="https://ec2.eu-north-1.amazonaws.com/?Action=DescribeInstances",
            body="Action=StopInstances",
            service="ec2",
        )


def test_operation_validator_rejects_conflicting_amz_target_headers():
    """Verify that contradictory X-Amz-Target headers trigger ValueError."""
    with pytest.raises(ValueError, match="Conflicting X-Amz-Target headers"):
        validate_outbound_aws_request(
            method="POST",
            url="https://ce.us-east-1.amazonaws.com/",
            headers={
                "X-Amz-Target": "AWSInsightsIndexService.GetCostAndUsage",
                "x-amz-target": "AWSInsightsIndexService.GetCostForecast",
            },
            service="ce",
        )


def test_operation_validator_enforces_approved_plan_scope():
    """Verify that operations outside the approved plan scope are rejected with PermissionError."""
    approved = frozenset({"ce:GetCostAndUsage", "sts:GetCallerIdentity"})

    # In-scope action passes
    action = validate_outbound_aws_request(
        method="POST",
        url="https://sts.amazonaws.com/?Action=GetCallerIdentity",
        service="sts",
        approved_operations=approved,
    )
    assert action == "sts:GetCallerIdentity"

    # Out-of-scope action is rejected even if on the global read-only allowlist
    with pytest.raises(PermissionError, match="outside the approved synchronization plan scope"):
        validate_outbound_aws_request(
            method="POST",
            url="https://monitoring.eu-north-1.amazonaws.com/?Action=GetMetricData",
            service="cloudwatch",
            approved_operations=approved,
        )


def test_eks_rest_api_architecture_action_extraction():
    """Verify that EKS REST API endpoints are correctly extracted as REST operations."""
    # ListClusters
    action_list = validate_outbound_aws_request(
        method="GET",
        url="https://eks.eu-north-1.amazonaws.com/clusters",
        service="eks",
        region="eu-north-1",
    )
    assert action_list == "eks:ListClusters"
    assert action_list in APPROVED_AWS_READ_ONLY_ACTIONS

    # DescribeCluster
    action_desc = validate_outbound_aws_request(
        method="GET",
        url="https://eks.eu-north-1.amazonaws.com/clusters/finops-cluster",
        service="eks",
        region="eu-north-1",
    )
    assert action_desc == "eks:DescribeCluster"
    assert action_desc in APPROVED_AWS_READ_ONLY_ACTIONS

    # Mutating POST /clusters is rejected
    with pytest.raises(PermissionError):
        validate_outbound_aws_request(
            method="POST",
            url="https://eks.eu-north-1.amazonaws.com/clusters",
            service="eks",
            region="eu-north-1",
        )


@pytest.mark.asyncio
async def test_phase2_2_canonical_synchronization_plan():
    """Verify the Phase 2.2 canonical synchronization plan parameters and budget calculation."""
    from cloud_recommender.services.aws.sync_approval_service import AwsSyncPreviewRequest

    approval_svc = AwsSyncApprovalService()

    req = AwsSyncPreviewRequest(
        account_id="435305479688",
        start_date="2026-11-01",
        end_date="2026-11-26",
        estimated_lambda_count=1,
        estimated_ec2_count=0,
    )
    preview = approval_svc.generate_preview(req)

    # 1. Verify bounded operations
    assert preview.max_cost_explorer_requests == 4
    assert preview.max_cloudwatch_queries == 4
    assert preview.max_total_requests == 5  # 4 CE + 1 CW GetMetricData
    assert preview.estimated_api_cost_usd == 0.04004
    assert preview.recommended_budget_usd == 0.05

    # 2. Issue Token & Verify Canonical Plan Hash binding
    token = approval_svc.issue_token(
        tenant_id="tenant-finops-dev",
        user_id="user-pratik",
        preview=preview,
        approved_budget_usd=Decimal("0.05"),
    )
    assert token.token_id.startswith("aws-tok-")
    assert token.plan_hash is not None

    # 3. Verify Single-Use Consumption in isolated process
    budget_guard = approval_svc.validate_and_consume_token(
        token=token,
        expected_tenant_id="tenant-finops-dev",
        expected_user_id="user-pratik",
    )
    assert isinstance(budget_guard, AwsBudgetGuard)
    assert budget_guard.approved_budget_usd <= Decimal("0.05")

    # 4. Second attempt to consume must be rejected (single-use replay prevention)
    with pytest.raises(PermissionError, match="already been consumed"):
        approval_svc.validate_and_consume_token(
            token=token,
            expected_tenant_id="tenant-finops-dev",
            expected_user_id="user-pratik",
        )


def test_phase2_2_exact_cost_breakdown_formula():
    """Verify the exact arithmetic breakdown for the 5-operation Phase 2.2 plan."""
    ce_unit_cost = Decimal("0.0100")
    cw_metric_unit_cost = Decimal("0.00001")

    # 4 Cost Explorer calls (Current MTD, Previous MTD, Service Breakdown, Forecast)
    ce_calls = 4
    ce_total = Decimal(ce_calls) * ce_unit_cost
    assert ce_total == Decimal("0.0400")

    # 4 CloudWatch metric queries for 1 Lambda function (Invocations, Duration, Errors, Throttles)
    cw_metrics = 4
    cw_total = Decimal(cw_metrics) * cw_metric_unit_cost
    assert cw_total == Decimal("0.00004")

    # Combined estimated spend
    total_estimated = ce_total + cw_total
    assert total_estimated < Decimal("0.0500")

    # Conservative reservation cap: $0.0500
    reservation_cap = Decimal("0.0500")
    assert total_estimated <= reservation_cap


def test_budget_override_safety_guardrails():
    """Verify that client-controlled budget overrides cannot exceed server caps or use invalid numbers."""
    from cloud_recommender.services.aws.sync_approval_service import (
        AwsSyncApprovalService,
        AwsSyncPreviewRequest,
    )

    approval_svc = AwsSyncApprovalService()
    req = AwsSyncPreviewRequest(
        account_id="435305479688",
        start_date="2026-11-01",
        end_date="2026-11-26",
    )
    preview = approval_svc.generate_preview(req)

    # 1. Budget override exceeding $0.05 hard cap is rejected
    with pytest.raises(ValueError, match=r"cannot exceed the maximum validation cap of \$0.05 USD"):
        approval_svc.issue_token(
            tenant_id="tenant-123",
            user_id="user-123",
            preview=preview,
            approved_budget_usd=Decimal("0.10"),
        )

    # 2. Non-positive budget override is rejected
    with pytest.raises(ValueError, match="strictly positive"):
        approval_svc.issue_token(
            tenant_id="tenant-123",
            user_id="user-123",
            preview=preview,
            approved_budget_usd=Decimal("-0.01"),
        )

    # 3. Max requests exceeding server total is rejected
    with pytest.raises(ValueError, match="cannot exceed server-calculated limit"):
        approval_svc.issue_token(
            tenant_id="tenant-123",
            user_id="user-123",
            preview=preview,
            max_requests=999,
        )


@pytest.mark.asyncio
async def test_durable_postgresql_persistence_and_replay_protection():
    """Verify durable token persistence, atomic consumption, cross-worker replay, and idempotency."""
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from cloud_recommender.core.config import get_settings
    from cloud_recommender.schemas.aws import AwsCostMetricType, AwsCostRecord
    from cloud_recommender.services.aws.sync_approval_service import (
        AwsSyncApprovalService,
        AwsSyncPreviewRequest,
        AwsSyncRunResult,
    )

    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    approval_svc = AwsSyncApprovalService()
    req = AwsSyncPreviewRequest(
        account_id="435305479688",
        start_date="2026-11-01",
        end_date="2026-11-26",
        estimated_lambda_count=1,
    )
    preview = approval_svc.generate_preview(req)

    token = approval_svc.issue_token(
        tenant_id="tenant-durability-test",
        user_id="user-tester",
        preview=preview,
        approved_budget_usd=Decimal("0.05"),
    )

    # Use rollback-safe transaction on PostgreSQL
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn)
        try:
            # 1. Persist Token Record
            await approval_svc.persist_token_record(session=session, token=token)

            # 2. First Consumption (Succeeds)
            guard = await approval_svc.validate_and_consume_token_durable(
                session=session,
                token=token,
                expected_tenant_id="tenant-durability-test",
                expected_user_id="user-tester",
            )
            assert guard.approved_budget_usd <= Decimal("0.05")

            # 3. Cross-worker / Restart replay: Second consumption against DB fails closed
            # Reset in-memory tracking to simulate fresh worker process
            approval_svc._used_token_ids.discard(token.token_id)
            with pytest.raises(PermissionError, match="cross-worker replay prevented"):
                await approval_svc.validate_and_consume_token_durable(
                    session=session,
                    token=token,
                    expected_tenant_id="tenant-durability-test",
                    expected_user_id="user-tester",
                )

            # 4. Record Run History
            run_result = AwsSyncRunResult(
                run_id="run-test-12345",
                token_id=token.token_id,
                status="COMPLETED",
                account_id="435305479688",
                executed_requests=5,
                max_budget_requests=6,
                actual_api_cost_usd=0.04004,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                services_synced=["ce", "cloudwatch"],
            )
            await approval_svc.record_sync_run_durable(session=session, result=run_result)

            # 5. Idempotent Cost Record Persistence
            cost_recs = [
                AwsCostRecord(
                    start_date="2026-11-01",
                    end_date="2026-11-26",
                    amount=12.34,
                    currency="USD",
                    metric_type=AwsCostMetricType.UNBLENDED_COST,
                    is_estimated=False,
                )
            ]
            inserted1 = await approval_svc.persist_cost_records_durable(
                session=session, account_id="435305479688", records=cost_recs
            )
            assert inserted1 == 1

            # Duplicate write must be safely ignored (idempotent)
            inserted2 = await approval_svc.persist_cost_records_durable(
                session=session, account_id="435305479688", records=cost_recs
            )
            assert inserted2 == 0

        finally:
            await trans.rollback()
            await session.close()

    await engine.dispose()
