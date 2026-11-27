# AWS Phase 2.2 — CloudWatch Live Telemetry Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** 2026-11-26  
> **Target Resource:** Discovered Lambda Function `databricks-s3-ingest-24ae9`  
> **Region:** `eu-north-1`  
> **Status:** BOUNDED TELEMETRY PLAN AUDITED (LIVE DISPATCH PENDING AUTHORIZATION)

---

## 1. Discovered Resource Telemetry Scope

In accordance with Phase 2.2 requirements:
- No hypothetical EC2 instance metrics are queried (0 EC2 instances exist in account `435305479688`).
- Telemetry queries target the single verified live Lambda function: `databricks-s3-ingest-24ae9`.
- Lookback window is strictly bounded to the past 24 hours (`lookback_hours = 24`).
- No monitoring agents are deployed; no Container Insights or paid enhanced metrics are activated.

---

## 2. Metric Specifications & Statistics

| Metric Name | Namespace | Statistic | Unit | Dimension | Billable Queries |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Invocations** | `AWS/Lambda` | `Sum` | `Count` | `FunctionName=databricks-s3-ingest-24ae9` | 1 |
| **Duration** | `AWS/Lambda` | `Average` | `Milliseconds` | `FunctionName=databricks-s3-ingest-24ae9` | 1 |
| **Errors** | `AWS/Lambda` | `Sum` | `Count` | `FunctionName=databricks-s3-ingest-24ae9` | 1 |
| **Throttles** | `AWS/Lambda` | `Sum` | `Count` | `FunctionName=databricks-s3-ingest-24ae9` | 1 |
| **Total Queries** | — | — | — | — | **4** |

### Data Representation:
- Datapoint values of `0.0` (zero executions or errors) are strictly preserved as numeric zero and distinguished from missing/unreported datapoints (`None` / `NO_DATA`).
- For EC2 memory metrics without the CloudWatch agent, the system strictly reports `INSTRUMENTATION_REQUIRED`.

