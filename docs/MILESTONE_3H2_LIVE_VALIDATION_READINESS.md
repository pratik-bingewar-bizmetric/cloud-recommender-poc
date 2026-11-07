# Milestone 3H.2: Live Billing Ingestion Preflight Readiness & Query Approval Protocol

- **Target Workspace:** Azure Databricks Dev (`642006393507276`)
- **Workspace Host:** `https://adb-642006393507276.16.azuredatabricks.net`
- **Authentication Profile:** `azure-dev` (Azure CLI OAuth)
- **Target SQL Warehouse:** `Serverless Starter Warehouse` (ID: `05ed10a52697a344`)
- **Observed Warehouse State:** `STOPPED`
- **Current Operational Status:** `PREFLIGHT_READY_APPROVAL_BLOCKED`

---

## 1. Objective & Human Authorization Protocol

Milestone 3H.2 prepares the exact SQL statements, preflight validation checks, and operational safety boundaries required before live Databricks billing ingestion can be authorized.

> [!CAUTION]
> **Zero-Execution Boundary Active**: The SQL Warehouse is `STOPPED`. Neither frontend checkboxes nor API requests (`approved=true`) constitute authority to resume compute. Live execution remains completely blocked until the subscription owner provides explicit written authorization based on the specifications below.

---

## 2. Proposed Live SQL Statements

### Statement 1: Granular Billing Usage Extraction
```sql
SELECT 
    record_id,
    workspace_id,
    account_id,
    sku_name,
    cloud,
    usage_start_time,
    usage_end_time,
    usage_date,
    usage_unit,
    usage_quantity,
    record_type,
    ingestion_date,
    billing_origin_product,
    product_features,
    usage_metadata,
    custom_tags
FROM system.billing.usage
WHERE workspace_id = '642006393507276'
  AND usage_date >= '2026-10-01' 
  AND usage_date <= '2026-11-04'
ORDER BY usage_start_time DESC
LIMIT 100;
```
- **Purpose**: Ingest granular resource consumption records to populate the FinOps Command Center.
- **Data Scope**: Target workspace `642006393507276`, 35-day window (`2026-10-01` to `2026-11-04`).
- **Expected Result Size**: 11 to 100 records (~150 KB JSON payload).
- **Required Privileges**: `SELECT` privilege on catalog `system`, schema `billing`, table `usage`.

---

### Statement 2: Published Rate Card Ingestion
```sql
SELECT 
    sku_name,
    cloud,
    currency_code,
    price_per_unit,
    pricing_unit,
    price_start_time,
    price_end_time
FROM system.billing.list_prices
WHERE cloud = 'azure'
  AND (price_end_time IS NULL OR price_end_time >= '2026-10-01')
ORDER BY price_start_time DESC
LIMIT 50;
```
- **Purpose**: Ingest official published or contracted rate cards for deterministic spend joins.
- **Data Scope**: Azure cloud SKU pricing active during the observation period.
- **Expected Result Size**: ~10 to 50 records (~25 KB JSON payload).
- **Required Privileges**: `SELECT` privilege on catalog `system`, schema `billing`, table `list_prices`.

---

## 3. Financial & Operational Impact Assessment

1. **Warehouse State Transition**:
   - The warehouse will transition from `STOPPED` to `STARTING`, then `RUNNING`.
   - Cold start latency is estimated at 15–35 seconds (Serverless compute pool).
2. **Compute Burst Cost**:
   - Estimated serverless DBU consumption for 2 bounded queries is ~0.05 to 0.15 DBU (~$0.11 to $0.33 USD).
3. **Auto-Termination Guarantee**:
   - The target warehouse has a configured auto-stop threshold of 10 minutes.
   - If no subsequent queries arrive, compute returns to `STOPPED` automatically, bounding idle spend to less than $0.75 USD.
4. **Data Mutation**:
   - **Zero Mutations**: Pure read-only `SELECT` projections. AST security validator rejects any statement containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `MERGE`, `GRANT`, `REVOKE`, or multiple statements separated by semicolons.
5. **Rollback & Offline Fallback**:
   - If execution fails or is denied, the system seamlessly falls back to certified offline fixtures (`88,420.0 DBU`, `$168,834.25 spend`) with zero impact on dashboard availability.

---

## 4. Current Milestone Verification Status

- Warehouse State Polled: `STOPPED` (non-intrusive metadata inspection verified).
- SQL Execution: **BLOCKED** (0 live queries executed).
- Preflight Status: **READY**.
- Frozen Baseline: **INTACT**.

