# AWS Phase 2.1 — Telemetry and Pricing Intelligence Report

> **Repository:** `cloud-recommender-poc`  
> **Modules:** `backend/src/cloud_recommender/services/aws/cloudwatch_service.py`, `backend/src/cloud_recommender/services/aws/pricing_service.py`  
> **Status:** AUDITED, TESTED & ENFORCED

---

## 1. CloudWatch Telemetry Architecture & Instrumentation Gating

AWS CloudWatch provides historical time-series metrics required for rightsizing and waste detection. However, querying unavailable or uninstrumented metrics wastes API quotas and produces misleading zero-values.

### 1.1 Instrumentation Gating Invariants

- **EC2 Compute Telemetry:**
  - `CPUUtilization`, `NetworkIn`, `NetworkOut`, `DiskReadBytes`, `DiskWriteBytes` are basic hypervisor-level metrics available out of the box.
  - `MemoryUtilization` is **not** natively available without the CloudWatch Agent installed inside the guest OS. Querying memory on an uninstrumented EC2 instance is rejected with `instrumentation_status="AGENT_REQUIRED"`.
- **Lambda Serverless Telemetry:**
  - `Invocations`, `Duration`, `Errors`, `Throttles`, and `ConcurrentExecutions` are collected natively.
- **RDS Database Telemetry:**
  - `CPUUtilization`, `FreeStorageSpace`, `DatabaseConnections`, and `ReadIOPS` are queried through standard dimensions (`DBInstanceIdentifier`).

---

## 2. Pricing Intelligence & Canonical Cache Invariants

The AWS Price List API (`pricing.us-east-1.amazonaws.com`) provides official retail rates. Because Price List queries are relatively slow and rate-limited, Phase 2.1 establishes a strict canonical caching contract.

### 2.1 Canonical Cache Key Specification

$$\text{Cache Key} = \text{service\_code} : \text{region} : \text{resource\_type} : \text{instance\_type\_or\_tier} : \text{storage\_type}$$

Example:
`AmazonEC2:eu-north-1:AWS::EC2::Instance:t3.micro:gp3`

### 2.2 Pricing Source Classification

Every price returned to the frontend or calculation engine carries an explicit classification:
1. `LIVE_AWS_PRICE_LIST`: Retrieved in real-time from the AWS Price List API.
2. `CACHED_AWS_PRICE_LIST`: Retrieved from the in-memory or database cache originating from Price List API.
3. `OFFLINE_REFERENCE_CATALOG`: Fallback rate from the local deterministic reference catalog when Price List API is unavailable or offline mode is active.

### 2.3 Operating Hours Standard

AWS computes on-demand compute monthly costs using the standard **730 operating hours per month** ($365 \times 24 / 12 = 730$). Phase 2.1 standardizes all monthly rate estimations on 730 hours and marks partial estimates explicitly with `is_partial_estimate=True` when unit pricing represents only a component of total cost (e.g., Lambda invocation count without duration memory charges).

