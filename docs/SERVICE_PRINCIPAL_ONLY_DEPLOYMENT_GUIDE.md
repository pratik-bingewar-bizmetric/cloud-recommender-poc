# Service Principal-Only Deployment & Operations Guide

**Document ID:** `DEPLOY-GUIDE-PHASE3`  
**Status:** Approved  
**Target Environment:** Azure App Service (`FinopsBackendApp`) + Microsoft Fabric Web App  
**Repository:** `cloud-recommender-poc`  
**Branch:** `feature/backend-security-hardening`

---

## 1. Overview

This deployment and operations guide provides administrators and DevOps engineers with instructions to configure, deploy, and operate the **Service Principal-Only Authentication** architecture for the FinOps application.

---

## 2. Azure Prerequisites & Service Principal Setup

To connect an Azure subscription to the FinOps platform, an Azure administrator must create an Azure Entra App Registration (Service Principal) with least-privilege, read-only permissions.

### 2.1 Step 1: Create Microsoft Entra App Registration
Using the Azure CLI:
```bash
# Set your target subscription ID
SUBSCRIPTION_ID="00000000-0000-0000-0000-000000000000"

# 1. Create the Entra Application Registration
az ad app create --display-name "FinOps-Recommender-ReadOnly"

# 2. Get Application (Client) ID
CLIENT_ID=$(az ad app list --display-name "FinOps-Recommender-ReadOnly" --query "[0].appId" -o tsv)

# 3. Create Service Principal for the Application
az ad sp create --id "$CLIENT_ID"

# 4. Generate a Client Secret (Valid for 1 year)
CLIENT_SECRET=$(az ad app credential reset --id "$CLIENT_ID" --years 1 --query "password" -o tsv)

# 5. Get Directory (Tenant) ID
TENANT_ID=$(az account show --query "tenantId" -o tsv)

echo "Tenant ID:       $TENANT_ID"
echo "Client ID:       $CLIENT_ID"
echo "Subscription ID: $SUBSCRIPTION_ID"
echo "Client Secret:   $CLIENT_SECRET"
```

### 2.2 Step 2: Assign Read-Only RBAC Roles
The FinOps platform strictly enforces read-only access. Assign the following roles at the subscription scope:

```bash
# 1. Reader Role (Required for resource inventory, topology, resource groups, and metrics)
az role assignment create \
  --assignee "$CLIENT_ID" \
  --role "Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID"

# 2. Cost Management Reader Role (Recommended for FinOps billing & cost analysis)
az role assignment create \
  --assignee "$CLIENT_ID" \
  --role "Cost Management Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID"

# 3. Monitoring Reader Role (Optional, for detailed telemetry and alert analysis)
az role assignment create \
  --assignee "$CLIENT_ID" \
  --role "Monitoring Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID"
```

> [!IMPORTANT]
> Never assign `Contributor`, `Owner`, or any write permissions. The platform enforces a zero-execution policy and will refuse or ignore write permissions.

---

## 3. Backend Deployment: Azure App Service (`FinopsBackendApp`)

### 3.1 Environment Variables Configuration
Configure the following App Service Application Settings in Azure Portal (**App Service** &rarr; **Configuration** &rarr; **Application settings**):

| Setting Name | Recommended Value | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `production` | Application operational mode |
| `LOG_LEVEL` | `INFO` | Structured logging verbosity |
| `SECRET_KEY` | `<cryptographically-secure-random-64-hex>` | Application cryptographic master key |
| `AZURE_AUTHORITY_URL` | `https://login.microsoftonline.com` | Microsoft Entra token endpoint authority |
| `AZURE_LIVE_CONNECT_ATTEMPTS_PER_MINUTE` | `10` | Brute-force rate limiting per client/tenant |
| `AZURE_LIVE_REQUEST_TIMEOUT_SECONDS` | `20` | Upstream ARM request timeout |
| `CORS_ORIGINS` | `https://app.fabric.microsoft.com,https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net` | Allowed frontend origins (comma-separated, normalized) |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` | Enables Oryx build during deployment |

### 3.2 Linux App Service Startup Command
In **App Service** &rarr; **Configuration** &rarr; **General settings** &rarr; **Startup Command**:
```bash
python -m uvicorn cloud_recommender.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### 3.3 Deployment Process (ZIP Package Deployment)
```powershell
# 1. Run local verification
backend\.venv\Scripts\ruff.exe check backend/src backend/tests
backend\.venv\Scripts\mypy.exe --config-file backend/pyproject.toml backend/src
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_sp_only_auth.py backend/tests/test_config.py backend/tests/test_app_service_readiness.py -v

# 2. Package deployment ZIP (excluding .git, .env, __pycache__, .venv)
# 3. Deploy via Azure CLI or Azure Portal Deployment Center:
az webapp deploy \
  --resource-group "<your-resource-group>" \
  --name "FinopsBackendApp" \
  --src-path "deploy.zip" \
  --type zip
```

---

## 4. Frontend Deployment: Microsoft Fabric Web App

### 4.1 Frontend Environment Configuration
In `fabric-integration/finops-app/packages/frontend/.env.production` (or Fabric Web App settings):
```env
VITE_API_BASE_URL=https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1
```

### 4.2 Build & Publish
```bash
# 1. Install dependencies
npm --prefix fabric-integration/finops-app install

# 2. Run unit and component test suites
npm --prefix fabric-integration/finops-app/packages/frontend test -- --run

# 3. Compile production bundle
npm --prefix fabric-integration/finops-app/packages/frontend run build

# 4. Deploy static bundle (dist/) to Microsoft Fabric Web App hosting
```

---

## 5. End-to-End Operational Verification Runbook

### 5.1 Verification Checklist
1. **Backend Health Check:**
   ```bash
   curl -i -X GET "https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/health"
   # Expected: HTTP 200 OK {"status":"healthy", ...}
   ```
2. **CORS Preflight Check:**
   ```bash
   curl -i -X OPTIONS "https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net/api/v1/auth/connect" \
     -H "Origin: https://app.fabric.microsoft.com" \
     -H "Access-Control-Request-Method: POST"
   # Expected: HTTP 200 OK, Access-Control-Allow-Origin: https://app.fabric.microsoft.com
   ```
3. **Application Login:**
   - Open the Microsoft Fabric frontend URL.
   - The user is greeted by the **Connect to FinOps Platform** screen.
   - Enter Account Name, Subscription ID, Tenant ID, Client ID, and Client Secret.
   - Click **Connect & Access FinOps Dashboard**.
   - Verify that the dashboard loads with inventory, cost overview, and recommendations.

---

## 6. Troubleshooting Common Microsoft Entra Errors

| Error Code | Microsoft Entra Message | Root Cause & Resolution |
| :--- | :--- | :--- |
| **AADSTS7000215** | `Invalid client secret is provided` | The entered client secret is incorrect or has been rotated. Generate a new secret in Entra App Registrations. |
| **AADSTS7000222** | `The provided client secret keys are expired` | The client secret has passed its expiration date. Create a new secret and update credentials. |
| **AADSTS700016** | `Application with identifier was not found` | The Client ID does not exist in the specified Tenant ID. Verify that both GUIDs are correct. |
| **AADSTS90002** | `Tenant identifier not found` | The Tenant ID is incorrect or represents an unverified directory. |
| **AADSTS7000112** | `Application is disabled` | The Entra App Registration is disabled. Enable the application under Enterprise Applications in Azure Portal. |
| **403 SUBSCRIPTION_ACCESS_DENIED** | `Service Principal does not have Reader access` | The Service Principal lacks the `Reader` role assignment on the target subscription. Assign the `Reader` role using `az role assignment create`. |
| **400 SUBSCRIPTION_DISABLED** | `Azure subscription is disabled` | The target subscription has been cancelled, suspended, or disabled in Azure Cost Management. Re-activate the subscription or select an active subscription. |

