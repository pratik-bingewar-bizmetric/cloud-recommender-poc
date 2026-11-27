"""Centralized fail-closed AWS outbound operation allowlist and security validator.

Validates every outbound AWS API request before SigV4 signing and network dispatch against:
1. AWS service and canonical endpoint structure.
2. Exact approved read-only API operation (Query Action, JSON X-Amz-Target, REST path).
3. Request protocol (enforcing HTTPS only; rejecting arbitrary ports and userinfo).
4. Outbound partition and signing region.
5. Strict rejection of any mutating operation (POST/PUT/DELETE/PATCH mutations).
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

# Approved AWS host suffixes
ALLOWED_AWS_HOST_SUFFIXES = (
    ".amazonaws.com",
    ".amazonaws.com.cn",
)

# Comprehensive allowlist of approved read-only AWS actions across all integrated services
APPROVED_AWS_READ_ONLY_ACTIONS: frozenset[str] = frozenset(
    {
        # 1. AWS STS (Security Token Service)
        "sts:GetCallerIdentity",
        # 2. AWS IAM (Identity and Access Management)
        "iam:ListRoles",
        "iam:GetAccountSummary",
        "iam:ListAccountAliases",
        # 3. AWS EC2 (Elastic Compute Cloud) - Strictly Describe* read-only
        "ec2:DescribeRegions",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeRouteTables",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeVolumes",
        "ec2:DescribeInstances",
        "ec2:DescribeNatGateways",
        # 4. AWS S3 (Simple Storage Service) - Read-only bucket & discovery
        "s3:ListAllMyBuckets",
        "s3:ListBucket",
        "s3:ListObjectsV2",
        "s3:GetBucketLocation",
        # 5. AWS Lambda - Read-only discovery
        "lambda:ListFunctions",
        "lambda:GetFunction",
        # 6. AWS RDS (Relational Database Service) - Read-only discovery
        "rds:DescribeDBInstances",
        # 7. AWS CloudWatch (Monitoring) - Read-only metrics & telemetry
        "cloudwatch:ListMetrics",
        "cloudwatch:GetMetricData",
        # 8. AWS Cost Explorer - Read-only spend & forecast queries
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "ce:GetDimensionValues",
        "ce:GetTags",
        # 9. AWS ECS (Elastic Container Service) - Read-only cluster discovery
        "ecs:ListClusters",
        "ecs:DescribeClusters",
        # 10. AWS EKS (Elastic Kubernetes Service) - Read-only cluster discovery
        "eks:ListClusters",
        "eks:DescribeCluster",
        # 11. AWS Price List API - Read-only retail pricing catalog
        "pricing:GetProducts",
        "pricing:DescribeServices",
        "pricing:GetAttributeValues",
        # 12. AWS Cost and Usage Reports (CUR) & Data Exports
        "cur:DescribeReportDefinitions",
        "bcm-data-exports:ListExports",
    }
)

# Explicit blocklist of dangerous mutation actions for defense-in-depth error messaging
EXPLICIT_MUTATION_ACTIONS: frozenset[str] = frozenset(
    {
        "ec2:terminateinstances",
        "ec2:stopinstances",
        "ec2:runinstances",
        "ec2:rebootinstances",
        "iam:createrole",
        "iam:attachrolepolicy",
        "iam:putrolepolicy",
        "iam:createuser",
        "lambda:createfunction",
        "lambda:updatefunctioncode",
        "lambda:deletefunction",
        "cloudwatch:putmetricdata",
        "cloudwatch:deletemetric",
        "s3:putobject",
        "s3:deleteobject",
        "s3:createbucket",
        "s3:deletebucket",
        "rds:createdbinstance",
        "rds:deletedbinstance",
    }
)


def _extract_query_action(url: str, body: bytes | str | None) -> str | None:
    """Extract Action parameter from URL query string or x-www-form-urlencoded body.

    Rejects duplicate or conflicting Action parameters.
    """
    parsed = urlsplit(url)
    actions: list[str] = []
    if parsed.query:
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query_actions = [v for k, v in pairs if k == "Action"]
        actions.extend(query_actions)

    if body:
        body_str = body.decode("utf-8", errors="ignore") if isinstance(body, bytes) else str(body)
        if "Action=" in body_str:
            pairs = parse_qsl(body_str, keep_blank_values=True)
            body_actions = [v for k, v in pairs if k == "Action"]
            actions.extend(body_actions)

    if not actions:
        return None

    # Check for duplicate conflicting Action parameters
    unique_actions = set(actions)
    if len(unique_actions) > 1:
        raise ValueError(
            f"Conflicting Action parameters detected in request: {sorted(unique_actions)}"
        )

    return actions[0]


def _extract_json_target_action(headers: dict[str, str] | None) -> str | None:
    """Extract action from X-Amz-Target header for JSON RPC services.

    Rejects duplicate or conflicting X-Amz-Target headers.
    """
    if not headers:
        return None

    targets: list[str] = []
    for k, v in headers.items():
        if k.lower() == "x-amz-target":
            targets.append(v.strip())

    if not targets:
        return None

    if len(set(targets)) > 1:
        raise ValueError(f"Conflicting X-Amz-Target headers detected: {sorted(set(targets))}")

    target = targets[0]
    # Target is formatted as ServiceName.ActionName (e.g. AWSInsightsIndexService.GetCostAndUsage)
    parts = target.split(".")
    return parts[-1] if parts else target


def _extract_rest_action(service: str, method: str, url: str) -> str:
    """Derive canonical action for REST-style AWS APIs (S3, Lambda, EKS).

    Note:
        AWS EKS uses a RESTful API architecture over HTTPS with resource-oriented URIs
        (e.g., GET /clusters, GET /clusters/{name}), distinct from Query or JSON-RPC protocols.
    """
    parsed = urlsplit(url)
    path = parsed.path or "/"
    query = parsed.query or ""

    if service == "s3":
        if method.upper() == "GET":
            if "location" in query:
                return "s3:GetBucketLocation"
            if "list-type=2" in query or "prefix=" in query:
                return "s3:ListObjectsV2"
            host = (parsed.hostname or "").lower()
            if host in (
                "s3.amazonaws.com",
                "s3.eu-north-1.amazonaws.com",
                "s3.us-east-1.amazonaws.com",
            ) and path in ("", "/"):
                return "s3:ListAllMyBuckets"
            return "s3:ListObjectsV2"
        elif method.upper() == "PUT":
            return "s3:PutObject"
        elif method.upper() == "DELETE":
            return "s3:DeleteObject"
        return f"s3:Unknown{method.upper()}"

    if service == "lambda":
        if method.upper() == "GET":
            if "/functions" in path:
                if path.endswith("/functions") or path.endswith("/functions/"):
                    return "lambda:ListFunctions"
                return "lambda:GetFunction"
        elif method.upper() == "POST":
            return "lambda:CreateFunction"
        elif method.upper() == "DELETE":
            return "lambda:DeleteFunction"
        return f"lambda:Unknown{method.upper()}"

    if service == "eks":
        if method.upper() == "GET":
            if "/clusters" in path:
                if path.endswith("/clusters") or path.endswith("/clusters/"):
                    return "eks:ListClusters"
                return "eks:DescribeCluster"
        elif method.upper() == "POST":
            return "eks:CreateCluster"
        elif method.upper() == "DELETE":
            return "eks:DeleteCluster"
        return f"eks:Unknown{method.upper()}"

    return f"{service}:Unknown"


def validate_outbound_aws_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
    service: str = "sts",
    region: str = "us-east-1",
    partition: str = "aws",
    connection_owner: str | None = None,
    approved_operations: set[str] | list[str] | frozenset[str] | None = None,
) -> str:
    """Centralized fail-closed validation of outbound AWS operations.

    Raises:
        ValueError: If URL structure, protocol, port, or userinfo violates security rules.
        PermissionError: If operation is not on the approved read-only allowlist, attempts mutation,
                         or falls outside the approved synchronization plan scope.

    Returns:
        The validated canonical action (e.g. 'ce:GetCostAndUsage', 'ec2:DescribeInstances').
    """
    _ = connection_owner
    if not region or not isinstance(region, str):
        raise ValueError("Invalid AWS signing region.")
    # 1. Enforce HTTPS Protocol
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise ValueError(
            f"Insecure protocol '{parsed.scheme}': AWS outbound requests must strictly use HTTPS."
        )

    # 2. Reject Userinfo (e.g. https://user:pass@host)
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise ValueError("Untrusted URL: Userinfo in AWS endpoint authority is strictly rejected.")

    # 3. Reject Arbitrary Ports (Must be standard 443 or None)
    if parsed.port is not None and parsed.port != 443:
        raise ValueError(
            f"Arbitrary port '{parsed.port}': Outbound AWS endpoints must strictly use port 443."
        )

    # 4. Enforce Hostname Structure & Domain Allowlist
    host = (parsed.hostname or "").lower()
    if not host or not any(host.endswith(suffix) for suffix in ALLOWED_AWS_HOST_SUFFIXES):
        raise ValueError(
            f"Untrusted endpoint host '{host}': Outbound requests must target approved amazonaws.com allowlist domains."
        )

    # 5. Partition Verification
    if partition not in ("aws", "aws-cn", "aws-us-gov"):
        raise ValueError(f"Invalid AWS partition '{partition}'.")

    # 6. Extract Action Based on Protocol and Host
    host_parts = host.split(".")
    detected_svc: str | None = None
    if host_parts:
        candidate = host_parts[0]
        if candidate in (
            "sts",
            "iam",
            "ec2",
            "s3",
            "lambda",
            "rds",
            "monitoring",
            "cloudwatch",
            "ce",
            "pricing",
            "ecs",
            "eks",
            "cur",
            "bcm-data-exports",
        ):
            detected_svc = candidate
        elif "s3" in host:
            detected_svc = "s3"

    service_lower = (detected_svc if (service == "sts" and detected_svc) else service).lower()
    action_name: str | None = None

    if service_lower in ("sts", "iam", "ec2", "rds", "cloudwatch", "monitoring"):
        # Query Protocol APIs
        raw_action = _extract_query_action(url, body)
        if raw_action:
            svc_prefix = "cloudwatch" if service_lower == "monitoring" else service_lower
            action_name = f"{svc_prefix}:{raw_action}"
    elif service_lower in ("ce", "cost_explorer", "pricing", "ecs", "cur", "bcm-data-exports"):
        # JSON RPC APIs
        raw_action = _extract_json_target_action(headers)
        if raw_action:
            svc_prefix = "ce" if service_lower in ("ce", "cost_explorer") else service_lower
            action_name = f"{svc_prefix}:{raw_action}"
    elif service_lower in ("s3", "lambda", "eks"):
        # REST APIs
        action_name = _extract_rest_action(service_lower, method, url)

    # If action could not be resolved from headers or query, fallback to REST extraction
    if not action_name:
        action_name = _extract_rest_action(service_lower, method, url)

    # 7. Check for Explicit Disallowed Mutations
    if method.upper() in ("DELETE", "PUT", "PATCH") and not (
        service_lower == "s3" and method.upper() in ("PUT", "DELETE")
    ):
        raise PermissionError(
            f"Mutating HTTP method '{method.upper()}' is strictly rejected by FinOps safety controls."
        )

    action_lower = action_name.lower()
    if (
        action_lower in EXPLICIT_MUTATION_ACTIONS
        or any(
            mut in action_lower
            for mut in ("terminate", "delete", "create", "put", "attach", "stopinstance")
        )
        and not any(safe in action_lower for safe in ("list", "describe", "get"))
    ):
        raise PermissionError(
            f"Mutating AWS action '{action_name}' is strictly rejected by FinOps safety controls."
        )

    # 8. Check Against Central Fail-Closed Allowlist
    if action_name not in APPROVED_AWS_READ_ONLY_ACTIONS:
        raise PermissionError(
            f"AWS operation '{action_name}' is not in the approved read-only allowlist. Request rejected."
        )

    # 9. Verify Scope Against Approved Synchronization Plan (if provided)
    if approved_operations is not None and action_name not in approved_operations:
        raise PermissionError(
            f"AWS operation '{action_name}' is outside the approved synchronization plan scope: {sorted(approved_operations)}."
        )

    return action_name
