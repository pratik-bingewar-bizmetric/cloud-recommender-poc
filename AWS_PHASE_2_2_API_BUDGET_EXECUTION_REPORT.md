# AWS Phase 2.2 — API Budget Execution Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** 2026-11-26  
> **Status:** BUDGET ALLOCATION AUDITED & ENFORCED

---

## 1. Official AWS API Pricing Basis

Pricing verified from official AWS documentation (effective November 2026):
1. **AWS Cost Explorer API (`ce:*`):**
   - \$0.0100 per paginated request (`GetCostAndUsage`, `GetCostForecast`).
   - Rate source: AWS Billing and Cost Management Pricing.
2. **AWS CloudWatch Metrics API (`cloudwatch:GetMetricData`):**
   - \$0.0100 per 1,000 metrics requested ($0.00001 per metric).
   - First 1,000,000 metrics per month are included in AWS Free Tier across the account.
   - For safety and strict fail-closed accounting, `AwsBudgetGuard` does **not** assume free tier coverage and reserves \$0.00001 per metric query.
3. **AWS STS & Pricing APIs (`sts:*`, `pricing:*`):**
   - \$0.0000 (no charge).

---

## 2. Proposed Budget vs. Actual Allocation

| Operation | Unit Cost | Proposed Count | Estimated Spend |
| :--- | :--- | :--- | :--- |
| `ce:GetCostAndUsage` (Current MTD) | \$0.0100 | 1 call | \$0.0100 |
| `ce:GetCostAndUsage` (Comparable Previous MTD) | \$0.0100 | 1 call | \$0.0100 |
| `ce:GetCostAndUsage` (Service Breakdown) | \$0.0100 | 1 call | \$0.0100 |
| `ce:GetCostForecast` (Remaining-Month Forecast) | \$0.0100 | 1 call | \$0.0100 |
| `cloudwatch:GetMetricData` (Lambda Telemetry) | \$0.00001 / metric | 4 metric queries | \$0.00004 |
| **Total Estimated Spend** | — | **5 operations (8 items)** | **\$0.04004 USD** |
| **Enforced Budget Cap** | — | — | **\$0.05000 USD** |

`AwsBudgetGuard` enforces a hard ceiling of **\$0.0500 USD**. Any request that would cause cumulative reservations to exceed \$0.0500 USD is rejected immediately with `AwsBudgetExceededError`. Furthermore, client-supplied budget overrides are validated against the server-calculated maximum count and cannot exceed \$0.0500 USD.

