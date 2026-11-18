# Databricks Dev Workspace Live Integration & Verification Report (M2.2A)

> **Document Status:** Complete & Verified  
> **Target Workspace:** `adb-deaccelerator-dev` (ID: `642006393507276`)  
> **Host URL:** `https://adb-642006393507276.16.azuredatabricks.net`  
> **Cloud Provider:** Azure (Region: Central India)  
> **Effective Authentication:** Azure CLI Delegated Token (`2ff814a6-3304-4ab8-85cb-cd0e6f879c1d`)  
> **Authenticated Identity:** `pratik.bingewar@bizmetric.com` (User ID: `146809578344068`)  
> **Date:** November 13, 2026  

---

## 1. Executive Summary

Milestone **M2.2A** resolves the authentication and connectivity block for the Databricks Development workspace (`adb-deaccelerator-dev`, ID `642006393507276`) by implementing **Azure CLI Delegated Authentication** for local development while preserving strict **OAuth 2.0 M2M Service Principal Authentication** for unattended production environments.

Previously, attempts to access the Dev workspace via the Service Principal (`FinOps-ReadOnly-Connector`, Client ID `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7`) failed with HTTP 403 / 401 errors because the SP had not been provisioned as an authorized member in workspace `642006393507276`. In contrast, the authenticated Azure CLI user (`pratik.bingewar@bizmetric.com`) possesses full workspace entitlements (`workspace-access`, `databricks-sql-access`, `workspace-consume`).

Through this implementation:
1. **Azure CLI Credential Provider** was implemented in `backend/src/cloud_recommender/services/databricks/auth.py`, acquiring Bearer tokens dynamically for Azure Databricks resource `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d` with an in-memory TTL buffer (300s) and zero persistence to disk, database, logs, or frontend.
2. **Strict Environment Separation** was enforced: `DEV_LOCAL` uses Azure CLI delegated auth; `PROD` strictly requires Service Principal OAuth credentials and fails closed.
3. **Two-Gate Protocol** was executed and fully passed:
   - **Gate 1 (Implementation Verification):** 31/31 backend tests passed in 10.93s, Ruff check/format passed, Mypy strict typing passed with zero errors, Next.js frontend ESLint, TypeScript check, and production build succeeded.
   - **Gate 2 (Actual Workspace Live Verification):** 14/14 discovery targets were verified against the live Dev workspace `642006393507276`, discovering 79 active resources (1 cluster, 1 cluster policy, 1 SQL warehouse, 27 model serving endpoints, 3 Databricks apps, 36 MLflow experiments/runs, 9 Unity Catalog catalogs with 108 schemas and 780 tables, and 14 System Tables schemas with 46 tables).

---

## 2. Forensic Root Cause Analysis: SP vs. Azure CLI

### 2.1 The Discrepancy
| Parameter | Service Principal Path (Blocked) | Azure CLI Delegated Path (Working) |
| :--- | :--- | :--- |
| **Identity** | `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7` (`FinOps-ReadOnly-Connector`) | `pratik.bingewar@bizmetric.com` (User ID `146809578344068`) |
| **Entitlements** | None in workspace `642006393507276` (`SCIM totalResults: 0`) | `workspace-access`, `databricks-sql-access`, `workspace-consume` |
| **Tenant** | `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` | `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` |
| **Token Resource** | `https://fe82a67c.../oauth2/v2.0/token` | `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d` (Azure Databricks App ID) |
| **Response** | `HTTP 403 Forbidden` (`User is not authorized in this workspace`) | `HTTP 200 OK` (Full SCIM and Workspace API access) |

### 2.2 Root Cause
The Service Principal was created in Microsoft Entra ID but was never registered in the Dev workspace's internal SCIM directory or assigned workspace access. The Azure CLI user identity, however, has direct user membership and active workspace entitlements. 

---

## 3. Architecture & Implementation Details

### 3.1 `AzureCliCredentialProvider` (`auth.py`)
A dedicated credential provider class manages Azure CLI token lifecycle:
- **CLI Detection:** Checks for `az` or `az.cmd` via `shutil.which`.
- **Session Validation:** Executes `az account show` to confirm an active tenant login and returns the user principal.
- **Dynamic Token Acquisition:** Runs `az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --output json`.
- **In-Memory Caching:** Caches the Bearer token in memory until `expires_on - 300` seconds to avoid repeated subprocess invocations while guaranteeing fresh tokens.
- **Secret Scrubbing:** Overrides logging and error formatters to replace raw tokens and authorization headers with `[REDACTED_TOKEN]`.

### 3.2 Workspace Client Resolution Strategy
`DatabricksAuthService.create_workspace_client` uses deterministic priority:
1. **Production Mode (`PROD`):** If `environment="production"` or `app_env="production"` or `auth_type="oauth-m2m"`, strictly uses Service Principal OAuth. If SP credentials are missing or invalid, it **fails closed** and never falls back to personal developer Azure CLI credentials.
2. **Development Mode (`DEV_LOCAL`):** If `environment="development"` on Azure or `auth_type="azure-cli"`, invokes `AzureCliCredentialProvider`. If Azure CLI is not logged in, returns an actionable error (`"Azure CLI session unauthenticated. Run 'az login'"`).
3. **Databricks CLI Profile Fallback:** Uses named CLI profiles (e.g., AWS Databricks).
4. **Explicit Credentials Fallback:** Uses provided client credentials if non-placeholder.

---

## 4. Gate 1 — Implementation Verification Results

| Verification Check | Target Component | Command Executed | Status | Exit Code / Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **Code Formatting** | Backend Databricks services & tests | `ruff format --check` | **PASSED** | Code 0: 7 files formatted |
| **Linter Check** | Backend Databricks services & tests | `ruff check` | **PASSED** | Code 0: All checks passed |
| **Type Check** | Backend Databricks services | `mypy` | **PASSED** | Code 0: Success, no issues found |
| **Backend Unit Tests** | Databricks test suite | `pytest backend/tests/test_databricks_workspace.py` | **PASSED** | Code 0: 31 passed in 10.93s |
| **Frontend Lint** | FinOps Next.js UI | `npm --prefix frontend run lint` | **PASSED** | Code 0: No ESLint warnings/errors |
| **Frontend Type Check** | FinOps TypeScript codebase | `npm --prefix frontend run typecheck` | **PASSED** | Code 0: `tsc --noEmit` clean |
| **Frontend Production Build** | Next.js App Router | `npm --prefix frontend run build` | **PASSED** | Code 0: Production build successful |

### Unit Test Coverage Breakdown
- `test_azure_cli_provider_detection`: Verifies discovery of `az` executable on Windows and Linux.
- `test_azure_cli_provider_session_validation_success`: Verifies extraction of username and tenant from `az account show`.
- `test_azure_cli_provider_session_validation_unauthenticated`: Verifies clean error handling on expired sessions.
- `test_azure_cli_provider_token_acquisition_and_caching`: Verifies dynamic token acquisition and TTL buffer expiration.
- `test_azure_cli_provider_missing_cli_raises`: Confirms helpful error when Azure CLI is not installed.
- `test_azure_cli_provider_token_error_scrubbing`: Confirms zero token leakage in exception messages.
- `test_environment_separation_dev_vs_prod`: Enforces that production never falls back to personal CLI.
- `test_discovery_service_all_categories_success`: Validates end-to-end multi-category response assembly.
- `test_discovery_service_permission_denied_isolation`: Ensures 403 on one category does not compromise other categories.

---

## 5. Gate 2 — Actual Workspace Live Verification Matrix

All 14 workspace targets were verified against the live Databricks Dev workspace (`adb-deaccelerator-dev`, ID `642006393507276`):

| # | Target Service | API Endpoint / SDK Method | HTTP Status | Actual Count | Status | Key Discovered Resources / Evidence |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **1** | **Current User** | `databricks-sdk/current_user.me` | 200 | 1 | **LIVE_VERIFIED** | `pratik.bingewar@bizmetric.com` (ID: `146809578344068`) |
| **2** | **Workspace Groups** | `GET /api/2.0/preview/scim/v2/Groups` | 200 | 11 | **LIVE_VERIFIED** | `admins`, `users`, `grp_data_engineers`, `grp_data_scientists`, `de-accelerator-dev` |
| **3** | **Compute Clusters** | `databricks-sdk/clusters.list` | 200 | 1 | **LIVE_VERIFIED** | `adf-deaccelator-compute` (`1102-081455-7t3bqp3v`, state `TERMINATED`, node `Standard_D3_v2`) |
| **4** | **Cluster Policies** | `databricks-sdk/cluster_policies.list` | 200 | 1 | **LIVE_VERIFIED** | `Personal Compute` (`0012DDEB5AAF23F0`, definition: single-node, DBR 13.3+) |
| **5** | **Instance Pools** | `databricks-sdk/instance_pools.list` | 200 | 0 | **NO_DATA** | Confirmed zero pools configured (`empty_confirmed: true`) |
| **6** | **SQL Warehouses** | `databricks-sdk/warehouses.list` | 200 | 1 | **LIVE_VERIFIED** | `Serverless Starter Warehouse` (`05ed10a52697a344`, `STOPPED`, serverless=True, size 2X-Small) |
| **7** | **Jobs / Workflows** | `databricks-sdk/jobs.list` | 200 | 0 | **NO_DATA** | Confirmed zero workflows scheduled (`empty_confirmed: true`) |
| **8** | **Job Runs** | `databricks-sdk/jobs.list_runs` | 200 | 0 | **NO_DATA** | Confirmed zero past runs found (`empty_confirmed: true`, limit=25) |
| **9** | **Delta Live Pipelines** | `databricks-sdk/pipelines.list_pipelines` | 200 | 0 | **NO_DATA** | Confirmed zero Lakeflow pipelines (`empty_confirmed: true`) |
| **10** | **Model Serving** | `databricks-sdk/serving_endpoints.list` | 200 | 27 | **LIVE_VERIFIED** | 27 endpoints (`databricks-claude-opus-5-5`, `databricks-gpt-oss-120b`, `databricks-meta-llama-3-3-70b-instruct`) |
| **11** | **Databricks Apps** | `databricks-sdk/apps.list` | 200 | 3 | **LIVE_VERIFIED** | `cement-demand-forecasting`, `mcp-generate-ppt`, `wonder-cement-app` |
| **12** | **MLflow** | `databricks-sdk/experiments.search_experiments` | 200 | 36 | **LIVE_VERIFIED** | 36 active experiments and runs discovered |
| **13** | **Unity Catalog** | `databricks-sdk/catalogs.list` | 200 | 9 | **LIVE_VERIFIED** | 9 catalogs (`samples`, `deaccelerator`, `system`, `metrobank_poc`), 108 schemas, 780 tables |
| **14** | **System Tables** | `catalogs.list` / `schemas.list` | 200 | 14 | **LIVE_VERIFIED** | 14 schemas (`billing`, `compute`, `access`, `ai_gateway`, `query`), 46 tables discovered |

---

## 6. Security, Zero-Execution & FinOps Guardrails

1. **Zero-Execution Policy:**
   - No SQL queries were executed against any SQL warehouse or cluster.
   - The discovered SQL warehouse `05ed10a52697a344` is in state `STOPPED`. The system verified warehouse presence and configuration via control-plane metadata APIs without starting compute or incurring DBU cost.
2. **Credential Redaction:**
   - Tokens acquired via `az account get-access-token` are stored strictly in memory for the duration of the request lifecycle.
   - All log messages, error handlers, and HTTP response serializers scrub sensitive bearer tokens with `[REDACTED_TOKEN]`.
   - The `.env` file containing client configuration is excluded via `.gitignore` and is verified untracked by Git.
3. **No Synthetic Fallback:**
   - Synthetic fallback data has been removed from the live Dev connection path. The UI and API return actual workspace resources with accurate status indicators (`LIVE`, `NO_DATA`, `STOPPED`, `TERMINATED`).

---

## 7. Production Transition Roadmap

When promoting the service principal to the Dev workspace or deploying to Production:
1. **Workspace Entitlement Provisioning:**
   - An account administrator must navigate to Databricks Account Console -> **User management** -> **Service principals** -> select `FinOps-ReadOnly-Connector` -> assign to workspace `adb-deaccelerator-dev` (`642006393507276`) with entitlements `workspace-access` and `databricks-sql-access`.
2. **Grant Unity Catalog Permissions:**
   ```sql
   GRANT USE CATALOG ON CATALOG system TO `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7`;
   GRANT USE SCHEMA ON SCHEMA system.billing TO `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7`;
   GRANT SELECT ON TABLE system.billing.usage TO `1dc51b34-ba35-46c9-8f2a-71930fa5e9a7`;
   ```
3. **Zero Code Changes in Production:**
   - The application is already configured to automatically switch to OAuth M2M Service Principal authentication in Production mode (`APP_ENV=production` or `DATABRICKS_AUTH_TYPE=oauth-m2m`).

