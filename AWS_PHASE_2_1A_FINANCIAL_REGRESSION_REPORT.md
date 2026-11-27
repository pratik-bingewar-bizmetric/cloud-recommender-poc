# AWS Phase 2.1A — Financial Accuracy & Regression Verification Report

> **Repository:** `cloud-recommender-poc`  
> **Status:** VERIFIED & DETERMINISTIC  
> **Date:** November 2026

---

## 1. Financial Precision & Micro-Billing Aggregation

### 1.1 Invariant: Preservation of `decimal.Decimal` Without Early Rounding

In cloud billing, micro-transactions (e.g. AWS Lambda invocations, S3 requests, DynamoDB read/write units) cost fractions of a cent (e.g. \$0.004). If individual billing line items are prematurely rounded to 2 decimal places using `ROUND_HALF_UP`, each item rounds to \$0.00, resulting in total spend vanishing entirely:
$$1,000 \times \text{round}(\$0.004, 2) = 1,000 \times \$0.00 = \$0.00 \quad (\text{Catastrophic Error})$$

In Phase 2.1A, `backend/src/cloud_recommender/services/aws/cost_explorer_service.py` strictly preserves raw `Decimal` precision throughout internal calculations and data structures (`raw_cost_amount`, `cost_usd`). `ROUND_HALF_UP` to two decimal places is applied strictly at the presentation boundary (`cost_usd_formatted` or summary total display).

### 1.2 Regression Test Evidence (`test_financial_precision_aggregation_regression`)

- **Input:** 1,000 synthetic billing records, each with `UnblendedCost = 0.004` USD.
- **Expected Total:** $1,000 \times 0.004 = \$4.00000 \rightarrow \$4.00$.
- **Result:**
  - `total_cost = Decimal('4.0000000000')`
  - Quantized to 2 places: `Decimal('4.00')`
  - Early-rounding failure avoided. Verified in `test_financial_precision_aggregation_regression`.

---

## 2. Non-Overlapping Actual MTD and Forecast Intervals

### 2.1 AWS Cost Explorer Date Semantics

AWS Cost Explorer defines interval boundaries with exclusive end dates:
$$\text{TimePeriod} = [\text{Start}, \text{End})$$

To prevent double-counting or day omission:
- If today is $T = \text{2026-11-26}$:
  - **Actual MTD Interval:** `2026-11-01` to `2026-11-26` (covers Nov 1 through Nov 25 completed days).
  - **Remaining Forecast Interval:** `2026-11-26` to `2026-12-01` (covers Nov 26 through Nov 30).
  - $\text{actual\_cost\_period\_end} = \text{forecast\_period\_start} = T$.
  - Zero overlapping days, zero missing days.

### 2.2 December-to-January Rollover & Leap Years

The date computation handles year boundaries:
- December 2026 ($T = \text{2026-12-15}$):
  - Actual: `2026-12-01` to `2026-12-15`
  - Forecast: `2026-12-15` to `2027-01-01` (next month starts on `2027-01-01`).
- Verified across month rollovers and leap year transitions.

---

## 3. Dynamic Prediction Interval Evaluation

Rather than assuming symmetric 95% confidence intervals from AWS Cost Explorer (`MeanValue - LowerBound == UpperBound - MeanValue`), `AwsCostForecast` evaluates symmetry dynamically:
```python
is_sym = (
    abs((mean - lower) - (upper - mean)) < Decimal("0.01")
    if (lower is not None and upper is not None)
    else False
)
```
This guarantees accurate representation of non-normal spend distributions.

---

## 4. Multi-Currency Rejection Invariant

AWS Cost Explorer multi-account consolidations occasionally return mixed currencies (e.g. USD and EUR). Summing numbers with differing currencies is mathematically invalid.

In Phase 2.1A:
- If distinct currency units are detected across groups, `get_cost_summary(...)` marks:
  - `data_availability = "MIXED_CURRENCIES"`
  - `current_month_to_date_cost = None`
  - Explicit warning notes explaining the multi-currency condition.
- Verified in `test_mixed_currency_rejection`.

