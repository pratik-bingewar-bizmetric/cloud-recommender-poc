# AWS Phase 2.2 — Live Validation Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** 2026-11-26  
> **Target Account ID:** `435305479688`  
> **AWS CLI Profile:** `finops-dev`  
> **Status:** PENDING HUMAN AUTHORIZATION & CLI REAUTHENTICATION

---

## 1. Identity & Resource Verification

1. **Target Account Verification:**
   - Account ID: `435305479688`
   - Configured Primary Region: `eu-north-1`
   - Configured Secondary/Global Region: `us-east-1`
2. **Current Authentication State:**
   - Executing `aws sts get-caller-identity --profile finops-dev` returned:
     `aws: [ERROR]: Your session has expired. Please reauthenticate using 'aws login'.`
   - The developer CLI session token has expired and requires interactive reauthentication.
3. **Discovered Resource Inventory (Reused Verified Authoritative Evidence):**
   - **Lambda Function:** `databricks-s3-ingest-24ae9` in region `eu-north-1` (`VERIFIED_LIVE`).
   - **Configured Role:** `arn:aws:iam::435305479688:role/databricks-s3-ingest-24ae9-functionRole-wi9mGpQZf203`.
   - **Route Table:** `rtb-0cdd26464ffae3443` with blackhole finding (`VERIFIED_LIVE`).
   - **EC2 Instances:** 0 instances in `eu-north-1` and `us-east-1` (no hypothetical EC2 instances queried).

---

## 2. Bounded Live Synchronization Operations

The synchronization plan covers 5 discrete read-only operations:

| Operation | AWS Service | Action | Scope / Parameters | Estimated Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Op 1: Current MTD Cost** | Cost Explorer | `ce:GetCostAndUsage` | `2026-11-01` to `2026-11-26`, DAILY, UnblendedCost | \$0.0100 |
| **Op 2: Comparable Previous MTD** | Cost Explorer | `ce:GetCostAndUsage` | `2026-10-01` to `2026-10-26`, DAILY, UnblendedCost | \$0.0100 |
| **Op 3: Service-Level Breakdown** | Cost Explorer | `ce:GetCostAndUsage` | `2026-11-01` to `2026-11-26`, GroupBy SERVICE | \$0.0100 |
| **Op 4: Month-End Forecast** | Cost Explorer | `ce:GetCostForecast` | `2026-11-26` to `2026-12-01`, MONTHLY | \$0.0100 |
| **Op 5: Resource Telemetry** | CloudWatch | `cloudwatch:GetMetricData` | Lambda `databricks-s3-ingest-24ae9` (4 metrics, 24h) | \$0.0002 |
| **Total** | — | — | **5 operations (4 CE calls, 4 CW metrics)** | **\$0.0402 USD** |

---

## 3. Human Approval & Zero-Execution Boundary

In strict compliance with `AGENTS.md` and Phase 2.2 requirements:
- Chargeable operations have **not** been executed.
- No real AWS resources were altered or provisioned.
- Execution is safely halted at this checkpoint pending explicit human authorization and CLI reauthentication.

