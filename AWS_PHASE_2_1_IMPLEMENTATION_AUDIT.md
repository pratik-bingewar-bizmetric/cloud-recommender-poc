# AWS Phase 2.1 — Implementation Audit Report

> **Repository:** `cloud-recommender-poc`  
> **Target Account ID:** `435305479688`  
> **Regions:** `eu-north-1` (Primary), `us-east-1` (Global/Pricing)  
> **AWS CLI Profile:** `finops-dev`  
> **Date:** November 2026  
> **Status:** AUDITED & HARDENED

---

## 1. Executive Summary

This report documents the architectural, security, and algorithmic audit of the AWS Phase 2 implementation, identifying critical gaps and detailing the Phase 2.1 hardening measures introduced. 

Phase 2 established the core integrations for AWS Cost Explorer, CloudWatch Metrics, Price List API, and CUR inspection. Phase 2.1 rigorously elevates these foundations into an enterprise-grade FinOps intelligence engine by introducing **strict decimal arithmetic**, **multi-dimensional projection forecasting**, **server-side API cost guardrails**, **HMAC-SHA256 single-use approval tokens**, **strict SigV4 outbound allowlisting**, and **CUR manifest verification**.

---

## 2. Audit Findings & Resolution Matrix

| Area | Pre-Phase 2.1 State | Identified Risk / Gap | Phase 2.1 Hardened State |
| :--- | :--- | :--- | :--- |
| **Financial Arithmetic** | Float arithmetic for currency sums | IEEE 754 floating-point rounding errors (e.g., `0.1 + 0.2 = 0.30000000000000004`) | `Decimal` arithmetic throughout with `ROUND_HALF_UP` to 2 decimal places. |
| **Spend Forecasting** | Forwarded raw `GetCostForecast` total | Under-projected month-end spend by confusing remaining future forecast with full-month total | Projected Month-End Spend formula: $\text{Projected} = \text{Actual MTD} + \text{Remaining Forecast}$. |
| **Pagination** | Single-page retrieval or unbounded loop | Silent record dropping on large accounts (>100 services/tags) or infinite loop | Hardened pagination loop consuming `NextPageToken` with bounded page safety cap (`max_pages=5`). |
| **Credit / Refund Handling** | Filtered negative amounts or zeroed | Distorted FinOps accounting; ignored tax credits, EDP discounts, and refund adjustments | Fully preserves signed adjustments and credits while ordering net costs properly. |
| **API Cost Guardrails** | Client-initiated ad-hoc API calls on page mount | Risk of accidental Cost Explorer ($0.01/call) runaway charges during user navigation | Cryptographic HMAC single-use approval token workflow with atomic server-side budget guard (`AwsBudgetGuard`). |
| **Network Security** | Unrestricted host target in SigV4 | Potential SSRF / credential leak if URL parameter was spoofed | Strict outbound host suffix allowlist (`*.amazonaws.com`) and pre-network rejection of mutating HTTP verbs (`DELETE`, `PUT`, `PATCH`). |
| **Pricing Caching** | Non-standard composite string keys | Redundant Price List API queries due to non-canonical key variance | Canonical cache key: `{service}:{region}:{resource_type}:{tier}:{storage}` with explicit source tagging (`LIVE_AWS_PRICE_LIST`, `CACHED_AWS_PRICE_LIST`, `OFFLINE_REFERENCE_CATALOG`). |
| **CUR Readiness** | Bucket existence checked via ListObjects | S3 key presence confused with readable manifest schema | Two-stage verification: distinguishes bucket presence (`ListObjectsV2`) from manifest schema read (`s3:GetObject`). |

---

## 3. Core Architecture Review

```
[ Browser Client / React UI ]
        │  1. Request Sync Preview (Connection, Regions, Date Range)
        ▼
[ POST /api/v1/aws/sync/preview ]
        │  2. Compute worst-case request count & cost cap ($0.02 - $0.05)
        │  3. Issue HMAC-SHA256 Signed Single-Use Token (TTL: 15 min)
        ▼
[ User Review & Explicit Approval in UI ]
        │  4. User clicks "Authorize & Sync"
        ▼
[ POST /api/v1/aws/sync/approve-and-run ]
        │  5. Validate HMAC, check TTL, verify single-use (replay prevention)
        │  6. Instantiate AwsBudgetGuard(max_requests, max_cost)
        │  7. Execute bounded queries (Cost Explorer, CloudWatch)
        │  8. Atomically count requests (raise PermissionError if breached)
        ▼
[ Read-Only Telemetry Ingested into Persistence Layer ]
```

---

## 4. Verification and Compliance

- **Zero Cloud Mutations:** Verified that all executed AWS calls use read-only actions. SigV4 client strictly aborts before network if method is `DELETE`, `PUT`, or `PATCH`.
- **Zero IAM Modifications:** No IAM roles, policies, or inline permissions were created or altered.
- **Fail-Closed Principle:** When Cost Explorer or CloudWatch permissions are denied, the system returns `PERMISSION_DENIED` and `None` for costs; it **never converts missing financial data to $0.00**.

