# LIVE FINOPS DATA ARCHITECTURE SPECIFICATION

> **Document Identifier:** `ARCH-FINOPS-LIVE-2026-01`  
> **Target Version:** `v3.0.0-live-data`  
> **Status:** APPROVED & ENFORCED  
> **Target Environment:** Azure Databricks (`adb-642006393507276.16.azuredatabricks.net`)  
> **Security Guardrail:** 100% Read-Only / Zero-Execution Enforced / Zero Autonomous Cloud Modifications  

---

## 1. Architectural Overview & Design Principles

The Bizmetric FinOps & Infrastructure Intelligence Platform transitions from static baseline fixtures to an authoritative, live-data-driven financial architecture.

```mermaid
flowchart TD
    subgraph Data_Sources["Authoritative Cloud Data Sources"]
        DBX_USAGE["Databricks System Tables<br/>(system.billing.usage)"]
        DBX_PRICES["Databricks System Tables<br/>(system.billing.list_prices)"]
        DBX_QUERIES["Databricks System Tables<br/>(system.query.history)"]
        AZ_ACM["Azure Cost Management REST API<br/>(Microsoft.CostManagement/query)"]
        AZ_ARM["Azure Resource Manager REST API<br/>(Read-Only Resource Hierarchy)"]
    end

    subgraph Ingestion_Layer["Ingestion & Reconciliation Layer"]
        DBX_INGEST["Databricks Billing Ingestion Service<br/>(Idempotent, Decimal Rate Join)"]
        AZ_INGEST["Azure Cost Management Service<br/>(Actual Invoiced Cost Extraction)"]
        DEDUP["Deduplication & Idempotency Store<br/>(Unique Hash on Provider + RecordId)"]
    end

    subgraph Canonical_Store["Canonical Financial Model (PostgreSQL / In-Memory)"]
        CANON_RECS["Canonical Billing Records (FOCUS-Aligned)"]
        CANON_BUDGET["Configured Approved Budgets"]
        CANON_FC["Persisted Forecast Snapshots"]
        CANON_ANOM["Detected Statistical Anomalies"]
        CANON_OPT["Optimization Decisions (Savings Lifecycle)"]
    end

    subgraph Calculation_Engine["Certified FinOps Analytics Services"]
        KPI_ENG["Dynamic KPI Engine (Total Spend, DBU, Platform)"]
        AI_ENG["AI Economics Engine (Prompt/Completion Tokens, Endpoints)"]
        FC_ENG["Run-Rate Projection & MAPE Accuracy Engine"]
        ANOM_ENG["Z-Score Outlier Detector (> 2.5 SD Baseline)"]
        ALLOC_ENG["Tag & Cost Center Allocation Engine"]
    end

    subgraph Presentation_Layer["Next.js FinOps Command Center (UI)"]
        DASH["Executive Overview (7 Certified Cards)"]
        EXP["Cost Explorer & Multi-Cloud Reconciliation"]
        BUDGET_VIEW["Forecast & Budgets (Scenario Simulator)"]
        STATUS_BADGES["Authoritative Status Badges<br/>(LIVE, CACHED, ESTIMATED, SOURCE UNAVAILABLE)"]
    end

    DBX_USAGE --> DBX_INGEST
    DBX_PRICES --> DBX_INGEST
    DBX_QUERIES --> DBX_INGEST
    AZ_ACM --> AZ_INGEST
    AZ_ARM --> AZ_INGEST

    DBX_INGEST --> DEDUP --> CANON_RECS
    AZ_INGEST --> DEDUP --> CANON_RECS

    CANON_RECS --> KPI_ENG
    CANON_RECS --> AI_ENG
    CANON_RECS --> FC_ENG
    CANON_RECS --> ANOM_ENG
    CANON_RECS --> ALLOC_ENG

    CANON_BUDGET --> KPI_ENG
    CANON_FC --> FC_ENG
    CANON_ANOM --> ANOM_ENG
    CANON_OPT --> KPI_ENG

    KPI_ENG --> DASH
    AI_ENG --> DASH
    FC_ENG --> BUDGET_VIEW
    ANOM_ENG --> DASH
    ALLOC_ENG --> EXP
    DASH --> STATUS_BADGES

    style Data_Sources fill:#f8fafc,stroke:#64748b,stroke-width:2px
    style Ingestion_Layer fill:#eff6ff,stroke:#2563eb,stroke-width:2px
    style Canonical_Store fill:#ecfdf5,stroke:#059669,stroke-width:2px
    style Calculation_Engine fill:#faf5ff,stroke:#7c3aed,stroke-width:2px
    style Presentation_Layer fill:#fffbeb,stroke:#d97706,stroke-width:2px
```

### Core Architectural Guardrails:
1. **Zero-Execution & Strict Read-Only Access:** Under no circumstance does the platform issue `CREATE`, `UPDATE`, `DELETE`, or `ALTER` operations to customer subscriptions or Databricks workspaces.
2. **Deterministic Arithmetic:** All pricing multiplications and cost rollups use Python `Decimal` with `ROUND_HALF_UP` to cents. Floating-point accumulation errors are prohibited.
3. **Strict Separation of Telemetry from Cost:** Resource inventory counts and raw telemetry from Azure Resource Manager (ARM) are never multiplied by list prices to fabricate "actual" costs when live billing data is missing.
4. **Honest Data Transparency:** If a provider API is unconfigured or unavailable, the system renders `SOURCE UNAVAILABLE` with diagnostic guidance rather than falling back to fictitious numbers.

---

## 2. Ingestion Pipeline & Provider Integration

### 2.1 Databricks Billing Ingestion (`BillingIngestionService`)
- **Target Workspace:** `642006393507276` (`adb-642006393507276.16.azuredatabricks.net`)
- **Target SQL Warehouse:** `05ed10a52697a344` (`Serverless Starter Warehouse`)
- **System Tables Ingested:**
  1. `system.billing.usage`: Metered consumption events (`usage_quantity`, `usage_unit`, `record_type`, `usage_start_time`, `custom_tags`).
  2. `system.billing.list_prices`: Authoritative contract rate cards (`price_per_unit`, `pricing_unit`, `price_start_time`, `price_end_time`).
  3. `system.query.history`: Query execution duration, cluster attribution, and concurrency profiles.
- **Warehouse Safety Gating:**
  - If the warehouse is `STOPPED`, the service locks live execution, reports `warehouse_status="STOPPED"`, `system_tables_status="APPROVAL_REQUIRED"`, and serves verified cached records with `data_quality_status=DataFreshnessStatus.CACHED`.
  - Zero compute resume commands are issued without separate human authorization.

### 2.2 Azure Cost Management Integration (`AzureCostManagementService`)
- **Target Scope:** Azure Subscription `sub-finops-enterprise-01`.
- **Target REST API:** `POST https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01`.
- **Invoiced Infrastructure Coverage:** Virtual Machines, Managed Disks, ADLS Gen2 Hot/Cool storage capacity, Data Egress bandwidth, and Private Endpoints.
- **Failure Mode:** If Service Principal credentials lack `Cost Management Reader`, returns `DataFreshnessStatus.SOURCE_UNAVAILABLE`.

---

## 3. Canonical Data Model & Deduplication Engine

Every incoming raw event is normalized into a `CanonicalBillingRecord`:

```mermaid
classDiagram
    class CanonicalBillingRecord {
        +String record_id [Primary Key]
        +String provider ["databricks" | "azure"]
        +String billing_account_id
        +String subscription_id
        +String workspace_id
        +String resource_id
        +String service_category ["Compute" | "Storage" | "Network" | "AI"]
        +String sku_name
        +DateTime usage_start_time
        +DateTime usage_end_time
        +String usage_date
        +Decimal usage_quantity
        +String usage_unit ["DBU" | "TB-month" | "GB"]
        +Decimal list_unit_price
        +Decimal effective_cost
        +String currency ["USD"]
        +Boolean is_retraction
        +Boolean is_embedded_in_platform
        +Dict tags
        +DataFreshnessStatus data_quality_status
    }
```

### Deduplication Guarantee:
- Uniqueness is strictly enforced on `(provider, record_id)`.
- Re-running an ingestion job updates existing records in-place without incrementing counts or inflating financial totals.
- Retractions (`usage_quantity < 0`) are preserved with their negative cost and netted against gross spend.

---

## 4. Rebuilt KPI Calculations & Lineage

| KPI Metric | Calculation Methodology | Authoritative Data Source | Double-Counting Safeguard |
| :--- | :--- | :--- | :--- |
| **Total Spend** | $\sum \text{EffectiveCost}_{\text{Databricks}} + \sum \text{EffectiveCost}_{\text{Azure}}$ | `system.billing.usage` $\bowtie$ `system.billing.list_prices` + Azure Cost Management | Storage & Network isolated; AI compute not added twice |
| **Databricks Spend** | $\sum (\text{usage\_quantity} \times \text{matched\_price})$ | `system.billing.usage` (DBU meters) + Delta Lakehouse storage | Compute DBU isolated from raw VM infrastructure |
| **AI & GenAI Spend** | Model Serving DBU + AI Gateway Tokens + Vector Search | `MODEL_SERVING_COMPUTE` records + `system.ai_gateway.usage` | Marked as *Embedded Perspective Lens*, not additive to Total Spend |
| **DBU Consumption** | $\sum \text{usage\_quantity} \quad (\text{WHERE unit = 'DBU'})$ | `system.billing.usage` | Strict unit separation: never combined with tokens or GB |
| **Azure Storage Spend** | $\sum \text{Cost} \quad (\text{WHERE category = 'Storage'})$ | Azure Cost Management query API | Returns `SOURCE UNAVAILABLE` when live ACM is unconfigured |
| **Azure Network Spend** | $\sum \text{Cost} \quad (\text{WHERE category = 'Network'})$ | Azure Cost Management query API | Returns `SOURCE UNAVAILABLE` when live ACM is unconfigured |
| **Forecast Month-End** | $\text{round}\left(\text{MTD Spend} \times \frac{30.0}{\text{Elapsed Days}}, -2\right)$ | Dynamic velocity extrapolation over actual billing records | Clearly labeled as `ESTIMATED / PROJECTION` |
| **Forecast Accuracy** | $100 - \text{MAPE}$ over closed billing periods | Historical forecast snapshots compared with closed actuals | Requires $\ge 3$ completed monthly cycles; otherwise `NOT AVAILABLE` |
| **Cost Anomalies** | Z-score statistical outlier detection ($> 2.5\sigma$) | Telemetry from trailing 30-day usage window | Returns dynamic detected count; never a fixed hardcoded number |
| **Identified Savings** | $\sum \text{estimated\_savings}$ across approved decisions | FinOps Optimization Engine | Realized savings remains strictly $\$0.00$ until deployment verification |

---

## 5. Security & Tenant Isolation

- **Role-Based Access Control (RBAC):** Verified using Microsoft Entra ID JWT validation (`Admin`, `Reader`, `CostManagementReader`).
- **Workspace Isolation:** Every query enforces `workspace_id = '642006393507276'` server-side. Cross-tenant leakage is physically impossible.
- **Credential Protection:** Bearer tokens, client secrets, and Databricks PAT tokens are strictly redacted from logs, responses, and exported reports.

