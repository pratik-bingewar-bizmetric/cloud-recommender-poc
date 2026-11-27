# AWS Phase 2.1 — Financial Accuracy Report

> **Repository:** `cloud-recommender-poc`  
> **Module:** `backend/src/cloud_recommender/services/aws/cost_explorer_service.py`  
> **Status:** AUDITED, TESTED & ENFORCED

---

## 1. Principles of Financial Accuracy

In enterprise FinOps applications, financial data accuracy is paramount. A discrepancy of a single cent can cascade into auditing failures and erode customer trust. In Phase 2.1, the financial engine was audited and rebuilt under three immutable tenets:

1. **Exact Decimal Representation:** Native binary floating-point arithmetic (`float`) must never be used for currency storage, summation, or rounding. All values are represented as `decimal.Decimal` and quantized to 2 decimal places using `ROUND_HALF_UP`.
2. **Projected Month-End Spend Accuracy:** AWS Cost Explorer's `GetCostForecast` API calculates the expected spend for the *remaining* window of the month. Conflating this with the total month-end spend results in severe under-forecasting. Phase 2.1 enforces the complete formula:
   $$\text{Projected Month-End Cost} = \text{Actual MTD Cost} + \text{Remaining Forecast Cost}$$
3. **No Fabricated Zeroes:** When an AWS account has Cost Explorer disabled, lacks `ce:GetCostAndUsage` IAM permissions, or has not generated historical billing, the system must report `data_availability="PERMISSION_DENIED"` or `"DATA_UNAVAILABLE"` and return `None` for cost totals. Converting an unknown spend to `$0.00` is strictly forbidden.

---

## 2. Spend Forecasting Formula & Confidence Intervals

### 2.1 Formula Definition

When querying Cost Explorer midway through a month (e.g., Day 26 of a 30-day month):
- **Actual MTD Cost:** Aggregated spend from Day 1 through Day 26:
  $$C_{\text{MTD}} = \sum_{d=1}^{26} c_d$$
- **Remaining Forecast Amount:** Forecasted spend from Day 26 through End of Month returned by `GetCostForecast`:
  $$F_{\text{rem}} = \mathbb{E}\left[\sum_{d=26}^{30} c_d\right]$$
- **Total Projected Month-End Cost:**
  $$C_{\text{projected}} = C_{\text{MTD}} + F_{\text{rem}}$$
- **Confidence Intervals (95% Level):**
  $$\text{Interval}_{\text{lower}} = C_{\text{MTD}} + F_{\text{lower}}$$
  $$\text{Interval}_{\text{upper}} = C_{\text{MTD}} + F_{\text{upper}}$$

### 2.2 Numerical Verification (Unit Test Reference)

From `backend/tests/test_aws_phase2_1.py`:
- Actual MTD spend: **$50.00**
- Remaining period forecast: **$25.00** (Lower Bound: $20.00, Upper Bound: $30.00)
- **Result:**
  - `remaining_forecast_amount`: **$25.00**
  - `actual_month_to_date_cost`: **$50.00**
  - `projected_month_end_cost`: **$75.00**
  - `prediction_interval_lower_bound`: **$70.00**
  - `prediction_interval_upper_bound`: **$80.00**

---

## 3. Month-over-Month (MoM) and Leap-Year Date Math

Month-over-month comparisons are sensitive to month lengths and leap years. Comparing 26 days in February (28 days) with 26 days in January (31 days) requires calendar-aware boundaries:

```python
# MTD window: current_month_start to today
start_mtd_str = current_month_start.strftime("%Y-%m-%d")
end_mtd_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")

# Comparable previous MTD window: previous_month_start to min(today.day, days_in_prev_month)
start_prev_str = prev_month_start.strftime("%Y-%m-%d")
days_in_prev_month = (current_month_start - timedelta(days=1)).day
comp_day = min(today.day, days_in_prev_month)
end_comp_prev_str = (prev_month_start.replace(day=comp_day) + timedelta(days=1)).strftime("%Y-%m-%d")
```

If previous comparable spend is greater than $0.00, percentage change is calculated deterministically:
$$\Delta_{\text{MoM}} = \left(\frac{C_{\text{MTD}} - C_{\text{comp\_prev}}}{C_{\text{comp\_prev}}}\right) \times 100\%$$

---

## 4. Credits, Discounts, and Negative Adjustments

AWS billing records frequently include negative adjustments:
- Tax exemptions / refunds
- Enterprise Discount Program (EDP) credits
- Savings Plans / Reserved Instance amortizations
- AWS Free Tier promotional credits

In Phase 2.1, `_parse_group_breakdown` handles negative line items correctly:
1. Negative amounts are preserved without being stripped or coerced to zero.
2. Group percentages are computed relative to the gross or net spend baseline.
3. Sorted breakdowns display highest-spend items first, placing credit adjustments transparently at the bottom.

