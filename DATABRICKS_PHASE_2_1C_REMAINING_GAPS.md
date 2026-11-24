# Phase 2.1C: Databricks Integration Remaining Gaps & Dependencies

> **Document Status:** Active Engineering Record  
> **Phase:** 2.1C — Databricks Integration Completion (Warehouse-Independent)  
> **Date:** 2026-11-23  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/gcp-service-account-integration`

---

## 1. Delineation: Code Completeness vs Cloud Tenant Dependencies

All application code, API routes, database schemas, cryptographic approval logic, chunk pagination parsers, reconciliation evaluators, and frontend UI components are **100% complete and tested**.

The remaining gaps are external cloud infrastructure dependencies that require authorized human operator action.

---

## 2. Inventory of Remaining Dependencies & Gaps

| # | Gap / Dependency Area | Technical Description | Impact on FinOps System | Action Required to Unblock |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **SQL Warehouse Suspended State** | Target SQL Warehouse `Serverless Starter Warehouse` (`05ed10a52697a344`) is in `State.STOPPED`. Auto-stop is set to 5 minutes. | Live SQL extraction via Statement Execution API cannot run without starting compute. | Operator must start the warehouse in the Databricks console (`/sql/warehouses`). Zero-execution guardrail forbids automated restart. |
| **2** | **Service Principal Workspace Entitlement** | Dedicated Service Principal (`5ba1fa61-e125-4521-b4f1-67849e75529d`) lacks `Workspace access` entitlement in `accounts.azuredatabricks.net`. | Production SP authentication returns 403 Forbidden. Current live access relies on Azure CLI delegated user (`pratik.bingewar@bizmetric.com`). | Databricks Account Admin must grant `Workspace access` in Account Console -> User Management -> Service Principals. |
| **3** | **Unpriced Preview Compute SKUs** | Databricks preview SKUs (specifically `GENIE_SPACE_COMPUTE`) have no published rate in `system.billing.list_prices`. | Reconciliation status remains `PARTIAL_PRICING` (70.20% DBU coverage) because unpriced compute cannot be matched against a list price. | Unmatched compute is safely preserved without assigning `$0.00`. Databricks will publish official SKU pricing upon general availability. |

---

## 3. Recommended Execution Path for Unblocking Live Data

1. **Step 1 (Human Operator Action):**
   - Access: `https://adb-642006393507276.16.azuredatabricks.net/sql/warehouses`
   - Start warehouse `05ed10a52697a344`. Wait ~15 seconds until status indicates `RUNNING`.
2. **Step 2 (Trigger Application Ingestion):**
   - Open FinOps Command Center.
   - Click **Approve & Start Ingestion (Usage)**.
   - The application will automatically extract live usage rows across all chunks, persist to PostgreSQL, advance the watermark checkpoint in `billing_source_checkpoints`, and display certified spend.

