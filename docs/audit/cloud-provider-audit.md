# FinOps & Infrastructure Intelligence Platform — Cloud Provider Audit

> **Status:** Phase 1 Evidence-Based Audit  
> **Repository:** `cloud-recommender-poc`  
> **Cloud Scopes:** Microsoft Azure & Google Cloud Platform (GCP)  
> **Evaluation Date:** October 2026  

---

## 1. Provider Readiness & Authentication Matrix

| Cloud Provider | Feature Area | Auth Mechanism | Required Read-Only IAM Role(s) | Operational Status | Live / Mock Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Microsoft Azure** | Subscription Discovery | Azure CLI (`az login`) / DefaultAzureCredential | `Reader` | **Verified Operational** | Live when authenticated; fallback to `sub-prod-enterprise-01` |
| **Microsoft Azure** | Resource Graph Inventory | ARM REST API / SDK | `Reader` | **Verified Operational** | Discovers VMs, Disks, App Services, VNets |
| **Microsoft Azure** | Telemetry & Health | Azure Monitor (`microsoft.insights`) | `Monitoring Reader` | **Verified Operational** | Live platform metrics; in-guest RAM requires AMA |
| **Microsoft Azure** | Retail Prices Catalog | Public HTTP API (No auth required) | None (Public REST Endpoint) | **Verified Operational** | Direct live queries to `prices.azure.com` with local JSON cache |
| **Google Cloud (GCP)** | Public Billing Catalog | `GCP_CLOUD_API_KEY` | None (Public Cloud Billing Catalog) | **Verified Operational** | Direct live queries to `cloudbilling.googleapis.com` |
| **Google Cloud (GCP)** | Project Discovery | OAuth2 Bearer Token / ADC / Service Account | `roles/browser` or `roles/resourcemanager.organizationViewer` | **Verified Operational** | Discovers live projects via `projects:search`; surfaces 403 if unassigned |
| **Google Cloud (GCP)** | Cloud Asset Inventory | Google Cloud Asset Inventory API v1 | `roles/cloudasset.viewer` | **Verified Operational** | Discovers 31 assets in `cloud-recommender-pricing-dev` |
| **Google Cloud (GCP)** | Cloud Monitoring / Telemetry| Cloud Monitoring API v3 | `roles/monitoring.viewer` | **Partially Operational** | Ops Agent required for VM telemetry; project contains 0 VMs |

---

## 2. GCP Resource Manager 403 Diagnosis & Least-Privilege IAM Roles

### 2.1 The Issue
When calling the Cloud Resource Manager API to discover active projects via `https://cloudresourcemanager.googleapis.com/v3/projects:search`, calls failed with HTTP 403 Forbidden:
```json
{
  "error": {
    "code": 403,
    "message": "The caller does not have permission",
    "status": "PERMISSION_DENIED"
  }
}
```

### 2.2 Root Cause Analysis
1. In Google Cloud IAM, `roles/resourcemanager.projectViewer` was an experimental or obsolete role string and is not a valid predefined role in current Google Cloud IAM documentation.
2. The Google Cloud Resource Manager v3 `projects:search` method requires the permission `resourcemanager.projects.get` or `resourcemanager.organizations.get`.
3. The correct, least-privilege predefined roles supported by Google Cloud IAM are:
   - **`roles/browser` (Browser):** Read access to browse the hierarchy for a project, folder, and organization.
   - **`roles/resourcemanager.organizationViewer`:** Organization Viewer for tenant-level visibility.
   - **`roles/cloudasset.viewer` (Cloud Asset Viewer):** Required to export and inspect assets via Cloud Asset Inventory.

### 2.3 Strict Separation of Authentication
The platform strictly enforces the architectural boundary between the public Cloud Billing Catalog API and private tenant discovery:
- **`GCP_CLOUD_API_KEY`:** Used exclusively for querying public pricing SKUs from Google's Cloud Billing Catalog. It is **never** sent to private Resource Manager or Asset Inventory endpoints.
- **`GCP_ACCESS_TOKEN` / ADC / Service Account:** Used exclusively for read-only project and asset queries.

---

## 3. GCP Inventory Classification & Truthful Scope Sizing

### 3.1 Breakdown of Discovered Assets in `cloud-recommender-pricing-dev`
When authenticated against the live GCP development project `cloud-recommender-pricing-dev`, Cloud Asset Inventory returned **31 distinct asset records**. An initial naive display counted these as 31 active infrastructure resources. 

A rigorous inspection of the underlying GCP resource types revealed:

| Resource Type | Discovered Count | Canonical Classification | Infrastructure Impact |
| :--- | :--- | :--- | :--- |
| `serviceusage.googleapis.com/Service` | 25 | `api_service` | Enabled Google APIs (e.g. Cloud Run API, Compute API, Billing API). $0.00 idle cost. |
| `apikeys.googleapis.com/Key` | 1 | `security_credential` | GCP Cloud API Key used for catalog pricing. $0.00 infrastructure cost. |
| `cloudresourcemanager.googleapis.com/Project` | 1 | `configuration_metadata` | Project container metadata. |
| `logging.googleapis.com/LogBucket` | 2 | `configuration_metadata` | Default `_Default` and `_Required` log storage buckets. |
| `logging.googleapis.com/LogSink` | 2 | `configuration_metadata` | Default Cloud Logging routing sinks. |
| `compute.googleapis.com/Instance` | **0** | `infrastructure_resource` | Zero Virtual Machines present in project. |
| `compute.googleapis.com/Disk` | **0** | `infrastructure_resource` | Zero Persistent Disks present in project. |
| `sqladmin.googleapis.com/Instance` | **0** | `infrastructure_resource` | Zero Cloud SQL databases present in project. |

### 3.2 UI Truthfulness & Classification Engine
To prevent misleading the user into believing that 31 billable servers were running, the backend categorization logic in [`gcp_inventory.py::_map_asset_type_to_canonical`](file:///backend/src/cloud_recommender/services/inventory/gcp_inventory.py#L356-L510) and the frontend inventory counter in [`SectionCloudScopeInventory.tsx`](file:///frontend/src/components/SectionCloudScopeInventory.tsx) were refined:
- Total discovered: **31 records**
- Breakdown shown: **0 Infrastructure · 25 Enabled APIs · 6 Configuration & Security Assets**
- The Overview dashboard reflects zero active compute instances, accurately presenting zero CPU consumption rather than synthesizing false load curves.

---

## 4. Azure Read-Only Scope & Architecture Alignment

Azure integration operates via Azure Resource Graph and ARM REST endpoints with three least-privilege read-only roles:
1. `Reader`: Read resource configurations, tags, and subscription hierarchy.
2. `Cost Management Reader`: Read billing budgets and cost management rollups.
3. `Monitoring Reader`: Read platform metrics (`microsoft.insights/metrics`) and resource health.

The platform complies 100% with the **Zero-Execution Policy**:
- No write actions (`Contributor`, `Owner`, `deployments/*`) are ever requested or utilized.
- All remediation advice in Cost & Waste presents read-only inspection commands (`az disk show`, `az vm show`).

