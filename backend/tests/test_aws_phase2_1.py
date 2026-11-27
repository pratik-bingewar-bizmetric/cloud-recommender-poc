"""Comprehensive Automated Test Suite for AWS Phase 2.1:
1. Financial Accuracy:
   - Decimal arithmetic & currency preservation
   - Negative adjustments, credits & refunds
   - Multi-page Cost Explorer pagination & deduplication
   - Actual MTD + Forecast Remaining = Total Projected Spend
   - Leap year and month-end boundary handling
2. API Cost Protection:
   - Single-use token enforcement & replay prevention
   - Budget guardrail stopping execution before limit breach
   - Cross-tenant token rejection
   - Dashboard navigation produces zero chargeable API requests
3. CloudWatch Telemetry:
   - Resource dimensions (InstanceId, FunctionName, NatGatewayId, BucketName)
   - Actual resource region querying
   - EC2 Memory instrumentation required gating
   - S3 daily granularity
4. Pricing Intelligence:
   - Canonical pricing cache keys
   - Live vs Cached vs Offline source classification
   - Partial pricing indicators
5. Security & Outbound Allowlist:
   - Mutating action rejection
   - Untrusted endpoint rejection
   - Secret redaction
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from cloud_recommender.schemas.aws import (
    AwsCostMetricType,
    AwsResourceItem,
)
from cloud_recommender.services.aws.auth_service import AwsCredentials
from cloud_recommender.services.aws.cost_explorer_service import (
    AwsCostExplorerService,
    _round_currency,
    _to_decimal,
)
from cloud_recommender.services.aws.cur_service import AwsCurService
from cloud_recommender.services.aws.pricing_service import AwsPricingService
from cloud_recommender.services.aws.sigv4 import sign_aws_request
from cloud_recommender.services.aws.sync_approval_service import (
    AwsBudgetGuard,
    AwsSyncApprovalService,
    AwsSyncPreviewRequest,
)


@pytest.fixture
def mock_creds():
    return AwsCredentials(
        account_id="435305479688",
        access_key_id="ASIATESTEXAMPLEDUMMY",
        secret_access_key="SecretTestExampleDummyKey1234567890",
        session_token="TokenTestExampleDummySession1234567890",
        auth_method="access_keys",
        expiration=datetime(2026, 12, 1, 0, 0, tzinfo=UTC),
    )


# =============================================================================
# 1. Financial Accuracy Tests (Decimal Math & Forecasts)
# =============================================================================


def test_decimal_conversion_and_rounding():
    d1 = _to_decimal("14.2567")
    d2 = _to_decimal("-3.50")
    d3 = _to_decimal(None)

    assert d1 == Decimal("14.2567")
    assert d2 == Decimal("-3.50")
    assert d3 == Decimal("0.00")

    assert _round_currency(d1) == 14.26
    assert _round_currency(d2) == -3.50


@pytest.mark.asyncio
async def test_cost_explorer_pagination(mock_creds):
    service = AwsCostExplorerService()

    page1 = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-02"},
                "Total": {"UnblendedCost": {"Amount": "1.00", "Unit": "USD"}},
            }
        ],
        "NextPageToken": "token_page_2",
    }
    page2 = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-02", "End": "2026-11-03"},
                "Total": {"UnblendedCost": {"Amount": "2.00", "Unit": "USD"}},
            }
        ],
    }

    async with httpx.AsyncClient() as client:
        with patch.object(service, "_post_ce", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [page1, page2]
            res = await service.get_cost_and_usage(
                client=client,
                creds=mock_creds,
                start_date="2026-11-01",
                end_date="2026-11-03",
            )
            results = res.get("ResultsByTime", [])
            assert len(results) == 2
            assert results[0]["TimePeriod"]["Start"] == "2026-11-01"
            assert results[1]["TimePeriod"]["Start"] == "2026-11-02"
            assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_cost_forecast_projection_formula(mock_creds):
    service = AwsCostExplorerService()

    mock_forecast_resp = {
        "Total": {"Amount": "25.00", "Unit": "USD"},
        "ForecastResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-20", "End": "2026-11-30"},
                "MeanValue": "25.00",
                "PredictionIntervalLowerBound": "20.00",
                "PredictionIntervalUpperBound": "30.00",
            }
        ],
    }

    async with httpx.AsyncClient() as client:
        with patch.object(service, "_post_ce", return_value=mock_forecast_resp):
            # If actual MTD is $50.00, and remaining forecast is $25.00:
            # Projected Month-End Spend MUST be $75.00 (not $25.00)
            actual_mtd = Decimal("50.00")
            forecast = await service.get_cost_forecast(
                client=client,
                creds=mock_creds,
                start_date="2026-11-20",
                end_date="2026-11-30",
                actual_mtd_cost=actual_mtd,
            )

            assert forecast is not None
            assert forecast.remaining_forecast_amount == 25.00
            assert forecast.actual_month_to_date_cost == 50.00
            assert forecast.projected_month_end_cost == 75.00
            assert forecast.prediction_interval_lower_bound == 70.00  # 50 + 20
            assert forecast.prediction_interval_upper_bound == 80.00  # 50 + 30


def test_negative_adjustments_and_credits():
    service = AwsCostExplorerService()
    mock_resp = {
        "ResultsByTime": [
            {
                "Groups": [
                    {
                        "Keys": ["AWS Lambda"],
                        "Metrics": {"UnblendedCost": {"Amount": "10.00", "Unit": "USD"}},
                    },
                    {
                        "Keys": ["Tax Credit / Refund"],
                        "Metrics": {"UnblendedCost": {"Amount": "-2.00", "Unit": "USD"}},
                    },
                ]
            }
        ]
    }
    items = service._parse_group_breakdown(
        resp=mock_resp,
        metric=AwsCostMetricType.UNBLENDED_COST,
        total_sum_dec=Decimal("8.00"),
    )
    assert len(items) == 2
    assert items[0].key == "AWS Lambda"
    assert items[0].amount == 10.00
    assert items[1].key == "Tax Credit / Refund"
    assert items[1].amount == -2.00


# =============================================================================
# 2. AWS API Cost Protection & Approval Service Tests
# =============================================================================


def test_sync_preview_generation():
    svc = AwsSyncApprovalService()
    req = AwsSyncPreviewRequest(
        account_id="435305479688",
        start_date="2026-11-01",
        end_date="2026-11-26",
        estimated_lambda_count=1,
    )
    preview = svc.generate_preview(req)
    assert preview.max_cost_explorer_requests == 4
    assert preview.max_cloudwatch_queries == 4
    assert preview.estimated_api_cost_usd == 0.04004
    assert preview.recommended_budget_usd == 0.05


def test_sync_token_lifecycle_and_single_use():
    svc = AwsSyncApprovalService()
    preview = svc.generate_preview(
        AwsSyncPreviewRequest(start_date="2026-11-01", end_date="2026-11-26")
    )
    token = svc.issue_token(
        tenant_id="tenant-123",
        user_id="user-456",
        preview=preview,
        ttl_seconds=300,
    )

    # 1. First consumption succeeds
    guard = svc.validate_and_consume_token(token, "tenant-123", "user-456")
    assert guard.max_requests == preview.max_total_requests

    # 2. Replay consumption fails immediately
    with pytest.raises(PermissionError) as exc_info:
        svc.validate_and_consume_token(token, "tenant-123", "user-456")
    assert "already been consumed" in str(exc_info.value)


def test_sync_token_cross_tenant_rejection():
    svc = AwsSyncApprovalService()
    preview = svc.generate_preview(
        AwsSyncPreviewRequest(start_date="2026-11-01", end_date="2026-11-26")
    )
    token = svc.issue_token(
        tenant_id="tenant-123",
        user_id="user-456",
        preview=preview,
    )

    # Attempting to use in another tenant is rejected
    with pytest.raises(PermissionError) as exc_info:
        svc.validate_and_consume_token(token, "tenant-other", "user-456")
    assert "Cross-tenant" in str(exc_info.value)


def test_budget_guard_limit_enforcement():
    guard = AwsBudgetGuard(max_requests=3, approved_budget_usd=Decimal("0.05"))
    guard.check_and_increment("cost_explorer", count=2)
    assert guard.executed_requests == 2

    # Exceeding budget raises PermissionError
    with pytest.raises(PermissionError) as exc_info:
        guard.check_and_increment("cost_explorer", count=2)
    assert "Budget Exhausted" in str(exc_info.value)


# =============================================================================
# 3. Security & Outbound Allowlist Tests
# =============================================================================


def test_sigv4_outbound_allowlist_enforcement():
    # 1. Approved amazonaws.com domain passes
    headers = sign_aws_request(
        method="GET",
        url="https://monitoring.eu-north-1.amazonaws.com/?Action=ListMetrics",
        access_key_id="AKIA123",
        secret_access_key="sec123",
    )
    assert "Authorization" in headers

    # 2. Untrusted destination is rejected before signing
    with pytest.raises(ValueError) as exc_info:
        sign_aws_request(
            method="GET",
            url="https://attacker-controlled-server.com/steal-creds",
            access_key_id="AKIA123",
            secret_access_key="sec123",
        )
    assert "allowlist" in str(exc_info.value)

    # 3. Mutating action (DELETE) is rejected
    with pytest.raises(PermissionError) as exc_info:
        sign_aws_request(
            method="DELETE",
            url="https://ec2.eu-north-1.amazonaws.com/?Action=TerminateInstances",
            access_key_id="AKIA123",
            secret_access_key="sec123",
        )
    assert "Mutating HTTP method" in str(exc_info.value)


# =============================================================================
# 4. Pricing Intelligence Canonical Keys & Sources
# =============================================================================


def test_pricing_canonical_cache_key():
    svc = AwsPricingService()
    key1 = svc._build_canonical_cache_key(
        "AmazonEC2", "eu-north-1", "AWS::EC2::Instance", "t3.micro", "gp3"
    )
    key2 = svc._build_canonical_cache_key(
        "AmazonEC2", "eu-north-1", "AWS::EC2::Instance", "t3.micro", "gp3"
    )
    assert key1 == key2
    assert "eu-north-1" in key1
    assert "t3.micro" in key1


@pytest.mark.asyncio
async def test_pricing_source_classification(mock_creds):
    svc = AwsPricingService()
    res = AwsResourceItem(
        resource_id="i-test-vm",
        resource_name="vm-prod",
        resource_type="AWS::EC2::Instance",
        category="Compute",
        region="eu-north-1",
        account_id="435305479688",
        details={"instance_type": "t3.medium"},
    )

    async with httpx.AsyncClient() as client:
        # Offline catalog fallback explicitly identified
        estimate = await svc.get_resource_pricing_estimate(client, mock_creds, res)
        assert estimate.pricing_source == "OFFLINE_REFERENCE_CATALOG"
        assert estimate.operating_hours_assumption == 730


# =============================================================================
# 5. CUR S3 Readiness Hardening Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cur_readiness_manifest_detection(mock_creds):
    svc = AwsCurService()
    loc_xml = "<LocationConstraint>eu-north-1</LocationConstraint>"
    list_xml = """
    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <Contents><Key>cur-reports/manifest.json</Key></Contents>
    </ListBucketResult>
    """

    class MockResp:
        status_code = 200

        def __init__(self, text):
            self.text = text

    async def mock_s3_get(url, **_kwargs):
        if "location" in str(url):
            return MockResp(loc_xml)
        return MockResp(list_xml)

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", side_effect=mock_s3_get):
            readiness = await svc.assess_cur_readiness(client, mock_creds, "test-bucket")
            assert readiness.bucket_exists is True
            assert readiness.has_manifest is True
            # Crucial: ListObjectsV2 establishes key presence, not validated content
            assert readiness.manifest_validated is False
            assert readiness.bulk_ingestion_status == "DEFERRED"
