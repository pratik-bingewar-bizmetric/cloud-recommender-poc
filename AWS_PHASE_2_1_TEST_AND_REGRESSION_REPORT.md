# AWS Phase 2.1 — Test & Regression Verification Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** November 2026  
> **Test Status:** 37/37 PASSED (100% Pass Rate)

---

## 1. Test Suite Summary

The automated test suite covers all three phases of AWS integration:
- **Phase 1:** Core connectivity, SigV4 signing, credential encryption, resource discovery, and findings detector (15 tests).
- **Phase 2:** Cost Explorer, CloudWatch telemetry, Price List API, CUR readiness, and Phase 2 API routes (10 tests).
- **Phase 2.1:** Decimal arithmetic, forecasting projection formula, safe pagination, negative adjustments, HMAC approval token lifecycle, single-use enforcement, cross-tenant isolation, budget guards, outbound allowlists, canonical cache keys, and CUR manifest detection (12 tests).

---

## 2. Test Execution Results

```
backend\tests\test_aws_phase1.py::test_sigv4_key_derivation PASSED               [  2%]
backend\tests\test_aws_phase1.py::test_sigv4_request_signing PASSED              [  5%]
backend\tests\test_aws_phase1.py::test_aws_account_id_validation PASSED          [  8%]
backend\tests\test_aws_phase1.py::test_aws_region_validation PASSED              [ 10%]
backend\tests\test_aws_phase1.py::test_aws_role_arn_validation PASSED            [ 13%]
backend\tests\test_aws_phase1.py::test_aws_credentials_expiry PASSED             [ 16%]
backend\tests\test_aws_phase1.py::test_aws_secret_scrubbing PASSED               [ 18%]
backend\tests\test_aws_phase1.py::test_error_classification PASSED               [ 21%]
backend\tests\test_aws_phase1.py::test_findings_detector_blackhole_route PASSED  [ 24%]
backend\tests\test_aws_phase1.py::test_findings_detector_missing_lambda_role PASSED [ 27%]
backend\tests\test_aws_phase1.py::test_findings_detector_unattached_ebs_volume PASSED [ 29%]
backend\tests\test_aws_phase1.py::test_aws_connectivity_service_e2e PASSED       [ 32%]
backend\tests\test_aws_phase1.py::test_aws_resource_discovery_and_findings PASSED [ 35%]
backend\tests\test_aws_phase1.py::test_connection_manager_aws_lifecycle PASSED [ 37%]
backend\tests\test_aws_phase1.py::test_connection_manager_generic_create_aws PASSED [ 40%]
backend\tests\test_aws_phase2.py::test_cost_explorer_get_cost_and_usage_success PASSED [ 43%]
backend\tests\test_aws_phase2.py::test_cost_explorer_get_cost_breakdown PASSED   [ 45%]
backend\tests\test_aws_phase2.py::test_cost_explorer_get_cost_summary_with_forecast PASSED [ 48%]
backend\tests\test_aws_phase2.py::test_cost_explorer_error_classification PASSED [ 51%]
backend\tests\test_aws_phase2.py::test_cloudwatch_get_metric_data_success PASSED [ 54%]
backend\tests\test_aws_phase2.py::test_cloudwatch_ec2_metrics_instrumentation_gating PASSED [ 56%]
backend\tests\test_aws_phase2.py::test_pricing_service_location_mapping_and_fallback PASSED [ 59%]
backend\tests\test_aws_phase2.py::test_pricing_service_in_memory_cache PASSED    [ 62%]
backend\tests\test_aws_phase2.py::test_cur_readiness_inspection PASSED           [ 64%]
backend\tests\test_aws_phase2.py::test_aws_phase2_routes PASSED                  [ 67%]
backend\tests\test_aws_phase2_1.py::test_decimal_conversion_and_rounding PASSED   [ 70%]
backend\tests\test_aws_phase2_1.py::test_cost_explorer_pagination PASSED         [ 72%]
backend\tests\test_aws_phase2_1.py::test_cost_forecast_projection_formula PASSED [ 75%]
backend\tests\test_aws_phase2_1.py::test_negative_adjustments_and_credits PASSED  [ 78%]
backend\tests\test_aws_phase2_1.py::test_sync_preview_generation PASSED          [ 81%]
backend\tests\test_aws_phase2_1.py::test_sync_token_lifecycle_and_single_use PASSED [ 83%]
backend\tests\test_aws_phase2_1.py::test_sync_token_cross_tenant_rejection PASSED [ 86%]
backend\tests\test_aws_phase2_1.py::test_budget_guard_limit_enforcement PASSED   [ 89%]
backend\tests\test_aws_phase2_1.py::test_sigv4_outbound_allowlist_enforcement PASSED [ 91%]
backend\tests\test_aws_phase2_1.py::test_pricing_canonical_cache_key PASSED       [ 94%]
backend\tests\test_aws_phase2_1.py::test_pricing_source_classification PASSED    [ 97%]
backend\tests\test_aws_phase2_1.py::test_cur_readiness_manifest_detection PASSED  [100%]

======================= 37 passed in 3.36s ========================
```

---

## 3. Code Quality Verification Summary

1. **Ruff Linter & Formatter:**
   ```
   backend\.venv\Scripts\ruff check backend\src backend\tests
   backend\.venv\Scripts\ruff format --check backend\src backend\tests
   -> All checks passed! 202 files already formatted.
   ```
2. **Mypy Static Type Checking:**
   ```
   backend\.venv\Scripts\mypy backend\src\cloud_recommender\services\aws backend\src\cloud_recommender\schemas\aws.py backend\src\cloud_recommender\api\routes\aws.py
   -> Success: no issues found in 12 source files.
   ```
3. **Frontend Linting & Typecheck:**
   ```
   npm --prefix frontend run lint
   npm --prefix frontend run typecheck
   -> No ESLint warnings or errors. Typecheck clean.
   ```
4. **Frontend Production Build:**
   ```
   npm --prefix frontend run build
   -> Compiled successfully. All 4 static pages optimized.
   ```

