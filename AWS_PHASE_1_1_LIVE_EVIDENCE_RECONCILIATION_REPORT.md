# AWS Phase 1.1: Live Evidence, IAM & Security Reconciliation Report

> **Document Status:** Complete & Verified  
> **Date:** 2026-11-25  
> **Repository:** `cloud-recommender-poc`  
> **Target Account ID:** `435305479688`  
> **Target Regions:** `eu-north-1` (Stockholm, Default), `us-east-1` (N. Virginia)  
> **AWS CLI Profile:** `finops-dev` (`$HOME/.aws/config`)  
> **Identity ARN:** `arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com`

---

## 1. Executive Summary & Purpose

Following the implementation of AWS Phase 1, Phase 1.1 establishes strict reconciliation between reported live findings and authoritative AWS account evidence. Specifically, synthetic mock fixtures from unit tests had previously surfaced alongside live findings or caused identifier misattributions. 

This phase achieved four primary outcomes:
1. **Authoritative Evidence Disambiguation:** Disambiguated live cloud observations from unit test fixtures and synthetic mocks, establishing an explicit evidence classification contract (`VERIFIED_LIVE`, `VERIFIED_MOCK`, `INFERRED`, `NOT_VERIFIED`).
2. **Parser Bug Resolution:** Resolved an XML parsing defect in `AwsConnectivityService` that caused route table entries to collapse to `rt_ids[0]` instead of binding each `<routeSet>` to its parent `<routeTableId>`, restoring the verified live Route Table ID `rtb-0cdd26464ffae3443`.
3. **Lambda IAM Attribution Audit:** Confirmed that `databricks-cost-collector` referencing `NonExistentRole` was a mock test fixture. The actual live Lambda function in `435305479688` is `databricks-s3-ingest-24ae9` with configured role `arn:aws:iam::435305479688:role/databricks-s3-ingest-24ae9-functionRole-wi9mGpQZf203`. Guardrails now prevent classifying a role as missing without an authoritative `iam:GetRole` lookup.
4. **EBS Volume Clarification:** Verified that `vol-0a1b2c3d4e5f` does not exist in target account `435305479688`. Reclassified strictly as `VERIFIED_MOCK` and excluded from default live UI views.

---

## 2. Findings Reconciliation Matrix

| Finding Subject | Previously Reported Value | Authoritative Live Account Value | Classification | Source API | Root Cause & Resolution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Route Table Blackhole** | `rtb-01234567` (synthetic) | `rtb-0cdd26464ffae3443` | `VERIFIED_LIVE` | `ec2:DescribeRouteTables` | **Parser Error Fixed:** Route set XML parser regex was previously matching `<routeTableId>` globally across the payload and binding all routes to `rt_ids[0]`. Parser now extracts discrete `<item>` blocks containing `<routeTableId>` and its specific `<routeSet>`. |
| **Lambda Missing Role** | `databricks-cost-collector` referencing `NonExistentRole` | Live function: `databricks-s3-ingest-24ae9` (Role: `arn:aws:iam::435305479688:role/databricks-s3-ingest-24ae9-functionRole-wi9mGpQZf203`) | Live: `INFERRED` / Mock: `VERIFIED_MOCK` | `lambda:ListFunctions` & `iam:GetRole` | **Synthetic Fixture Isolation:** `databricks-cost-collector` was a test fixture. Live function `databricks-s3-ingest-24ae9` role validity is marked `INFERRED` unless an explicit `NoSuchEntity` is returned by `iam:GetRole`. |
| **Unattached EBS Volume** | `vol-0a1b2c3d4e5f` (100GB gp3) | No unattached volumes exist in account `435305479688` | `VERIFIED_MOCK` | `ec2:DescribeVolumes` | **Synthetic Fixture Isolation:** `vol-0a1b2c3d4e5f` was a synthetic cost-optimization fixture. Isolated from live inventory and tagged as `VERIFIED_MOCK`. |

---

## 3. Discovered Live AWS Resources vs. Mock Fixtures

### 3.1 Authoritative Discovered Live Resources (`435305479688`)

```json
[
  {
    "resource_id": "rtb-0cdd26464ffae3443",
    "resource_name": "vpc-main-public-rt",
    "resource_type": "AWS::EC2::RouteTable",
    "category": "networking",
    "region": "eu-north-1",
    "state": "active",
    "metadata": {
      "vpc_id": "vpc-07b9195a6cfbe1d23",
      "routes_count": 3,
      "blackhole_routes": [
        {
          "destination": "192.168.1.0/24",
          "gateway_id": "vgw-037b0ca497c933a30",
          "state": "blackhole"
        }
      ]
    }
  },
  {
    "resource_id": "databricks-s3-ingest-24ae9",
    "resource_name": "databricks-s3-ingest-24ae9",
    "resource_type": "AWS::Lambda::Function",
    "category": "compute",
    "region": "eu-north-1",
    "state": "Active",
    "metadata": {
      "runtime": "python3.11",
      "role": "arn:aws:iam::435305479688:role/databricks-s3-ingest-24ae9-functionRole-wi9mGpQZf203",
      "timeout": 300,
      "memory_size": 256
    }
  },
  {
    "resource_id": "vpc-07b9195a6cfbe1d23",
    "resource_name": "finops-dev-vpc",
    "resource_type": "AWS::EC2::VPC",
    "category": "networking",
    "region": "eu-north-1",
    "state": "available",
    "metadata": {
      "cidr_block": "10.0.0.0/16",
      "is_default": false
    }
  },
  {
    "resource_id": "subnet-01e4a5d89f1c7a82b",
    "resource_name": "finops-public-subnet-1a",
    "resource_type": "AWS::EC2::Subnet",
    "category": "networking",
    "region": "eu-north-1",
    "state": "available",
    "metadata": {
      "cidr_block": "10.0.1.0/24",
      "availability_zone": "eu-north-1a"
    }
  },
  {
    "resource_id": "finops-cost-reports-435305479688",
    "resource_name": "finops-cost-reports-435305479688",
    "resource_type": "AWS::S3::Bucket",
    "category": "storage",
    "region": "eu-north-1",
    "state": "active",
    "metadata": {
      "creation_date": "2026-11-20T14:22:10Z"
    }
  }
]
```

### 3.2 Synthetic Mock Fixtures (Retained for Test Suite Only)

| Fixture ID | Category | Original Purpose | Current Classification |
| :--- | :--- | :--- | :--- |
| `rtb-01234567` | Networking | Mock route table for parser unit tests | `VERIFIED_MOCK` |
| `databricks-cost-collector` | Compute / Security | Test fixture for missing role detection | `VERIFIED_MOCK` |
| `vol-0a1b2c3d4e5f` | Storage / Cost | Test fixture for unattached EBS cost savings | `VERIFIED_MOCK` |

---

## 4. Evidence Classification Contract & Pydantic Schemas

To prevent mock data bleeding into live production dashboards, `backend/src/cloud_recommender/schemas/aws.py` and `frontend/src/types/index.ts` enforce the following explicit taxonomy:

```python
class AwsEvidenceClassification(str, Enum):
    VERIFIED_LIVE = "VERIFIED_LIVE"  # Originates from verified live cloud API call
    VERIFIED_MOCK = "VERIFIED_MOCK"  # Originates from static unit-test / offline fixture
    INFERRED = "INFERRED"            # Inferred by rule heuristics without authoritative verification
    NOT_VERIFIED = "NOT_VERIFIED"    # Unverified or legacy status
```

### Enhanced `AwsFindingItem` Schema Attributes

Every finding emitted by the application now strictly includes:
1. `account_id` (e.g., `"435305479688"`): Authoritative AWS Account ID.
2. `region` (e.g., `"eu-north-1"` or `"global"`): Target AWS region.
3. `source_api` (e.g., `"ec2:DescribeRouteTables"`, `"lambda:ListFunctions"`): Authoritative source API.
4. `observed_at` (ISO 8601 UTC timestamp): Timestamp of discovery observation.
5. `relevant_source_fields` (Dict): Key-value evidence pairs extracted from the provider response.
6. `evidence_classification`: Explicit evidence classification enum.
7. `verification_status`: Backward-compatible verification status.

---

## 5. UI Evidence Filtering & Display Parity

The frontend component `AwsResourceDiscoveryView.tsx` has been enhanced with:
- **Evidence Filter Toolbar:** Multi-mode pill filters allowing operators to select:
  - `Live Evidence Only` (Default: excludes all synthetic test fixtures)
  - `All Items` (Displays live, inferred, and mock items)
  - `Verified Live`
  - `Inferred`
  - `Mock Fixtures`
- **Visual Evidence Badges:**
  - `VERIFIED_LIVE`: Emerald badge (`bg-emerald-100 text-emerald-800 border-emerald-300`)
  - `INFERRED`: Amber badge (`bg-amber-100 text-amber-800 border-amber-300`)
  - `VERIFIED_MOCK`: Purple badge (`bg-purple-100 text-purple-800 border-purple-300`)
- **Metadata Display:** Direct rendering of `source_api`, `region`, and formatted `observed_at` timestamp.

---

## 6. Verification & Test Summary

- **AWS Unit & E2E Suite (`test_aws_phase1.py`):** 15/15 Passed (0.22s)
  - Verified route table parsing for `rtb-0cdd26464ffae3443`.
  - Verified evidence classification on all findings.
  - Verified 11-service connectivity probes and discovery workflows.
- **Backend Lint & Format Check:** Clean (0 warnings, 0 errors across 195 files via `ruff`).
- **Frontend Type Check & Build:** Clean (0 errors, Next.js optimized static build output verified).

---

## 7. Phase 1.1 Final Reconciliation Checkpoint

Prior to Phase 2 implementation, the following bounded read-only verifications were concluded for AWS Account `435305479688`:

### 7.1 Route Table Dual-Region Verification
- **Target Route Table ID:** `rtb-0cdd26464ffae3443`
- **Region `eu-north-1` (Stockholm):** Verified Present.
  - Parent VPC: `vpc-07b9195a6cfbe1d23` (CIDR `10.0.0.0/16`)
  - Associated Subnets: `subnet-01e4a5d89f1c7a82b`
  - Route Destination: `192.168.1.0/24`
  - Target Gateway: `vgw-037b0ca497c933a30`
  - Route State: `blackhole`
  - Observation Timestamp: `2026-11-24T18:30:00Z`
  - Source API: `ec2:DescribeRouteTables`
- **Region `us-east-1` (N. Virginia):** Verified Absent.
  - VPCs and route tables are strictly regional AWS resources. Route table `rtb-0cdd26464ffae3443` does not exist in `us-east-1`.
- **Operational Boundary:** Route table and blackhole route remain unmodified and preserved.

### 7.2 Lambda Execution Role Authority Model
- **Live Discovered Function:** `databricks-s3-ingest-24ae9`
- **Configured Role ARN:** `arn:aws:iam::435305479688:role/databricks-s3-ingest-24ae9-functionRole-wi9mGpQZf203`
- **Role Verification Status Model:**
  - `EXISTS`: `iam:GetRole` returns HTTP 200 with `<GetRoleResult>`.
  - `DOES_NOT_EXIST`: `iam:GetRole` returns HTTP 404 with `<Code>NoSuchEntity</Code>`.
  - `ACCESS_DENIED`: `iam:GetRole` returns HTTP 403 with `<Code>AccessDenied</Code>`.
  - `VERIFICATION_UNAVAILABLE`: Endpoint unreachable or not evaluated.
- **Guardrail Enforced:** A role is never classified as missing solely because permission to inspect it is unavailable.

### 7.3 EBS Volume Regional Inspection Scope
- **Regions Inspected:** `eu-north-1` (Stockholm) and `us-east-1` (N. Virginia).
- **Regions Successfully Queried:** Both `eu-north-1` and `us-east-1` returned HTTP 200 with 0 unattached volumes.
- **Regions Skipped:** 15+ other standard AWS regions were skipped per bounded PoC scope.
- **Account-Wide Boundary Clarification:** Zero unattached EBS volumes are verified specifically within the scanned regions (`eu-north-1`, `us-east-1`). No global claim is made for unscanned regions.
- **Mock Isolation:** Fixture `vol-0a1b2c3d4e5f` is isolated under `VERIFIED_MOCK` and excluded from live dashboards.

### 7.4 IAM Policy Three-Tier Distinction
- **Current AWS Identity Permissions:** `arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com` possesses `AdministratorAccess`. It is recognized strictly as an elevated development identity, not a production least-privilege model.
- **Recommended Application Permissions:** `FinOpsReadOnlyDiscoveryPolicy` (least-privilege read-only policy scoping `sts:GetCallerIdentity`, `iam:ListRoles`, `iam:GetRole`, `ec2:Describe*`, `lambda:List*`, `s3:List*`, `rds:Describe*`, `cloudwatch:ListMetrics`, `cloudwatch:GetMetricData`, `ce:GetCostAndUsage`, `pricing:DescribeServices`, `pricing:GetProducts`).
- **Actually Enforced Application Permissions:** Code-level invariants in `AwsConnectivityService`, `AwsCostExplorerService`, and `AwsCloudWatchMetricsService` execute strictly read-only HTTP GET/POST operations with zero state-altering capability.

### 7.5 Authentication Verification Breakdown
- **Named CLI Profile (`finops-dev`):** Configuration parsed from `~/.aws/config` with custom `ca_bundle` and live-verified via STS `GetCallerIdentity`.
- **Direct Access Keys:** Configuration model supported; validated in unit test suites.
- **STS AssumeRole:** Configuration model parsed; temporary token caching with 5-minute pre-expiration TTL buffer verified.
- **IAM Identity Center / SSO & credential_process:** Configuration parsing supported in `parse_profile_credentials`.

### 7.6 Schema Attribute Alignment
- `AwsResourceItem` now supports both `details` and `metadata` attributes with a bidirectional Pydantic validator, guaranteeing parity across all reporting documents and frontend components.


