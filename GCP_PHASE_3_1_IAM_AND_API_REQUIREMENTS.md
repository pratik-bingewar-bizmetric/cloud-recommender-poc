# GCP Phase 3.1 — IAM Permissions & API Requirements

> **Document Status:** Complete & Live Verified  
> **Date:** 2026-11-23  
> **Repository:** `cloud-recommender-poc`  
> **Target GCP Project:** `cloud-recommender-pricing-dev` (`963778958698`)  
> **Service Account Principal:** `finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com`  

---

## 1. Executive Summary

This document establishes the verified IAM permission baseline and API enablement requirements for the GCP integration within the Bizmetric FinOps Platform.

A live cryptographic audit of the target project's IAM policy via `cloudresourcemanager.googleapis.com:getIamPolicy` confirmed that **the Service Account already possesses all necessary read-only Viewer roles on `cloud-recommender-pricing-dev`**. 

Earlier reports of `PERMISSION_DENIED` were caused by an OAuth2 token scope mismatch (`cloud-platform.read-only` vs canonical `cloud-platform`), which has been resolved in the codebase. With the scope update, **7 out of 8 services now succeed with HTTP 200**, confirming that no further IAM changes are required on the existing project for Phase 3.1.

This guide provides the definitive reference for administrators onboarding additional GCP projects or configuring custom least-privilege roles.

---

## 2. Live IAM State on `cloud-recommender-pricing-dev`

A direct API call to `POST https://cloudresourcemanager.googleapis.com/v3/projects/cloud-recommender-pricing-dev:getIamPolicy` returned the following live role bindings for `serviceAccount:finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com`:

| Role Name | Role Description | Status |
| :--- | :--- | :---: |
| `roles/browser` | Read access to browse project hierarchy and resources | **ACTIVE** |
| `roles/cloudasset.viewer` | Read-only access to Cloud Asset Inventory search APIs | **ACTIVE** |
| `roles/cloudsql.viewer` | Read-only access to Cloud SQL instance metadata | **ACTIVE** |
| `roles/compute.viewer` | Read-only access to Compute Engine VM and disk metadata | **ACTIVE** |
| `roles/monitoring.viewer` | Read-only access to Cloud Monitoring metrics and descriptors | **ACTIVE** |
| `roles/recommender.viewer` | Read-only access to Cloud Recommender cost recommendations | **ACTIVE** |
| `roles/serviceusage.serviceUsageConsumer` | Permission to consume enabled APIs in the project | **ACTIVE** |
| `roles/serviceusage.serviceUsageViewer` | Permission to inspect enabled and disabled APIs | **ACTIVE** |
| `roles/storage.viewer` | Read-only access to Cloud Storage bucket metadata | **ACTIVE** |

---

## 3. Architectural Clarification: OAuth2 Scopes vs Cloud IAM

### The Root Cause of Prior 403 Errors
In Google Cloud architecture, authorization is governed by two independent layers:
1. **OAuth2 Scopes:** Defined during token issuance at `https://oauth2.googleapis.com/token`.
2. **Cloud IAM Permissions:** Defined by role bindings in Cloud Resource Manager.

Google's API Gateway enforces that an access token must have sufficient OAuth scopes *before* evaluating Cloud IAM permissions:
- When the backend requested `https://www.googleapis.com/auth/cloud-platform.read-only`, APIs such as Cloud Asset Inventory (`cloudasset.googleapis.com`), Cloud SQL (`sqladmin.googleapis.com`), and Cloud Monitoring (`monitoring.googleapis.com`) rejected the calls at the gateway level with:
  ```json
  {
    "error": {
      "code": 403,
      "message": "Request had insufficient authentication scopes.",
      "status": "PERMISSION_DENIED",
      "details": [{ "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT" }]
    }
  }
  ```
- **The Solution:** For automated Service Account credentials, Google recommends the canonical scope `https://www.googleapis.com/auth/cloud-platform`. Least-privilege security is strictly enforced at the IAM layer by granting read-only roles (`roles/*.viewer`). The Service Account cannot execute mutations because it has zero write permissions in IAM.

---

## 4. Enabled vs Disabled Google Cloud APIs

A live audit of project `cloud-recommender-pricing-dev` via `serviceusage.googleapis.com/v1/projects/.../services?filter=state:ENABLED` revealed **30 enabled Google Cloud APIs**:

### 4.1 Verified Enabled APIs (Live & Operational)
1. `analyticshub.googleapis.com` (Analytics Hub)
2. `apptopology.googleapis.com` (Application Topology)
3. `backupdr.googleapis.com` (Backup and DR)
4. `bigquery.googleapis.com` (BigQuery API — Ready for billing export)
5. `bigqueryconnection.googleapis.com`
6. `bigquerydatapolicy.googleapis.com`
7. `bigquerydatatransfer.googleapis.com`
8. `bigquerymigration.googleapis.com`
9. `bigqueryreservation.googleapis.com`
10. `bigquerystorage.googleapis.com`
11. `cloudapis.googleapis.com`
12. `cloudasset.googleapis.com` (**Cloud Asset Inventory — Operational**)
13. `cloudbilling.googleapis.com` (**Cloud Billing API — Operational**)
14. `cloudresourcemanager.googleapis.com` (**Cloud Resource Manager — Operational**)
15. `cloudtrace.googleapis.com`
16. `dataform.googleapis.com`
17. `dataplex.googleapis.com`
18. `datastore.googleapis.com`
19. `logging.googleapis.com` (Cloud Logging)
20. `monitoring.googleapis.com` (**Cloud Monitoring — Operational**)
21. `recommender.googleapis.com` (**Cloud Recommender — Operational**)
22. `servicemanagement.googleapis.com`
23. `servicenetworking.googleapis.com`
24. `serviceusage.googleapis.com` (**Service Usage — Operational**)
25. `sql-component.googleapis.com`
26. `sqladmin.googleapis.com` (**Cloud SQL Admin — Operational**)
27. `storage-api.googleapis.com`
28. `storage-component.googleapis.com`
29. `storage.googleapis.com` (**Cloud Storage — Operational**)
30. `telemetry.googleapis.com`

### 4.2 Disabled API: Compute Engine (`compute.googleapis.com`)
- **Status:** **DISABLED (DEFERRED)**
- **Diagnostic Message:** `"Compute Engine API has not been used in project cloud-recommender-pricing-dev before or it is disabled."`
- **Cause:** Google Cloud prohibits enabling the Compute Engine API on projects without an active linked billing account.
- **Handling:** Cleanly classified as `GcpServiceConnectivityState.DEFERRED` without throwing application errors or failing the overall connection.

---

## 5. Administrator Action Checklist for Onboarding Projects

When connecting a new GCP Project or Organization to the FinOps Platform, an authorized **Google Cloud Project Owner or IAM Administrator** should execute the following steps:

### Step 1: Enable Core APIs
In the target project, execute the following Google Cloud CLI command (or enable via GCP Console &rarr; APIs & Services):
```bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  cloudasset.googleapis.com \
  storage.googleapis.com \
  sqladmin.googleapis.com \
  monitoring.googleapis.com \
  recommender.googleapis.com \
  bigquery.googleapis.com
```
*(Note: Do not enable `compute.googleapis.com` unless an active billing account is linked to the project).*

### Step 2: Grant Read-Only Predefined IAM Roles
Assign the minimum set of predefined Viewer roles to the Service Account:
```bash
SA_EMAIL="finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com"
PROJECT_ID="<TARGET_PROJECT_ID>"

for ROLE in \
  roles/browser \
  roles/cloudasset.viewer \
  roles/storage.viewer \
  roles/cloudsql.viewer \
  roles/monitoring.viewer \
  roles/recommender.viewer \
  roles/serviceusage.serviceUsageViewer \
  roles/serviceusage.serviceUsageConsumer
do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE" \
    --condition=None
done
```

### Step 3: Granular Permissions Reference (Custom Role Alternative)
For enterprise organizations requiring a single, custom least-privilege role rather than multiple predefined roles, create custom role `FinOpsReadOnlyViewer` with the following explicit permissions:

| Service Area | Granular Required Permissions |
| :--- | :--- |
| **Resource Manager** | `resourcemanager.projects.get`<br>`resourcemanager.projects.list` |
| **Service Usage** | `serviceusage.services.get`<br>`serviceusage.services.list` |
| **Asset Inventory** | `cloudasset.assets.searchAllResources`<br>`cloudasset.assets.searchAllIamPolicies` |
| **Cloud Storage** | `storage.buckets.get`<br>`storage.buckets.list` |
| **Cloud SQL** | `cloudsql.instances.get`<br>`cloudsql.instances.list` |
| **Compute Engine** *(when billed)* | `compute.instances.get`<br>`compute.instances.list`<br>`compute.disks.list` |
| **Cloud Monitoring** | `monitoring.metricDescriptors.get`<br>`monitoring.metricDescriptors.list`<br>`monitoring.timeSeries.list` |
| **Cloud Recommender** | `recommender.computeInstanceIdleResourceRecommendations.get`<br>`recommender.computeInstanceIdleResourceRecommendations.list` |

---

## 6. Zero-Execution & Safety Verification

1. **Strictly Read-Only:** All calls executed by `cloud-recommender-poc` use HTTP `GET` requests (with the exception of `POST :searchAllResources` which is Google's read-only search convention).
2. **No Mutating Permissions:** None of the granted roles (`roles/*.viewer`) have permissions to create, update, delete, reboot, or modify any cloud resource.
3. **Billing Invariant:** The Service Account possesses zero billing permissions (`roles/billing.admin`, `roles/billing.user`), ensuring it is mathematically impossible for the platform to link accounts or incur charges.

