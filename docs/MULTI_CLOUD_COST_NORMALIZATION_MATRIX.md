# Multi-Cloud Cost Normalization Matrix & Financial Transformation Audit

> **Document:** `docs/MULTI_CLOUD_COST_NORMALIZATION_MATRIX.md`  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/databricks-apps-integration`  
> **Audit Type:** Forensic Financial Transformation & Pricing Normalization Review  
> **Status:** AUDITED — EVIDENCE-BASED ASSESSMENT  
> **Overall Classification:** **3. PARTIALLY IMPLEMENTED (DATABRICKS DBU NORMALIZATION IMPLEMENTED; MULTI-CLOUD COMMITMENT & AMORTIZATION NORMALIZATIONS NOT IMPLEMENTED)**  

---

## 1. Executive Summary

This audit forensically inspects the 17 cost normalization capabilities across Microsoft Azure, Amazon Web Services (AWS), Google Cloud Platform (GCP), and Databricks.

### Key Audit Conclusions:
- **Databricks DBU Charges:** Fully implemented and deterministic. `usage_quantity * list_price` is joined on `(sku_name, cloud, usage_date)` validity intervals.
- **Commitments & Reservations (Azure RIs, AWS Savings Plans, GCP CUDs):** **NOT IMPLEMENTED**. No amortization, unblending, or unused commitment calculation engines exist in backend services.
- **Credits & Discounts:** Credits are not ingested or netted dynamically from cloud invoices; only negative usage adjustments (retractions) in Databricks System Tables are processed.
- **Currency Conversion:** Handled on the frontend via static fixed exchange rates ([`frontend/src/lib/financials.ts:18–44`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/frontend/src/lib/financials.ts#L18-L44)). No dynamic foreign exchange (FX) rate feed or historical rate lookup is implemented.
- **Unit Aggregation Incompatibilities:** **IMPLEMENTED AND VERIFIED**. Strict unit separation guards prevent `DBU`, `BYTE_HOURS`, and `TOKEN` from being mathematically summed.

---

## 2. 17-Point Cost Normalization Capability Audit

| # | Normalization Capability | Target Functionality | Implemented Status | Implemented Location & Evidence | Gaps & Client Disclaimers |
|:---:|:---|:---|:---:|:---|:---|
| **1** | **Gross / List Cost** | Cost before any enterprise, volume, or commitment discounts | **PARTIALLY IMPLEMENTED** | Backend rate matching joins `sku_name` against list price in `BillingPriceRecord` (`billing_ingestion_service.py:366`). | In `finops_analytics_service.py:729`, `list_cost` equals `effective_cost` ($10,545.00). No discount spread is computed. |
| **2** | **Contracted Cost** | Price negotiated under enterprise agreement (EA, EDP) | **NOT IMPLEMENTED** | Frontend Settings displays hardcoded table (`finops_analytics_service.py:5281`). No contract rate lookup table exists in database. | Cannot ingest custom enterprise contract discount matrices dynamically. |
| **3** | **Billed Cost** | Invoice charge appearing on customer billing statement | **NOT IMPLEMENTED** | No invoice reconciliation table exists in database. | Platform cannot reconcile actual monthly bank invoices against telemetry. |
| **4** | **Effective / Amortized Cost** | Upfront commitment distributed across hourly resource usage | **NOT IMPLEMENTED** | Mentioned in descriptive string only (`finops_analytics_service.py:2643`). No amortization math exists. | Reservation purchases appear as $0 or unrepresented rather than distributed amortized costs. |
| **5** | **Discounts** | Programmatic or negotiated price reductions | **NOT IMPLEMENTED** | No discount deduction logic in `billing_ingestion_service.py`. | All calculated costs use raw matched unit rates. |
| **6** | **Credits** | Promotional, POC, or SLA compensation credits | **NOT IMPLEMENTED** | No credit ledger model. Only negative usage retractions are processed (`usage_quantity < 0`). | Credits cannot be netted against spend or isolated into credit buckets. |
| **7** | **Reservations (Azure RIs)** | 1-year or 3-year committed VM/SQL instances | **PARTIALLY IMPLEMENTED (Waste Engine Only)** | `waste_debt_engine.py:46–60` checks `cfg.get("reservation_id")` and prevents claiming phantom savings on stopped VMs. | Azure reservation inventory is not queried; RI utilization and coverage are not calculated. |
| **8** | **Savings Plans (AWS)** | Compute or EC2 hourly spend commitments | **NOT IMPLEMENTED** | `ENABLE_AWS = False`. | AWS Savings Plans are completely absent. |
| **9** | **Committed-Use Discounts (GCP CUDs)** | Resource or spend-based Google Cloud commitments | **NOT IMPLEMENTED** | GCP engine uses public On-Demand catalog rates only (`gcp_engine.py`). | CUD discounts are not modeled or attributed. |
| **10** | **Upfront Commitment Charges** | Cash outlay for all-upfront or partial-upfront commitments | **NOT IMPLEMENTED** | Zero accounting tables for capital expenditures or prepaid commitments. | Upfront payments cannot be tracked. |
| **11** | **Unused Commitment (Waste)** | Expired or unutilized capacity under active reservations | **NOT IMPLEMENTED** | No reservation utilization tracking. | Cannot report idle reservation waste. |
| **12** | **SKU Normalization** | Cross-cloud taxonomy mapping (e.g. Standard_D4ds_v5 to m6i.xlarge to n2-standard-4) | **IMPLEMENTED AND VERIFIED** | `catalog_repo.py` and `multi_cloud_comparator.py:100–180` map services across categories (`compute`, `database`, `storage`). | High fidelity for architecture generation; not currently integrated into live billing ledger. |
| **13** | **Currency Conversion** | Dynamic multi-currency conversion with historical FX | **PARTIALLY IMPLEMENTED (Static Rates)** | `frontend/src/lib/financials.ts:18–44` supports USD, EUR (0.92), GBP (0.79), JPY (154.2), AUD (1.52), CAD (1.38). | Exchange rates are hardcoded constants. No live ECB or OpenExchangeRates integration exists. |
| **14** | **Tax Treatment** | Identification and segregation of VAT/GST/sales taxes | **NOT IMPLEMENTED** | All models assume pre-tax pricing. | Taxes are neither calculated nor displayed. |
| **15** | **Usage-Unit Conversion** | Standardizing core-hours, GB-months, IOPS-seconds | **PARTIALLY IMPLEMENTED (Guards Only)** | `billing_ingestion_service.py:349` guards against unit conflation (`if record.usage_unit != "DBU": return`). | Incompatible units are safely blocked from cross-addition, but mathematical unit converters (e.g. MB to GB) are absent. |
| **16** | **Databricks DBU Charges** | Metered Databricks Units multiplied by DBU rate card | **IMPLEMENTED AND VERIFIED** | `billing_ingestion_service.py:366–372` implements exact decimal math `(usage_qty * price_per_unit).quantize(0.01)`. | 100% verified by test suite `test_billing_ingestion.py`. |
| **17** | **Databricks vs Cloud Infra Charges** | Separation of Databricks software DBU from underlying Azure VMs/disks | **PARTIALLY IMPLEMENTED (Descriptive)** | `finops_analytics_service.py:1627` documents separation: $176,840 Databricks DBU vs $284,620 total cloud spend. | No automated cross-billing reconciliation correlates VM meter IDs in Azure invoice with Databricks cluster runtime. |

---

## 3. Provider-by-Provider Normalization Matrix

| Cloud Provider | Source Raw Field | Transformation Logic | Canonical Target Field | Formula / Math Applied | Status |
|:---|:---|:---|:---|:---|:---:|
| **Databricks** | `system.billing.usage.usage_quantity` | Direct decimal parsing | `BillingUsageRecord.usage_quantity` | `Decimal(str(qty))` | **VERIFIED** |
| **Databricks** | `system.billing.list_prices.price_per_unit` | Temporal interval join on `(sku, cloud, usage_date)` | `BillingUsageRecord.effective_cost` | `round_half_up(qty * price, 2)` | **VERIFIED** |
| **Databricks** | `usage.usage_unit` | Unit validation guard | `BillingUsageRecord.usage_unit` | Strict string equality (`"DBU"`, `"BYTE_HOURS"`) | **VERIFIED** |
| **Azure** | Retail Prices API `retailPrice` | Public API HTTP query with query parameters | `AzurePriceItem.retail_price` | `float(item["retailPrice"])` | **VERIFIED** |
| **Azure** | ARM Resource VM Size | Heuristic sizing lookup | `DiscoveredResource.monthly_cost_usd` | Sizing table hourly rate * 730 hours | **VERIFIED** |
| **Azure** | Cost Management Export | N/A | `cost_details.pretax_cost` (Lakehouse) | Schema defined only; no live ingestion runner active | **DESIGNED ONLY** |
| **Azure** | Reservation Amortization | N/A | N/A | None | **NOT IMPLEMENTED** |
| **GCP** | Cloud Billing Catalog `pricingExpression` | Tiered price extraction | `GcpSkuItem.tiered_rates` | Tiered nanos to USD calculation | **VERIFIED** |
| **GCP** | BigQuery Billing Export | N/A | N/A | None (Mock benchmark fixture active) | **NOT IMPLEMENTED** |
| **AWS** | AWS Price List API | Bundled offline cache only | `AwsPriceItem` (Catalog) | Static JSON catalog parsing | **OFFLINE ONLY** |
| **AWS** | AWS CUR 2.0 | N/A | N/A | None (`ENABLE_AWS = False`) | **NOT IMPLEMENTED** |

---

## 4. Specific Forensic Answers

1. **Are Azure reservation charges amortized?**  
   **No.** Azure reservation charges are not amortized. Neither `connection_service.py`, `azure_inventory.py`, nor `finops_analytics_service.py` contain reservation amortization math.
2. **Are AWS Savings Plans and Reserved Instances represented correctly?**  
   **No.** AWS live billing is completely disabled (`ENABLE_AWS = False`).
3. **Are GCP committed-use discounts represented correctly?**  
   **No.** GCP pricing engine queries on-demand catalog SKUs only.
4. **Are Databricks DBU charges separated from underlying cloud infrastructure charges?**  
   **Yes, conceptually; but not reconciled automatically.** DBU charges are tracked via `BillingUsageRecord` ($176,840.00 across 88,420 DBU). Azure VMs are tracked via ARM inventory ($284,620.00). However, the platform lacks an automated correlation engine to map specific Azure VM billing meter rows to corresponding Databricks cluster worker node records.
5. **Are credits netted against costs or retained as separate financial entries?**  
   **Neither.** Provider promotional/invoice credits are not ingested. Negative usage quantities representing Databricks task retractions are preserved in `BillingUsageRecord.usage_quantity`.
6. **Does currency conversion use a traceable exchange-rate source and date?**  
   **No.** Currency conversion in `frontend/src/lib/financials.ts` applies hardcoded multiplication factors (e.g. `0.92` for EUR, `0.79` for GBP). There is no live FX API connection or historical rate table.
7. **Are incompatible units prevented from being aggregated?**  
   **Yes.** In `billing_ingestion_service.py:349–353` and `test_finops_analytics.py`, unit guards explicitly verify that `DBU` is never summed with `BYTE_HOURS`, `TOKEN`, or count metrics.
8. **Can duplicate cloud and Databricks expenditure be detected?**  
   **Partially.** The waste engine detects orphaned VMs and unattached disks, but cross-billing double-counting between Azure VM meters and Databricks DBU charges is documented as an analytical limitation rather than detected programmatically.

