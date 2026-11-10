# Azure Databricks Apps Production Deployment Guide

> **Target Workspace:** Azure Databricks Workspace `642006393507276`  
> **Workspace URL:** `https://adb-642006393507276.16.azuredatabricks.net`  
> **Application Name:** `bizmetric-finops`  
> **Platform Version:** Production Runbook V1.0  
> **Repository:** `cloud-recommender-poc`  
> **Status:** Deployment Ready — Awaiting Cloud Execution Approval  

---

## 1. Prerequisites Checklist

Before executing the deployment to Azure Databricks, verify that the following prerequisites are met:

- [ ] **Databricks CLI v0.200+** installed and authenticated:
  ```bash
  databricks --version
  databricks auth describe --profile azure-dev
  ```
- [ ] **Workspace Access:** Verified access to workspace `642006393507276` with permissions to manage Databricks Apps.
- [ ] **External PostgreSQL Database:** Provisioned Azure Database for PostgreSQL Flexible Server with TLS enabled.
- [ ] **Microsoft Entra Application Registration:** Created Service Principal with `Reader` and `Cost Management Reader` roles.
- [ ] **Databricks Secret Scope:** Created secret scope `finops-secrets` for secure credential storage.
- [ ] **Pre-Flight Validation:** All local tests, builds, and typechecks passing.

---

## 2. Pre-Deployment Build & Migration Procedure

### Step 2.1: Compile Frontend Production Assets
In the local workspace or CI/CD runner:
```bash
# Navigate to frontend directory
cd frontend

# Install pinned dependencies
npm ci

# Run typecheck and lint
npm run typecheck
npm run lint

# Generate optimized production build
npm run build
cd ..
```
*Verification:* Ensure `frontend/.next` is generated successfully.

### Step 2.2: Execute Controlled Database Migration
In compliance with production governance, migrations are executed as a separate controlled task, **never on application startup**:
```bash
# Point DATABASE_URL to production PostgreSQL flexible server
export DATABASE_URL="postgresql+asyncpg://finops_admin:<password>@psql-finops-prod.postgres.database.azure.com:5432/cloud_recommender?ssl=require"

# Check target connection and current schema revision
python backend/scripts/run_migrations.py --check-only

# Apply migrations up to head
python backend/scripts/run_migrations.py --revision head
```
*Verification:* Confirm Alembic reports `Migration completed successfully (OK)`.

---

## 3. Secret Scope Configuration

Store production credentials in the Databricks Secret Scope so they are never checked into source control or exposed in environment manifests:

```bash
# 1. Create secret scope
databricks secrets create-scope finops-secrets

# 2. Store PostgreSQL connection credentials
databricks secrets put-secret finops-secrets postgres-password --string-value "<production-db-password>"

# 3. Store Microsoft Entra ID (Azure) credentials
databricks secrets put-secret finops-secrets azure-client-secret --string-value "<azure-sp-client-secret>"

# 4. Verify registered secrets (values remain hidden)
databricks secrets list-secrets finops-secrets
```

---

## 4. Databricks App Creation & Deployment

### Step 4.1: Create the Databricks App
```bash
databricks apps create bizmetric-finops \
  --description "Bizmetric FinOps & Infrastructure Intelligence Platform" \
  --profile azure-dev
```

### Step 4.2: Deploy Application Package
Deploy the application package containing `app.yaml`, `run_databricks_app.py`, `backend/`, and `frontend/`:
```bash
databricks apps deploy bizmetric-finops \
  --source-code-path . \
  --profile azure-dev
```

### Step 4.3: Monitor Deployment Progress
```bash
databricks apps get bizmetric-finops --profile azure-dev
```
Wait until `app_status` transitions from `DEPLOYING` to `RUNNING`.

---

## 5. Post-Deployment Verification & Smoke Tests

### Step 5.1: Retrieve Application URL
```bash
databricks apps get bizmetric-finops --profile azure-dev --output json | jq -r .url
```
*Example Output:* `https://bizmetric-finops-642006393507276.16.azuredatabricks.net`

### Step 5.2: Probe Health & Readiness Endpoints
```bash
# 1. Probe Liveness (Next.js & FastAPI Process Health)
curl -s -i "https://<app-url>/health"
# Expected: HTTP 200 OK {"status": "ok", "service": "bizmetric-finops", ...}

# 2. Probe Readiness (PostgreSQL Connectivity & Zero-Execution Boundary)
curl -s -i "https://<app-url>/health/ready"
# Expected: HTTP 200 OK {"status": "ready", "dependencies": {"database": {"status": "connected"}, ...}}
```

### Step 5.3: Verify User Interface & RBAC
1. Open the application URL in an authenticated browser.
2. Confirm the **Bizmetric** logo displays with zero "POC" badges.
3. Confirm **Executive Overview** displays all 7 certified KPI cards and the **AI FinOps Intelligence & Cost Analysis** panel.
4. Navigate to **Warehouses** under Section A and verify the amber banner:  
   `Warehouse State: STOPPED (Zero-Execution Policy Enforced)`.
5. Confirm Serverless Starter Warehouse `05ed10a52697a344` remains halted.

---

## 6. Rollback & Troubleshooting Procedures

### 6.1 Inspect Application Logs
```bash
databricks apps logs bizmetric-finops --profile azure-dev
```

### 6.2 Rollback to Prior Deployment
```bash
# Redeploy prior certified release commit
git checkout <prior-stable-commit-hash>
databricks apps deploy bizmetric-finops --source-code-path . --profile azure-dev
```

### 6.3 Emergency Application Stop
```bash
databricks apps stop bizmetric-finops --profile azure-dev
```

