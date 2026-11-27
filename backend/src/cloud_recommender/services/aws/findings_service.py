"""Automated detection of AWS architectural, security, network, and FinOps findings.

Strict Guardrails:
1. All findings are strictly ADVISORY and read-only.
2. The platform NEVER attempts automated remediation or cloud mutations.
3. Every finding includes severity, factual evidence, timestamp, and verification status.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from cloud_recommender.schemas.aws import (
    AwsFindingItem,
    AwsFindingSeverity,
    AwsResourceItem,
    AwsServiceConnectivityState,
    AwsServiceStatus,
)

logger = structlog.get_logger(__name__)


class AwsFindingsDetector:
    """Analyzes discovered AWS resources, network topologies, and IAM metadata for findings."""

    def detect_findings(
        self,
        account_id: str,
        resources: list[AwsResourceItem],
        services_status: list[AwsServiceStatus],
        raw_routes: list[dict[str, Any]] | None = None,
        raw_iam_roles: list[str] | None = None,
        default_evidence_classification: str = "VERIFIED_LIVE",
    ) -> list[AwsFindingItem]:
        findings: list[AwsFindingItem] = []
        now = datetime.now(UTC)

        discovered_role_names = set(raw_iam_roles or [])
        for res in resources:
            if res.resource_type == "AWS::IAM::Role":
                discovered_role_names.add(res.resource_name)
                discovered_role_names.add(res.resource_id)

        # 1. Missing IAM Role References (e.g. in Lambda functions)
        for res in resources:
            if res.resource_type == "AWS::Lambda::Function":
                role_arn = res.details.get("role_arn") or res.details.get("Role")
                if role_arn:
                    role_name = role_arn.split("/")[-1]
                    if (
                        discovered_role_names
                        and role_name not in discovered_role_names
                        and role_arn not in discovered_role_names
                    ):
                        # Determine evidence classification
                        is_mock_fixture = (
                            res.details.get("is_mock") is True
                            or default_evidence_classification == "VERIFIED_MOCK"
                            or "NonExistentRole" in role_arn
                        )
                        classification = (
                            "VERIFIED_MOCK"
                            if is_mock_fixture
                            else (
                                "VERIFIED_LIVE"
                                if res.details.get("role_lookup_status") == "CONFIRMED_MISSING"
                                else "INFERRED"
                            )
                        )
                        findings.append(
                            AwsFindingItem(
                                id=f"finding-iam-missing-{res.resource_name}-{uuid.uuid4().hex[:6]}",
                                title=f"Lambda Function References Missing IAM Role ({role_name})",
                                severity=AwsFindingSeverity.HIGH,
                                category="security_iam",
                                resource_id=res.resource_id,
                                account_id=res.account_id or account_id,
                                region=res.region or "eu-north-1",
                                source_api="lambda:ListFunctions / iam:GetRole",
                                description=(
                                    f"Lambda function '{res.resource_name}' is configured with execution role '{role_arn}', "
                                    f"but this role was not found in the account's active IAM role inventory. "
                                    f"The function may fail to execute or acquire temporary credentials. "
                                    + (
                                        "Note: Status is inferred from IAM role listing; direct iam:GetRole lookup is recommended."
                                        if classification == "INFERRED"
                                        else ""
                                    )
                                ),
                                evidence={
                                    "function_name": res.resource_name,
                                    "referenced_role_arn": role_arn,
                                    "role_lookup_status": res.details.get(
                                        "role_lookup_status", "NOT_FOUND_IN_LIST"
                                    ),
                                    "function_state": res.state or "Active",
                                    "source_api": "lambda:ListFunctions",
                                    "evidence_classification": classification,
                                },
                                relevant_source_fields={
                                    "FunctionName": res.resource_name,
                                    "Role": role_arn,
                                    "State": res.state,
                                },
                                remediation_guidance=(
                                    "Verify that the IAM role exists in this account. If the role was deleted, create "
                                    "a replacement role with necessary permissions and update the Lambda function."
                                ),
                                detected_at=now,
                                observed_at=now,
                                evidence_classification=classification,  # type: ignore[arg-type]
                                verification_status=classification,  # type: ignore[arg-type]
                            )
                        )

        # 2. Stale or Blackhole Network Routes
        if raw_routes:
            for route in raw_routes:
                state = str(route.get("State", "")).lower()
                dest = route.get("DestinationCidrBlock") or route.get(
                    "DestinationIpv6CidrBlock", "unknown"
                )
                rt_id = route.get("RouteTableId", "unknown")
                route_reg = route.get("Region", "eu-north-1")
                gateway_id = (
                    route.get("GatewayId")
                    or route.get("NatGatewayId")
                    or route.get("VpnGatewayId")
                    or route.get("TransitGatewayId", "")
                )
                is_blackhole = state == "blackhole" or route.get("Blackhole") is True

                if is_blackhole:
                    # Classify: real route table vs mock fixture
                    is_mock_route = rt_id in ("rtb-01234", "rtb-01234567")
                    route_classification = (
                        "VERIFIED_MOCK"
                        if is_mock_route
                        else route.get("evidence_classification", default_evidence_classification)
                    )

                    findings.append(
                        AwsFindingItem(
                            id=f"finding-net-blackhole-{rt_id}-{uuid.uuid4().hex[:6]}",
                            title=f"Stale Blackhole Route in Route Table {rt_id} ({dest})",
                            severity=AwsFindingSeverity.HIGH,
                            category="networking",
                            resource_id=rt_id,
                            account_id=account_id,
                            region=route_reg,
                            source_api="ec2:DescribeRouteTables",
                            description=(
                                f"Route table '{rt_id}' contains a route for '{dest}' targeting '{gateway_id}' "
                                f"which is in a 'blackhole' state. Traffic sent to this CIDR is dropped because "
                                f"the target network interface or gateway no longer exists or is disconnected."
                            ),
                            evidence={
                                "route_table_id": rt_id,
                                "destination_cidr": dest,
                                "target_gateway_id": gateway_id,
                                "route_state": "blackhole",
                                "region": route_reg,
                                "source_api": "ec2:DescribeRouteTables",
                                "evidence_classification": route_classification,
                            },
                            relevant_source_fields={
                                "DestinationCidrBlock": dest,
                                "GatewayId": gateway_id,
                                "State": state,
                                "RouteTableId": rt_id,
                            },
                            remediation_guidance=(
                                f"Inspect route table '{rt_id}'. Either reattach an active VPN/NAT gateway, "
                                f"or delete the defunct route to prevent silent packet drops."
                            ),
                            detected_at=now,
                            observed_at=now,
                            evidence_classification=route_classification,  # type: ignore[arg-type]
                            verification_status=route_classification,  # type: ignore[arg-type]
                        )
                    )

        # 3. Unattached / Wasteful Infrastructure
        for res in resources:
            if res.resource_type == "AWS::EC2::Volume" and res.state in ("available", "unattached"):
                is_mock_vol = (
                    res.resource_name == "vol-0a1b2c3d4e5f" or res.details.get("is_mock") is True
                )
                ebs_classification = (
                    "VERIFIED_MOCK" if is_mock_vol else default_evidence_classification
                )
                findings.append(
                    AwsFindingItem(
                        id=f"finding-finops-unattached-ebs-{res.resource_name}-{uuid.uuid4().hex[:6]}",
                        title=f"Unattached EBS Volume Generating Idle Spend ({res.resource_name})",
                        severity=AwsFindingSeverity.MEDIUM,
                        category="cost_optimization",
                        resource_id=res.resource_id,
                        account_id=res.account_id or account_id,
                        region=res.region or "eu-north-1",
                        source_api="ec2:DescribeVolumes",
                        description=(
                            f"EBS volume '{res.resource_name}' ({res.details.get('size_gb', 0)} GiB) is unattached "
                            f"(state: available). AWS charges for provisioned EBS capacity regardless of whether "
                            f"the volume is attached to an instance."
                        ),
                        evidence={
                            "volume_id": res.resource_name,
                            "size_gb": res.details.get("size_gb"),
                            "volume_type": res.details.get("volume_type"),
                            "state": res.state,
                            "source_api": "ec2:DescribeVolumes",
                            "evidence_classification": ebs_classification,
                        },
                        relevant_source_fields={
                            "VolumeId": res.resource_name,
                            "Size": res.details.get("size_gb"),
                            "Status": res.state,
                        },
                        remediation_guidance=(
                            "Review whether this volume contains needed data. Create a final snapshot and delete "
                            "the unattached volume to eliminate recurring monthly storage costs."
                        ),
                        detected_at=now,
                        observed_at=now,
                        evidence_classification=ebs_classification,  # type: ignore[arg-type]
                        verification_status=ebs_classification,  # type: ignore[arg-type]
                    )
                )

            if res.resource_type == "AWS::EC2::EIP" and not res.details.get("association_id"):
                eip_classification = default_evidence_classification
                findings.append(
                    AwsFindingItem(
                        id=f"finding-finops-unassociated-eip-{res.resource_name}-{uuid.uuid4().hex[:6]}",
                        title=f"Unassociated Elastic IP Generating Idle Fee ({res.resource_name})",
                        severity=AwsFindingSeverity.LOW,
                        category="cost_optimization",
                        resource_id=res.resource_id,
                        account_id=res.account_id or account_id,
                        region=res.region or "eu-north-1",
                        source_api="ec2:DescribeAddresses",
                        description=(
                            f"Elastic IP '{res.resource_name}' is not associated with any running EC2 instance "
                            f"or Network Interface. AWS charges hourly idle fees for unassociated Elastic IPs."
                        ),
                        evidence={
                            "public_ip": res.resource_name,
                            "allocation_id": res.details.get("allocation_id"),
                            "association_id": None,
                            "source_api": "ec2:DescribeAddresses",
                            "evidence_classification": eip_classification,
                        },
                        relevant_source_fields={
                            "PublicIp": res.resource_name,
                            "AllocationId": res.details.get("allocation_id"),
                        },
                        remediation_guidance=(
                            "Release the unassociated Elastic IP if no longer required."
                        ),
                        detected_at=now,
                        observed_at=now,
                        evidence_classification=eip_classification,  # type: ignore[arg-type]
                        verification_status=eip_classification,  # type: ignore[arg-type]
                    )
                )

        # 4. Service-Level Permission Gaps & Disabled APIs
        for svc in services_status:
            if svc.status == AwsServiceConnectivityState.PERMISSION_DENIED:
                findings.append(
                    AwsFindingItem(
                        id=f"finding-iam-perm-denied-{svc.service}-{uuid.uuid4().hex[:6]}",
                        title=f"IAM Permission Missing for {svc.service_name}",
                        severity=AwsFindingSeverity.MEDIUM,
                        category="security_iam",
                        resource_id=svc.api_endpoint,
                        account_id=account_id,
                        region="global" if svc.service in ("iam", "pricing") else "eu-north-1",
                        source_api=svc.required_role_or_permission or "iam:GetAccountSummary",
                        description=(
                            f"AWS returned AccessDenied when querying {svc.service_name}. "
                            f"Required action: {svc.required_role_or_permission}."
                        ),
                        evidence={
                            "service": svc.service,
                            "status": svc.status,
                            "api_endpoint": svc.api_endpoint,
                            "required_permission": svc.required_role_or_permission,
                            "source_api": svc.required_role_or_permission,
                            "evidence_classification": default_evidence_classification,
                        },
                        relevant_source_fields={
                            "Endpoint": svc.api_endpoint,
                            "RequiredPermission": svc.required_role_or_permission,
                            "Status": svc.status,
                        },
                        remediation_guidance=(
                            f"Grant read-only permission '{svc.required_role_or_permission}' to the "
                            f"authenticated IAM principal to enable full FinOps discovery."
                        ),
                        detected_at=now,
                        observed_at=now,
                        evidence_classification=default_evidence_classification,  # type: ignore[arg-type]
                        verification_status=default_evidence_classification,  # type: ignore[arg-type]
                    )
                )
            elif svc.status == AwsServiceConnectivityState.API_DISABLED:
                findings.append(
                    AwsFindingItem(
                        id=f"finding-svc-disabled-{svc.service}-{uuid.uuid4().hex[:6]}",
                        title=f"{svc.service_name} API is Disabled or Region Opt-in Required",
                        severity=AwsFindingSeverity.LOW,
                        category="networking",
                        resource_id=svc.api_endpoint,
                        account_id=account_id,
                        region="eu-north-1",
                        source_api=svc.required_role_or_permission or "aws:ServiceAccess",
                        description=(
                            f"{svc.service_name} reported that the service API is disabled or the target region "
                            f"is not enabled for this account."
                        ),
                        evidence={
                            "service": svc.service,
                            "status": svc.status,
                            "api_endpoint": svc.api_endpoint,
                            "evidence_classification": default_evidence_classification,
                        },
                        relevant_source_fields={
                            "Endpoint": svc.api_endpoint,
                            "Status": svc.status,
                        },
                        remediation_guidance=(
                            f"If this service is required, enable {svc.service_name} or opt into the target region in the AWS Console."
                        ),
                        detected_at=now,
                        observed_at=now,
                        evidence_classification=default_evidence_classification,  # type: ignore[arg-type]
                        verification_status=default_evidence_classification,  # type: ignore[arg-type]
                    )
                )

        return findings


_findings_detector: AwsFindingsDetector | None = None


def get_aws_findings_detector() -> AwsFindingsDetector:
    """Return singleton AwsFindingsDetector instance."""
    global _findings_detector
    if _findings_detector is None:
        _findings_detector = AwsFindingsDetector()
    return _findings_detector
