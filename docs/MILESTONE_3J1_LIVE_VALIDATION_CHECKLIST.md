# MILESTONE 3J.1 — Live Validation & Staging Deployment Checklist

> **Purpose:** Operational runbook for authorizing live queries against Azure Databricks System Tables.  
> **Status:** PRE-AUTHORIZATION GATE ACTIVE  
> **Target Workspace:** Azure Databricks `642006393507276`  
> **Target Warehouse:** `Serverless Starter Warehouse` (`05ed10a52697a344`)

---

## 1. Operating Rules & Pre-Conditions

1. **Explicit Human Approval Required:**
   - Under no circumstances may an agent or automated worker start, resume, or issue live SQL statements without an authorized human operator executing this checklist.
2. **Read-Only System Tables Scope:**
   - Permitted tables are strictly limited to `system.billing.usage` and `system.billing.list_prices`.
   - All catalog/schema mutation statements (`CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, `DELETE`) are programmatically blocked by the application's read-only validator.
3. **One-Time Cryptographic Token:**
   - Any live query must present a valid HMAC-SHA256 authorization token signed by the application secret key within its 15-minute TTL window.
   - Tokens are single-use; replay attempts will fail immediately.

---

## 2. Step-by-Step Operator Verification

### Phase 1: Environment & Identity Verification
- [ ] 1. Verify caller identity in Azure CLI:
  ```powershell
  az account show --query "{subscription:id, user:user.name, tenant:tenantId}"
  ```
- [ ] 2. Confirm Azure Databricks CLI authentication profile:
  ```powershell
  databricks auth profiles
  # Ensure profile 'azure-dev' points to https://adb-642006393507276.16.azuredatabricks.net
  ```
- [ ] 3. Verify warehouse status (MUST be verified without starting):
  ```powershell
  # Using Databricks CLI or API:
  databricks warehouses get 05ed10a52697a344 --profile azure-dev
  # Confirm: state is 'STOPPED'
  ```

### Phase 2: Ingestion Preflight Validation
- [ ] 4. Call preflight API endpoint (`/api/v1/finops/ingestion/validate`):
  ```powershell
  curl -X POST http://localhost:8000/api/v1/finops/ingestion/validate `
    -H "Content-Type: application/json" `
    -d '{"workspace_id": "642006393507276"}'
  ```
- [ ] 5. Review preflight diagnostics payload:
  - `warehouse_status`: must report `WAREHOUSE_STOPPED`.
  - `exact_query_preview`: verify query text only targets `system.billing.usage`.
  - `start_warehouse_permitted`: confirm whether customer policy permits automated warehouse start upon approval.

### Phase 3: Issuing Single-Use HMAC Approval Token
- [ ] 6. Human administrator generates approval token for the specific query hash:
  ```python
  from cloud_recommender.services.databricks.sql_client import DatabricksSqlService
  sql_svc = DatabricksSqlService()
  token = sql_svc.issue_approval_token(
      query="SELECT * FROM system.billing.usage WHERE workspace_id = '642006393507276' ...",
      warehouse_id="05ed10a52697a344",
      max_age_seconds=900,
  )
  print(f"Approval Token: {token}")
  ```

### Phase 4: Executing Authorized Ingestion
- [ ] 7. Submit ingestion request with approval token (`/api/v1/finops/ingestion/run`):
  ```powershell
  curl -X POST http://localhost:8000/api/v1/finops/ingestion/run `
    -H "Content-Type: application/json" `
    -d '{
      "workspace_id": "642006393507276",
      "is_approved": true,
      "approval_token": "<TOKEN>",
      "start_warehouse_if_stopped": true
    }'
  ```
- [ ] 8. Verify ingestion ledger outputs in database and Command Center:
  - Check `billing_ingestion_runs` table for `status = 'COMPLETED'`.
  - Verify `billing_reconciliation_results` matches net DBU and spend.
  - Inspect Command Center UI (http://localhost:3000) under Settings > Watermark Checkpoints.

