# MILESTONE 3J.1 — Test Evidence & Verification Logs

> **Repository:** `cloud-recommender-poc`  
> **Milestone:** 3J.1  
> **Timestamp:** November 7, 2026  
> **Target Workspace:** `642006393507276` (Azure Databricks)  
> **Frozen Commit:** `c2c87027f64b59fb784d990b9485781dde05e6f8`

---

## 1. Test Execution Summary

```
================================================================================
                               TEST SUITE AUDIT SUMMARY
================================================================================
  Backend Unit & Integration Tests:     335 PASSED, 2 SKIPPED, 0 FAILED (337 total)
  Backend Static Type Check (mypy):     SUCCESS (0 issues across 84 source files)
  Backend Lint & Syntax (ruff check):   SUCCESS (0 errors across 120 files)
  Backend Formatting (ruff format):     SUCCESS (120 files formatted)
  Frontend Static Type Check (tsc):     SUCCESS (0 errors)
  Frontend Lint (next lint):            SUCCESS (0 errors, 0 warnings)
  Frontend Production Build:            SUCCESS (all static pages generated)
  Frozen Fabric Baseline Diff:          0 DIFF (100% frozen)
================================================================================
```

---

## 2. Command Line Evidence & Outputs

### 2.1 Backend Full Pytest Suite

```powershell
Command: & backend\.venv\Scripts\python.exe -m pytest backend/tests/ -v
Exit Code: 0
Output:
============================= test session starts =============================
platform win32 -- Python 3.12.16, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\...\cloud-recommender-poc\backend
configfile: pyproject.toml
plugins: anyio-4.15.1, langsmith-0.14.7, asyncio-1.4.0, cov-7.1.0
collected 337 items

backend\tests\test_alembic_migration.py ......................... PASSED [  1%]
backend\tests\test_analysis_and_architecture_api.py ............. PASSED [  3%]
backend\tests\test_azure_inventory.py ........................... PASSED [  5%]
backend\tests\test_azure_retail_prices.py ....................... PASSED [  7%]
backend\tests\test_catalog_api.py ............................... PASSED [ 10%]
backend\tests\test_catalog_schema_and_seeds.py .................. PASSED [ 13%]
backend\tests\test_config.py .................................... PASSED [ 15%]
backend\tests\test_configuration.py ............................. PASSED [ 20%]
backend\tests\test_connections_and_tokens.py .................... PASSED [ 24%]
backend\tests\test_cors.py ...................................... PASSED [ 26%]
backend\tests\test_databricks_workspace.py ...................... PASSED [ 29%]
backend\tests\test_db.py ........................................ PASSED [ 30%]
backend\tests\test_entra_auth.py ................................ PASSED [ 35%]
backend\tests\test_finops_analytics.py .......................... PASSED [ 38%]
backend\tests\test_foundry_provider.py .......................... PASSED [ 42%]
backend\tests\test_gcp_inventory_and_comparison.py .............. PASSED [ 46%]
backend\tests\test_gcp_pricing.py ............................... PASSED [ 47%]
backend\tests\test_health.py .................................... PASSED [ 48%]
backend\tests\test_ingestion_enforcement.py ..................... PASSED [ 53%]
backend\tests\test_inventory_api.py ............................. PASSED [ 54%]
backend\tests\test_milestone_3f_audit.py ........................ PASSED [ 57%]
backend\tests\test_milestone_3g1_adversarial.py ................. PASSED [ 67%]
backend\tests\test_milestone_3g2_reconciliation.py .............. PASSED [ 70%]
backend\tests\test_milestone_3g3_reconciliation.py .............. PASSED [ 72%]
backend\tests\test_milestone_3g_reconciliation.py ............... PASSED [ 75%]
backend\tests\test_milestone_3h_ingestion.py .................... PASSED [ 82%]
backend\tests\test_monitoring_api.py ............................ PASSED [ 83%]
backend\tests\test_monitoring_service.py ........................ PASSED [ 86%]
backend\tests\test_optimization_schema.py ....................... PASSED [ 87%]
backend\tests\test_postgres_integration.py s s .................. 2 SKIPPED [ 88%]
backend\tests\test_pricing_engine.py ............................ PASSED [ 91%]
backend\tests\test_recommendation_schema.py ..................... PASSED [ 92%]
backend\tests\test_repositories_and_persistence.py .............. PASSED [ 94%]
backend\tests\test_waste_and_technical_debt.py .................. PASSED [ 98%]
backend\tests\test_workload_schema.py ........................... PASSED [100%]

================= 335 passed, 2 skipped in 120.79s (0:02:00) ==================
```

---

### 2.2 Backend Type Check (`mypy`)

```powershell
Command: & backend\.venv\Scripts\python.exe -m mypy backend/src/
Exit Code: 0
Output:
Success: no issues found in 84 source files
```

---

### 2.3 Backend Code Formatting & Linting (`ruff`)

```powershell
Command: & backend\.venv\Scripts\python.exe -m ruff check backend/src backend/tests
Exit Code: 0
Output:
All checks passed!

Command: & backend\.venv\Scripts\python.exe -m ruff format --check backend/src backend/tests
Exit Code: 0
Output:
120 files already formatted
```

---

### 2.4 Frontend Type Check (`tsc --noEmit`)

```powershell
Command: npm --prefix frontend run typecheck
Exit Code: 0
Output:
> frontend@0.1.0 typecheck
> tsc --noEmit
```

---

### 2.5 Frontend Lint (`next lint`)

```powershell
Command: npm --prefix frontend run lint
Exit Code: 0
Output:
> frontend@0.1.0 lint
> next lint

✔ No ESLint warnings or errors
```

---

### 2.6 Frontend Production Build (`next build`)

```powershell
Command: npm --prefix frontend run build
Exit Code: 0
Output:
> frontend@0.1.0 build
> next build

  ▲ Next.js 14.2.35
  - Environments: .env.local

   Creating an optimized production build ...
 ✓ Compiled successfully
   Linting and checking validity of types ...
   Collecting page data ...
   Generating static pages (0/5) ...
   Generating static pages (1/5) 
   Generating static pages (2/5) 
   Generating static pages (3/5) 
 ✓ Generating static pages (5/5)
   Finalizing page optimization ...
   Collecting build traces ...

Route (app)                              Size     First Load JS
┌ ○ /                                    157 kB          246 kB
└ ○ /_not-found                          880 B          89.6 kB
+ First Load JS shared by all            88.7 kB
  ├ chunks/2117-05132bdc06a19b1e.js      31.9 kB
  ├ chunks/fd9d1056-333c62e562f6a97d.js  53.6 kB
  └ other shared chunks (total)          3.16 kB

○  (Static)  prerendered as static content
```

---

### 2.7 Frozen Fabric Baseline Git Diff

```powershell
Command: git diff c2c87027f64b59fb784d990b9485781dde05e6f8 -- fabric-udf sync-agent function_app.py
Exit Code: 0
Output:
(empty - zero diffs detected)
```

