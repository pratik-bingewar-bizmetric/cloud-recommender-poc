# Production Deployment Runbook: Databricks FinOps Command Center

- **System:** Cloud Recommender & Databricks FinOps Command Center
- **Target OS:** Linux (Ubuntu 22.04 LTS / Alpine) or Windows Server
- **Runtime:** Python 3.12+, Node.js 20+
- **Database:** PostgreSQL 15+ (asyncpg / psycopg)

---

## 1. Environment Variable Template

Create a secure `.env` file in the root and `backend/` directories. Never commit secrets to source control.

```bash
# --- Application Environment ---
APP_NAME=cloud-recommender-poc
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO
SECRET_KEY=CHANGE_THIS_TO_SECURE_64_CHAR_HEX_KEY

# --- Database Persistence ---
DATABASE_URL=postgresql+asyncpg://finops_user:STRONG_PASSWORD@db-postgres.internal:5432/finops_db

# --- Databricks Read-Only Integration ---
DATABRICKS_HOST=https://adb-642006393507276.16.azuredatabricks.net
DATABRICKS_WAREHOUSE_ID=05ed10a52697a344
DATABRICKS_AUTH_TYPE=oauth-m2m
DATABRICKS_CLIENT_ID=YOUR_AZURE_SP_APP_ID
DATABRICKS_CLIENT_SECRET=YOUR_AZURE_SP_CLIENT_SECRET
DATABRICKS_PROFILE=
DATABRICKS_QUERY_TIMEOUT_SECONDS=30

# --- Frontend URL & CORS ---
CORS_ORIGINS=["https://finops.yourdomain.com", "http://localhost:3000"]
NEXT_PUBLIC_API_URL=https://api-finops.yourdomain.com
```

---

## 2. Database Migration Procedure

1. Verify database connectivity:
   ```bash
   cd backend
   .venv/bin/python -c "from cloud_recommender.db.session import check_db_health; import asyncio; print(asyncio.run(check_db_health()))"
   ```

2. Inspect pending revisions:
   ```bash
   .venv/bin/alembic history
   .venv/bin/alembic current
   ```

3. Apply migration to head:
   ```bash
   .venv/bin/alembic upgrade head
   ```
   *Expected outcome*: Revision `2026_11_07_0002` applies `billing_usage_records`, `billing_price_records`, `billing_ingestion_runs`, `billing_reconciliation_results`, `billing_source_checkpoints`, `billing_scope_snapshots`, and `billing_calculation_versions`.

---

## 3. Service Startup Instructions

### 3.1 Backend Service (FastAPI)
```bash
cd backend
.venv/bin/uvicorn cloud_recommender.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 4
```

### 3.2 Frontend Service (Next.js)
```bash
cd frontend
npm ci
npm run build
npm start -- -p 3000
```

---

## 4. Health Check & Validation Verification

Probe the following endpoints to verify service readiness:

1. **Service Liveness**:
   ```bash
   curl -s http://localhost:8000/api/v1/health | jq .
   ```
2. **FinOps Command Center Readiness**:
   ```bash
   curl -s http://localhost:8000/api/v1/finops/ingestion/status | jq .
   ```
   *Expected output*: `warehouse_status: "WAREHOUSE_STOPPED"`, `system_tables_status: "APPROVAL_REQUIRED"`, `can_execute: false`.

3. **Preflight Validation Check**:
   ```bash
   curl -X POST -s http://localhost:8000/api/v1/finops/ingestion/validate | jq .
   ```

---

## 5. Rollback Procedures

### 5.1 Database Rollback
If a schema issue arises, roll back the billing ingestion migration safely:
```bash
cd backend
.venv/bin/alembic downgrade 2026_10_12_0001
```

### 5.2 Compute Emergency Stop
If a SQL warehouse was resumed inadvertently, issue an emergency stop via the Databricks CLI or metadata API:
```bash
databricks sql-warehouses stop 05ed10a52697a344
```

