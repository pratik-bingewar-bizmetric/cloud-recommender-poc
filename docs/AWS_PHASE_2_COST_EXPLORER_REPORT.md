# AWS Phase 2 — Cost Explorer Service Report

> **AWS Service:** Cost Explorer (`ce.us-east-1.amazonaws.com`)  
> **API Actions:** `GetCostAndUsage`, `GetCostForecast`, `GetDimensionValues`, `GetTags`  
> **Scope & Metrics:** UnblendedCost, AmortizedCost, NetUnblendedCost, NetAmortizedCost  

---

## 1. Service Capabilities & Design

The `AwsCostExplorerService` retrieves historical, current, and forecasted financial spend across the target account `435305479688`.

### Key Features
1. **SigV4 Authentication Protocol:**
   - Targets `https://ce.us-east-1.amazonaws.com/` using `X-Amz-Target: AWSInsightsIndexService.<Action>`.
   - Headers: `application/x-amz-json-1.1`.
2. **Fail-Closed Data Truth Invariant:**
   - Missing data or permission denial (`AccessDeniedException`) is **never** converted into zero cost ($0.00).
   - If permissions are denied, `data_availability` is explicitly marked `PERMISSION_DENIED` and cost fields remain `None`.
3. **Multi-Dimensional Grouping:**
   - Grouping by `SERVICE`, `REGION`, `USAGE_TYPE`, and `LINKED_ACCOUNT`.
   - Normalizes group items with percentage-of-total calculations.
4. **Predictive Forecasting:**
   - Calls `GetCostForecast` for the remainder of the current month.
   - Provides mean forecast amount alongside prediction intervals (lower and upper bounds).

---

## 2. API Schema Reference

```json
{
  "account_id": "435305479688",
  "metric_type": "UnblendedCost",
  "currency": "USD",
  "current_month_to_date_cost": 64.20,
  "previous_month_cost": 58.10,
  "comparable_previous_month_to_date_cost": 52.00,
  "month_over_month_percentage_change": 23.5,
  "daily_trend": [
    {
      "start_date": "2026-11-01",
      "end_date": "2026-11-02",
      "amount": 2.15,
      "currency": "USD",
      "is_estimated": false
    }
  ],
  "top_services": [
    {
      "key": "Amazon Elastic Compute Cloud - Compute",
      "amount": 42.10,
      "percentage": 65.57,
      "unit": "USD"
    }
  ],
  "forecast": {
    "mean_amount": 78.50,
    "lower_bound": 72.00,
    "upper_bound": 85.00,
    "confidence_level": 80
  },
  "data_availability": "AVAILABLE"
}
```

---

## 3. Financial Safety & Query Guardrails
- **Billing Protection:** AWS Cost Explorer charges $0.01 per paginated API request beyond the free tier.
- **Throttling & Cache:** Background automatic polling is disabled by default (`autoSyncEnabled=false`).
- **Bounded Invocations:** Frontend requests only on explicit tab activation or manual refresh.

