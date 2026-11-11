# Client Architecture Questionnaire — Implementation Evidence Audit

> **Master Deliverable:** `docs/CLIENT_ARCHITECTURE_QUESTIONNAIRE_EVIDENCE_REPORT.md`  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/databricks-apps-integration`  
> **Target Environment:** Azure Databricks Apps (`bizmetric-finops`, Workspace `642006393507276`)  
> **Audit Type:** Forensic Architecture & Codebase Evidence Assessment  
> **Mode:** 100% Read-Only Forensic Audit (Zero Source Mutations, Zero Database Writes, Zero Cloud Mutations)  
> **Audit Date:** 2026-11-11  
> **Investigator:** Principal FinOps & Cloud Solutions Architect / Staff Software Engineer  

---

## Executive Summary & High-Level Classification Scorecard

This audit provides forensic, evidence-backed answers to the eight core client architecture questions regarding the **Bizmetric FinOps & Infrastructure Intelligence Platform**. Every capability is evaluated strictly against the active codebase, database schemas, API contracts, and automated tests.

### Scorecard by Client Question:

| # | Architecture Domain | Implemented Status | Confidence Level | Primary Audit Conclusion |
|:---:|:---|:---:|:---:|:---|
| **Q1** | **Canonical Cost Data Model & FOCUS Alignment** | **3. PARTIALLY IMPLEMENTED / 4. DESIGNED ONLY** | High | **FOCUS is NOT implemented.** The platform uses a proprietary internal model directly derived from Databricks System Tables (`system.billing.usage` / `list_prices`). |
| **Q2** | **Multi-Cloud Cost Normalization** | **3. PARTIALLY IMPLEMENTED** | High | Databricks DBU charges and strict unit separation (`DBU`, `BYTE_HOURS`, `TOKEN`) are fully normalized. **Amortization, reservations (RIs, CUDs, Savings Plans), and dynamic currency conversions are NOT implemented.** |
| **Q3** | **Cost Allocation & Rule Engine** | **3. PARTIALLY IMPLEMENTED / 4. DESIGNED ONLY** | High | Tag extraction from Azure ARM and Databricks is implemented. **The allocation rulebook, BU spend breakdown, and completeness metrics are hardcoded in-memory demonstration fixtures.** No customer rule editor or DB model exists. |
| **Q4** | **Optimization Recommendations & Savings Validation** | **1. IMPLEMENTED & VERIFIED (Heuristics) / 4. DESIGNED ONLY (Savings Validation)** | High | 8 deterministic heuristic rules (Azure/GCP) and 5 Databricks decisions are active with AI explanations. Native Cloud Advisors (Azure Advisor) are not integrated. **Post-implementation realized savings validation is designed only.** |
| **Q5** | **Detailed L2 Microsoft Fabric Architecture** | **3. PARTIALLY IMPLEMENTED** | High | Lakehouse provisioning (`4bba3647-...`), Delta schemas, and Sync Agent are scripted in `fabric-integration/`. The UDF used local SQLite at `/tmp/lakehouse_finops.db`. **The live web app has Fabric disabled by default (`ENABLE_MICROSOFT_FABRIC = False`).** |
| **Q6** | **Security & Multi-Tenant Governance** | **1. IMPLEMENTED & VERIFIED (Auth/RBAC) / 5. NOT IMPLEMENTED (Tenant Isolation)** | High | Entra ID RS256 JWT auth, RBAC (`Admin`, `FinOpsAdmin`, `Reader`), and Zero-Execution HMAC approval tokens are verified. **PostgreSQL database tables lack `tenant_id` columns; multi-tenant row isolation is not implemented (single-tenant only).** |
| **Q7** | **Provider-Specific Data Freshness** | **4. DOCUMENTED & DESIGNED ONLY** | High | **The "30-minute ingestion cadence" is a static hardcoded UI string.** No automated background scheduler exists in backend. Freshness for billing is daily batch; resource inventory is real-time on-demand (< 5s). |
| **Q8** | **FinOps Action Loop & Remediation** | **3. PARTIALLY IMPLEMENTED (Human Advisory)** | High | Advisory opportunity detection, impact analysis, prioritization, and interactive status changes are implemented. **Automated cloud remediation is blocked by the Zero-Execution policy. Ticketing integrations (Jira/ServiceNow) are not implemented.** |

---

## Detailed Evidence-Backed Answers to the 8 Client Questions

---

### QUESTION 1 — CANONICAL COST DATA MODEL AND FOCUS ALIGNMENT

#### 1.1 Direct Answer & Forensic Findings
- **Is the implementation based on FinOps FOCUS?**  
  **No.** The implementation is **not** based on the FinOps Open Cost & Usage Specification (FOCUS). A repository-wide code search (`git grep -i "focus"`) confirms zero occurrences of FOCUS standard schema definitions, column names, or specification references.
- **Specification Version Targeted:**  
  None. FOCUS 1.0 / 1.1 are documented as architectural targets in roadmaps, but have zero active implementation in the code.
- **Data Model Classification:**  
  **Proprietary internal model.** The primary billing fact tables and schemas mirror Databricks System Tables (`system.billing.usage` and `system.billing.list_prices`).
- **Implemented vs. FOCUS Columns:**  
  None of the standard uppercase FOCUS 1.0 columns (`BilledCost`, `EffectiveCost`, `ChargePeriodStart`, `ConsumedQuantity`, `SubAccountId`) are used. The platform uses snake_case Databricks fields (`usage_quantity`, `usage_unit`, `sku_name`, `effective_cost`, `usage_start_time`, `workspace_id`).
- **Fact Table & Dimension Storage:**  
  - Relational Database (PostgreSQL): [`BillingUsageRecordModel`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/db/models.py#L568-L690) (`billing_usage_records`) stores normalized usage events and effective cost.
  - Price Table: [`BillingPriceRecordModel`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/db/models.py#L692-L749) (`billing_price_records`) stores published list price intervals.
  - OneLake Lakehouse Schema: [`fabric-integration/lakehouse/schemas.py:34–78`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/fabric-integration/lakehouse/schemas.py#L34-L78) defines an analytical Delta table `cost_details` matching Azure Cost Management export columns.
  - Commitments, Credits, and Invoices: **Not stored in separate fact tables.**

#### 1.2 Evidence References
- Database ORM Models: [`backend/src/cloud_recommender/db/models.py:568–749`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/db/models.py#L568-L749)
- Alembic Migration: [`backend/alembic/versions/2026_11_07_0002_billing_ingestion_and_reconciliation.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/alembic/versions/2026_11_07_0002_billing_ingestion_and_reconciliation.py)
- Domain Schemas: [`backend/src/cloud_recommender/schemas/billing_ingestion.py:17–77`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/schemas/billing_ingestion.py#L17-L77)
- Detailed Mapping Audit: [`docs/FOCUS_CANONICAL_COST_MODEL_MAPPING.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/FOCUS_CANONICAL_COST_MODEL_MAPPING.md)

#### 1.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"The platform uses a normalized, high-integrity billing ledger schema designed for Databricks System Tables, providing strict idempotency by record ID, unit segregation, and exact price matching."*
- **DO NOT CLAIM:** *"The platform is FinOps FOCUS 1.0 compliant."* (Factually false).

---

### QUESTION 2 — COST NORMALIZATION

#### 2.1 Direct Answer & Forensic Findings
- **Gross / List Cost:** Partially implemented. Backend joins SKU against list prices in `BillingPriceRecordModel` ([`billing_ingestion_service.py:366`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/billing_ingestion_service.py#L366)).
- **Contracted / Billed Cost:** **Not implemented.** No customer enterprise discount schedules or invoice reconciliation tables exist.
- **Amortization of Reservations & Savings Plans:** **Not implemented.**  
  - Azure Reservations are not amortized.
  - AWS Savings Plans / RIs are not implemented (`ENABLE_AWS = False`).
  - GCP Committed-Use Discounts are not implemented.
  - The waste engine ([`waste_debt_engine.py:46–60`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/inventory/waste_debt_engine.py#L46-L60)) checks if an active reservation exists to prevent claiming phantom savings on stopped VMs, but does not calculate financial amortization.
- **Credits & Retractions:** Provider promotional/invoice credits are not ingested. However, Databricks negative usage quantities (retractions/corrections) are strictly preserved in `BillingUsageRecord.usage_quantity`.
- **Currency Conversion:** Handled on the frontend via static fixed exchange rates ([`frontend/src/lib/financials.ts:18–44`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/frontend/src/lib/financials.ts#L18-L44): EUR 0.92, GBP 0.79, JPY 154.2). No dynamic FX rate feed exists.
- **Unit Aggregation Incompatibilities:** Fully enforced. `billing_ingestion_service.py:349–353` explicitly blocks cross-unit addition (`DBU` vs `BYTE_HOURS` vs `TOKEN`).
- **Databricks DBU vs. Cloud Infrastructure Charges:** DBU charges are metered via `BillingUsageRecord` ($176,840.00 across 88,420 DBU). Azure VMs are metered via ARM inventory ($284,620.00). The platform documents their boundary ([`finops_analytics_service.py:1627`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L1627)), but does not execute automated cross-billing VM meter reconciliation.

#### 2.2 Evidence References
- Normalization Logic: [`backend/src/cloud_recommender/services/databricks/billing_ingestion_service.py:348–378`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/billing_ingestion_service.py#L348-L378)
- Reservation Guard: [`backend/src/cloud_recommender/services/inventory/waste_debt_engine.py:46–60`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/inventory/waste_debt_engine.py#L46-L60)
- Currency Engine: [`frontend/src/lib/financials.ts:18–44`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/frontend/src/lib/financials.ts#L18-L44)
- Normalization Matrix: [`docs/MULTI_CLOUD_COST_NORMALIZATION_MATRIX.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/MULTI_CLOUD_COST_NORMALIZATION_MATRIX.md)

#### 2.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"The platform enforces strict unit segregation preventing incompatible metrics from being summed, and computes exact effective DBU costs using temporal list-price joins."*
- **DO NOT CLAIM:** *"The platform automatically amortizes Azure reservations or ingests AWS Savings Plans and GCP CUDs."*

---

### QUESTION 3 — COST ALLOCATION

#### 3.1 Direct Answer & Forensic Findings
- **Tag Interpretation:** Tags are parsed from Azure ARM (`res.tags`) and Databricks (`custom_tags`).
- **Ownership & Cost Center Derivation:** Tag values (`Owner`, `CostCenter`, `Environment`) are extracted into `custom_tags_json` in the usage record.
- **Untagged Resources:** Highlighted in the ledger with `allocation_status = "Unallocated"` and `owner_tag = "unassigned"` (e.g. Databricks Apps, $1,240.00).
- **Customer Allocation Rule Engine:** **NOT IMPLEMENTED.**  
  The 4 allocation rules displayed on the Cost Allocation page (`Production Owner Tag`, `Workspace Mapping`, `Shared Storage Allocation`, `Fallback Central Pool`) are **hardcoded Python fixtures** in [`finops_analytics_service.py:2788–2820`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L2788-L2820).
- **Rule Configurability:** Customers **cannot** create, edit, approve, version, or deactivate allocation rules. No database tables or CRUD APIs exist.
- **Mathematical Reconciliation:** In the 24-record canonical ledger, allocated spend ($175,600.00) + unallocated spend ($1,240.00) equals total spend ($176,840.00) with zero discrepancy.

#### 3.2 Evidence References
- Hardcoded Allocation Rules: [`backend/src/cloud_recommender/services/databricks/finops_analytics_service.py:2788–2820`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L2788-L2820)
- Unallocated Spend Test: [`backend/tests/test_finops_analytics.py::test_unattributed_cost_preservation_for_apps`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/tests/test_finops_analytics.py)
- Allocation Audit Report: [`docs/COST_ALLOCATION_IMPLEMENTATION_AUDIT.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/COST_ALLOCATION_IMPLEMENTATION_AUDIT.md)

#### 3.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"The platform extracts FinOps tags from cloud infrastructure and Databricks usage records, reconciling allocated and unallocated spend in the billing ledger."*
- **DO NOT CLAIM:** *"Customers can dynamically define, edit, and version custom allocation rules in the platform today."*

---

### QUESTION 4 — OPTIMIZATION RECOMMENDATIONS AND REALIZED SAVINGS

#### 4.1 Direct Answer & Forensic Findings
- **Native Cloud Advisors (Azure Advisor, AWS Trusted Advisor, GCP Recommender):** **Not integrated.** The platform does not query native cloud advisor APIs.
- **Bizmetric Deterministic Heuristics:** **Implemented and verified.** [`waste_debt_engine.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/inventory/waste_debt_engine.py) implements 8 deterministic rules (unattached disks, deallocated VMs with reservation checks, orphan public IPs, unattached NICs).
- **Databricks Workload Decisions:** **Implemented and verified.** [`finops_analytics_service.py:520–680`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L520-L680) implements 5 active recommendations (`dec-01` to `dec-05` totaling $24,530.00/month potential savings).
- **Generative AI Explanations:** **Implemented and verified.** Azure AI Foundry / OpenAI GPT-4o (`foundry_provider.py`) generates contextual justifications and implementation steps without inventing financial numbers.
- **Savings Tracking Lifecycle:**  
  - Potential and Estimated savings: Computed deterministically.
  - Approved and Deferred actions: Interactive via `POST /api/v1/finops/optimization-advisor/{decision_id}/action` and tracked in memory.
  - Realized and Verified savings: **Designed only.** The platform does not perform automated post-implementation telemetry comparisons against baselines.

#### 4.2 Evidence References
- Waste Engine: [`backend/src/cloud_recommender/services/inventory/waste_debt_engine.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/inventory/waste_debt_engine.py)
- Databricks Decisions: [`backend/src/cloud_recommender/services/databricks/finops_analytics_service.py:520–680`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L520-L680)
- AI Narrative Provider: [`backend/src/cloud_recommender/services/ai/foundry_provider.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/ai/foundry_provider.py)
- Optimization Audit: [`docs/OPTIMIZATION_AND_SAVINGS_VALIDATION_AUDIT.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/OPTIMIZATION_AND_SAVINGS_VALIDATION_AUDIT.md)

#### 4.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"The platform uses deterministic heuristic rules to identify idle compute, unattached storage, and oversized Databricks clusters, calculating estimated savings with explicit rate-card assumptions."*
- **DO NOT CLAIM:** *"The platform automatically verifies realized savings via post-implementation billing telemetry or pulls recommendations from Azure Advisor."*

---

### QUESTION 5 — DETAILED L2 MICROSOFT FABRIC ARCHITECTURE

#### 5.1 Direct Answer & Forensic Findings
- **Resolution of Apparent Discrepancy:**  
  - The Fabric UDF (`fabric-integration/fabric-udf/function_app.py`) **does use SQLite at `/tmp/lakehouse_finops.db`** as its local temporary connection store.
  - The 5 OneLake Delta tables (`resource_inventory`, `cost_details`, `resource_metrics`, `token_telemetry`, `sync_history`) are scripted in [`fabric-integration/lakehouse/init_delta_schemas.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/fabric-integration/lakehouse/init_delta_schemas.py) and targeted at Lakehouse `4bba3647-0112-4adc-8b18-f7a422461404` in Workspace `672a6995-4190-4000-befd-5cc6479c3f74`.
  - **Live Web App Status:** The active web application running in `backend/` and `frontend/` **does not read OneLake Delta tables**. Feature flag `ENABLE_MICROSOFT_FABRIC = false` is active in [`frontend/src/config/features.ts:18`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/frontend/src/config/features.ts#L18). The core application serves FinOps telemetry from FastAPI and native Databricks System Tables.
- **Orchestration & Scheduling:** Sync agent is invoked via CLI only; no automated Fabric Data Factory pipeline is scheduled.

#### 5.2 Evidence References
- Lakehouse Config: [`fabric-integration/lakehouse/lakehouse_config.json`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/fabric-integration/lakehouse/lakehouse_config.json)
- Schema Initializer: [`fabric-integration/lakehouse/init_delta_schemas.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/fabric-integration/lakehouse/init_delta_schemas.py)
- Fabric UDF Host: [`fabric-integration/fabric-udf/function_app.py:2348`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/fabric-integration/fabric-udf/function_app.py#L2348)
- Feature Flag: [`frontend/src/config/features.ts:18`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/frontend/src/config/features.ts#L18)
- Fabric Architecture Audit: [`docs/FABRIC_L2_IMPLEMENTED_ARCHITECTURE.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/FABRIC_L2_IMPLEMENTED_ARCHITECTURE.md)

#### 5.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"The platform repository contains provisioned Microsoft Fabric lakehouse configurations and Delta-rs schemas on OneLake, designed for long-term analytical telemetry storage."*
- **DO NOT CLAIM:** *"The live deployed Databricks App currently reads its operational dashboards from OneLake Delta tables."*

---

### QUESTION 6 — SECURITY AND GOVERNANCE

#### 6.1 Direct Answer & Forensic Findings
- **Entra ID Authentication & RBAC:** **Implemented and verified.** Cryptographic JWT validation via PyJWKClient with RS256 algorithm enforcement, tenant ID verification, and role checks (`Admin`, `FinOpsAdmin`, `Reader`) in [`backend/src/cloud_recommender/core/auth.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/core/auth.py).
- **Zero-Execution & Read-Only Governance:** **Implemented and verified.** Cloud connections operate strictly with `Reader` and `Cost Management Reader`. Databricks SQL execution requires HMAC-signed approval tokens.
- **Secret Handling:** Zero plaintext credentials committed or logged. Secrets are stored in Databricks Secret Scopes (`finops-secrets`) in production.
- **Customer / Tenant Data Isolation:** **NOT IMPLEMENTED.**  
  PostgreSQL database tables lack `tenant_id` columns and Row-Level Security (RLS). The application assumes a single-tenant dedicated deployment per instance. In a shared multi-tenant SaaS deployment, cross-tenant leakage would occur.

#### 6.2 Evidence References
- Auth Engine: [`backend/src/cloud_recommender/core/auth.py:41–230`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/core/auth.py#L41-L230)
- SQL Approval Gate: [`backend/src/cloud_recommender/services/databricks/sql_client.py:220–290`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/sql_client.py#L220-L290)
- Auth Test Suite: [`backend/tests/test_entra_auth.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/tests/test_entra_auth.py)
- Security Audit Report: [`docs/SECURITY_AND_TENANT_ISOLATION_AUDIT.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/SECURITY_AND_TENANT_ISOLATION_AUDIT.md)

#### 6.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"The application enforces Microsoft Entra ID JWT authentication, least-privilege read-only cloud permissions, and cryptographic approval gates for Databricks compute queries."*
- **DO NOT CLAIM:** *"The database supports multi-tenant row-level security across different commercial client tenants."*

---

### QUESTION 7 — PROVIDER-SPECIFIC DATA FRESHNESS

#### 7.1 Direct Answer & Forensic Findings
- **The 30-Minute Ingestion Claim:** **Designed only (Hardcoded UI string).**  
  In [`finops_analytics_service.py:5258–5264`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L5258-L5264), the metrics (`Billing Ingestion Cadence: Every 30 minutes`, `Usage Event Latency p95: 18 minutes`) are static string literals.
- **Scheduler Frequency:** **Zero background schedulers exist.** The backend contains no Celery, APScheduler, or cron jobs.
- **Actual Polling Frequency:** Ingestion runs **on-demand only** when manually authorized by an operator.
- **Measured End-to-End Freshness:** **NOT MEASURED.**
- **True Latency Breakdown:**
  - Resource Inventory (ARM): Real-time on-demand discovery (< 5 seconds).
  - Telemetry Metrics (Azure Monitor): ~5 minutes aggregation latency.
  - Billing System Tables: Batch delay of 1 to 6 hours from Databricks runtime.
  - Azure Cost Management Exports: 8 to 24 hours batch publication delay.

#### 7.2 Evidence References
- Static Metrics: [`backend/src/cloud_recommender/services/databricks/finops_analytics_service.py:5258–5264`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L5258-L5264)
- Freshness Audit Report: [`docs/PROVIDER_DATA_FRESHNESS_AUDIT.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/PROVIDER_DATA_FRESHNESS_AUDIT.md)

#### 7.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"Infrastructure inventory is discovered in real-time on-demand, while billing data aligns with daily provider batch export cycles."*
- **DO NOT CLAIM:** *"The platform automatically polls and updates billing data every 30 minutes."*

---

### QUESTION 8 — FINOPS ACTION LOOP

#### 8.1 Direct Answer & Forensic Findings
- **Action Execution:** **Not implemented by design (Zero-Execution Guardrail).** The platform is strictly an advisory system; it never mutates customer subscriptions, stops clusters, or resizes VMs autonomously.
- **Ticketing Integrations:** **Not implemented.** Zero integrations exist for Jira, ServiceNow, or Azure DevOps.
- **Interactive Review:** Implemented in memory. Operators can mark recommendations as Approved, Deferred, or Implemented via the UI, creating in-memory audit log entries.
- **Savings Realization Loop:** **Designed only.** The platform does not track frozen pre-change baselines or evaluate post-change telemetry to verify realized dollar savings.

#### 8.2 Evidence References
- Decision Override Method: [`backend/src/cloud_recommender/services/databricks/finops_analytics_service.py:684–706`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/finops_analytics_service.py#L684-L706)
- Operational Guardrails: [`AGENTS.md:Section 2`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/AGENTS.md)
- Action Lifecycle Audit: [`docs/FINOPS_ACTION_LIFECYCLE_AUDIT.md`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/docs/FINOPS_ACTION_LIFECYCLE_AUDIT.md)

#### 8.3 Safe Client Statements vs. Claims NOT to Make
- **SAFE TO STATE:** *"The platform provides human-in-the-loop decision governance, enabling operators to review, prioritize, approve, and track optimization initiatives without risking unintended infrastructure outages."*
- **DO NOT CLAIM:** *"The platform automatically executes remediations in the cloud or creates tickets in Jira/ServiceNow."*

---

## 3. Product & Architectural Decisions Required

To transition from the current POC state to a full commercial release, leadership must decide on:

1. **FOCUS Adoption Strategy:** Formally adopt FOCUS 1.0 schema definitions in PostgreSQL fact tables, replacing proprietary Databricks column names.
2. **Multi-Tenancy Architecture:** Decide whether to implement PostgreSQL Row-Level Security (RLS) with `tenant_id` partitioning or deploy single-tenant dedicated containers per enterprise client (current model).
3. **Background Scheduling Engine:** Select and deploy an asynchronous job scheduler (Celery, Temporal, or Azure Functions Timer Trigger) to execute true periodic billing ingestion.
4. **ITSM Ticketing Roadmapping:** Prioritize webhook/REST adapters for Jira Cloud and ServiceNow for automated ticket dispatch.
5. **Realized Savings Verification Engine:** Build a telemetry comparator that snapshots 30-day pre-change cost baselines and validates post-change telemetry.

