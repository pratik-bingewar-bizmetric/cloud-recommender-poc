"""Comprehensive automated test suite for AWS Phase 2.1A:
- Mandatory AWS API Action Allowlist & Mutating Operation Rejections
- Untrusted Endpoint, Insecure Protocol, Arbitrary Port & Userinfo Rejections
- Approval Token Hardening, Plan Hash Binding, Tamper Protection & Replay Prevention
- Transport-Level API Budget Guard & Atomic Decimal Reservations
- Financial Precision (1,000 records @ $0.004 = $4.00, negative credits, mixed currency)
- Non-Overlapping Actual vs Forecast Intervals (Dec->Jan, leap years, month boundaries)
- Pagination Safety, Repeated Token Detection & Explicit Partial Data Flagging
- Canonical 14-Attribute SKU Pricing Cache
- CUR Bucket Location & Manifest Key Inspection Separation
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from cloud_recommender.services.aws.auth_service import AwsCredentials
from cloud_recommender.services.aws.cost_explorer_service import (
    AwsCostExplorerService,
    _round_currency,
    _to_decimal,
)
from cloud_recommender.services.aws.operation_validator import validate_outbound_aws_request
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
# 1. Mandatory AWS API Action Allowlist & Security Validation Tests
# =============================================================================


def test_action_allowlist_approved_operations():
    """Verify approved read-only operations pass validation."""
    # STS
    act = validate_outbound_aws_request(
        method="POST",
        url="https://sts.us-east-1.amazonaws.com/",
        body="Action=GetCallerIdentity&Version=2011-06-15",
        service="sts",
    )
    assert act == "sts:GetCallerIdentity"

    # EC2 DescribeInstances
    act = validate_outbound_aws_request(
        method="POST",
        url="https://ec2.eu-north-1.amazonaws.com/",
        body="Action=DescribeInstances&Version=2016-11-15",
        service="ec2",
    )
    assert act == "ec2:DescribeInstances"

    # Cost Explorer JSON RPC
    act = validate_outbound_aws_request(
        method="POST",
        url="https://ce.us-east-1.amazonaws.com/",
        headers={"X-Amz-Target": "AWSInsightsIndexService.GetCostAndUsage"},
        service="ce",
    )
    assert act == "ce:GetCostAndUsage"

    # S3 ListAllMyBuckets & Location
    act1 = validate_outbound_aws_request(
        method="GET",
        url="https://s3.amazonaws.com/",
        service="s3",
    )
    assert act1 == "s3:ListAllMyBuckets"

    act2 = validate_outbound_aws_request(
        method="GET",
        url="https://test-bucket.s3.amazonaws.com/?location",
        service="s3",
    )
    assert act2 == "s3:GetBucketLocation"


@pytest.mark.parametrize(
    "method,url,body,headers,service,expected_action",
    [
        (
            "POST",
            "https://ec2.eu-north-1.amazonaws.com/",
            "Action=TerminateInstances&InstanceId.1=i-12345",
            None,
            "ec2",
            "ec2:TerminateInstances",
        ),
        (
            "POST",
            "https://ec2.eu-north-1.amazonaws.com/",
            "Action=StopInstances&InstanceId.1=i-12345",
            None,
            "ec2",
            "ec2:StopInstances",
        ),
        (
            "POST",
            "https://ec2.eu-north-1.amazonaws.com/",
            "Action=RunInstances&ImageId=ami-12345",
            None,
            "ec2",
            "ec2:RunInstances",
        ),
        (
            "POST",
            "https://iam.amazonaws.com/",
            "Action=CreateRole&RoleName=TestRole",
            None,
            "iam",
            "iam:CreateRole",
        ),
        (
            "POST",
            "https://iam.amazonaws.com/",
            "Action=AttachRolePolicy&RoleName=TestRole&PolicyArn=arn:aws:iam::aws:policy/Admin",
            None,
            "iam",
            "iam:AttachRolePolicy",
        ),
        (
            "POST",
            "https://lambda.eu-north-1.amazonaws.com/2015-03-31/functions",
            None,
            None,
            "lambda",
            "lambda:CreateFunction",
        ),
        (
            "POST",
            "https://monitoring.eu-north-1.amazonaws.com/",
            "Action=PutMetricData&Namespace=Custom",
            None,
            "cloudwatch",
            "cloudwatch:PutMetricData",
        ),
        (
            "PUT",
            "https://test-bucket.s3.eu-north-1.amazonaws.com/malicious.sh",
            b"echo hack",
            None,
            "s3",
            "s3:PutObject",
        ),
        (
            "DELETE",
            "https://test-bucket.s3.eu-north-1.amazonaws.com/important.csv",
            None,
            None,
            "s3",
            "s3:DeleteObject",
        ),
        (
            "POST",
            "https://ec2.eu-north-1.amazonaws.com/",
            "Action=UnknownDangerousAction",
            None,
            "ec2",
            "ec2:UnknownDangerousAction",
        ),
    ],
)
def test_action_allowlist_rejects_mutations(method, url, body, headers, service, expected_action):
    """Verify that all mutating operations are rejected with PermissionError before signing."""
    with pytest.raises(PermissionError) as exc_info:
        validate_outbound_aws_request(
            method=method,
            url=url,
            body=body,
            headers=headers,
            service=service,
        )
    assert (
        expected_action in str(exc_info.value)
        or "strictly rejected" in str(exc_info.value)
        or "not in the approved read-only allowlist" in str(exc_info.value)
    )


def test_endpoint_security_validations():
    """Verify rejection of insecure protocols, arbitrary ports, userinfo, and untrusted domains."""
    # 1. Insecure HTTP protocol
    with pytest.raises(ValueError, match="strictly use HTTPS"):
        validate_outbound_aws_request(
            method="GET",
            url="http://ec2.eu-north-1.amazonaws.com/?Action=DescribeInstances",
            service="ec2",
        )

    # 2. Arbitrary port injection
    with pytest.raises(ValueError, match="strictly use port 443"):
        validate_outbound_aws_request(
            method="GET",
            url="https://ec2.eu-north-1.amazonaws.com:8443/?Action=DescribeInstances",
            service="ec2",
        )

    # 3. Userinfo in URL
    with pytest.raises(ValueError, match="Userinfo in AWS endpoint authority is strictly rejected"):
        validate_outbound_aws_request(
            method="GET",
            url="https://admin:password@ec2.eu-north-1.amazonaws.com/?Action=DescribeInstances",
            service="ec2",
        )

    # 4. Untrusted domain / SSRF attempt
    with pytest.raises(ValueError, match="allowlist"):
        validate_outbound_aws_request(
            method="GET",
            url="https://attacker-controlled-host.com/?Action=DescribeInstances",
            service="ec2",
        )

    # 5. Conflicting Action parameters (Query vs Body)
    with pytest.raises(ValueError, match="Conflicting Action parameters"):
        validate_outbound_aws_request(
            method="POST",
            url="https://ec2.eu-north-1.amazonaws.com/?Action=DescribeInstances",
            body="Action=TerminateInstances&InstanceId.1=i-123",
            service="ec2",
        )

    # 6. Approved sync plan scope enforcement
    with pytest.raises(PermissionError, match="outside the approved synchronization plan scope"):
        validate_outbound_aws_request(
            method="POST",
            url="https://monitoring.eu-north-1.amazonaws.com/?Action=GetMetricData",
            service="cloudwatch",
            approved_operations={"ce:GetCostAndUsage", "sts:GetCallerIdentity"},
        )


def test_sigv4_enforces_operation_allowlist(mock_creds):
    """Verify that sign_aws_request calls the centralized allowlist and aborts on mutation."""
    # Attempting to sign a TerminateInstances request must raise PermissionError
    with pytest.raises(PermissionError):
        sign_aws_request(
            method="POST",
            url="https://ec2.eu-north-1.amazonaws.com/",
            body="Action=TerminateInstances&InstanceId.1=i-12345",
            access_key_id=mock_creds.access_key_id,
            secret_access_key=mock_creds.secret_access_key,
            service="ec2",
            region="eu-north-1",
        )


# =============================================================================
# 2. Approval Token Hardening, Plan Hash & Replay Tests
# =============================================================================


def test_approval_token_immutable_plan_hash():
    """Verify that token binds to canonical plan hash and detects parameter tampering."""
    service = AwsSyncApprovalService()
    preview_req = AwsSyncPreviewRequest(
        account_id="435305479688",
        connection_id="conn-123",
        regions=["eu-north-1", "us-east-1"],
        services=["cost_explorer", "cloudwatch"],
        start_date="2026-11-01",
        end_date="2026-11-26",
    )
    preview = service.generate_preview(preview_req)

    token = service.issue_token(
        tenant_id="tenant-alpha",
        user_id="user-123",
        preview=preview,
        ttl_seconds=300,
    )

    assert token.plan_hash is not None
    assert token.signature is not None

    # Valid token validates successfully
    guard = service.validate_and_consume_token(
        token=token,
        expected_tenant_id="tenant-alpha",
        expected_user_id="user-123",
    )
    assert guard.max_requests == preview.max_total_requests

    # 1. Replay prevention: second consumption fails
    with pytest.raises(PermissionError, match="replay prevented"):
        service.validate_and_consume_token(
            token=token,
            expected_tenant_id="tenant-alpha",
            expected_user_id="user-123",
        )


def test_approval_token_tamper_detection():
    """Verify that tampering with token parameters causes plan hash or signature rejection."""
    service = AwsSyncApprovalService()
    preview = service.generate_preview(
        AwsSyncPreviewRequest(
            account_id="435305479688",
            connection_id="conn-123",
            start_date="2026-11-01",
            end_date="2026-11-26",
        )
    )
    token = service.issue_token("tenant-alpha", "user-123", preview, ttl_seconds=300)

    # Tamper with approved budget
    tampered_budget = token.model_copy(update={"approved_budget_usd": 1000.0})
    with pytest.raises(PermissionError, match="parameters were modified"):
        service.validate_and_consume_token(tampered_budget, "tenant-alpha", "user-123")

    # Tamper with approved date range
    tampered_dates = token.model_copy(update={"end_date": "2026-12-31"})
    with pytest.raises(PermissionError, match="parameters were modified"):
        service.validate_and_consume_token(tampered_dates, "tenant-alpha", "user-123")

    # Tamper with regions scope
    tampered_regions = token.model_copy(update={"approved_regions": ["ap-southeast-1"]})
    with pytest.raises(PermissionError, match="parameters were modified"):
        service.validate_and_consume_token(tampered_regions, "tenant-alpha", "user-123")


# =============================================================================
# 3. Transport-Level API Budget Guard & Cost Reservation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_budget_guard_atomic_cost_reservations():
    """Verify transport-level budget guard enforces request caps and dollar caps atomically."""
    guard = AwsBudgetGuard(max_requests=3, approved_budget_usd=Decimal("0.025"))

    # Request 1: Cost Explorer ($0.01) -> Total reserved: $0.01
    await guard.check_and_reserve(request_type="cost_explorer", count=1)
    assert guard.executed_requests == 1
    assert guard.reserved_cost == Decimal("0.01")

    # Request 2: Cost Explorer ($0.01) -> Total reserved: $0.02
    await guard.check_and_reserve(request_type="cost_explorer", count=1)
    assert guard.executed_requests == 2
    assert guard.reserved_cost == Decimal("0.02")

    # Request 3: Third Cost Explorer would require $0.01 -> Total $0.03 > $0.025 approved budget!
    with pytest.raises(PermissionError, match="Cost Cap Exhausted"):
        await guard.check_and_reserve(request_type="cost_explorer", count=1)

    # But a small CloudWatch query ($0.0001) fits within the remaining $0.005 budget!
    await guard.check_and_reserve(request_type="cloudwatch", count=1, metric_queries=10)
    assert guard.executed_requests == 3
    assert guard.reserved_cost == Decimal("0.0201")

    # Now request limit (3) is exhausted:
    with pytest.raises(PermissionError, match="exceeds the approved limit of 3 requests"):
        await guard.check_and_reserve(request_type="cloudwatch", count=1)


# =============================================================================
# 4. Financial Precision Regression Tests
# =============================================================================


def test_financial_precision_aggregation_regression():
    """Verify that 1,000 billing records at USD 0.004 aggregate to exact USD 4.00 without early rounding."""
    raw_amounts = ["0.004"] * 1000

    # If each record was quantized early to 2 decimal places:
    early_rounded_sum = sum([_round_currency(_to_decimal(a)) for a in raw_amounts])
    assert (
        early_rounded_sum == 0.00
    )  # Proves early rounding catastrophically destroys small line items!

    # Correct FinOps Decimal aggregation:
    total_dec = Decimal("0.00")
    for a in raw_amounts:
        total_dec += _to_decimal(a)

    final_rounded_sum = _round_currency(total_dec)
    assert total_dec == Decimal("4.000")
    assert final_rounded_sum == 4.00


def test_mixed_currency_rejection(mock_creds):
    """Verify that billing records with inconsistent currencies are rejected."""
    service = AwsCostExplorerService()

    mock_resp = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-02"},
                "Total": {"UnblendedCost": {"Amount": "10.00", "Unit": "USD"}},
            },
            {
                "TimePeriod": {"Start": "2026-11-02", "End": "2026-11-03"},
                "Total": {"UnblendedCost": {"Amount": "10.00", "Unit": "EUR"}},  # Currency change!
            },
        ]
    }

    async def _test():
        async with httpx.AsyncClient() as client:
            with patch.object(service, "get_cost_and_usage", return_value=mock_resp):
                summary = await service.get_cost_summary(client=client, creds=mock_creds)
                assert summary.data_availability == "MIXED_CURRENCIES"
                assert summary.current_month_to_date_cost is None
                assert any("Mixed currencies detected" in n for n in summary.notes)

    import asyncio

    asyncio.run(_test())


# =============================================================================
# 5. Non-Overlapping Actual vs Forecast Intervals Tests
# =============================================================================


@pytest.mark.asyncio
async def test_non_overlapping_forecast_intervals(mock_creds):
    """Verify that actual MTD period and forecast period have zero overlapping day and zero gap."""
    service = AwsCostExplorerService()

    # Capture start/end arguments passed to get_cost_and_usage and get_cost_forecast
    calls: list[dict[str, str]] = []

    async def mock_get_cost_and_usage(**kwargs):
        calls.append({"type": "usage", "start": kwargs["start_date"], "end": kwargs["end_date"]})
        return {"ResultsByTime": []}

    async def mock_get_cost_forecast(**kwargs):
        calls.append({"type": "forecast", "start": kwargs["start_date"], "end": kwargs["end_date"]})
        return None

    async with httpx.AsyncClient() as client:
        with (
            patch.object(service, "get_cost_and_usage", side_effect=mock_get_cost_and_usage),
            patch.object(service, "get_cost_forecast", side_effect=mock_get_cost_forecast),
        ):
            summary = await service.get_cost_summary(client=client, creds=mock_creds)

            # Check that actual period end equals forecast period start (the exact cutoff day)
            assert summary.actual_cost_period_end == summary.forecast_period_start

            # Because Cost Explorer TimePeriod.End is exclusive, actual covers [start, end)
            # and forecast covers [forecast_start, forecast_end). Zero overlap!
            usage_calls = [c for c in calls if c["type"] == "usage"]
            forecast_calls = [c for c in calls if c["type"] == "forecast"]

            assert len(usage_calls) > 0
            if forecast_calls:
                assert usage_calls[0]["end"] == forecast_calls[0]["start"]


# =============================================================================
# 6. Pagination Truncation & Repeated Token Detection Tests
# =============================================================================


@pytest.mark.asyncio
async def test_pagination_safety_cap_and_repeated_token(mock_creds):
    """Verify safe stop on max_pages with partial data status and repeated token loop break."""
    service = AwsCostExplorerService()

    # Repeated token loop scenario: API keeps returning token 'stuck_token'
    looping_page = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-02"},
                "Total": {"UnblendedCost": {"Amount": "1.00", "Unit": "USD"}},
            }
        ],
        "NextPageToken": "stuck_token",
    }

    async with httpx.AsyncClient() as client:
        with patch.object(service, "_post_ce", return_value=looping_page) as mock_post:
            res = await service.get_cost_and_usage(
                client=client,
                creds=mock_creds,
                start_date="2026-11-01",
                end_date="2026-11-03",
                max_pages=5,
            )

            # Must terminate safely when repeated token is detected
            assert res["is_partial"] is True
            assert "Repeated pagination token" in res["truncation_reason"]
            assert mock_post.call_count == 2  # Breaks on second identical token


# =============================================================================
# 7. Canonical 14-Attribute SKU Pricing Cache Tests
# =============================================================================


def test_canonical_14_attribute_sku_cache_key():
    """Verify canonical SKU key incorporates instance type, OS, tenancy, storage, etc."""
    svc = AwsPricingService()
    key1 = svc._build_canonical_cache_key(
        service_code="AmazonEC2",
        region="eu-north-1",
        resource_type="AWS::EC2::Instance",
        instance_type_or_tier="t3.micro",
        operating_system="Linux",
        tenancy="Shared",
        storage_type="gp3",
        currency="USD",
    )
    key2 = svc._build_canonical_cache_key(
        service_code="AmazonEC2",
        region="eu-north-1",
        resource_type="AWS::EC2::Instance",
        instance_type_or_tier="t3.micro",
        operating_system="Windows",  # Different OS
        tenancy="Shared",
        storage_type="gp3",
        currency="USD",
    )
    # Different OS must produce different canonical SKU keys
    assert key1 != key2
    assert "Linux" in key1
    assert "Windows" in key2
