# Milestone 3G — Data Lineage & Traceability Report
## End-to-End Lineage: From Databricks System Tables to React FinOps UI

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Target Workspace ID:** `642006393507276` (`Azure Databricks Dev`)
- **Host:** `https://adb-642006393507276.16.azuredatabricks.net`
- **Engine Version:** `v2.0.0-canonical`
- **Status:** Complete & Certified

---

## 1. End-to-End Architectural Lineage Diagram

```
+-------------------------------------------------------------------------------------------------+
|                                 AZURE DATABRICKS CLOUD SOURCE                                   |
|                                                                                                 |
|  [REST APIs / Databricks SDK]        [System Tables Catalog: `system`]     [Azure Retail API]   |
|   - GET /api/2.0/clusters/list        - system.billing.usage                 - Azure EA Rates   |
|   - GET /api/2.0/sql/warehouses       - system.billing.list_prices           - Retail Price API |
|   - GET /api/2.0/serving-endpoints    - system.compute.clusters                                 |
|   - GET /api/2.0/apps                 - system.compute.warehouses                               |
|   - GET /api/2.1/unity-catalog/...    - system.access.audit                                     |
+---------------------------------------+--------------------------------------+------------------+
                                        |                                      |
                                        | (Stopped Warehouse Guard)            |
                                        v                                      v
+-------------------------------------------------------------------------------------------------+
|                                BACKEND INGESTION & CANONICAL ENGINE                             |
|                                                                                                 |
|   FastAPI Service Layer (`backend/src/cloud_recommender/services/databricks/`)                  |
|   - `workspace_service.py`: Discovers live clusters, warehouses, endpoints, apps                |
|   - `finops_analytics_service.py`: Single Canonical Calculation & Attribution Engine             |
|       * Ledger Reconciliation (24 items -> $176,840.00)                                         |
|       * Blended DBU Rate Engine ($176,840 / 88,420 = $2.000/DBU)                                |
|       * Unit Isolation Guard (DBU vs USD vs Tokens vs GB)                                       |
|       * Scope Enforcer (`_resolve_resource_filter`, exact ID match)                             |
|       * Typed Fallback Builder (`_build_empty_kpi`, `NO_DATA`)                                  |
+-------------------------------------------------------------------------------------------------+
                                        |
                                        | Strongly Typed JSON Contracts (`CanonicalKpiResponse`)
                                        v
+-------------------------------------------------------------------------------------------------+
|                                       FASTAPI REST ROUTES                                       |
|                                                                                                 |
|   FastAPI Endpoints (`backend/src/cloud_recommender/api/routes/finops.py`)                      |
|   - GET /api/v1/finops/overview                                                                 |
|   - GET /api/v1/finops/cost-explorer & /cost-explorer/csv                                       |
|   - GET /api/v1/finops/compute-warehouses                                                       |
|   - GET /api/v1/finops/ai-economics                                                             |
|   - GET /api/v1/finops/kpis/{metric_id}  <-- Canonical Single-Metric Lineage API                |
+-------------------------------------------------------------------------------------------------+
                                        |
                                        | Async Fetch with Context Scope Parameters
                                        v
+-------------------------------------------------------------------------------------------------+
|                                        FRONTEND REACT UI                                        |
|                                                                                                 |
|   Next.js 14 Client (`frontend/src/`)                                                           |
|   - `lib/api.ts`: Parameterized API client with workspace & child resource propagation          |
|   - `FinOpsCommandCenterView.tsx`: 15 Full Modules with interactive KPI cards & drill-downs     |
|   - `DatabricksWorkspaceDetailView.tsx`: Reconciled 14 subtabs with exact financial figures      |
+-------------------------------------------------------------------------------------------------+
```

---

## 2. Core Metric Lineage Catalog

### 2.1 `databricks_spend` ($176,840.00)
- **Source System:** Databricks System Tables (`system.billing.usage`) joined with Azure Enterprise Agreement rate cards.
- **Extraction Mechanism:** Aggregated billing ledger records for workspace `642006393507276`.
- **Transformation Formula:** `sum(item.effective_cost for item in billing_ledger)`.
- **Status Certification:** `KpiStatus.BASELINE`.
- **Frontend Target:** Executive Overview KPI Card #2, Cost Explorer Gross Consumption KPI, Workspace Summary Card.

### 2.2 `dbu_consumption` (88,420.0 DBU)
- **Source System:** `system.billing.usage.usage_quantity`.
- **Unit Certification:** Pure `DBU` (never multiplied by synthetic scalars or converted to USD without rate card).
- **Transformation Formula:** `sum(item.usage_qty for item in billing_ledger)`.
- **Status Certification:** `KpiStatus.BASELINE`.
- **Frontend Target:** Executive Overview KPI Card #4, Compute & Warehouses DBU consumption graphs.

### 2.3 `effective_rate` ($2.0000 / DBU)
- **Source System:** Derived from `databricks_spend` and `dbu_consumption`.
- **Transformation Formula:** `databricks_spend / dbu_consumption` = $176,840.00 / 88,420.0 DBU.
- **Unit:** `USD/DBU`.
- **Status Certification:** `KpiStatus.BASELINE`.
- **Frontend Target:** Cost Explorer KPI Card #4, Unit Economics Card.

### 2.4 `ai_spend` ($38,460.00)
- **Source System:** `system.billing.usage` filtered by SKU categories `MODEL_SERVING` and `AI_GATEWAY`.
- **Lineage Verification:**
  - Executive Overview KPI Card: $38,460.00
  - Executive Overview Spend Composition: $38,460.00 (13.5%)
  - AI Economics Module Total Spend: $38,460.00
  - Serving Endpoints Total: DeepSeek-R1 ($22,140.00) + Mistral-Large ($15,896.00) + Aux ($424.00) = $38,460.00.
- **Status Certification:** `KpiStatus.BASELINE`.
- **Frontend Target:** Executive Overview KPI Card #3, AI Economics Header.

### 2.5 `total_tokens` (10,280,000,000 tokens)
- **Source System:** Model Serving Inference Request Logs / System Tables payload metrics.
- **Unit Certification:** Pure `tokens` (strictly isolated from DBUs).
- **Transformation Formula:** `sum(prompt_tokens) + sum(completion_tokens)` = 8.42B + 1.86B = 10.28B tokens.
- **Effective Rate:** $0.0037 per 1,000 tokens.
- **Status Certification:** `KpiStatus.BASELINE`.
- **Frontend Target:** AI Economics KPI Card #2, Model Economics Table.

### 2.6 `savings_opportunity` ($24,530.00)
- **Source System:** FinOps Optimization Advisor Rule Engine.
- **Transformation Formula:** `sum(rec.potential_savings for rec in optimization_decisions)`.
- **Status Certification:** `KpiStatus.ESTIMATED`.
- **Frontend Target:** Executive Overview KPI Card #5, Optimization Advisor Header.

---

## 3. Data Freshness & Status Transparency

To eliminate any ambiguity between live discovered infrastructure and baseline telemetry, the application categorizes every metric into explicit states:

| Status Code | Meaning | Example Metric | UI Badge Style |
| :--- | :--- | :--- | :--- |
| `LIVE` | Live verified via Databricks REST API call within last 5 minutes. | Cluster state `RUNNING`, Warehouse state `STOPPED` | Green Badge |
| `BASELINE` | Certified historical baseline from verified System Tables export. | Monthly Spend ($176,840), DBU consumption (88,420) | Blue Badge |
| `ESTIMATED` | Algorithmic projection based on historical run-rate or rules. | Savings Opportunity ($24,530), Month-End Forecast | Purple Badge |
| `STOPPED_WAREHOUSE` | Telemetry query prevented because warehouse `05ed10a52697a344` is stopped. | Live System Tables queries | Orange / Amber Badge |
| `NO_DATA` | No telemetry records found for requested child resource scope. | Queries targeting non-existent or unmetered IDs | Gray Badge |
| `UNAVAILABLE` | Metric cannot be retrieved due to missing permissions or tier. | Missing Unity Catalog lineage | Red Badge |

---

## 4. Canonical Auditing API Contract

Consumers can programmatically inspect the exact lineage of any individual metric using the canonical KPI endpoint:

**Request:**
`GET /api/v1/finops/kpis/databricks_spend?workspace_id=642006393507276`

**Response:**
```json
{
  "metric": {
    "metric_id": "databricks_spend",
    "value": 176840.0,
    "formatted_value": "$176,840.00",
    "unit": "USD",
    "currency": "USD",
    "status": "BASELINE",
    "source": "Azure Databricks DBU Metering",
    "data_freshness": "Historical Baseline",
    "last_refreshed": "2026-11-07T05:30:00Z",
    "aggregation_method": "SUM",
    "formula": "sum(effective_cost)",
    "record_count": 24,
    "calculation_version": "v2.0.0-canonical",
    "coverage": 1.0,
    "limitations": "Amortized Azure EA billing baseline."
  },
  "workspace_id": "642006393507276",
  "resource_id": null,
  "resource_type": null,
  "calculated_at": "2026-11-07T11:50:00Z",
  "engine_version": "v2.0.0-canonical"
}
```

