# AWS Phase 2 — Live Validation Plan & Chargeable API Budget Proposal

> **Target Cloud Environment:** AWS Account `435305479688`  
> **Regions:** `eu-north-1` (Primary), `us-east-1` (Pricing / Cost Explorer Endpoint)  
> **Estimated Maximum Cost:** < $0.05 USD  

---

## 1. Chargeable API Call Analysis

In AWS, standard API queries for resource inventory (EC2, Lambda, S3, RDS) are free of charge. However, specific FinOps services carry standard metered costs:

| API Service | API Call | Standard AWS Unit Cost | Proposed Calls in Validation | Estimated Cost |
| :--- | :--- | :--- | :--- | :--- |
| **AWS Cost Explorer** | `ce:GetCostAndUsage` | $0.01 per request | 2 (MTD Daily + Top Services) | $0.02 |
| **AWS Cost Explorer** | `ce:GetCostForecast` | $0.01 per request | 1 (Month-End Forecast) | $0.01 |
| **AWS Price List API** | `pricing:GetProducts` | Free of charge (us-east-1) | 3 (Cached locally) | $0.00 |
| **AWS CloudWatch** | `cloudwatch:GetMetricData` | $0.01 per 1,000 metrics | ~10 metric queries | < $0.001 |
| **Total Estimated Run Cost** | | | | **~$0.03 USD** |

---

## 2. Bounded Live Validation Execution Sequence

To execute live verification without exceeding the $0.05 budget:

1. **Step 1: Authenticate via `finops-dev` Profile:**
   - Execute STS Caller Identity check.
2. **Step 2: Single Cost Explorer MTD Query:**
   - Request MTD unblended daily spend for `2026-11-01` through current date.
   - Cache results in memory.
3. **Step 3: Sample CloudWatch Telemetry:**
   - Request 24h CPU utilization for discovered EC2 instances and Lambda invocations in `eu-north-1`.
   - Verify Memory utilization is reported as `INSTRUMENTATION_REQUIRED`.
4. **Step 4: Price List On-Demand Lookup:**
   - Query retail catalog rate for `AWS::EC2::Instance` (`t3.medium`) in `eu-north-1` (`EU (Stockholm)`).
5. **Step 5: Verify CUR Bucket Read-Only Access:**
   - Query `s3:GetBucketLocation` for `finops-cost-reports-435305479688`.

