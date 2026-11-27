# AWS Phase 2.2 — Canonical Live Validation Approval Plan & Cost Proposal

> **Repository:** `cloud-recommender-poc`  
> **Status:** PENDING HUMAN OPERATOR AUTHORIZATION (STOPPED AT LIVE CHECKPOINT)  
> **Date:** 2026-11-26  
> **Target Account ID:** `435305479688`  
> **AWS Profile:** `finops-dev`  
> **Primary Region:** `eu-north-1` | **Cost Explorer / CloudWatch Region:** `us-east-1`  
> **Target Lambda Resource:** `databricks-s3-ingest-24ae9-databricksApiFunction-XYl6Jk2AKjOJ`  
> **Target Lambda ARN:** `arn:aws:lambda:us-east-1:435305479688:function:databricks-s3-ingest-24ae9-databricksApiFunction-XYl6Jk2AKjOJ`

---

## 1. Objective & Human Authorization Request

In strict compliance with `AGENTS.md` (Zero-Execution Policy, Deterministic Pricing, and Mandatory Human Approval), all chargeable live validation against AWS is halted.

This document represents the single, canonical, immutable execution plan governing backend execution, API approval preview, frontend approval modal, HMAC approval tokens, transport-level budget guardrails, audit ledgers, and database persistence.

Zero EC2 metric queries are planned because zero EC2 instances exist across both `eu-north-1` and `us-east-1`.

---

## 2. Distinction of Request Types & Financial Impact

Pricing verified directly against official AWS pricing documentation (effective November 2026):
- **Cost Explorer API (`ce:*`):** \$0.0100 per paginated request (`GetCostAndUsage`, `GetCostForecast`).
- **CloudWatch `GetMetricData`:** \$0.01 per 1,000 metrics requested (\$0.00001 per billable metric unit). Note: `GetMetricData` is separately chargeable and is **not** covered by standard basic metrics.
- **STS `GetCallerIdentity`:** \$0.0000 (included with AWS identity).

| Operation | Target Service | Parameters / Scope | Proposed Count | Unit Cost | Estimated Spend |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`sts:GetCallerIdentity`** | AWS STS | Identity check (`finops-dev`) | 1 request | \$0.0000 | \$0.00000 |
| **`ce:GetCostAndUsage`** | AWS Cost Explorer (`us-east-1`) | Current MTD (`2026-11-01` to `2026-11-26`, MONTHLY, `NetUnblendedCost`) | 1 request | \$0.0100 | \$0.01000 |
| **`ce:GetCostAndUsage`** | AWS Cost Explorer (`us-east-1`) | Comparable Previous MTD (`2026-10-01` to `2026-10-26`, MONTHLY, `NetUnblendedCost`) | 1 request | \$0.0100 | \$0.01000 |
| **`ce:GetCostAndUsage`** | AWS Cost Explorer (`us-east-1`) | Top Services Breakdown (`2026-11-01` to `2026-11-26`, GroupBy SERVICE) | 1 request | \$0.0100 | \$0.01000 |
| **`ce:GetCostForecast`** | AWS Cost Explorer (`us-east-1`) | Remaining Month Forecast (`2026-11-26` to `2026-12-01`, `NET_UNBLENDED_COST`) | 1 request | \$0.0100 | \$0.01000 |
| **`cloudwatch:GetMetricData`** | AWS CloudWatch (`us-east-1`) | 1 request with 4 metric queries on Lambda `databricks-s3-ingest-24ae9-databricksApiFunction-XYl6Jk2AKjOJ` (Invocations, Duration, Errors, Throttles) | 4 metric units | \$0.00001 | \$0.00004 |
| **Total Proposed Live Run** | — | — | **6 total HTTP dispatches (5 chargeable)** | — | **\$0.04004 USD** |
| **Enforced Budget Ceiling** | — | — | — | — | **\$0.05000 USD** |
| **Unallocated Margin** | — | — | — | — | **\$0.00996 USD** |

> [!IMPORTANT]
> Estimated charges ($0.04004 USD) and reserved charges ($0.04004 USD) are guardrail figures and do not constitute an official AWS invoice. Actual AWS charges are confirmed only upon subsequent billing cycle reconciliation.

---

## 3. Strict Pre-Dispatch Execution Sequence (Step 6 Compliance)

Before executing chargeable operations, the system enforces the following transactionally consistent lifecycle:
1. **User Authentication & Permission:** Verify `CurrentUser` identity and tenant context (`owner_key_for`).
2. **Ownership Validation:** Validate target connection ownership and account `435305479688`.
3. **Cryptographic Plan Hash Verification:** Validate HMAC-SHA256 signature and verify that query dates, operations, and limits have not been tampered with.
4. **Atomic Pre-Dispatch Consumption:** Atomically consume token in PostgreSQL before any chargeable request is sent:
   ```sql
   UPDATE billing_approval_tokens
   SET is_consumed = True, consumed_at = now()
   WHERE token_id = :id AND is_consumed = False;
   ```
   If `rowcount == 0`, immediately fail closed with `PermissionError` (replays across workers or restarts blocked).
5. **Durable Ledger Initialization:** Insert an initial execution record into `billing_ingestion_runs` with status `IN_PROGRESS`.
6. **Transport-Level Reservation:** `AwsBudgetGuard` reserves \$0.01 before each Cost Explorer call and \$0.00004 before CloudWatch `GetMetricData`.
7. **Execution & Finalization:** Dispatches requests, persisting raw usage records into `billing_usage_records` and marking the sync status `COMPLETED` (or `BUDGET_EXHAUSTED` / `FAILED` / `UNKNOWN`).

---

## 4. Operational Boundaries

- **Zero Chargeable Retries:** Automatic retries for chargeable calls are strictly disabled.
- **Single Page Limit:** Pagination beyond 1 page for this validation run is blocked (`PARTIAL_DATA` classified if truncated).
- **Zero Resource Mutation:** No Lambda invocation, no IAM changes, no metric filters.
- **Dashboard Read Isolation:** Reading `/api/v1/aws/cost/*`, `/api/v1/aws/metrics/*`, and `/api/v1/aws/sync/history` reads exclusively from stored PostgreSQL records and will never trigger background AWS calls.
   - Execute single `ce:GetCostAndUsage` for period `[2026-11-01, 2026-11-26)` with granularity `MONTHLY`.
   - Charge: \$0.01 USD.
4. **Step 4: Top-5 Service Cost Breakdown (Cost Explorer):**
   - Execute single `ce:GetCostAndUsage` grouped by `DIMENSION: SERVICE`.
   - Charge: \$0.01 USD.
5. **Step 5: Remaining Month-End Spend Forecast (Cost Explorer):**
   - Execute single `ce:GetCostForecast` for period `[2026-11-26, 2026-12-01)`.
   - Charge: \$0.01 USD.
6. **Step 6: Resource Telemetry Sample (CloudWatch):**
   - Query CPU utilization metrics for discovered live EC2 instances in `eu-north-1`.
   - Charge: \$0.00 USD (within AWS free tier).
7. **Step 7: Token Consumption & Closure:**
   - Mark approval token as `CONSUMED`.
   - Generate `AWS_PHASE_2_2_LIVE_VALIDATION_REPORT.md` capturing all live telemetry and exact billing charges incurred.

---

## 4. Safety Guardrails Enforced During Execution

- **Zero Mutations:** `operation_validator.py` will intercept and block any non-allowlisted action.
- **Fail-Closed Budget:** `AwsBudgetGuard` enforces the \$0.05 cap at the transport level.
- **Zero Cloud Changes:** No resources will be provisioned, stopped, or altered.
- **Read-Only Scope:** AWS credentials will only invoke read-only APIs.

---

## 5. Authorization Request

To proceed with live execution against AWS Account `435305479688`:
> Please reply with **"Approved"** or indicate authorization to execute Phase 2.2 with a cap of **\$0.05 USD**.

