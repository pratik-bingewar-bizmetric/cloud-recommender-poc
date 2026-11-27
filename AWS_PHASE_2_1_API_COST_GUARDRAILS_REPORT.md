# AWS Phase 2.1 — API Cost Guardrails & Approval Workflow Report

> **Repository:** `cloud-recommender-poc`  
> **Module:** `backend/src/cloud_recommender/services/aws/sync_approval_service.py`  
> **Status:** AUDITED, TESTED & ENFORCED

---

## 1. Context and Problem Statement

AWS Cost Explorer charges **$0.01 per paginated API request** (`GetCostAndUsage`, `GetCostForecast`). CloudWatch Metrics queries incur charges of **$0.01 per 1,000 metrics requested** (`GetMetricData`).

In poorly architected cloud dashboards:
- Mounting a UI view triggers 3–5 Cost Explorer queries.
- Switching tabs or refreshing the browser initiates duplicate queries.
- Large multi-account tenants with automated polling can incur unintended AWS charges.

To eliminate this operational risk, Phase 2.1 institutes an **immutable server-side API cost guardrail** modeled after the application's Databricks approval workflow.

---

## 2. Server-Side Guardrail Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Frontend UI                           │
│  - Displays "Sync Live Data" button                         │
│  - No automated background queries on mount                 │
│  - Shows preview modal with budget cap before execution     │
└──────────────────────────────┬──────────────────────────────┘
                               │
            1. POST /api/v1/aws/sync/preview
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 AwsSyncApprovalService                      │
│  - Computes upper-bound query count                         │
│  - Calculates maximum cost: $0.01/CE, $0.00001/metric       │
│  - Issues HMAC-SHA256 Token (Single-Use, 15-min TTL)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
            2. Token returned to client
            3. User clicks "Authorize Live Ingestion"
            4. POST /api/v1/aws/sync/approve-and-run
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   AwsBudgetGuard                            │
│  - Validates HMAC signature & tenant/user ownership         │
│  - Verifies canonical plan hash matches parameters          │
│  - Verifies token has not been consumed (Replay prevention) │
│  - Atomically reserves request & Decimal budget (asyncio.Lock)
│  - Enforces hard stop if max_requests or budget is exceeded │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Cryptographic Token Specification

Tokens issued by `AwsSyncApprovalService` are cryptographically bound using HMAC-SHA256 with the application secret key:

$$\text{Payload} = \text{token\_id} : \text{tenant\_id} : \text{user\_id} : \text{connection\_id} : \text{account\_id} : \text{budget} : \text{max\_requests} : \text{expires\_at}$$
$$\text{Signature} = \text{HMAC-SHA256}(K_{\text{secret}}, \text{Payload})$$

### Enforced Token Invariants:
1. **Single-Use Replay Prevention:** Once a token is presented to `/approve-and-run`, its `token_id` is permanently added to an in-memory consumed ledger. Attempting to reuse the token raises `PermissionError("Approval token has already been consumed")`.
2. **Strict Expiration (TTL):** Tokens expire 15 minutes (900 seconds) after issuance. Expired tokens are rejected before any network traffic is initiated.
3. **Cross-Tenant Isolation:** Tokens carry the tenant ID and user ID of the requesting user. Presentation by a different tenant or user is rejected with HTTP 403.
4. **Tamper Proofing:** Modifying the requested budget or request count invalidates the HMAC signature.

---

## 4. Atomic Request Accounting (`AwsBudgetGuard`)

During live data ingestion, each downstream service call must acquire clearance from `AwsBudgetGuard`:

```python
# Before issuing a Cost Explorer query:
budget_guard.check_and_increment("cost_explorer", count=1)
resp = await cost_service.get_cost_and_usage(...)
```

If the loop or service attempts to exceed the approved request cap, `AwsBudgetGuard` immediately raises a `PermissionError`, terminating execution before the chargeable AWS API call is dispatched.

