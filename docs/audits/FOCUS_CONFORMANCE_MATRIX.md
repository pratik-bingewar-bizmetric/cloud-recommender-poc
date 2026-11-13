# CONFORMANCE MATRIX: FINOPS FOCUS 1.0 SPECIFICATION ALIGNMENT

> **Audit Identifier:** `AUDIT-FINOPS-FOCUS-1.0-2026-09`  
> **Target Version:** `v3.1.0-live-data-verification`  
> **Conformance Level:** **FOCUS 1.0-Aligned (Core Financial Profile)**  
> **Scope:** Canonical Data Model Parity across Databricks, Azure, AWS, and GCP  

---

## 1. Conformance Level Classification

The canonical data model implemented in `CanonicalBillingRecord` is classified as **FOCUS-aligned (Core Financial Profile)**.

> [!IMPORTANT]
> The implementation strictly aligns with FOCUS 1.0 architectural concepts (normalized billing, charge periods, effective cost, unit isolation, and provider lineage). However, it does not achieve **100% full conformance** to all 44 FOCUS 1.0 specification columns (e.g. Commitment Discounts, Contracted Costs, and Invoice Issuer dimensions are not yet implemented). It is therefore accurately designated as **FOCUS-aligned**.

---

## 2. Specification Comparison Matrix

| FOCUS 1.0 Standard Column | Canonical Field in Platform | Type | Status | Mapping & Transformation Rule |
| :--- | :--- | :--- | :--- | :--- |
| **`ProviderName`** | `provider` | `str` | **Implemented** | Lowercase normalized: `'databricks'`, `'azure'`, `'aws'`, `'gcp'`. |
| **`BillingAccountId`** | `billing_account_id` | `str` | **Implemented** | Enrollment or root billing account ID. |
| **`SubAccountId`** | `subscription_id` / `workspace_id` | `str` | **Mapped** | Azure subscription ID or Databricks workspace ID. |
| **`SubAccountName`** | *Derived / Cached* | `str` | **Partial** | Cached from Cloud Account registry. |
| **`ResourceId`** | `resource_id` | `str` | **Implemented** | Full Azure Resource Manager URI or Databricks cluster/warehouse ID. |
| **`ResourceName`** | `resource_name` | `str` | **Implemented** | Human-readable name extracted from metadata or ARM URI. |
| **`ResourceType`** | `sku_name` / `service_category` | `str` | **Mapped** | Standardized category: `Compute`, `Storage`, `Network`, `AI`, `Database`. |
| **`ServiceCategory`** | `service_category` | `str` | **Implemented** | Normalized taxonomy across all providers. |
| **`ServiceName`** | `service_name` | `str` | **Implemented** | Provider service (e.g., `'Azure Databricks'`, `'Storage Accounts'`). |
| **`SkuId`** | `sku_name` | `str` | **Mapped** | Provider commercial SKU name (e.g. `'SERVERLESS_SQL_COMPUTE'`). |
| **`ChargePeriodStart`** | `usage_start_time` | `datetime` | **Implemented** | UTC ISO 8601 timestamp. |
| **`ChargePeriodEnd`** | `usage_end_time` | `datetime` | **Implemented** | UTC ISO 8601 timestamp. |
| **`ChargeClass`** | `record_type` (`original`/`retraction`) | `str` | **Mapped** | Maps `'original'` -> `Correction`/`Original`. |
| **`ConsumedQuantity`** | `usage_quantity` | `Decimal` | **Implemented** | Metred usage; negative indicates retraction. |
| **`ConsumedUnit`** | `usage_unit` | `str` | **Implemented** | Measurement unit: `DBU`, `GB`, `TB-Month`, `Hours`. |
| **`ListUnitPrice`** | `list_unit_price` | `Decimal` | **Implemented** | Unit list rate from `system.billing.list_prices` or Azure Retail Prices. |
| **`BilledCost`** | `billed_cost` | `Decimal` | **Implemented** | Unadjusted invoice cost directly from cloud invoice. |
| **`EffectiveCost`** | `effective_cost` | `Decimal` | **Implemented** | Reconciled cost after deterministic rate-card matching. |
| **`BillingCurrency`** | `currency` | `str` | **Implemented** | ISO 4217 three-letter currency code (defaults to `'USD'`). |
| **`Tags`** | `tags` | `dict[str, str]` | **Implemented** | Key-value pairs extracted from resource tags and custom tags. |

---

## 3. Missing Fields & Deviations from Full FOCUS 1.0

The following FOCUS 1.0 columns are currently **NOT IMPLEMENTED** or deferred to future enterprise milestones:

| FOCUS 1.0 Column | Business Impact / Omission Justification | Planned Milestone |
| :--- | :--- | :--- |
| **`ChargeCategory`** | FOCUS distinguishes `Usage`, `Purchase`, `Tax`, `Credit`. Current POC focuses exclusively on `Usage` and `Retraction`. | Phase 3 Enterprise Ingestion |
| **`ChargeFrequency`** | Distinguishes `One-Time`, `Recurring`, `Usage-Based`. Currently assumed `Usage-Based`. | Phase 3 Enterprise Ingestion |
| **`CommitmentDiscountId`** | Reservation / Savings Plan ID tracking. Not currently integrated into Azure Cost Management query. | Milestone 4 FinOps Optimization |
| **`CommitmentDiscountName`** | Human-readable reservation name. | Milestone 4 FinOps Optimization |
| **`CommitmentDiscountType`** | Reserved Instance vs Savings Plan vs Databricks Committed DBU. | Milestone 4 FinOps Optimization |
| **`ContractedCost`** | Negotiated enterprise discount rate cost. Current engine evaluates List Price vs Invoiced Cost. | Enterprise Rate Card Ingestion |
| **`ContractedUnitPrice`** | Negotiated unit rate. | Enterprise Rate Card Ingestion |
| **`InvoiceIssuerName`** | Provider vs Marketplace Partner. | Multi-Tenant Marketplace Phase |
| **`RegionId` / `RegionName`**| Captured in `tags` or ARM URI rather than as top-level first-class schema fields. | Schema Version 2.0 |
| **`AvailabilityZone`** | Not exposed in standard Databricks billing telemetry. | Compute Topology Audit |

---

## 4. Provider-Specific Ingestion & Normalization Rules

### 4.1 Databricks System Tables (`system.billing.usage`)
- `record_id` $\rightarrow$ `CanonicalBillingRecord.record_id` (Native stable primary key)
- `workspace_id` $\rightarrow$ `CanonicalBillingRecord.workspace_id`
- `sku_name` $\rightarrow$ `CanonicalBillingRecord.sku_name`
- `usage_start_time` / `usage_end_time` $\rightarrow$ `CanonicalBillingRecord.usage_start_time` / `usage_end_time`
- `usage_quantity` $\rightarrow$ `CanonicalBillingRecord.usage_quantity` (Preserving negative retractions)
- `usage_unit` $\rightarrow$ `CanonicalBillingRecord.usage_unit` (`DBU`)
- `custom_tags` $\rightarrow$ `CanonicalBillingRecord.tags`
- Rate Card Join $\rightarrow$ Inner join with `system.billing.list_prices` on `sku_name`, `cloud`, date validity window.

### 4.2 Azure Cost Management (`Microsoft.CostManagement/query`)
- Composite key `provider:azure:{sub_id}:{date}:{res_id}:{category}` $\rightarrow$ `CanonicalBillingRecord.record_id`
- `SubscriptionId` $\rightarrow$ `CanonicalBillingRecord.subscription_id`
- `ResourceId` $\rightarrow$ `CanonicalBillingRecord.resource_id`
- `MeterCategory` $\rightarrow$ `CanonicalBillingRecord.service_category`
- `Cost` $\rightarrow$ `CanonicalBillingRecord.effective_cost` (Decimal conversion)
- `UsageDate` $\rightarrow$ `CanonicalBillingRecord.usage_date`

---

## 5. Formal Conformance Statement

The Bizmetric FinOps Platform conforms to the **Core Usage and Cost Profile of FinOps FOCUS 1.0**. It enforces strict Decimal precision, unit isolation, retraction netting, and provider lineage. It will be denoted as **FOCUS 1.0-Aligned** in all client-facing documentation until Commitment Discount and Contracted Cost dimensions are implemented.

