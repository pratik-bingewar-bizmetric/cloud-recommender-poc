# Azure Account Hierarchy & Service Integration Implementation Report

> **Platform:** FinOps & Infrastructure Intelligence Platform  
> **Topic:** Cloud Hierarchy & Service Modeling  
> **Status:** Production-Ready  
> **Date:** November 2026

---

## 1. Architectural Motivation

In modern cloud computing, treating specialized PaaS and SaaS offerings like Databricks and Fabric as independent cloud providers disconnects them from their true operational context. 

In enterprise Azure deployments:
- Azure Databricks is provisioned within an Azure Resource Group under a specific Azure Subscription and billed via Azure DBU meters.
- Microsoft Fabric leverages Azure AD (Entra ID) tenant authentication, with storage anchored in Azure OneLake and compute capacities allocated against Azure subscriptions.
- Cross-charging, tag inheritance, and cost optimization require understanding the underlying subscription and tenant topology.

To align with this reality, the FinOps platform establishes a **Parent Account → Service Integration** architecture.

---

## 2. Data Model Implementation

### 2.1 Service Integration Interface
The frontend types (`frontend/src/types/index.ts`) have been enriched with the `ServiceIntegration` contract:

```typescript
export interface ServiceIntegration {
  service_type: "arm" | "databricks" | "fabric" | "gcp_core";
  display_name: string;
  status: "connected" | "ready_to_connect" | "standby" | "error";
  auth_method: string;
  capabilities: string[];
  details?: string;
}
```

### 2.2 Extended Cloud Connection Contract
The `CloudConnection` interface embeds an array of active service integrations:

```typescript
export interface CloudConnection {
  id: string;
  name: string;
  provider: "azure" | "gcp" | "aws";
  scope_id: string; // Azure Subscription ID or GCP Project ID
  display_name: string;
  tenant_or_org_id?: string; // Azure AD Tenant ID or GCP Org ID
  auth_method: string;
  status: "connected" | "ready_to_connect" | "error";
  last_verified_at: string;
  is_live: boolean;
  capabilities: string[];
  access_limitations?: string[];
  service_integrations?: ServiceIntegration[];
}
```

---

## 3. Azure Account Anatomy

### 3.1 Primary Account Cards
In `ConnectCloudView.tsx`, Azure accounts are instantiated with complete service integration state:

#### Azure Production Account (`conn-azure-prod`):
- **Subscription ID:** `f718c261-ab85-49fd-907e-99c022cc2aeb`
- **Tenant ID:** `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`
- **Authentication:** Azure CLI Credentials (OAuth2)
- **Status:** Connected & Verified
- **Nested Service Integrations:**
  1. **Azure Resource Manager (ARM):** Status: `connected`, Auth: `Reader Role (CLI OAuth)`, Capabilities: `["ARM Inventory", "Metrics", "Cost Management API"]`, Details: `48 Resource Groups, 98 Resources discovered`.
  2. **Azure Databricks:** Status: `connected`, Auth: `Azure CLI OAuth & System Tables Probed`, Capabilities: `["adb-lakehouse-eastus (642006393507276)", "system.billing", "query_history"]`, Details: `Unity Catalog & Billing System Tables Live`.
  3. **Microsoft Fabric:** Status: `connected`, Auth: `Service Principal (Fabric.Read.All)`, Capabilities: `["ws-fabric-analytics-01", "Direct Lake", "F64 Capacity"]`, Details: `FinOps Lakehouse & Capacity Telemetry Synchronized`.

#### Azure Analytics & Dev Account (`conn-azure-dev`):
- **Subscription ID:** `e827a192-3bc1-49e0-812d-11c033bb1fea`
- **Tenant ID:** `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`
- **Authentication:** Service Principal (OAuth2)
- **Nested Service Integrations:**
  1. **ARM:** Connected (36 RGs, 56 Resources cataloged)
  2. **Azure Databricks:** Connected (`adb-lakehouse-prod`, DBU Billing)
  3. **Microsoft Fabric:** Standby (Requires Fabric workspace capacity assignment)

---

## 4. Google Cloud Independence

Google Cloud remains an independent top-level provider:
- **Connection ID:** `conn-gcp-prod`
- **Name:** Smart Expense GCP Production
- **Project ID:** `smart-expense-prod-8812`
- **Organization ID:** `organizations/44910293817`
- **Auth Method:** GCP Service Account (Read-Only JSON Key)
- **Integrations:** GCP Platform Core (Compute Engine, Cloud Storage, BigQuery Billing Export)

---

## 5. Add New Connection Redesign

The **Add New Cloud Account** modal in `ConnectCloudView.tsx` guides users through an ecosystem-first configuration:

1. **Step 1: Choose Cloud Ecosystem**
   - Microsoft Azure (ARM, Databricks, and Fabric)
   - Google Cloud (Compute, BigQuery, and Storage)
2. **Step 2: Account & Tenant Metadata**
   - Account Display Name
   - Subscription ID (or GCP Project ID)
   - Tenant ID (or GCP Organization ID)
3. **Step 3: Service Integrations Selection**
   - Toggles for Azure Resource Manager (default checked)
   - Toggle for Azure Databricks (optional workspace URL & token)
   - Toggle for Microsoft Fabric (optional workspace ID & capacity ID)
4. **Step 4: Strictly Read-Only Credentials**
   - Azure CLI / Azure Service Principal (Client Secret)
   - Strict validation feedback preventing write permission usage

