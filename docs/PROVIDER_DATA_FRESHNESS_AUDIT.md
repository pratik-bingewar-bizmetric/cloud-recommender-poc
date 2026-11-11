# Provider-Specific Data Freshness & Ingestion Latency Audit

> **Document:** `docs/PROVIDER_DATA_FRESHNESS_AUDIT.md`  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/databricks-apps-integration`  
> **Audit Type:** Forensic Data Ingestion Cadence & Latency Audit  
> **Status:** AUDITED — EVIDENCE-BASED ASSESSMENT  
> **Overall Classification:** **4. DOCUMENTED & DESIGNED ONLY (THE "30-MINUTE INGESTION CADENCE" IS A HARDCODED UI STRING; NO BACKGROUND SCHEDULER EXISTS)**  

---

## 1. Executive Summary & Forensic Findings on the "30-Minute Cycle" Claim

A critical investigation was conducted into the claim:
> *"Billing ingestion cadence operates every 30 minutes with a p95 usage event latency of 18 minutes."*

### Forensic Audit Findings:
1. **The "30-Minute Cadence" Is a Static Hardcoded String:**  
   In [`backend/src/cloud_recommender/services/databricks/finops_analytics_service.py:5258–5264`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L5258-L5264), the pipeline health metrics are hardcoded static Python string literals:
   ```python
   PipelineHealthMetric(metric_name="Billing Ingestion Cadence", metric_value="Every 30 minutes"),
   PipelineHealthMetric(metric_name="Usage Event Latency p95", metric_value="18 minutes"),
   PipelineHealthMetric(metric_name="Last Successful Reconciliation", metric_value="Today 10:15 UTC"),
   ```
2. **Zero Automated Background Schedulers Exist in Backend:**  
   - A search for background schedulers (`apscheduler`, `celery`, `cron`, `temporal`, `airflow`, or recurring `asyncio` tasks) across `backend/` returned **zero matches**.
   - The application executes ingestion and discovery **only on-demand** when a user clicks a button in the UI or invokes an API endpoint.
3. **Provider Publication Realities Preclude 30-Minute End-to-End Billing Freshness:**  
   Cloud billing exports are batch-published by providers on 4- to 24-hour cycles. Claiming a live 30-minute end-to-end freshness for billing invoices is technically impossible due to provider-side upstream publication lag.

---

## 2. Technical Latency Definitions & Conceptual Distinctions

To ensure clear communication with enterprise clients, the five distinct components of data freshness must be distinguished:

```
[Event Occurs in Cloud]
       │
       ▼  (1. Provider Publication Delay: 2 to 24 hours)
[Published to Provider Export / System Table]
       │
       ▼  (2. Polling Interval: Manual on-demand click / No background cron)
[Ingestion Triggered by Platform]
       │
       ▼  (3. Ingestion & Network Latency: 2 to 15 seconds)
[Extracted & Staging Written]
       │
       ▼  (4. Processing & Normalization Latency: < 500 ms)
[Saved in Database / In-Memory Store]
       │
       ▼  (5. Dashboard Freshness: Cached / On-Mount Refresh)
[Rendered in User Browser]
```

1. **Source Publication Delay:** The time elapsed between a cloud resource consuming energy and the provider generating the metering record in its billing pipeline (Azure Cost Management: 8–24 hrs; AWS CUR: 8–24 hrs; GCP BigQuery: 4–24 hrs; Databricks System Tables: 1–6 hrs).
2. **Polling Interval:** The frequency at which the platform's ingest engine checks for new provider records (currently **On-Demand / Manual only**).
3. **Ingestion Latency:** The duration of network extraction and file download.
4. **Processing Latency:** Time taken to parse, deduplicate, and join rate cards (< 500 ms in memory).
5. **Dashboard Freshness:** Frequency of client-side data refetching (on page navigation).

---

## 3. Provider-by-Provider Measured Freshness Matrix

| Cloud Provider / Telemetry Source | Upstream Publication Cadence | Platform Ingestion Trigger | Latest Observed Source Timestamp | Latest Successful Ingestion | Measured End-to-End Freshness | Operational Status |
|:---|:---|:---|:---:|:---:|:---:|:---:|
| **Databricks `system.billing.usage`** | 1 to 6 hours batch delay | Manual operator approval (Zero-Execution Gate) | `2026-11-04T23:59:59Z` (Baseline fixture) | On-demand | **NOT MEASURED (Offline Baseline Active)** | **PARTIALLY IMPLEMENTED (Gate Verified)** |
| **Databricks `system.billing.list_prices`** | Monthly / Event-driven updates | Ingested concurrently with usage | `2026-01-01T00:00:00Z` (Rate card) | On-demand | **NOT MEASURED (Static Rate Card)** | **IMPLEMENTED AND VERIFIED** |
| **Databricks `system.query.history`** | Near-real-time (2–15 minutes) | On-demand API query | Current day (Mock baseline) | On-demand | **NOT MEASURED** | **PARTIALLY IMPLEMENTED** |
| **Azure Resource Inventory (ARM)** | Immediate (Near-real-time read) | Live query on Account selection | Live read from ARM REST endpoint | Real-time on page load | **< 5 seconds (Real-time)** | **IMPLEMENTED AND VERIFIED** |
| **Azure Cost Management Export** | Batch (1 to 2 times daily; 8–24h lag) | Standalone sync agent script | Scripted only | None active in live app | **NOT MEASURED** | **DESIGNED ONLY** |
| **Azure Monitor Metrics** | 1 to 5 minutes aggregation | REST API query | Real-time | Real-time | **~5 minutes** | **IMPLEMENTED AND VERIFIED** |
| **AWS CUR / Cost Explorer** | Batch (3 times daily) | N/A (`ENABLE_AWS = False`) | N/A | None | **NOT APPLICABLE** | **NOT IMPLEMENTED** |
| **AWS CloudWatch Metrics** | 1 to 5 minutes | N/A (`ENABLE_AWS = False`) | N/A | None | **NOT APPLICABLE** | **NOT IMPLEMENTED** |
| **GCP Cloud Billing Export** | Streamed/Batch (4 to 24 hours) | Benchmark fixture fallback | Static fixture | Static fixture | **NOT MEASURED (Fixture)** | **NOT IMPLEMENTED** |
| **GCP Cloud Monitoring** | 1 to 5 minutes | REST API client | Real-time | Real-time | **~5 minutes** | **IMPLEMENTED AND VERIFIED** |

---

## 4. Key Takeaways for Client Communication

1. **Do Not Claim Automated 30-Minute Billing Refreshes:** Upstream cloud billing data from Azure and AWS is not published every 30 minutes by Microsoft or Amazon.
2. **Accurate Positioning:**
   - **Infrastructure Inventory & Health:** Real-time on-demand discovery (< 5 seconds latency).
   - **Resource Utilization Telemetry:** 5-minute metric granularity via Azure Monitor and GCP Cloud Monitoring.
   - **Billing & Cost Data:** Daily batch reconciliation aligned with provider invoice publication cycles.

