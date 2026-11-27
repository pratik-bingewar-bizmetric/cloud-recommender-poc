# AWS Phase 2.1 — Live Validation Approval Plan

> **Target Environment:** AWS Account `435305479688`  
> **Target Region:** `eu-north-1` (Primary) & `us-east-1` (Pricing)  
> **AWS CLI Profile:** `finops-dev`  
> **Estimated Maximum Cost:** $\le \$0.05$ USD  
> **Status:** PENDING HUMAN APPROVAL (CHECKPOINT ENFORCED)

---

## 1. Checkpoint Statement

In accordance with `AGENTS.md` and repository operational principles:
> **The POC must NEVER execute chargeable or mutating infrastructure calls without explicit human approval.**

All Phase 2.1 code, security hardening, decimal arithmetic, and cost guardrails have been implemented, statically verified, and tested against deterministic offline suites.

**Execution has halted at this checkpoint.** Live AWS Cost Explorer queries will not be executed until you review and grant explicit approval for this bounded live validation plan.

---

## 2. Bounded Live Validation Scope & Cost Breakdown

The live validation is strictly bounded to a single synchronization run with hard caps:

| API Service | Operation | Requested Calls | Unit Rate | Maximum Estimated Cost |
| :--- | :--- | :--- | :--- | :--- |
| **AWS Cost Explorer** | `GetCostAndUsage` (MTD summary) | 1 | $0.01 / request | $0.010 USD |
| **AWS Cost Explorer** | `GetCostAndUsage` (Prior month baseline) | 1 | $0.01 / request | $0.010 USD |
| **AWS Cost Explorer** | `GetCostAndUsage` (Service breakdown) | 1 | $0.01 / request | $0.010 USD |
| **AWS Cost Explorer** | `GetCostForecast` (Month-end projection) | 1 | $0.01 / request | $0.010 USD |
| **AWS CloudWatch** | `GetMetricData` (Lambda & EC2 metrics) | 2 | $0.00001 / metric | < $0.001 USD |
| **AWS Price List** | `GetProducts` / `DescribeServices` | 0 (cached) | Free tier | $0.000 USD |
| **AWS S3 / CUR** | `ListObjectsV2` (Manifest check) | 1 | $0.000005 / list | < $0.001 USD |
| **TOTAL UPPER BOUND** | | **6 requests** | | **$0.041 USD ($\le \$0.05$)** |

---

## 3. Human Approval & Execution Procedure

When you are ready to proceed with live validation:

### Option A: Via FinOps Application UI (Recommended)
1. Open the application frontend at `http://localhost:3000`.
2. Navigate to the **AWS Resource Discovery & Cost Intelligence** view.
3. Click the **"Sync Live Data"** button.
4. Review the preview dialog confirming the maximum budget cap ($0.05 USD).
5. Click **"Authorize & Run Live Sync"**.

### Option B: Via Terminal / API
Submit the following approval command:
```bash
# 1. Generate preview and approval token
curl -X POST http://localhost:8000/api/v1/aws/sync/preview \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"connection_id": "<CONNECTION_ID>", "services": ["cost_explorer", "cloudwatch"]}'

# 2. Execute approved sync using the returned single-use cryptographic token
curl -X POST http://localhost:8000/api/v1/aws/sync/approve-and-run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"token": <TOKEN_OBJECT>}'
```

