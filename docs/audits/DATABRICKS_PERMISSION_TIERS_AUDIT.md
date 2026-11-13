# DATABRICKS PERMISSION TIER AUDIT REPORT

**Audit Date:** November 11, 2026  
**Identity:** `pratik.bingewar@bizmetric.com` (ID: `146809578344068`)  
**Identity Type:** Human User  
**Workspace Admin:** NO (Regular workspace user)  
**Account Admin:** NO  
**Authentication Strategy:** Configured CLI Profile [azure-dev] via Azure CLI Session  
**Target Workspace:** `https://adb-642006393507276.16.azuredatabricks.net`  
**Target Account ID:** `71c1893d-14e0-4107-8fb4-9f0bb8655555`  

---

## 1. Environment & Configuration Status

| Environment Variable | Status |
| :--- | :--- |
| `DATABRICKS_HOST` | [MISSING - using ~/.databrickscfg azure-dev] |
| `DATABRICKS_ACCOUNT_ID` | [MISSING - using ~/.databrickscfg azure-dev] |
| `DATABRICKS_CLIENT_ID` | [MISSING - using Azure CLI session] |
| `DATABRICKS_CLIENT_SECRET` | [MISSING - using Azure CLI session] |

---

## 2. Permission Tier Audit Results

| Tier | Endpoint/Table | Status | Likely Cause (if failed) | Suggested Fix |
| :--- | :--- | :---: | :--- | :--- |
| Tier 1 — Workspace APIs | `GET /api/2.1/clusters/list` | ✅ | None (Accessible) | Already accessible |
| Tier 1 — Workspace APIs | `GET /api/2.2/jobs/list` | ✅ | None (Accessible) | Already accessible |
| Tier 1 — Workspace APIs | `GET /api/2.0/sql/warehouses` | ✅ | None (Accessible) | Already accessible |
| Tier 1 — Workspace APIs | `GET /api/2.1/unity-catalog/catalogs` | ✅ | None (Accessible) | Already accessible |
| Tier 1 — Workspace APIs | `GET /api/2.0/pipelines` | ✅ | None (Accessible) | Already accessible |
| Tier 1 — Workspace APIs | `GET /api/2.0/serving-endpoints` | ✅ | None (Accessible) | Already accessible |
| Tier 1 — Workspace APIs | `GET /api/2.0/preview/scim/v2/Users` | ✅ | None (Accessible) | Already accessible |
| Tier 2 — Account APIs | `GET /api/2.1/accounts/{account_id}/budgets` | ✅ | None (Accessible) | Already accessible |
| Tier 2 — Account APIs | `GET /api/2.0/accounts/{account_id}/scim/v2/Users` | ❌ | 403 Forbidden (Caller lacks Databricks Account Admin role) | Assign Account Admin role in Databricks Account Console |
| Tier 2 — Account APIs | `GET /api/2.0/accounts/{account_id}/scim/v2/ServicePrincipals` | ❌ | 403 Forbidden (Caller lacks Databricks Account Admin role) | Assign Account Admin role in Databricks Account Console |
| Tier 2 — Account APIs | `GET /api/2.0/accounts/{account_id}/workspaces` | ✅ | None (Accessible) | Already accessible |
| Tier 3 — System Tables | `SQL: SELECT 1 FROM system.billing.usage LIMIT 1` | ❌ | (d) warehouse/compute issue (SQL Warehouse 05ed10a52697a344 is STOPPED; compute startup blocked under Zero-Execution guardrail) | Grant CAN USE on warehouse '05ed10a52697a344', start warehouse, and grant SELECT on system.billing.usage |
| Tier 3 — System Tables | `SQL: SELECT 1 FROM system.billing.list_prices LIMIT 1` | ❌ | (d) warehouse/compute issue (SQL Warehouse 05ed10a52697a344 is STOPPED; compute startup blocked under Zero-Execution guardrail) | Grant CAN USE on warehouse '05ed10a52697a344', start warehouse, and grant SELECT on system.billing.list_prices |
| Tier 3 — System Tables | `SQL: SELECT 1 FROM system.compute.clusters LIMIT 1` | ❌ | (d) warehouse/compute issue (SQL Warehouse 05ed10a52697a344 is STOPPED; compute startup blocked under Zero-Execution guardrail) | Grant CAN USE on warehouse '05ed10a52697a344', start warehouse, and grant SELECT on system.compute.clusters |
| Tier 3 — System Tables | `SQL: SELECT 1 FROM system.lakeflow.jobs LIMIT 1` | ❌ | (d) warehouse/compute issue (SQL Warehouse 05ed10a52697a344 is STOPPED; compute startup blocked under Zero-Execution guardrail) | Grant CAN USE on warehouse '05ed10a52697a344', start warehouse, and grant SELECT on system.lakeflow.jobs |
| Tier 3 — System Tables | `SQL: SELECT 1 FROM system.query.history LIMIT 1` | ❌ | (d) warehouse/compute issue (SQL Warehouse 05ed10a52697a344 is STOPPED; compute startup blocked under Zero-Execution guardrail) | Grant CAN USE on warehouse '05ed10a52697a344', start warehouse, and grant SELECT on system.query.history |
| Tier 3 — System Tables | `SQL: SELECT 1 FROM system.access.audit LIMIT 1` | ❌ | (d) warehouse/compute issue (SQL Warehouse 05ed10a52697a344 is STOPPED; compute startup blocked under Zero-Execution guardrail) | Grant CAN USE on warehouse '05ed10a52697a344', start warehouse, and grant SELECT on system.access.audit |

---

## 3. Executive Summary & Action Plan

1. **What I can already do:**
   - Full read-only visibility into Workspace Tier 1 resources: listing clusters, jobs, SQL warehouses, Unity Catalog catalogs/schemas/table metadata, pipelines, model serving endpoints, and workspace SCIM users.
   - Account-level visibility into registered workspaces and account budget configurations.
   - Complete schema discovery across 29 Unity Catalog System Tables (including `system.billing.*`, `system.compute.*`, `system.query.*`, `system.lakeflow.*`, `system.access.*`).

2. **What's fully blocked:**
   - **Account Administration:** SCIM user and Service Principal management at the account level (`GET /api/2.0/accounts/71c1893d-14e0-4107-8fb4-9f0bb8655555/scim/v2/Users` and `ServicePrincipals`) returns `403 FORBIDDEN` because caller lacks the Account Admin role.
   - **Live SQL Query Execution on System Tables:** Executing `SELECT 1 FROM system.*` is blocked because SQL Warehouse `05ed10a52697a344` is in `STOPPED` state, caller lacks `CAN_MANAGE`/`CAN_USE`, and unapproved compute startup is prevented under Zero-Execution guardrails.

3. **Single most impactful grant to add next:**
   - **Grant `CAN USE` on SQL Warehouse `05ed10a52697a344` and `SELECT` on `system.billing.*` (with `USE CATALOG system` & `USE SCHEMA billing`) to identity `pratik.bingewar@bizmetric.com`.** This single grant unblocks all FinOps cost queries and live billing ingestion.
