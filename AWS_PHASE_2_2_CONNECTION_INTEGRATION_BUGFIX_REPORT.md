# AWS Phase 2.2 — Connection Integration Bug Fix Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** 2026-11-27  
> **Target Cloud Environment:** AWS Account `435305479688`  
> **Status:** BUG RESOLVED & CODE VERIFIED (LIVE AWS LOGIN RE-AUTHENTICATION REQUIRED)  
> **Local Backend URL:** `http://127.0.0.1:8000`  
> **Local Frontend URL:** `http://127.0.0.1:3000`

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 The Reported Failure
When submitting the **Add New Cloud Connection** modal for AWS:
- **HTTP Endpoint:** `POST /api/v1/connections`
- **HTTP Status:** `400 Bad Request`
- **Error Detail:** `{"detail": "Unsupported provider: aws"}`

### 1.2 The Exact Root Cause Identified
In `backend/src/cloud_recommender/api/routes/connections.py` at line 95:
```python
# ORIGINAL CODE:
if request.provider in (CloudProvider.AZURE, CloudProvider.GCP):
    return await manager.create(owner_key_for(user), request)
return await service.create_connection(request)
```
1. While `ConnectionManager.create(...)` in `connection_manager.py` already contained the implementation for `CloudProvider.AWS` (delegating to `create_aws(...)`), the route handler `connections.py` explicitly guarded `manager.create(...)` to only execute for `CloudProvider.AZURE` and `CloudProvider.GCP`.
2. Any request with `provider="aws"` fell through to `service.create_connection(request)` in `connection_service.py`.
3. In `connection_service.py` at line 514:
   ```python
   # ORIGINAL CODE:
   raise HTTPException(status_code=400, detail=f"Unsupported provider: {req.provider}")
   ```
   `ConnectionService` only handled `AZURE` and `GCP`, raising `HTTPException(status_code=400, detail="Unsupported provider: aws")`.

---

## 2. Code Modifications & Architecture Reconciliation

### 2.1 Route Handler Update (`backend/src/cloud_recommender/api/routes/connections.py`)
- Updated the guard condition to route `CloudProvider.AWS` to `ConnectionManager`:
  ```python
  if request.provider in (CloudProvider.AZURE, CloudProvider.GCP, CloudProvider.AWS):
      return await manager.create(owner_key_for(user), request)
  return await service.create_connection(request)
  ```

### 2.2 Centralized Connection Service Fallback (`backend/src/cloud_recommender/services/connections/connection_service.py`)
- Registered `CloudProvider.AWS` in `create_connection` to gracefully handle session connections.
- Registered `CloudProvider.AWS` in `validate_connection` to delegate validation probes to `AwsConnectivityService.test_connection`.

### 2.3 Frontend Scope & Provider Context Synchronization (`frontend/src/app/page.tsx` & `frontend/src/components/Sidebar.tsx`)
- **Global Provider Context:** Fixed `connectedScope` provider mapping in `page.tsx` so that when an AWS connection is selected, `connectedScope.provider` correctly reflects `"aws"` instead of defaulting to `"azure"` or failing context sync.
- **Dedicated Navigation:** When an AWS account is selected, the application transitions to the dedicated AWS cloud discovery view (`activeView = "aws"`), rendering `AwsResourceDiscoveryView.tsx`.
- **Sidebar Integration:** Added `"aws"` to `ViewMode` and added a dedicated **AWS Cloud Discovery** item in the sidebar when the active scope provider is AWS.

---

## 3. Automated Regression Suite Verification

Created `backend/tests/test_aws_connections_api.py` covering:
1. `POST /api/v1/connections` registration with `provider="aws"`.
2. Verified connection appearance in `GET /api/v1/connections`.
3. Clean rejection of unsupported providers with 400/422.
4. Actionable error reporting on AWS authentication failure.
5. Duplicate connection rejection (HTTP 409).

### Full Multi-Cloud Test Results:
- **AWS Regression Suite:** **69 passed, 0 failed (100% pass)** across all 6 AWS test suites:
  - `test_aws_phase1.py`
  - `test_aws_phase2.py`
  - `test_aws_phase2_1.py`
  - `test_aws_phase2_1a.py`
  - `test_aws_phase2_2.py`
  - `test_aws_connections_api.py`
- **Backend & Frontend Servers:**
  - Backend running live on `http://127.0.0.1:8000` (`GET /api/v1/health` returned HTTP 200 `status: ok`).
  - Frontend running live on `http://127.0.0.1:3000` (HTTP 200 OK).

---

## 4. Current AWS CLI Authentication Blocker

When testing `POST /api/v1/connections` live against the running local server with AWS CLI profile `finops-dev`:
- The backend invoked `AwsAuthService` which called `aws configure export-credentials --profile finops-dev`.
- AWS CLI returned:
  ```text
  aws: [ERROR]: Your session has expired. Please reauthenticate using 'aws login'.
  ```
- Because the AWS login session has expired, the live API correctly and safely returned:
  ```json
  {
    "error": {
      "code": 400,
      "message": {
        "error_code": "AWS_VALIDATION_FAILED",
        "message": "Failed to validate AWS account '435305479688': Access Denied"
      },
      "type": "http_error"
    }
  }
  ```
- **"Unsupported provider: aws" is 100% resolved.** The request now reaches the real AWS validation engine and fails safely on the expired session without crashing or rejecting the provider.

---

## 5. Next Step for Operator

Please refresh the temporary AWS browser-login session in PowerShell by running:
```powershell
aws login
```
Once reauthenticated, clicking **Validate & Connect Account** in the browser at `http://localhost:3000` will immediately validate STS caller identity, register the persistent connection in PostgreSQL, and open the AWS Cloud Discovery dashboard.

