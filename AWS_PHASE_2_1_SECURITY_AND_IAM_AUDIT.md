# AWS Phase 2.1 — Security and IAM Audit Report

> **Repository:** `cloud-recommender-poc`  
> **AWS Account ID:** `435305479688`  
> **Status:** AUDITED, HARDENED & ENFORCED

---

## 1. Zero Cloud Mutation & Zero IAM Modification Guarantee

As mandated by `AGENTS.md` and repository operational guardrails:
1. **The application is strictly read-only.** It possesses zero code paths for creating, updating, or deleting real AWS cloud infrastructure.
2. **Zero IAM policy modifications.** The application does not alter customer IAM roles, policies, group memberships, or service control policies (SCPs).

---

## 2. Outbound Network & SigV4 Security Hardening

In Phase 2.1, the low-level SigV4 signing module (`backend/src/cloud_recommender/services/aws/sigv4.py`) was hardened with two security gates:

### Gate 1: Host Suffix Allowlist
To prevent Server-Side Request Forgery (SSRF) and accidental leakage of signed AWS credentials to third-party or hostile servers, SigV4 enforces an outbound host suffix check:

```python
ALLOWED_AWS_HOST_SUFFIXES: tuple[str, ...] = (
    ".amazonaws.com",
    ".amazonaws.com.cn",
)

host = urllib.parse.urlparse(url).hostname or ""
if not any(host.endswith(suffix) for suffix in ALLOWED_AWS_HOST_SUFFIXES):
    raise ValueError(f"Outbound AWS request rejected: host '{host}' is not in approved allowlist.")
```

### Gate 2: Centralized Action Allowlist & Pre-Network Mutation Rejection
In Phase 2.1A and Phase 2.2, HTTP verb filtering was upgraded to a comprehensive pre-network operation validator (`operation_validator.py`). All outbound requests—whether using Query API `Action=...`, JSON-RPC `X-Amz-Target`, or REST paths—must match `APPROVED_AWS_READ_ONLY_ACTIONS` and the approved synchronization plan scope (`approved_operations`). Mutating actions (`ec2:TerminateInstances`, `iam:CreateRole`, `cloudwatch:PutMetricData`, `lambda:CreateFunction`, `s3:PutObject`, `s3:DeleteObject`), conflicting parameters, and unlisted actions are rejected immediately with `PermissionError` or `ValueError` before SigV4 signing or transmission. EKS is architecturally classified as a RESTful HTTPS API.

### Gate 3: Cryptographic Canonical Plan Hashing
Approval tokens cryptographically bind a `SHA-256` hash of the canonical execution plan (`approved_budget_usd`, `max_requests`, `approved_operations`, `date_bounds`). Any modification to execution parameters breaks the signature and is rejected.

---

## 3. Minimal Read-Only IAM Requirements

To enable live Phase 2.1 synchronization, the customer IAM principal requires the following minimal read-only permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "FinOpsCostExplorerReadOnly",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "ce:GetDimensionValues",
        "ce:GetTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsCloudWatchReadOnly",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsPricingReadOnly",
      "Effect": "Allow",
      "Action": [
        "pricing:GetProducts",
        "pricing:DescribeServices",
        "pricing:GetAttributeValues"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsCurReadinessInspectionOnly",
      "Effect": "Allow",
      "Action": [
        "cur:DescribeReportDefinitions",
        "s3:ListBucket"
      ],
      "Resource": "*"
    }
  ]
}
```

*Note: `s3:GetObject` is deliberately omitted from the default connection requirements until the user explicitly opts into bulk CUR report file extraction.*

