# Azure Subscription Authentication & RBAC Setup Guide

> **Application:** Bizmetric FinOps & Infrastructure Intelligence Platform  
> **Security Model:** Strictly Least-Privilege Read-Only & Zero-Execution  
> **Target Scope:** Multi-Subscription Azure Resource Management & Cost Ingestion  
> **Status:** Production Reference  

---

## 1. Authentication Architecture & Security Principles

The Bizmetric platform connects to customer Azure subscriptions using an **independent Microsoft Entra ID Service Principal** (Application Registration). 

### Golden Security Principles
1. **Zero-Mutation Guarantee:** The application is strictly an observability and recommendation platform. It contains no write, update, restart, or delete logic.
2. **Strictly Least-Privilege RBAC:** The Service Principal is granted only `Reader` and `Cost Management Reader` roles. Administrative roles (`Owner`, `Contributor`, `User Access Administrator`) are **strictly prohibited**.
3. **Decoupled Identity:** Azure subscription credentials remain completely separate from Azure Databricks workspace authentication.

```mermaid
flowchart LR
    subgraph DatabricksApp["Azure Databricks App (bizmetric-finops)"]
        Backend["FastAPI Backend<br/>(Azure SDK & httpx)"]
    end

    subgraph EntraID["Microsoft Entra ID (Azure AD)"]
        TokenEndpoint["OAuth2 Token Endpoint<br/>login.microsoftonline.com"]
    end

    subgraph AzureSubscriptions["Customer Azure Subscriptions"]
        Sub1["Subscription 1: sub-finops-enterprise-01<br/>Role: Reader, Cost Management Reader"]
        Sub2["Subscription 2: sub-data-platform-prod<br/>Role: Reader, Cost Management Reader"]
    end

    Backend -->|1. Client Credentials Grant<br/>(Client ID + Secret / Workload Identity)| TokenEndpoint
    TokenEndpoint -->|2. Short-Lived Access Token<br/>(Audience: management.azure.com)| Backend
    Backend -->|3. Read-Only ARM REST: Inventory| Sub1
    Backend -->|4. Read-Only Cost Management API| Sub1
    Backend -->|5. Switch Scope to Sub 2| Sub2
```

---

## 2. Required API Scopes & Minimum RBAC Roles

To support multi-subscription discovery, inventory, and cost analysis, the following roles must be assigned:

| Role Name | Scope | API Accessed | Business Purpose |
|:---|:---|:---|:---|
| **Reader** | Subscription / Resource Group | Azure Resource Manager (`management.azure.com`) | Discovers resource inventory, VM sizing, storage tiers, network topologies, and cluster VMs. |
| **Cost Management Reader** | Subscription / Billing Account | Azure Cost Management API (`Microsoft.CostManagement`) | Ingests daily amortized cost, usage records, reservation utilization, and enterprise invoice reconciliation. |
| **Monitoring Reader** *(Optional)* | Subscription | Azure Monitor (`Microsoft.Insights`) | Ingests compute utilization metrics (CPU %, Memory %, Network IOPS) for rightsizing analysis. |

> [!CAUTION]
> **Prohibited Roles:** Do NOT assign `Contributor`, `Owner`, or any custom role with `*/write` or `*/delete` actions. The platform enforces zero execution and will reject tokens carrying administrative write capabilities.

---

## 3. Provisioning the Service Principal (Azure CLI)

Run the following Azure CLI commands from an administrative terminal:

### Step 1: Create the Microsoft Entra Application
```bash
# Create Service Principal without initial role assignments
az ad sp create-for-rbac \
  --name "sp-bizmetric-finops-readonly" \
  --skip-assignment \
  --output json
```
*Output will provide:*
- `appId` (Client ID)
- `password` (Client Secret)
- `tenant` (Tenant ID)

### Step 2: Assign Roles to Subscription 1 (`sub-finops-enterprise-01`)
```bash
SP_APP_ID="<your-app-id>"
SUB_ID_1="c1a7d84e-289b-4b1e-9271-9e2b18642001"

# Assign Reader
az role assignment create \
  --assignee "$SP_APP_ID" \
  --role "Reader" \
  --scope "/subscriptions/$SUB_ID_1"

# Assign Cost Management Reader
az role assignment create \
  --assignee "$SP_APP_ID" \
  --role "Cost Management Reader" \
  --scope "/subscriptions/$SUB_ID_1"
```

### Step 3: Assign Roles to Additional Subscriptions (Optional)
```bash
SUB_ID_2="d2b8e95f-390c-5c2f-0382-0f3c29753112"

az role assignment create \
  --assignee "$SP_APP_ID" \
  --role "Reader" \
  --scope "/subscriptions/$SUB_ID_2"

az role assignment create \
  --assignee "$SP_APP_ID" \
  --role "Cost Management Reader" \
  --scope "/subscriptions/$SUB_ID_2"
```

---

## 4. Multi-Subscription Scope & Dynamic Switching

The platform supports seamless switching between authorized subscriptions without requiring service restarts:

1. **Discovery:** The backend queries `GET /subscriptions` using the Service Principal token to list all accessible subscriptions.
2. **Scope Switching:** When the user selects a different subscription in the UI, the frontend passes `subscription_id` as a query parameter.
3. **Cascading Reset:** Switching subscriptions automatically clears dependent resource group filters and recalculates all cost explorer and optimization KPIs within the new boundary.
4. **Diagnostic Error Handling:** If a subscription lacks `Cost Management Reader`, the platform gracefully returns `NOT AUTHORIZED` or `SOURCE UNAVAILABLE` with actionable diagnostic instructions rather than failing the entire dashboard.

---

## 5. Token Lifecycle, Caching & Renewal

- **Token Grant:** OAuth 2.0 Client Credentials Grant targeting `https://management.azure.com/.default`.
- **Token Cache:** Tokens are cached in-memory with automatic refresh 5 minutes prior to expiration (standard 60-minute token lifetime).
- **Error Diagnostics:**
  - `AADSTS700016`: Application not found or disabled in directory.
  - `AADSTS7000215`: Invalid client secret provided.
  - `AuthorizationFailed`: Missing `Reader` or `Cost Management Reader` RBAC assignment on the requested subscription scope.

