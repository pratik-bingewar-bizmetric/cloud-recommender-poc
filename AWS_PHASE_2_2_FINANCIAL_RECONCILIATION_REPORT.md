# AWS Phase 2.2 — Financial Reconciliation Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** 2026-11-26  
> **Status:** AUDITED & FORMULA VERIFIED (LIVE CHARGEABLE EXECUTION PENDING AUTHORIZATION)

---

## 1. Mathematical Formulas & Precision Rules

### 1.1 Projected Month-End Spend Formula
$$\text{Projected Month-End Spend} = \text{Actual MTD Spend} + \text{Remaining Forecast Spend}$$

- **Actual MTD Interval:** $[2026\text{-}11\text{-}01, 2026\text{-}11\text{-}26)$ (exclusive end date $T$).
- **Remaining Forecast Interval:** $[2026\text{-}11\text{-}26, 2026\text{-}12\text{-}01)$ (inclusive start date $T$, exclusive end date $T_{next\_month}$).
- Zero overlapping days, zero omitted days.

### 1.2 Month-over-Month (MoM) Trend Formula
$$\text{MoM Change \%} = \frac{\text{Current MTD} - \text{Previous Comparable MTD}}{\text{Previous Comparable MTD}} \times 100$$
- Safely handles zero or negative comparison denominators by reporting `None` rather than dividing by zero.

### 1.3 Decimal Precision Invariant
- Raw billing line amounts preserve `decimal.Decimal` precision without early rounding.
- Rounding (`ROUND_HALF_UP` to 2 decimal places) occurs strictly at the presentation boundary.
- Regression verification: 1,000 micro-transactions at \$0.004 yield exactly \$4.00 total spend.

---

## 2. Multi-Currency & Data Availability Classification

- If multiple distinct currencies are returned in a grouped query, the system marks `data_availability = "MIXED_CURRENCIES"` and sets `current_month_to_date_cost = None` to prevent invalid summation across currencies.
- If pagination is cut short due to budget cap limits, the response is explicitly tagged as `PARTIAL_DATA` (`is_partial = True`).

