# GCP Phase 3.1 — Billing Integration & Consumption Readiness Report

> **Document Status:** Complete Architecture & Gap Analysis  
> **Date:** 2026-11-23  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/gcp-service-account-integration`  
> **Target GCP Project:** `cloud-recommender-pricing-dev` (`963778958698`)  

---

## 1. Executive Context & Deferred Policy Compliance

Under the strict operational guardrails of the `cloud-recommender-poc` repository (AGENTS.md):
- **Zero-Spend & No-Mutation Invariant:** The platform must never incur cloud charges, link credit cards or billing accounts, or create paid resources.
- **Current State:** Project `cloud-recommender-pricing-dev` has no active billing account linked. All billing ingestion features remain intentionally **`DEFERRED`**.
- **Objective of Phase 3.1:** Audit existing GCP pricing engines (Phase A BOM generation) and produce the complete architectural blueprint, schema mapping, and ingestion pipeline design required for full multi-cloud FinOps billing (Phase B Optimization) when live billing is authorized.

---

## 2. Current Implementation: Deterministic Pricing Engine (Phase A)

The repository already includes an operational, deterministic pricing engine for Google Cloud Platform workloads:

### 2.1 Public Cloud Billing Catalog Client (`GcpBillingClient`)
- **API Endpoint:** `https://cloudbilling.googleapis.com/v1/services/{serviceId}/skus`
- **Authentication:** Evaluates public pricing via Google Cloud API Key or Service Account credentials with read-only scopes.
- **Mathematical Exactness:** Converts Google's `{units, nanos}` currency structure to Python `Decimal`:
  $$\text{Price} = \text{Decimal}(\text{units}) + \left(\frac{\text{Decimal}(\text{nanos})}{1{,}000{,}000{,}000}\right)$$
  Eliminates IEEE-754 floating-point rounding inaccuracies.
- **Regional Deterministic Matching:** `select_matching_gcp_sku()` selects SKUs based on exact region matching, usage type (`OnDemand`, `Preemptible`), and keyword filtering, rejecting arbitrary `skus[0]` fallbacks.

### 2.2 Offline Fallback Dataset
- When offline or during mock testing, the pricing engine falls back to `backend/src/cloud_recommender/data/gcp_pricing_catalog.json`, ensuring 100% testability without external network calls.

---

## 3. Enterprise GCP FinOps Billing Architecture (Phase B Blueprint)

In enterprise Google Cloud environments, itemized cost and usage telemetry is **not** polled via high-frequency REST APIs. Instead, Google Cloud provides the **Cloud Billing Export to BigQuery**, which streams real-time, audit-grade billing records into BigQuery tables.

### 3.1 Architectural Flow

```
+-------------------------------------------------------------------------------+
|                             Google Cloud Tenant                               |
|                                                                               |
|  +-------------------------+              +--------------------------------+  |
|  |  Cloud Billing Account  |              |        BigQuery Dataset        |  |
|  |   (Usage & Spend Log)   | -----------> |   (Itemized Billing Tables)    |  |
|  +-------------------------+   Streaming  +--------------------------------+  |
|                                  Export                  |                    |
+----------------------------------------------------------|--------------------+
                                                           |
                                      Read-Only SQL        | BigQuery API
                                      via Service Account  | (bigquery.googleapis.com)
                                                           v
+-------------------------------------------------------------------------------+
|                       Bizmetric FinOps Platform Backend                       |
|                                                                               |
|  +-------------------------------------------------------------------------+  |
|  |                      GcpBillingIngestionService                         |  |
|  |  1. Authenticates via Service Account (finops-gcp-reader)               |  |
|  |  2. Enforces Application-Managed Approval Token                         |  |
|  |  3. Executes incremental partitioned query on _PARTITIONTIME            |  |
|  |  4. Normalizes raw GCP BigQuery rows into FOCUS/FinOps domain models    |  |
|  +-------------------------------------------------------------------------+  |
|                                      |                                        |
|                                      v                                        |
|  +-------------------------------------------------------------------------+  |
|  |                       PostgreSQL FinOps Ledger                          |  |
|  |  - billing_usage_records  (Quantity, DBU/Core-Hours, Effective Cost)    |  |
|  |  - billing_price_records  (SKU List Prices & Contract Rates)            |  |
|  |  - billing_source_checkpoints (High watermarks & timestamps)            |  |
|  |  - billing_ingestion_runs (Cryptographic approval audit trail)          |  |
|  +-------------------------------------------------------------------------+  |
|                                      |                                        |
|                                      v                                        |
|  +-------------------------------------------------------------------------+  |
|  |                 Unified Multi-Cloud FinOps Dashboards                   |  |
|  |  (Executive Cost Overview • Cost Allocation • Cost Explorer • Advisor)  |  |
|  +-------------------------------------------------------------------------+  |
+-------------------------------------------------------------------------------+
```

### 3.2 The Three BigQuery Export Tables
1. **Standard Usage Cost Export (`gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`):**
   - Contains daily/hourly spend per project, service, SKU, and region.
   - Ideal for high-level executive spend overviews and cost trending.
2. **Detailed Usage Cost Export (`gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>`):**
   - **The FinOps Gold Standard:** Contains the specific resource ID (`resource.name`, `resource.global_name`), user labels, and GKE container annotations.
   - Enables exact resource-level cost attribution, idle resource waste detection, and departmental chargeback.
3. **Pricing Export (`cloud_pricing_export`):**
   - Contains customer-specific negotiated rates, committed use discount (CUD) rates, and public list prices.
   - Enables automatic pricing reconciliation against raw usage.

---

## 4. BigQuery to FinOps Ledger Schema Mapping

The Bizmetric FinOps Platform uses a standardized, multi-cloud PostgreSQL schema. Below is the mapping from GCP BigQuery export columns to the existing `billing_usage_records` and `billing_price_records` tables:

### 4.1 Usage Records Mapping (`billing_usage_records`)

| GCP BigQuery Column | FinOps Database Field | Data Type | Notes & Transformation |
| :--- | :--- | :--- | :--- |
| `billing_account_id` | `billing_account_id` | `VARCHAR(32)` | Cleaned billing account ID (e.g. `01ABCD-23EF45-678901`) |
| `'gcp'` | `cloud` | `VARCHAR(16)` | Cloud provider identifier: `'gcp'` |
| `project.id` | `workspace_id` / `account_id` | `VARCHAR(64)` | GCP Project ID |
| `sku.id` | `sku` | `VARCHAR(128)` | GCP SKU ID (e.g. `011E-3072-CBDB`) |
| `service.description` | `service_name` | `VARCHAR(128)` | E.g. `'Compute Engine'`, `'Cloud Storage'`, `'BigQuery'` |
| `sku.description` | `sku_description` | `TEXT` | Full SKU name |
| `usage_start_time` | `usage_start_time` | `TIMESTAMP` | Start of usage window |
| `usage_end_time` | `usage_end_time` | `TIMESTAMP` | End of usage window |
| `usage_start_time::date`| `usage_date` | `DATE` | Canonical partition date |
| `usage.amount` | `usage_quantity` | `NUMERIC(24,10)` | Raw consumption amount (Core-hours, GiB-months, seconds) |
| `usage.unit` | `usage_unit` | `VARCHAR(32)` | Consumption unit (e.g. `byte-seconds`, `seconds`, `requests`) |
| `cost` | `effective_cost` | `NUMERIC(18,6)` | Net billed cost after regular discounts |
| `currency` | `currency` | `VARCHAR(8)` | Currency code (e.g. `USD`, `EUR`, `INR`) |
| `resource.name` | `resource_id` | `TEXT` | Full canonical resource URI |
| `labels` | `tags` | `JSONB` | Key-value dictionary of user labels |
| `credits` | `discounts` | `JSONB` | CUDs, sustained use discounts, promotional credits |

### 4.2 Rate Card & Pricing Mapping (`billing_price_records`)

| GCP Pricing Column | FinOps Database Field | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `'gcp'` | `cloud` | `VARCHAR(16)` | `'gcp'` |
| `sku.id` | `sku` | `VARCHAR(128)` | Target SKU ID |
| `service.id` | `service_id` | `VARCHAR(64)` | GCP Service ID |
| `pricing_expression.tiered_rates[0].unit_price` | `list_price` | `NUMERIC(18,8)` | Base list price in USD |
| `pricing_expression.usage_unit` | `unit` | `VARCHAR(32)` | Rate card unit |
| `currency` | `currency` | `VARCHAR(8)` | Currency code |
| `pricing_expression.effective_time` | `effective_from` | `TIMESTAMP` | Price validity start date |

---

## 5. Ingestion Pipeline & Checkpoint Architecture

When billing is operational, ingestion will follow the proven **Application-Managed Approval & Checkpoint Pattern** established in Phase 2.1C for Databricks:

1. **Application-Managed Approval (`POST /api/v1/finops/ingestion/approve-and-run`):**
   - Operator clicks **"Approve & Start GCP Ingestion"** in the FinOps UI.
   - Backend validates `FinOpsAdmin` RBAC, checks project status, issues a short-lived single-use HMAC approval token, and executes extraction internally.
2. **Incremental High Watermark Extraction:**
   - Queries BigQuery using partition filtering:
     ```sql
     SELECT * FROM `PROJECT.DATASET.gcp_billing_export_resource_v1_ACCOUNT`
     WHERE _PARTITIONTIME >= TIMESTAMP(@last_checkpoint_timestamp)
       AND _PARTITIONTIME < TIMESTAMP(@current_run_timestamp)
     ORDER BY export_time ASC
     LIMIT 50000;
     ```
   - Persists high watermark in `billing_source_checkpoints` under `source_key = 'gcp:{project_id}:billing'`.
3. **Multi-Chunk Result Pagination:**
   - BigQuery client streams results in pages (up to 10,000 rows per chunk) with streaming insert into PostgreSQL `billing_usage_records`.
4. **Multi-Dimensional Reconciliation:**
   - Cross-references raw usage against the pricing export.
   - Calculates exact savings from Sustained Use Discounts (SUD) and Committed Use Discounts (CUD).

---

## 6. Implementation Readiness & Gap Analysis Matrix

| FinOps Capability | Current Status | Implemented Components | Gaps to Resolve Upon Billing Enablement |
| :--- | :---: | :--- | :--- |
| **Catalog Pricing Engine** | **WORKING** | `GcpBillingClient`, `GcpPricingEngine`, offline catalog | None (Phase A BOM pricing operational). |
| **BigQuery API Connectivity** | **READY** | `bigquery.googleapis.com` enabled in target project | Awaiting BigQuery dataset creation. |
| **Service Account Permissions** | **READY** | `finops-gcp-reader` authenticated live | Grant `roles/bigquery.dataViewer` and `roles/bigquery.jobUser`. |
| **Database Schema** | **READY** | PostgreSQL `billing_usage_records` and `billing_price_records` | Multi-cloud schema already supports `cloud = 'gcp'`. |
| **BigQuery Ingestion Service** | **IMPLEMENTED (Design)** | Pipeline architecture and query generator mapped | Implement `GcpBigQueryBillingService` using Google BigQuery Python client. |
| **Billing Account Export** | **DEFERRED** | Export configuration documented | Requires linked billing account and export setup in GCP Console. |
| **Approval UI Action** | **READY** | `approve-and-run` endpoint pattern established | Add GCP option to FinOps Command Center ingestion dropdown. |

---

## 7. Recommended Administrator Setup Steps (When Ready for Billing)

When the organization authorizes linking an active billing account:
1. **Configure BigQuery Export in GCP Console:**
   - Go to **Billing** &rarr; **Billing Export**.
   - Enable **Detailed usage cost** and **Pricing export**.
   - Select target BigQuery dataset (e.g. `cloud_recommender_billing`).
2. **Grant BigQuery Permissions to FinOps Service Account:**
   ```bash
   gcloud projects add-iam-policy-binding "cloud-recommender-pricing-dev" \
     --member="serviceAccount:finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com" \
     --role="roles/bigquery.dataViewer"
   
   gcloud projects add-iam-policy-binding "cloud-recommender-pricing-dev" \
     --member="serviceAccount:finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com" \
     --role="roles/bigquery.jobUser"
   ```
3. **Execute Approved Ingestion:**
   - Run `POST /api/v1/finops/ingestion/approve-and-run` with `cloud="gcp"`.

