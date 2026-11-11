# FinOps FOCUS & Canonical Cost Data Model Mapping Audit

> **Document:** `docs/FOCUS_CANONICAL_COST_MODEL_MAPPING.md`  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/databricks-apps-integration`  
> **Audit Type:** Forensic Data Architecture & Schema Parity Review  
> **Status:** AUDITED — EVIDENCE-BASED ASSESSMENT  
> **Overall Classification:** **3. PARTIALLY IMPLEMENTED / 4. DOCUMENTED & DESIGNED ONLY (FOCUS SPECIFICATION IS NOT IMPLEMENTED; PROPRIETARY INTERNAL MODEL DEPLOYED)**  

---

## 1. Executive Summary

This audit evaluates the canonical cost and billing data models implemented within the Bizmetric FinOps Platform across Microsoft Azure, Amazon Web Services (AWS), Google Cloud Platform (GCP), and Databricks against the **FinOps Open Cost & Usage Specification (FOCUS)**.

### Primary Audit Findings:
1. **Zero FOCUS Implementation:**  
   The platform does **not** implement the FinOps FOCUS specification (neither FOCUS 1.0 nor FOCUS 1.1). A comprehensive repository scan (`git grep -i "focus"`) confirms zero occurrences of FOCUS standard columns, schema definitions, or transformation functions.
2. **Proprietary Databricks-Centric Data Model:**  
   The implemented canonical cost engine is a **proprietary internal model** directly structured around **Databricks System Tables** (`system.billing.usage` and `system.billing.list_prices`).
3. **Multi-Cloud State:**  
   - **Databricks:** Fully modeled via [`BillingUsageRecordModel`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/db/models.py#L568) and [`BillingPriceRecordModel`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/db/models.py#L692) in PostgreSQL and in-memory services.
   - **Azure:** Azure Retail Prices public API model exists for rate discovery ([`backend/src/cloud_recommender/services/pricing/azure_retail_client.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/pricing/azure_retail_client.py#L59)), but no common multi-cloud fact table ingests Azure Cost Management export files in PostgreSQL.
   - **GCP:** Google Cloud Billing Catalog client exists for SKU discovery ([`backend/src/cloud_recommender/services/pricing/gcp_billing_client.py`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/pricing/gcp_billing_client.py#L27)), but no live BigQuery billing export fact table is implemented.
   - **AWS:** Excluded/Deferred (`ENABLE_AWS = False` in [`frontend/src/config/features.ts`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/frontend/src/config/features.ts#L24)). No AWS CUR data ingestion exists.

---

## 2. Implemented Database & ORM Schemas

### 2.1 Relational Fact Table: `billing_usage_records`
- **Location:** [`backend/src/cloud_recommender/db/models.py:568–690`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/db/models.py#L568-L690)
- **Migration:** [`backend/alembic/versions/2026_11_07_0002_billing_ingestion_and_reconciliation.py:28–75`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/alembic/versions/2026_11_07_0002_billing_ingestion_and_reconciliation.py#L28-L75)
- **Schema Attributes:**

```python
class BillingUsageRecordModel(Base):
    __tablename__ = "billing_usage_records"

    record_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sku_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    cloud: Mapped[str] = mapped_column(String(50), default="azure", nullable=False)
    usage_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usage_end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usage_date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    usage_unit: Mapped[str] = mapped_column(String(50), nullable=False, default="DBU")
    usage_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    record_type: Mapped[str] = mapped_column(String(50), default="original", nullable=False)
    ingestion_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    billing_origin_product: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_features_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    usage_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    custom_tags_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    effective_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    pricing_matched: Mapped[bool] = mapped_column(Boolean, default=False)
    currency: Mapped[str | None] = mapped_column(String(10), default="USD")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

### 2.2 Relational Rate Card Table: `billing_price_records`
- **Location:** [`backend/src/cloud_recommender/db/models.py:692–749`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/db/models.py#L692-L749)
- **Attributes:** `sku_name`, `cloud`, `currency_code`, `price_per_unit` (Numeric 18, 6), `pricing_unit` (DBU, gigabyte_month), `price_start_time`, `price_end_time`.

### 2.3 OneLake Delta Lake Schema (Lakehouse Design): `cost_details`
- **Location:** [`fabric-integration/lakehouse/schemas.py:34–78`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/fabric-integration/lakehouse/schemas.py#L34-L78)
- **Attributes:** `record_id`, `subscription_id`, `billing_account_id`, `service_name`, `service_tier`, `meter_category`, `meter_sub_category`, `meter_name`, `meter_id`, `unit_of_measure`, `usage_quantity`, `unit_price`, `pretax_cost`, `currency`, `billing_period_start_date`, `billing_period_end_date`, `date`, `resource_id`, `resource_name`, `resource_type`, `resource_group`, `location`, `consumed_service`, `tags`, `pricing_model`, `reservation_id`, `reservation_name`, `publisher_type`, `charge_type`, `frequency`, `ingestion_timestamp`.
- **Note:** This schema reflects the native **Azure Cost Management Export** tabular format, not FOCUS 1.0.

---

## 3. Field-Level FOCUS 1.0 Specification Gap Analysis

The table below provides a forensic cross-walk between standard FOCUS 1.0 specification columns and the platform's implemented models:

| Canonical Implemented Field | FOCUS 1.0 Standard Field | Azure Source Equivalent | AWS Source Equivalent | GCP Source Equivalent | Databricks System Tables Source | Implementation Status in Platform |
|:---|:---|:---|:---|:---|:---|:---:|
| `record_id` | N/A (Proprietary ID) | N/A | LineItemId | N/A | `record_id` | **IMPLEMENTED** (Databricks only) |
| `workspace_id` | `SubAccountId` | `subscriptionId` | `line_item_usage_account_id` | `project.id` | `workspace_id` | **IMPLEMENTED** |
| `account_id` | `BillingAccountId` | `billingAccountId` | `bill_payer_account_id` | `billing_account_id` | `account_id` | **PARTIAL** (Nullable) |
| `sku_name` | `SkuId` / `SkuPriceId` | `meterId` / `skuName` | `product_sku` | `sku.id` | `sku_name` | **IMPLEMENTED** |
| `cloud` | `ProviderName` | Provider ("Azure") | Provider ("AWS") | Provider ("GCP") | `cloud` ("azure") | **IMPLEMENTED** |
| `usage_start_time` | `ChargePeriodStart` | `date` / `meterStartTime` | `line_item_usage_start_date` | `usage_start_time` | `usage_start_time` | **IMPLEMENTED** |
| `usage_end_time` | `ChargePeriodEnd` | `meterEndTime` | `line_item_usage_end_date` | `usage_end_time` | `usage_end_time` | **IMPLEMENTED** |
| `usage_date` | `BillingPeriodStart` (Date) | `date` | `bill_billing_period_start_date`| `usage_start_time` (Date) | `usage_date` | **IMPLEMENTED** |
| `usage_unit` | `ConsumedUnit` | `unitOfMeasure` | `pricing_unit` | `usage.unit` | `usage_unit` | **IMPLEMENTED** |
| `usage_quantity` | `ConsumedQuantity` | `quantity` | `line_item_usage_amount` | `usage.amount` | `usage_quantity` | **IMPLEMENTED** |
| `effective_cost` | `EffectiveCost` | `costInBillingCurrency` | `line_item_unblended_cost` | `cost` | Derived: `usage_quantity * price_per_unit` | **IMPLEMENTED** |
| `currency` | `BillingCurrency` | `billingCurrency` | `line_item_currency_code` | `currency` | `currency` | **IMPLEMENTED** |
| `record_type` | `ChargeClass` | `chargeType` | `line_item_line_item_type` | `cost_type` | `record_type` | **PARTIAL** |
| `billing_origin_product`| `ServiceCategory` | `meterCategory` | `product_product_family` | `service.description` | `billing_origin_product` | **IMPLEMENTED** |
| `usage_metadata_json` | `ResourceId` / `ResourceName` | `resourceId` | `line_item_resource_id` | `resource.name` | `usage_metadata.cluster_id` / `warehouse_id` | **IMPLEMENTED** |
| `custom_tags_json` | `Tags` | `tags` | `resource_tags` | `labels` | `custom_tags` | **IMPLEMENTED** |
| *Not Implemented* | `BilledCost` | `costInBillingCurrency` | `line_item_blended_cost` | `cost` | N/A | **NOT IMPLEMENTED** |
| *Not Implemented* | `ListCost` | `unitPrice * quantity` | `pricing_public_on_demand_cost`| `cost_at_list` | `list_cost` in UI fixture only | **PARTIAL** (UI mock only) |
| *Not Implemented* | `ListUnitPrice` | `unitPrice` | `pricing_public_on_demand_rate`| `sku.pricing_info` | `price_per_unit` in price table | **PARTIAL** |
| *Not Implemented* | `ContractedCost` | N/A (EA rate * qty) | `pricing_contracted_cost` | N/A | N/A | **NOT IMPLEMENTED** |
| *Not Implemented* | `ContractedUnitPrice` | N/A | `pricing_contracted_rate` | N/A | Hardcoded UI label only | **NOT IMPLEMENTED** |
| *Not Implemented* | `ChargeCategory` | `Usage`, `Purchase`, etc. | `line_item_type` | `cost_type` | N/A | **NOT IMPLEMENTED** |
| *Not Implemented* | `CommitmentDiscountCategory`| `Reservation` | `SavingsPlan` / `RI` | `CUD` | N/A | **NOT IMPLEMENTED** |
| *Not Implemented* | `CommitmentDiscountId` | `reservationId` | `savings_plan_arn` | `commitment.id` | N/A | **NOT IMPLEMENTED** |
| *Not Implemented* | `InvoiceIssuerName` | "Microsoft" | "Amazon Web Services" | "Google" | N/A | **NOT IMPLEMENTED** |
| *Not Implemented* | `RegionId` / `RegionName` | `resourceLocation` | `product_region` | `location.region` | Hardcoded East US in baseline | **PARTIAL** |

---

## 4. Key Architectural Conclusions

1. **Compliance Statement:** The platform is **NOT FOCUS compliant** and **NOT FOCUS aligned**. Claiming FOCUS compliance to clients is factually inaccurate based on repository code.
2. **Proprietary Strengths:** While not FOCUS-compliant, the proprietary Databricks billing model exhibits high technical rigor for Databricks System Tables:
   - Preserves exact idempotency via `record_id`.
   - Correctly records negative usage quantities for ledger retractions.
   - Enforces strict unit segregation (`DBU` vs `BYTE_HOURS` vs `TOKEN`).
3. **Required Actions for FOCUS Adoption:**
   - Map `BillingUsageRecordModel` columns to official FOCUS 1.0 names (`ChargePeriodStart`, `ChargePeriodEnd`, `EffectiveCost`, `BilledCost`, `ConsumedQuantity`, `ConsumedUnit`, `SubAccountId`).
   - Create multi-cloud transformation adapters for Azure Cost Management Exports, AWS CUR 2.0, and GCP BigQuery Detailed Billing Export tables.

