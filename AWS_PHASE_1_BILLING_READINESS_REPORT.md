# AWS Phase 1: Billing & FinOps Cost Intelligence Readiness Report

> **Document Status:** Complete & Verified  
> **Date:** 2026-11-24  
> **Repository:** `cloud-recommender-poc`  
> **Target Account ID:** `435305479688`  
> **Billing Ingestion Status:** **DEFERRED (Phase 1 Boundary)**

---

## 1. Operational Principles & Deferred Status

In alignment with Phase 1 design boundaries, **live billing ingestion is strictly DEFERRED**:

- **No Billing Mutations:** Zero modifications to AWS Budgets, Cost Allocation Tags, or CUR report delivery buckets.
- **Read-Only Connectivity Verification:** The platform verifies the availability of cost and pricing endpoints without executing bulk telemetry downloads or spawning background ingestion pipelines.
- **Normalized Cost Modeling:** Architecture recommendations continue to utilize deterministic, offline-cached pricing catalogs for AWS compute, storage, databases, and network egress.

---

## 2. Cost Explorer & Price List API Verification

The `AwsConnectivityService` checks cost intelligence endpoints:

| Endpoint | Action | Purpose | Result |
| :--- | :--- | :--- | :---: |
| `ce.us-east-1.amazonaws.com` | `ce:GetDimensionValues` | Verifies whether the account has enabled Cost Explorer and whether caller permissions allow read-only dimension queries. | **SUCCESS** |
| `api.pricing.us-east-1.amazonaws.com` | `pricing:GetProducts` | Verifies public / authenticated read access to official AWS pricing catalogs without downloading gigabyte files. | **SUCCESS** |

---

## 3. FinOps Multi-Cloud Normalized Dimensions

AWS resources and pricing items are normalized to the application's unified schema:

```typescript
export interface CloudServiceItem {
  provider: "aws";
  service_category: "compute" | "storage" | "networking" | "database" | "security" | "monitoring";
  service_id: string;        // e.g. "AmazonEC2", "AmazonS3", "AWSLambda"
  sku_or_instance_type: string; // e.g. "t4g.medium", "Standard-IA", "db.r6g.large"
  region: string;            // e.g. "eu-north-1"
  unit: string;              // "Hrs", "GB-Mo", "Requests"
  unit_price_usd: string;    // Strict Decimal string representation
  pricing_tier: string;      // "OnDemand", "SavingsPlans", "Spot"
}
```

---

## 4. Phase 2 Billing Ingestion Roadmap

When authorized for Phase 2 billing integration, the ingestion engine will support:

1. **AWS Cost and Usage Report (CUR 2.0 / Data Exports):**
   - Parquet format delivery to an S3 bucket with Snappy compression.
   - Partitioned by billing period (`YEAR=2026/MONTH=11`).
2. **DuckDB / PyArrow Ingestion:**
   - Streamed chunk-by-chunk processing without high-memory spikes.
   - Reconciliation against PostgreSQL tables (`finops_billing_records`, `finops_anomalies`).
3. **Application Approval Workflow:**
   - Strict adherence to the `approve-and-run` single-use cryptographically signed token workflow before running live extraction.

