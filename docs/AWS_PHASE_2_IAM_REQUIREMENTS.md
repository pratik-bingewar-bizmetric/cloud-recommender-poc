# AWS Phase 2 — Comprehensive IAM Requirements & Least-Privilege Policy

> **AWS Account:** `435305479688`  
> **Policy Name:** `FinOpsPhase2CostAndTelemetryPolicy`  
> **Type:** Read-Only Customer Managed Policy  

---

## 1. Policy Definition (Least-Privilege JSON)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "FinOpsCostExplorerReadAccess",
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
      "Sid": "FinOpsCloudWatchTelemetryReadAccess",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsPricingCatalogReadAccess",
      "Effect": "Allow",
      "Action": [
        "pricing:DescribeServices",
        "pricing:GetProducts",
        "pricing:GetAttributeValues"
      ],
      "Resource": "*"
    },
    {
      "Sid": "FinOpsCurBucketInspectionReadAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::finops-cost-reports-435305479688"
      ]
    }
  ]
}
```

---

## 2. Three-Tier IAM Authority Matrix

1. **Tier 1 — Current Developer Identity (`finops-dev`):**
   - User: `arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com`
   - Active Policy: `AdministratorAccess` (full administrative rights for PoC development).
2. **Tier 2 — Recommended Least-Privilege Role (`FinOpsPhase2CostAndTelemetryPolicy`):**
   - Strictly scopes operations to `ce:*`, `cloudwatch:GetMetricData`, `pricing:*`, and read-only S3 inspection of `finops-cost-reports-435305479688`.
3. **Tier 3 — Code-Enforced Application Guardrails:**
   - Irrespective of the caller's cloud permissions, the application code strictly enforces pure read-only operations, zero mutations, memory instrumentation gating, and deferred CUR ingestion.

