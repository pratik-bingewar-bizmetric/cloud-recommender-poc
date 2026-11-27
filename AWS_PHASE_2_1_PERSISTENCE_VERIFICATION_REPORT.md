# AWS Phase 2.1 — Persistence & Data Model Verification Report

> **Repository:** `cloud-recommender-poc`  
> **Status:** AUDITED, TESTED & VERIFIED

---

## 1. Domain Model Parity & Multi-Cloud Parity

Phase 2.1 enforces schema parity between AWS, Azure, GCP, and Databricks. AWS financial and telemetry structures adhere to the domain contracts in `backend/src/cloud_recommender/schemas/aws.py`.

### Key Schema Entities:

1. **`AwsCostSummary`:**
   - `account_id: str`
   - `currency: str = "USD"`
   - `current_month_to_date_cost: float | None` (Derived from `Decimal`)
   - `previous_month_cost: float | None`
   - `comparable_previous_month_to_date_cost: float | None`
   - `month_over_month_percentage_change: float | None`
   - `forecast: AwsCostForecast | None`
   - `top_services: list[AwsCostBreakdownItem]`
   - `region_breakdown: list[AwsCostBreakdownItem]`
   - `data_availability: str = "AVAILABLE"`
   - `notes: list[str]`

2. **`AwsCostForecast`:**
   - `remaining_forecast_amount: float` (Future period mean estimate)
   - `actual_month_to_date_cost: float` (Spend to date)
   - `projected_month_end_cost: float` ($C_{\text{MTD}} + F_{\text{rem}}$)
   - `prediction_interval_lower_bound: float | None`
   - `prediction_interval_upper_bound: float | None`
   - `confidence_level: int = 95`
   - `forecast_observed_at: datetime`

3. **`AwsPricingEstimate`:**
   - `hourly_rate: float`
   - `monthly_estimated_rate: float` (Based on 730 operating hours)
   - `operating_hours_assumption: int = 730`
   - `is_partial_estimate: bool = False`
   - `pricing_source: str` (`LIVE_AWS_PRICE_LIST`, `CACHED_AWS_PRICE_LIST`, `OFFLINE_REFERENCE_CATALOG`)

4. **`AwsCurReadiness`:**
   - `bucket_name: str`
   - `bucket_exists: bool`
   - `bucket_accessible: bool`
   - `has_manifest: bool`
   - `manifest_validated: bool`
   - `readiness_status: str`
   - `notes: list[str]`

---

## 2. In-Memory and PostgreSQL Store Verification

- **In-Memory Connection Store:** Used during local testing and CI/CD pipelines via `CONNECTION_STORE="memory"`. All encryption/decryption cycles execute deterministically with throw-away test keys.
- **Audit Ledger:** Every approval token issuance, consumption, and execution result is recorded in the operational audit ledger with full actor attribution (`user_id`, `tenant_id`, timestamp, and requested budget).

