"""Comprehensive automated tests for AWS Phase 2:
- Cost Explorer Service (GetCostAndUsage, GetCostForecast, MTD, MoM, error handling)
- CloudWatch Metrics Service (GetMetricData, XML parsing, Lambda, EC2 instrumentation gating)
- Pricing Intelligence Service (Location mapping, caching, offline fallback)
- CUR Readiness Service (Bucket inspection, deferred bulk ingestion)
- AWS Phase 2 API Routes
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from cloud_recommender.schemas.aws import (
    AwsCostGranularity,
    AwsCostMetricType,
    AwsCostSummary,
    AwsPricingEstimate,
    AwsResourceItem,
)
from cloud_recommender.services.aws.auth_service import AwsCredentials
from cloud_recommender.services.aws.cloudwatch_service import AwsCloudWatchMetricsService
from cloud_recommender.services.aws.cost_explorer_service import (
    AwsCostExplorerError,
    AwsCostExplorerService,
)
from cloud_recommender.services.aws.cur_service import AwsCurService
from cloud_recommender.services.aws.pricing_service import (
    AwsPricingService,
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
# 1. Cost Explorer Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cost_explorer_get_cost_and_usage_success(mock_creds):
    service = AwsCostExplorerService()

    mock_response = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-02"},
                "Total": {"UnblendedCost": {"Amount": "1.25", "Unit": "USD"}},
                "Groups": [],
                "Estimated": False,
            },
            {
                "TimePeriod": {"Start": "2026-11-02", "End": "2026-11-03"},
                "Total": {"UnblendedCost": {"Amount": "1.35", "Unit": "USD"}},
                "Groups": [],
                "Estimated": False,
            },
        ]
    }

    async with httpx.AsyncClient() as client:
        with patch.object(service, "_post_ce", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            raw = await service.get_cost_and_usage(
                client=client,
                creds=mock_creds,
                start_date="2026-11-01",
                end_date="2026-11-03",
                granularity=AwsCostGranularity.DAILY,
                metric=AwsCostMetricType.UNBLENDED_COST,
            )

            records = raw.get("ResultsByTime", [])
            assert len(records) == 2
            assert records[0]["TimePeriod"]["Start"] == "2026-11-01"
            assert records[0]["Total"]["UnblendedCost"]["Amount"] == "1.25"
            assert records[0]["Total"]["UnblendedCost"]["Unit"] == "USD"
            assert records[1]["Total"]["UnblendedCost"]["Amount"] == "1.35"


@pytest.mark.asyncio
async def test_cost_explorer_get_cost_breakdown(mock_creds):
    service = AwsCostExplorerService()

    mock_response = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-26"},
                "Total": {},
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {"UnblendedCost": {"Amount": "45.50", "Unit": "USD"}},
                    },
                    {
                        "Keys": ["AWS Lambda"],
                        "Metrics": {"UnblendedCost": {"Amount": "0.15", "Unit": "USD"}},
                    },
                    {
                        "Keys": ["Amazon Simple Storage Service"],
                        "Metrics": {"UnblendedCost": {"Amount": "4.35", "Unit": "USD"}},
                    },
                ],
                "Estimated": False,
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        with patch.object(service, "_post_ce", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            raw = await service.get_cost_and_usage(
                client=client,
                creds=mock_creds,
                start_date="2026-11-01",
                end_date="2026-11-26",
                group_by=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            breakdown = service._parse_group_breakdown(
                raw,
                AwsCostMetricType.UNBLENDED_COST,
                total_sum=50.0,
            )

            assert len(breakdown) == 3
            # Sorted descending by cost
            assert breakdown[0].key == "Amazon Elastic Compute Cloud - Compute"
            assert breakdown[0].amount == 45.50
            assert breakdown[0].percentage > 90.0
            assert breakdown[1].key == "Amazon Simple Storage Service"
            assert breakdown[2].key == "AWS Lambda"


@pytest.mark.asyncio
async def test_cost_explorer_get_cost_summary_with_forecast(mock_creds):
    service = AwsCostExplorerService()

    async def mock_post_ce_side_effect(_client, _creds, action, payload):
        if action == "GetCostAndUsage":
            start = payload["TimePeriod"]["Start"]
            if "2026-10" in start or (datetime.now(UTC).month == 11 and "10-01" in start):
                return {
                    "ResultsByTime": [
                        {
                            "TimePeriod": {"Start": "2026-10-01", "End": "2026-10-31"},
                            "Total": {"UnblendedCost": {"Amount": "50.00", "Unit": "USD"}},
                            "Groups": [],
                        }
                    ]
                }
            else:
                return {
                    "ResultsByTime": [
                        {
                            "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-26"},
                            "Total": {"UnblendedCost": {"Amount": "60.00", "Unit": "USD"}},
                            "Groups": [
                                {
                                    "Keys": ["Amazon EC2"],
                                    "Metrics": {
                                        "UnblendedCost": {"Amount": "60.00", "Unit": "USD"}
                                    },
                                }
                            ],
                        }
                    ]
                }
        elif action == "GetCostForecast":
            return {
                "Total": {"Amount": "75.00", "Unit": "USD"},
                "ForecastResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2026-11-26", "End": "2026-11-30"},
                        "MeanValue": "15.00",
                        "PredictionIntervalLowerBound": "12.00",
                        "PredictionIntervalUpperBound": "18.00",
                    }
                ],
            }
        return {}

    async with httpx.AsyncClient() as client:
        with patch.object(service, "_post_ce", side_effect=mock_post_ce_side_effect):
            summary = await service.get_cost_summary(
                client=client,
                creds=mock_creds,
                metric=AwsCostMetricType.UNBLENDED_COST,
            )

            assert summary.current_month_to_date_cost is not None
            assert summary.currency == "USD"


@pytest.mark.asyncio
async def test_cost_explorer_error_classification(mock_creds):
    service = AwsCostExplorerService()

    class MockErrorResponse:
        status_code = 403
        text = '{"__type": "AccessDeniedException", "Message": "User is not authorized to perform: ce:GetCostAndUsage"}'

    async with httpx.AsyncClient() as client:
        with patch.object(client, "post", return_value=MockErrorResponse()):
            with pytest.raises(AwsCostExplorerError) as exc_info:
                await service._post_ce(
                    client=client,
                    creds=mock_creds,
                    action="GetCostAndUsage",
                    payload={},
                )
            assert exc_info.value.error_code == "PERMISSION_DENIED"
            assert "Access Denied" in exc_info.value.message


# =============================================================================
# 2. CloudWatch Metrics Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cloudwatch_get_metric_data_success(mock_creds):
    service = AwsCloudWatchMetricsService()

    xml_response = """
    <GetMetricDataResponse xmlns="http://monitoring.amazonaws.com/doc/2010-08-01/">
      <GetMetricDataResult>
        <MetricDataResults>
          <member>
            <Id>m0</Id>
            <Label>Invocations</Label>
            <StatusCode>Complete</StatusCode>
            <Timestamps>
              <member>2026-11-26T10:00:00Z</member>
              <member>2026-11-26T11:00:00Z</member>
            </Timestamps>
            <Values>
              <member>10.0</member>
              <member>15.0</member>
            </Values>
          </member>
        </MetricDataResults>
      </GetMetricDataResult>
      <ResponseMetadata>
        <RequestId>b3e7f9a1-0000-0000-0000-000000000000</RequestId>
      </ResponseMetadata>
    </GetMetricDataResponse>
    """

    class MockCwResponse:
        status_code = 200
        text = xml_response

    async with httpx.AsyncClient() as client:
        with patch.object(client, "post", return_value=MockCwResponse()):
            res = AwsResourceItem(
                resource_id="arn:aws:lambda:eu-north-1:435305479688:function:test-func",
                resource_name="test-func",
                resource_type="AWS::Lambda::Function",
                category="Serverless",
                region="eu-north-1",
                account_id="435305479688",
            )

            series_list = await service.get_resource_metrics(
                client=client,
                creds=mock_creds,
                resource=res,
                lookback_hours=24,
            )

            assert len(series_list) > 0
            invocations = next(s for s in series_list if s.metric_name == "Invocations")
            assert invocations.status == "AVAILABLE"
            assert len(invocations.data_points) == 2
            assert invocations.data_points[0].value == 10.0


@pytest.mark.asyncio
async def test_cloudwatch_ec2_metrics_instrumentation_gating(mock_creds):
    service = AwsCloudWatchMetricsService()

    async with httpx.AsyncClient() as client:
        with patch.object(
            service, "_fetch_single_metric_data", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = []

            res = AwsResourceItem(
                resource_id="i-0123456789abcdef0",
                resource_name="test-vm",
                resource_type="AWS::EC2::Instance",
                category="Compute",
                region="eu-north-1",
                account_id="435305479688",
            )

            series = await service.get_resource_metrics(
                client=client,
                creds=mock_creds,
                resource=res,
                lookback_hours=24,
            )

            cpu_series = next(s for s in series if s.metric_name == "CPUUtilization")
            memory_series = next(s for s in series if s.metric_name == "MemoryUtilization")

            assert cpu_series.status == "NO_DATA"
            # Crucial FinOps invariant: Memory on EC2 without agent is strictly INSTRUMENTATION_REQUIRED
            assert memory_series.status == "INSTRUMENTATION_REQUIRED"
            assert memory_series.latest_value is None


# =============================================================================
# 3. Pricing Intelligence Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_pricing_service_location_mapping_and_fallback(mock_creds):
    service = AwsPricingService()

    assert service.get_pricing_location("eu-north-1") == "EU (Stockholm)"
    assert service.get_pricing_location("us-east-1") == "US East (N. Virginia)"
    assert service.get_pricing_location("ap-south-1") == "Asia Pacific (Mumbai)"

    res = AwsResourceItem(
        resource_id="i-0123456789abcdef0",
        resource_name="t3.micro",
        resource_type="AWS::EC2::Instance",
        category="Compute",
        region="eu-north-1",
        account_id="435305479688",
        details={"instance_type": "t3.micro"},
    )

    class MockErrorResponse:
        status_code = 500
        text = "Internal Server Error"

    async with httpx.AsyncClient() as client:
        with patch.object(client, "post", return_value=MockErrorResponse()):
            estimate = await service.get_resource_pricing_estimate(
                client=client,
                creds=mock_creds,
                resource=res,
            )

            assert estimate is not None
            assert estimate.hourly_rate == 0.0416
            assert estimate.pricing_location == "EU (Stockholm)"
            assert estimate.is_list_price is True


@pytest.mark.asyncio
async def test_pricing_service_in_memory_cache(mock_creds):
    service = AwsPricingService()

    cached_est = AwsPricingEstimate(
        service="AmazonEC2",
        resource_type="AWS::EC2::Instance",
        region="eu-north-1",
        pricing_location="EU (Stockholm)",
        hourly_rate=0.0114,
        monthly_estimated_rate=8.322,
    )
    service._cache["AWS::EC2::Instance:eu-north-1:test-res"] = cached_est

    res = AwsResourceItem(
        resource_id="i-test-123",
        resource_name="test-res",
        resource_type="AWS::EC2::Instance",
        category="Compute",
        region="eu-north-1",
        account_id="435305479688",
    )

    async with httpx.AsyncClient() as client:
        estimate = await service.get_resource_pricing_estimate(
            client=client,
            creds=mock_creds,
            resource=res,
        )

        assert estimate.hourly_rate == 0.0114
        assert estimate.monthly_estimated_rate == 8.322


# =============================================================================
# 4. CUR Readiness Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cur_readiness_inspection(mock_creds):
    service = AwsCurService()

    loc_xml = """<LocationConstraint xmlns="http://s3.amazonaws.com/doc/2006-03-01/">eu-north-1</LocationConstraint>"""
    list_xml = """
    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <Name>finops-cost-reports-435305479688</Name>
      <Prefix></Prefix>
      <KeyCount>1</KeyCount>
      <Contents>
        <Key>daily-export/20261101-20261126/manifest.json</Key>
        <LastModified>2026-11-26T00:00:00.000Z</LastModified>
        <Size>1024</Size>
      </Contents>
    </ListBucketResult>
    """

    class MockLocResp:
        status_code = 200
        text = loc_xml

    class MockListResp:
        status_code = 200
        text = list_xml

    async def mock_s3_get(url, **_kwargs):
        if "location" in str(url):
            return MockLocResp()
        return MockListResp()

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", side_effect=mock_s3_get):
            readiness = await service.assess_cur_readiness(
                client=client,
                creds=mock_creds,
                target_bucket="finops-cost-reports-435305479688",
            )

            assert readiness.bucket_accessible is True
            assert readiness.bucket_region == "eu-north-1"
            assert readiness.bulk_ingestion_status == "DEFERRED"


# =============================================================================
# 5. AWS Phase 2 API Routes Tests
# =============================================================================


@pytest.mark.asyncio
async def test_aws_phase2_routes():
    from unittest.mock import MagicMock

    from httpx import ASGITransport, AsyncClient

    from cloud_recommender.core.auth import AuthenticatedUser, get_current_user
    from cloud_recommender.main import app

    # Override auth to simulate authenticated caller with proper scope
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        sub="test-user-id",
        oid="test-user-oid",
        tid="test-tenant",
        preferred_username="test@bizmetric.com",
        roles=["Reader"],
        scopes=["access_as_user"],
    )

    cost_mock = AsyncMock()
    cost_mock.auth_service = MagicMock()
    cost_mock.auth_service.parse_profile_credentials.return_value = {
        "account_id": "435305479688",
        "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "aws_session_token": None,
    }
    cost_mock.transport = None
    cost_mock.get_cost_summary.return_value = AwsCostSummary(
        account_id="435305479688",
        metric_type=AwsCostMetricType.UNBLENDED_COST,
        currency="USD",
        current_month_to_date_cost=42.50,
        data_availability="AVAILABLE",
    )
    cost_mock.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-02"},
                "Total": {"UnblendedCost": {"Amount": "10.0", "Unit": "USD"}},
                "Groups": [],
            }
        ]
    }
    from cloud_recommender.api.routes.aws import get_cost_service

    cost_mock._parse_group_breakdown = MagicMock(return_value=[])
    app.dependency_overrides[get_cost_service] = lambda: cost_mock

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Cost Summary
            resp = await client.get("/api/v1/aws/cost/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert "current_month_to_date_cost" in data
            assert data["currency"] == "USD"

            # 2. Cost Trend
            resp = await client.get(
                "/api/v1/aws/cost/trend?start_date=2026-11-01&end_date=2026-11-26"
            )
            assert resp.status_code == 200
            trend_data = resp.json()
            assert isinstance(trend_data, list)

            # 3. Cost Breakdown
            resp = await client.get(
                "/api/v1/aws/cost/breakdown?start_date=2026-11-01&end_date=2026-11-26&dimension=SERVICE"
            )
            assert resp.status_code == 200
            breakdown_data = resp.json()
            assert isinstance(breakdown_data, list)

            # 4. Metrics Summary
            resp = await client.get("/api/v1/aws/metrics/summary")
            assert resp.status_code == 200
            metrics_data = resp.json()
            assert "resources_metrics" in metrics_data
            assert "total_metrics_evaluated" in metrics_data

            # 5. Pricing Estimate
            resp = await client.get(
                "/api/v1/aws/pricing/estimate?resource_type=AWS::EC2::Instance&region=eu-north-1&resource_name=t3.micro"
            )
            assert resp.status_code == 200
            pricing_data = resp.json()
            assert "hourly_rate" in pricing_data
            assert "monthly_estimated_rate" in pricing_data

            # 6. CUR Readiness
            resp = await client.get("/api/v1/aws/cur/readiness")
            assert resp.status_code == 200
            cur_data = resp.json()
            assert cur_data["bulk_ingestion_status"] == "DEFERRED"

            # 7. Sync Health
            resp = await client.get("/api/v1/aws/sync/health")
            assert resp.status_code == 200
            health_data = resp.json()
            assert health_data["data_freshness_status"] in ["FRESH", "STALE", "PENDING", "ERROR"]
    finally:
        app.dependency_overrides.clear()
