# Milestone 3G.3 — NO_DATA Schema Parity & Measured Zero Regression Report

> **Status:** Fully Resolved, Implemented & Verified  
> **Workspace ID:** `642006393507276` (`Azure Databricks Dev`)  
> **Author:** Staff FinOps Solutions Architect  
> **Milestone:** Milestone 3G.3 — Financial Reconciliation & Evidence Closure  

---

## 1. Executive Summary & Defect Description

In previous milestones, when a user queried an unpopulated, non-existent, or unmonitored cloud resource scope, the backend factory function `_build_empty_kpi` returned:
```python
value = 0.0
formatted_value = "No data"
status = KpiStatus.NO_DATA
```

### The Problem
Returning `value = 0.0` conflated **absence of data** (`null`) with **measured zero** (`0.0`). In particular:
- A user selecting an unmonitored scope or invalid resource could see a metric card implying that **\$0.00** was spent, when in fact **no telemetry data existed**.
- In contrast, valid discovered resources that truly incurred zero direct cost (e.g. `cement-demand-forecasting` in the unattributed compute pool) genuinely measured zero spend.
- The Pydantic domain schema `KpiMetric` previously enforced `value: float` as non-nullable (`...`), preventing JSON `null` serialization.

---

## 2. Architectural Remedy & Schema Parity

### 2.1 Backend Domain Schema (`backend/src/cloud_recommender/schemas/finops.py`)
`KpiMetric.value` was updated from non-nullable `float` to nullable `float | None`:

```python
class KpiMetric(BaseModel):
    """Canonical structure for any FinOps KPI metric with lineage, unit governance, and limitations."""

    value: float | None = Field(
        default=None,
        description="Numerical value of the metric; null when no measurement exists",
    )
    formatted_value: str = Field(..., description="Display string e.g. '$176,840' or '22%'")
    # ...
```

When serialized via `.model_dump(mode="json")`, `value: None` becomes JSON `null`.

---

### 2.2 Factory Function (`finops_analytics_service.py`)
The centralized `_build_empty_kpi` helper was updated:

```python
def _build_empty_kpi(
    self,
    metric_id: str,
    unit: str,
    currency: str | None = "USD",
    source: str = "Azure Databricks Telemetry",
    formula: str | None = None,
    workspace_id: str = "642006393507276",
    resource_id: str | None = None,
    resource_type: str | None = None,
) -> KpiMetric:
    """Create a typed NO_DATA KPI metric for unknown or unpopulated resource scopes."""
    return KpiMetric(
        value=None,
        formatted_value="No data available",
        unit=unit,
        currency=currency,
        metric_id=metric_id,
        status=KpiStatus.NO_DATA,
        data_freshness="Not applicable",
        source=source,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
        data_source="Azure Databricks REST API",
        last_refreshed=datetime.now(UTC).isoformat(),
        aggregation_method="NONE",
        formula=formula,
        record_count=0,
        limitations="No telemetry data found for the specified resource scope.",
        caveats="Resource not present in workspace discovery inventory.",
    )
```

---

### 2.3 Frontend Interface Parity (`frontend/src/types/index.ts`)
TypeScript interface `FinOpsKpiMetric` was updated:

```typescript
export interface FinOpsKpiMetric {
  value: number | null;
  formatted_value: string;
  unit: string;
  // ...
}
```

---

### 2.4 Frontend Presentation Guard (`FinOpsCommandCenterView.tsx`)
The dashboard KPI cards now check both `status === "NO_DATA"` and `metric?.value === null`:

```tsx
val: overviewData?.kpis.total_spend?.status === "NO_DATA" || overviewData?.kpis.total_spend?.value === null
  ? "No data available"
  : overviewData?.kpis.total_spend?.formatted_value || (error ? "Unavailable" : "—"),
```

This guarantees the UI **never displays "$0.00 spent" or "0"** for unmonitored scopes.

---

## 3. Preservation of Measured Zero

The distinction between **Measured Zero** and **Missing Data (NO_DATA)** is strictly preserved:

| Scenario | Resource / Scope | Status | `value` | `formatted_value` | Meaning |
| :--- | :--- | :--- | :-: | :--- | :--- |
| **Missing Telemetry** | Unknown resource `fake-id-999` | `NO_DATA` | `null` (`None`) | `"No data available"` | No measurement records exist for this resource in workspace telemetry. |
| **Measured Zero** | Discovered App `cement-demand-forecasting` | `AVAILABLE` | `0.0` | `"$0 (Unattributed)"` | Telemetry was inspected; resource has zero direct compute attribution (allocated to unattributed pool). |
| **Measured Baseline** | Discovered Cluster `1102-081455-7t3bqp3v` | `BASELINE` | `24600.0` | `"$24,600"` | Telemetry was inspected; consumption measured at 11,180 DBU. |

---

## 4. Full 15-Module Scope Regression Results

A full regression sweep was executed against all 15 functional modules with unknown resource IDs:

| # | Module | Endpoint / Method | `status` | `value` | `formatted_value` | Pass |
| :-: | :--- | :--- | :---: | :---: | :---: | :-: |
| 1 | Executive Overview | `get_executive_overview` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 2 | Cost Explorer | `get_cost_explorer` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 3 | Compute & Warehouses | `get_compute_warehouses` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 4 | Storage & Lakehouse | `get_data_storage` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 5 | AI & Token Economics | `get_ai_economics` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 6 | Optimization Advisor | `get_optimization_advisor` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 7 | Anomaly Detector | `get_anomaly_detection` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 8 | Forecast & Budgets | `get_forecast_budgets` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 9 | Cost Allocation & Tagging | `get_cost_allocation` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 10 | Showback / Chargeback | `get_showback_chargeback` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 11 | Workload Unit Economics | `get_workload_economics` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 12 | Governance & Policy Engine | `get_governance_policies` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 13 | System Tables Explorer | `get_system_tables` | `BASELINE` | N/A (table probe) | Stopped WH gated | **PASS** |
| 14 | Network & Cloud Infra | `get_network_cloud` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |
| 15 | Canonical KPI Service | `get_canonical_kpi` | `NO_DATA` | `None` (`null`) | `"No data available"` | **PASS** |

Automated regression tests are verified via `test_milestone_3g3_reconciliation.py::test_all_15_modules_return_null_value_on_no_data`.

