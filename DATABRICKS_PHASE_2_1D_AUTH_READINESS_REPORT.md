# Databricks Phase 2.1D — Production Authentication Readiness Report

> **Document Status:** Complete & Verified  
> **Date:** 2026-11-23  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/gcp-service-account-integration`  
> **Target Cloud:** Microsoft Azure / Azure Databricks  

---

## 1. Executive Summary

Phase 2.1D was executed to resolve and verify production Databricks Service Principal authentication readiness without starting SQL warehouse compute or extracting live billing telemetry.

Through rigorous live HTTP/OIDC telemetry diagnostics and SDK test execution, the root cause of the production authentication failure was identified:
1. **Databricks OIDC Endpoint:** Service Principal `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` returned `HTTP 403 Forbidden` (`{"error":"access_denied","error_description":"Workspace 642006393507276 is inaccessible"}`) because the Service Principal exists at the Databricks Account level but has not been assigned `Workspace access` in the Databricks Account Console (`accounts.azuredatabricks.net`).
2. **Azure Entra ID Token Endpoint:** Direct probe to `https://login.microsoftonline.com/fe82a67c-faa7-4d9a-bbfa-7d25b7047b41/oauth2/v2.0/token` returned `HTTP 401 AADSTS7000215: Invalid client secret provided`. Inspection revealed that the configured `DATABRICKS_CLIENT_SECRET` in `.env` was a 36-character string matching the Azure App Registration **Secret ID (UUID)** format rather than the generated **Secret Value**.
3. **Fail-Closed Security & Zero Silent Fallback:** The backend architecture strictly prevents silent fallback from Service Principal authentication to personal developer Azure CLI credentials in production mode.
4. **Zero-Execution Compliance:** Target warehouse `05ed10a52697a344` remained strictly untouched in `STOPPED` state throughout all diagnostic probes.

---

## 2. Target Environment & Identity Configuration

| Configuration Parameter | Value | Description |
| :--- | :--- | :--- |
| **Workspace Name** | `Azure Databricks Dev` | Target Azure Databricks workspace |
| **Workspace ID** | `642006393507276` | Canonical Databricks Workspace Identifier |
| **Workspace Host** | `https://adb-642006393507276.16.azuredatabricks.net` | Target Databricks REST / OIDC URL |
| **SQL Warehouse Name** | `Serverless Starter Warehouse` | Serverless SQL compute resource |
| **SQL Warehouse ID** | `05ed10a52697a344` | Target SQL warehouse |
| **Warehouse Status** | `STOPPED` | Compute state (strictly preserved, zero mutation) |
| **Auto-Stop Duration** | 5 minutes | Scale-to-zero inactivity timer |
| **Configured SP Client ID** | `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` | Databricks / Azure AD Service Principal Application ID |
| **Azure Tenant ID** | `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` | Bizmetric Entra ID Tenant ID |
| **Delegated Dev Identity** | `pratik.bingewar@bizmetric.com` | Azure CLI user active in local development session |

---

## 3. Diagnostic Investigation & Root Cause Analysis

### 3.1 Databricks Native OAuth M2M Endpoint Probe

A live diagnostic request was dispatched to the Databricks workspace OIDC token endpoint:

- **Endpoint:** `POST https://adb-642006393507276.16.azuredatabricks.net/oidc/v1/token`
- **Payload:** `grant_type=client_credentials&scope=all-apis&client_id=1dc51b34-ba35-46c9-8f2a-71930fa5e9a7&client_secret=[REDACTED]`
- **Response:**
  ```json
  HTTP/1.1 403 Forbidden
  Content-Type: application/json
  {
    "error": "access_denied",
    "error_description": "Workspace 642006393507276 is inaccessible"
  }
  ```
- **Root Cause:** In Databricks unified multi-tenant architecture, Service Principals created at the Account level do not have implicit access to any workspace. Without explicit workspace assignment by an Account Admin, the workspace token endpoint rejects authentication with `access_denied`.

### 3.2 Azure Entra ID Token Endpoint Probe

To verify whether the Service Principal could authenticate via Azure Active Directory token exchange:

- **Endpoint:** `POST https://login.microsoftonline.com/fe82a67c-faa7-4d9a-bbfa-7d25b7047b41/oauth2/v2.0/token`
- **Scope:** `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default` (Azure Databricks Resource App ID)
- **Response:**
  ```json
  HTTP/1.1 401 Unauthorized
  Content-Type: application/json
  {
    "error": "invalid_client",
    "error_description": "AADSTS7000215: Invalid client secret provided. Ensure the secret being sent in the request is the client secret value, not the client secret ID..."
  }
  ```
- **Root Cause:** The `DATABRICKS_CLIENT_SECRET` configured in `.env` is 36 characters long with hyphens (UUID format). In Azure Portal -> App Registrations, each client secret displays two columns: **Secret ID** (UUID) and **Value** (random string visible only upon generation). The Secret ID was mistakenly copied into `.env`.

---

## 4. Required Administrator Remediation Action

To enable production M2M Service Principal authentication, an authorized **Databricks Account Administrator** must execute the following non-billable entitlement steps:

### Step 1: Grant Workspace Access in Databricks Account Console
1. Log in to the Databricks Account Console at **`https://accounts.azuredatabricks.net`**.
2. Select **Workspaces** from the left navigation panel.
3. Click on target workspace **`Azure Databricks Dev`** (`642006393507276`).
4. Select the **Permissions** tab.
5. Click **Add permissions**.
6. Search for and select Service Principal **`1dc51b34-ba35-46c9-8f2a-71930fa5e9a7`** (or create it in User Management if not present).
7. Assign Role: **`User`** (or `Admin`).
8. Check Entitlements:
   - **`Workspace access`** (Mandatory)
   - **`Databricks SQL access`** (Mandatory for SQL Statements API)
9. Click **Save**.

### Step 2: Grant Minimum SQL & Unity Catalog Permissions (In-Workspace)
1. Within workspace `https://adb-642006393507276.16.azuredatabricks.net`:
2. Navigate to **SQL Warehouses** -> Select `Serverless Starter Warehouse` (`05ed10a52697a344`).
3. Click **Permissions** -> Add Service Principal `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` -> Grant **`Can Use`**.
4. Navigate to **Catalog** -> `system` -> `billing`.
5. Grant `SELECT` on `system.billing.usage` and `system.billing.list_prices` to Service Principal `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7`.

### Step 3 (Optional if using Azure AD Token Exchange): Generate Secret Value
1. In Azure Portal -> Azure Active Directory / Entra ID -> **App registrations**.
2. Select App Registration `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7`.
3. Go to **Certificates & secrets** -> **Client secrets** -> **New client secret**.
4. Copy the **Value** column immediately and update `DATABRICKS_CLIENT_SECRET`.

---

## 5. Security & Architectural Guardrails Enforced

### 5.1 Strict Fail-Closed Security & Zero Silent Fallback
- `DatabricksAuthService.create_workspace_client` checks the operational environment and configured authentication mode:
  - When `environment="production"` or `auth_type="oauth-m2m"`, it mandates valid Service Principal credentials.
  - If SP credentials are missing, incomplete, or rejected, it throws `DatabricksAuthError`.
  - **Zero Silent Fallback:** It strictly refuses silent fallback to the developer's personal Azure CLI credentials in production.

### 5.2 Secret Scrubbing
- All logging and error handling pipelines pass through `DatabricksAuthService.scrub_sensitive`:
  - Client secrets, bearer tokens, and JWT strings are completely redacted (`[REDACTED_SECRET]`, `[REDACTED_TOKEN]`).
  - No plaintext credentials, session tokens, or keys are emitted in API responses, logs, or error payloads.

### 5.3 Zero-Execution Guardrail
- `DatabricksSqlService.check_warehouse_status()` verifies workspace authentication prior to any compute inspection.
- When authentication fails (401 or 403), the service classifies the status as `PERMISSION_DENIED`, sets `warehouse_state="UNKNOWN"` and `can_execute=False`, and returns immediately without attempting to inspect, start, or query the warehouse compute resource.

---

## 6. Verification & Automated Test Results

### 6.1 Phase 2.1D Automated Test Suite (`test_databricks_phase2_1d_auth.py`)

| Test Case | Description | Result |
| :--- | :--- | :---: |
| `test_production_mode_refuses_silent_fallback_to_azure_cli` | Verifies production mode fails closed when SP credentials are unset, refusing CLI fallback. | **PASSED** |
| `test_production_403_access_denied_is_classified_cleanly` | Verifies `403 Workspace is inaccessible` is classified as `permission_denied` / `HTTP_403`. | **PASSED** |
| `test_secret_scrubbing_redacts_tokens_and_client_secrets` | Verifies bearer tokens, secrets, and JWTs are replaced with redaction placeholders. | **PASSED** |
| `test_check_warehouse_status_reports_permission_denied_without_starting_compute` | Verifies warehouse inspection on 403 sets `PERMISSION_DENIED` without calling compute APIs. | **PASSED** |
| `test_dev_mode_uses_azure_cli_and_refuses_silent_sp_fallback` | Verifies dev mode requires Azure CLI and does not silently fall back to SP. | **PASSED** |

### 6.2 Full Regression Suite

- **Backend Databricks & FinOps Suite:** **173 passed, 0 failed** in 10.95s.
  - `test_databricks_phase2_1d_auth.py`: 5 passed
  - `test_databricks_approve_and_run.py`: 13 passed
  - `test_databricks_phase2_1c_readiness.py`: 6 passed
  - `test_databricks_workspace.py`: 31 passed
  - `test_databricks_phase4_e2e.py`: 9 passed
  - `test_finops_analytics.py`: 18 passed
  - `test_live_finops_integration.py`: 16 passed
  - `test_m7_1_billing_hardening.py`: 75 passed
- **Code Style & Formatting:** `ruff check` and `ruff format --check` passed with 0 errors.
- **Frontend Build Verification:** `tsc -b --noCheck && vite build` completed successfully (`dist/` generated, 0 errors).

---

## 7. Status & Next Milestones

| Capability | Current Status | Blocker / Next Action |
| :--- | :---: | :--- |
| **Azure CLI Delegated Auth (Dev)** | **WORKING (Live)** | Operational for local testing with `pratik.bingewar@bizmetric.com`. |
| **Service Principal M2M Auth (Prod)** | **BLOCKED (Diagnosed)** | Awaiting Databricks Account Admin workspace assignment in `accounts.azuredatabricks.net`. |
| **SQL Warehouse Compute** | **STOPPED (Protected)** | Compute startup intentionally guarded until authorized execution. |
| **Billing Ingestion Pipeline** | **READY** | Approval token workflow, pagination, DB persistence, and reconciliation verified. |

