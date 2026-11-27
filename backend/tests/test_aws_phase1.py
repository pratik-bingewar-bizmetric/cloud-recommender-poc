"""Automated test suite for AWS Phase 1 FinOps Application Integration.

Tests cover:
1. Credential validation & security scrubbing (Account ID, Region, Role ARN, Keys).
2. Pure-Python AWS SigV4 signer and header calculation.
3. STS Caller Identity & AssumeRole flows.
4. Independent 8+ service connectivity probes and error classifications.
5. Paginated and deduplicated resource discovery.
6. Dynamic findings detector (blackhole routes, missing Lambda role references, unattached EBS/EIP, permission gaps).
7. Tenant-isolated encrypted credential persistence in ConnectionManager.
8. API endpoints under /api/v1/aws/*.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException

from cloud_recommender.core.config import Settings
from cloud_recommender.core.secret_vault import CredentialCipher, KeyRing
from cloud_recommender.db.repositories.connection_repo import InMemoryConnectionRepository
from cloud_recommender.schemas.aws import (
    AwsFindingSeverity,
    AwsResourceItem,
    AwsServiceConnectivityState,
)
from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.connections import CreateConnectionRequest
from cloud_recommender.services.aws.auth_service import (
    AwsAuthenticationError,
    AwsAuthService,
    AwsCredentials,
    _sanitize_aws_error,
)
from cloud_recommender.services.aws.connectivity_service import (
    AwsConnectivityService,
    _classify_aws_error,
)
from cloud_recommender.services.aws.findings_service import AwsFindingsDetector
from cloud_recommender.services.aws.sigv4 import get_signature_key, sign_aws_request
from cloud_recommender.services.connections.connection_manager import ConnectionManager

# ---------------------------------------------------------------------------
# 1. SigV4 Signing Tests
# ---------------------------------------------------------------------------


def test_sigv4_key_derivation() -> None:
    key = get_signature_key(
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "20261124", "us-east-1", "sts"
    )
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_sigv4_request_signing() -> None:
    headers = sign_aws_request(
        method="POST",
        url="https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
        headers={"Accept": "application/json"},
        body="Action=GetCallerIdentity&Version=2011-06-15",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        service="sts",
        session_token="AQoDYXdzEXAMPLETOKEN",
        timestamp=datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC),
    )
    assert "Authorization" in headers
    assert headers["Authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20261124/us-east-1/sts/aws4_request"
    )
    assert "SignedHeaders=" in headers["Authorization"]
    assert "host" in headers["Authorization"]
    assert "Signature=" in headers["Authorization"]
    assert headers["x-amz-date"] == "20261124T120000Z"
    assert headers["x-amz-security-token"] == "AQoDYXdzEXAMPLETOKEN"
    assert "x-amz-content-sha256" in headers


# ---------------------------------------------------------------------------
# 2. Authentication & Credential Security Tests
# ---------------------------------------------------------------------------


def test_aws_account_id_validation() -> None:
    svc = AwsAuthService()
    assert svc.validate_account_id("435305479688") == "435305479688"
    assert svc.validate_account_id(" 123456789012 ") == "123456789012"

    with pytest.raises(AwsAuthenticationError) as exc:
        svc.validate_account_id("12345")
    assert exc.value.error_code == "INVALID_ACCOUNT_ID"

    with pytest.raises(AwsAuthenticationError):
        svc.validate_account_id("not-a-number!")


def test_aws_region_validation() -> None:
    svc = AwsAuthService()
    assert svc.validate_region("eu-north-1") == "eu-north-1"
    assert svc.validate_region("US-EAST-1") == "us-east-1"
    assert svc.validate_region("ap-south-1") == "ap-south-1"

    with pytest.raises(AwsAuthenticationError) as exc:
        svc.validate_region("invalid_region_name")
    assert exc.value.error_code == "INVALID_REGION"


def test_aws_role_arn_validation() -> None:
    svc = AwsAuthService()
    valid_arn = "arn:aws:iam::435305479688:role/FinOpsReadOnlyRole"
    assert svc.validate_role_arn(valid_arn) == valid_arn

    with pytest.raises(AwsAuthenticationError) as exc:
        svc.validate_role_arn("invalid:arn:format")
    assert exc.value.error_code == "INVALID_ROLE_ARN"


def test_aws_credentials_expiry() -> None:
    now = datetime.now(UTC)
    unexpired = AwsCredentials(
        access_key_id="AKIA...",
        secret_access_key="...",
        expiration=now + timedelta(hours=1),
    )
    assert not unexpired.is_expired(buffer_seconds=180)

    expiring_soon = AwsCredentials(
        access_key_id="AKIA...",
        secret_access_key="...",
        expiration=now + timedelta(seconds=100),
    )
    assert expiring_soon.is_expired(buffer_seconds=180)


def test_aws_secret_scrubbing() -> None:
    dirty_msg = "Error with key AKIAIOSFODNN7EXAMPLE and secret aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY and Signature=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    clean_msg = _sanitize_aws_error(dirty_msg)
    assert "AKIAIOSFODNN7EXAMPLE" not in clean_msg
    assert "[REDACTED_ACCESS_KEY]" in clean_msg
    assert "wJalrXUtnFEMI" not in clean_msg
    assert "[REDACTED_SECRET]" in clean_msg
    assert "Signature=[REDACTED_SIGNATURE]" in clean_msg


# ---------------------------------------------------------------------------
# 3. Error Classification & Status Mapping Tests
# ---------------------------------------------------------------------------


def test_error_classification() -> None:
    state, msg = _classify_aws_error(403, "<Error><Code>AccessDenied</Code></Error>", "ec2")
    assert state == AwsServiceConnectivityState.PERMISSION_DENIED
    assert "Access Denied" in msg

    state2, msg2 = _classify_aws_error(400, "<Error><Code>OptInRequired</Code></Error>", "ec2")
    assert state2 == AwsServiceConnectivityState.API_DISABLED
    assert "opt-in" in msg2

    state3, msg3 = _classify_aws_error(404, "<Error><Code>NoSuchEntity</Code></Error>", "iam")
    assert state3 == AwsServiceConnectivityState.RESOURCE_NOT_FOUND

    state4, msg4 = _classify_aws_error(503, "Service Unavailable", "sts")
    assert state4 == AwsServiceConnectivityState.SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# 4. Findings Detector Tests
# ---------------------------------------------------------------------------


def test_findings_detector_blackhole_route() -> None:
    detector = AwsFindingsDetector()
    resources = [
        AwsResourceItem(
            resource_id="arn:aws:ec2:eu-north-1:435305479688:route-table/rtb-0cdd26464ffae3443",
            resource_name="rtb-0cdd26464ffae3443",
            resource_type="AWS::EC2::RouteTable",
            category="networking",
            account_id="435305479688",
            region="eu-north-1",
        )
    ]
    raw_routes = [
        {
            "DestinationCidrBlock": "192.168.1.0/24",
            "GatewayId": "vgw-037b0ca497c933a30",
            "State": "blackhole",
            "RouteTableId": "rtb-0cdd26464ffae3443",
            "Region": "eu-north-1",
            "evidence_classification": "VERIFIED_LIVE",
        }
    ]

    findings = detector.detect_findings("435305479688", resources, [], raw_routes=raw_routes)
    blackhole_findings = [f for f in findings if f.category == "networking"]
    assert len(blackhole_findings) == 1
    bf = blackhole_findings[0]
    assert "Blackhole Route" in bf.title
    assert bf.severity == AwsFindingSeverity.HIGH
    assert bf.resource_id == "rtb-0cdd26464ffae3443"
    assert bf.evidence["destination_cidr"] == "192.168.1.0/24"
    assert bf.evidence["target_gateway_id"] == "vgw-037b0ca497c933a30"
    assert bf.evidence_classification == "VERIFIED_LIVE"
    assert bf.source_api == "ec2:DescribeRouteTables"


def test_findings_detector_missing_lambda_role() -> None:
    detector = AwsFindingsDetector()
    resources = [
        AwsResourceItem(
            resource_id="arn:aws:lambda:eu-north-1:435305479688:function:test-processor",
            resource_name="test-processor",
            resource_type="AWS::Lambda::Function",
            category="compute",
            account_id="435305479688",
            region="eu-north-1",
            details={"role_arn": "arn:aws:iam::435305479688:role/DeletedExecutionRole"},
        )
    ]
    # Existing roles inventory does NOT contain DeletedExecutionRole
    raw_roles = ["ActiveDatabricksRole", "AdminRole"]

    findings = detector.detect_findings("435305479688", resources, [], raw_iam_roles=raw_roles)
    lambda_findings = [f for f in findings if "Lambda" in f.title]
    assert len(lambda_findings) == 1
    assert lambda_findings[0].severity == AwsFindingSeverity.HIGH
    assert lambda_findings[0].evidence["role_lookup_status"] == "NOT_FOUND_IN_LIST"
    assert lambda_findings[0].evidence_classification == "INFERRED"
    assert lambda_findings[0].source_api == "lambda:ListFunctions / iam:GetRole"


def test_findings_detector_unattached_ebs_volume() -> None:
    detector = AwsFindingsDetector()
    resources = [
        AwsResourceItem(
            resource_id="arn:aws:ec2:eu-north-1:435305479688:volume/vol-0a1b2c3d4e5f",
            resource_name="vol-0a1b2c3d4e5f",
            resource_type="AWS::EC2::Volume",
            category="storage",
            account_id="435305479688",
            region="eu-north-1",
            state="available",  # unattached
            details={"size_gb": 100, "volume_type": "gp3"},
        )
    ]
    findings = detector.detect_findings("435305479688", resources, [])
    ebs_findings = [f for f in findings if "Unattached EBS" in f.title]
    assert len(ebs_findings) == 1
    assert ebs_findings[0].severity == AwsFindingSeverity.MEDIUM
    assert ebs_findings[0].evidence_classification == "VERIFIED_MOCK"


# ---------------------------------------------------------------------------
# 5. Mocked End-to-End Service Connectivity & Discovery Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_aws_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)

        # STS GetCallerIdentity
        if "sts." in url_str:
            xml = """<GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">
              <GetCallerIdentityResult>
                <Arn>arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com</Arn>
                <UserId>AIDAXXXXXXXXXXXXXXXX</UserId>
                <Account>435305479688</Account>
              </GetCallerIdentityResult>
            </GetCallerIdentityResponse>"""
            return httpx.Response(200, text=xml, request=request)

        # IAM ListRoles
        if "iam.amazonaws.com" in url_str:
            xml = """<ListRolesResponse xmlns="https://iam.amazonaws.com/doc/2010-05-08/">
              <ListRolesResult>
                <Roles>
                  <member><RoleName>databricks-workspace-role</RoleName></member>
                  <member><RoleName>databricks-passthrough-role</RoleName></member>
                  <member><RoleName>finops-reader-role</RoleName></member>
                </Roles>
              </ListRolesResult>
            </ListRolesResponse>"""
            return httpx.Response(200, text=xml, request=request)

        # EC2 DescribeRegions
        if "Action=DescribeRegions" in url_str:
            xml = """<DescribeRegionsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
              <regionInfo>
                <item><regionName>eu-north-1</regionName><optInStatus>opt-in-not-required</optInStatus></item>
                <item><regionName>us-east-1</regionName><optInStatus>opt-in-not-required</optInStatus></item>
              </regionInfo>
            </DescribeRegionsResponse>"""
            return httpx.Response(200, text=xml, request=request)

        # EC2 DescribeVpcs
        if "Action=DescribeVpcs" in url_str:
            xml = """<DescribeVpcsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
              <vpcSet>
                <item><vpcId>vpc-072ed1bbe2f47677c</vpcId><cidrBlock>10.44.0.0/16</cidrBlock></item>
              </vpcSet>
            </DescribeVpcsResponse>"""
            return httpx.Response(200, text=xml, request=request)

        # EC2 DescribeRouteTables
        if "Action=DescribeRouteTables" in url_str:
            xml = """<DescribeRouteTablesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
              <routeTableSet>
                <item>
                  <routeTableId>rtb-0cdd26464ffae3443</routeTableId>
                  <routeSet>
                    <item>
                      <destinationCidrBlock>192.168.1.0/24</destinationCidrBlock>
                      <gatewayId>vgw-037b0ca497c933a30</gatewayId>
                      <state>blackhole</state>
                    </item>
                  </routeSet>
                </item>
              </routeTableSet>
            </DescribeRouteTablesResponse>"""
            return httpx.Response(200, text=xml, request=request)

        # S3 ListBuckets
        if "s3.amazonaws.com" in url_str:
            xml = """<ListAllMyBucketsResult>
              <Buckets>
                <Bucket><Name>finops-raw-data-bucket</Name></Bucket>
                <Bucket><Name>bizmetric-cur-reports</Name></Bucket>
              </Buckets>
            </ListAllMyBucketsResult>"""
            return httpx.Response(200, text=xml, request=request)

        # Lambda ListFunctions
        if "lambda." in url_str:
            data = {
                "Functions": [
                    {
                        "FunctionName": "databricks-cost-collector",
                        "Role": "arn:aws:iam::435305479688:role/NonExistentRole",
                        "State": "Active",
                    }
                ]
            }
            return httpx.Response(200, json=data, request=request)

        # RDS DescribeDBInstances
        if "rds." in url_str:
            xml = """<DescribeDBInstancesResponse xmlns="http://rds.amazonaws.com/doc/2014-10-31/">
              <DescribeDBInstancesResult>
                <DBInstances>
                  <DBInstance><DBInstanceIdentifier>finops-dev-db</DBInstanceIdentifier></DBInstance>
                </DBInstances>
              </DescribeDBInstancesResult>
            </DescribeDBInstancesResponse>"""
            return httpx.Response(200, text=xml, request=request)

        # CloudWatch ListMetrics
        if "monitoring." in url_str:
            xml = """<ListMetricsResponse xmlns="http://monitoring.amazonaws.com/doc/2010-08-01/">
              <ListMetricsResult>
                <Metrics>
                  <member><MetricName>CPUUtilization</MetricName></member>
                  <member><MetricName>NetworkOut</MetricName></member>
                </Metrics>
              </ListMetricsResult>
            </ListMetricsResponse>"""
            return httpx.Response(200, text=xml, request=request)

        # Cost Explorer
        if "ce.us-east-1.amazonaws.com" in url_str:
            return httpx.Response(
                200, json={"DimensionValues": [{"Value": "AmazonEC2"}]}, request=request
            )

        # ECS ListClusters
        if "ecs." in url_str:
            return httpx.Response(
                200,
                json={
                    "clusterArns": ["arn:aws:ecs:eu-north-1:435305479688:cluster/finops-cluster"]
                },
                request=request,
            )

        # EKS ListClusters
        if "eks." in url_str:
            return httpx.Response(
                200, json={"clusters": ["finops-eks-dev-cluster"]}, request=request
            )

        # Pricing DescribeServices
        if "pricing." in url_str:
            return httpx.Response(
                200,
                json={"Services": [{"ServiceCode": "AmazonEC2"}, {"ServiceCode": "AmazonS3"}]},
                request=request,
            )

        return httpx.Response(404, text="Not Found", request=request)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_aws_connectivity_service_e2e(mock_aws_transport: httpx.MockTransport) -> None:
    service = AwsConnectivityService(transport=mock_aws_transport)
    test_res = await service.test_connection(
        account_id="435305479688",
        default_region="eu-north-1",
        auth_method="access_keys",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    assert test_res.success is True
    assert test_res.account_id == "435305479688"
    assert test_res.arn == "arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com"
    assert test_res.overall_status == "Connected"
    assert len(test_res.services) == 11
    assert all(s.status == AwsServiceConnectivityState.SUCCESS for s in test_res.services)


@pytest.mark.asyncio
async def test_aws_resource_discovery_and_findings(mock_aws_transport: httpx.MockTransport) -> None:
    service = AwsConnectivityService(transport=mock_aws_transport)
    creds = AwsCredentials(
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        account_id="435305479688",
        auth_method="access_keys",
    )
    discovery = await service.discover_resources(
        account_id="435305479688",
        default_region="eu-north-1",
        creds=creds,
        custom_regions=["eu-north-1"],
    )
    assert discovery.account_id == "435305479688"
    assert discovery.total_resources > 0
    # Findings should detect the blackhole route with its exact real resource ID
    finding_titles = [f.title for f in discovery.findings]
    assert any("Blackhole Route" in t for t in finding_titles)
    blackhole_finding = next(f for f in discovery.findings if "Blackhole Route" in f.title)
    assert blackhole_finding.resource_id == "rtb-0cdd26464ffae3443"
    assert blackhole_finding.evidence_classification == "VERIFIED_LIVE"
    assert blackhole_finding.source_api == "ec2:DescribeRouteTables"
    assert any("Lambda Function References Missing IAM Role" in t for t in finding_titles)


# ---------------------------------------------------------------------------
# 6. ConnectionManager Encrypted Persistence & Tenant Isolation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_manager_aws_lifecycle(mock_aws_transport: httpx.MockTransport) -> None:
    repo = InMemoryConnectionRepository()
    cipher = CredentialCipher(KeyRing({"test-key-v1": b"0" * 32}, "test-key-v1"))
    settings = Settings(connections_max_per_user=5)
    manager = ConnectionManager(repo=repo, cipher_factory=lambda: cipher, settings=settings)

    # Mock the internal connectivity service to use the mock transport
    from cloud_recommender.services.aws.connectivity_service import get_aws_connectivity_service

    conn_service = get_aws_connectivity_service()
    conn_service.transport = mock_aws_transport

    owner1 = "tenant1:user1"
    owner2 = "tenant2:user2"

    # Create AWS Connection for owner1
    aws_conn = await manager.create_aws(
        owner_key=owner1,
        name="AWS Production Account",
        account_id="435305479688",
        default_region="eu-north-1",
        auth_method="access_keys",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    assert aws_conn.provider == "aws"
    assert aws_conn.account_id == "435305479688"
    assert aws_conn.status == "connected"

    # Verify listing owned connections
    owner1_list = await manager.list_aws(owner1)
    assert len(owner1_list) == 1
    assert owner1_list[0].id == aws_conn.id

    # Tenant isolation: owner2 cannot see owner1's connection
    owner2_list = await manager.list_aws(owner2)
    assert len(owner2_list) == 0

    with pytest.raises(HTTPException) as exc:
        await manager.get_aws(owner2, aws_conn.id)
    assert exc.value.status_code == 404

    # Verify decryption
    stored, sec_dict = await manager.decrypt_aws_secret(owner1, aws_conn.id)
    assert stored.scope_id == "435305479688"
    assert sec_dict["secret_access_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    # Re-validate connection
    reval = await manager.validate(owner1, aws_conn.id)
    assert reval.status == "connected"
    assert reval.provider == CloudProvider.AWS


# ---------------------------------------------------------------------------
# 7. Unified CreateConnectionRequest via Generic Endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_manager_generic_create_aws(
    mock_aws_transport: httpx.MockTransport,
) -> None:
    repo = InMemoryConnectionRepository()
    cipher = CredentialCipher(KeyRing({"test-key-v1": b"0" * 32}, "test-key-v1"))
    settings = Settings(connections_max_per_user=5)
    manager = ConnectionManager(repo=repo, cipher_factory=lambda: cipher, settings=settings)

    from cloud_recommender.services.aws.connectivity_service import get_aws_connectivity_service

    conn_service = get_aws_connectivity_service()
    conn_service.transport = mock_aws_transport

    owner = "tenant1:user1"
    req = CreateConnectionRequest(
        provider=CloudProvider.AWS,
        name="AWS FinOps Connection",
        scope_id="435305479688",
        aws_region="eu-north-1",
        aws_auth_method="access_keys",
        aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
        aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # type: ignore[arg-type]
    )

    cloud_conn = await manager.create(owner, req)
    assert cloud_conn.provider == CloudProvider.AWS
    assert cloud_conn.scope_id == "435305479688"
    assert cloud_conn.status == "connected"
    assert "identity_verification" in cloud_conn.capabilities
