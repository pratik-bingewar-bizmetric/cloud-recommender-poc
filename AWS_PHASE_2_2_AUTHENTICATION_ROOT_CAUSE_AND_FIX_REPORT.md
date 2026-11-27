# AWS Phase 2.2 — P0 Authentication Root Cause, Fix & Verification Report

**Document Version:** 1.0.0  
**Target AWS Account:** `435305479688`  
**Identity Verified:** `arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com`  
**Status:** COMPLETED & LIVE VERIFIED (HTTP 201 Created)  
**Date:** 2026-11-27  

---

## 1. Executive Summary

A P0 critical blocker prevented AWS cloud connection registration via `POST /api/v1/connections` in the FinOps application, returning:
```
Failed to validate AWS account '435305479688': Authentication Failed
```

Through live runtime inspection, tracing, and deterministic reproduction on the running services, **three compounding root causes** were identified and corrected. Following the fix:
1. `POST /api/v1/connections` successfully registered AWS account `435305479688` with **HTTP 201 Created**.
2. All **11 out of 11** AWS core services reported `SUCCESS` (overall status: `Connected`).
3. The connection is durably persisted in PostgreSQL and returned via `GET /api/v1/connections` and `GET /api/v1/aws/connections`.
4. Zero security compromises: corporate CA certificate trust (`aws-combined-ca.pem`) and Zscaler compatibility were strictly maintained, with zero `verify=False` and zero secret leaks.
5. All **69 automated AWS tests** across all 6 test suites passed cleanly with 0 failures and 0 warnings.

---

## 2. Root Cause Analysis

### Root Cause 1: Missing Corporate CA Bundle in Async HTTP Probes (Zscaler Interception)
- **Symptom:** Outbound HTTPS requests to AWS endpoints (notably `s3.amazonaws.com` and `sts.eu-north-1.amazonaws.com`) failed with `ConnectError` or SSL certificate verification errors.
- **Root Cause:** In enterprise environments with Zscaler SSL inspection, AWS CLI is configured with:
  ```ini
  [profile finops-dev]
  ca_bundle = C:\Users\pratik.bingewar\certificates\aws-combined-ca.pem
  ```
  However, Python `httpx.AsyncClient` in `AwsConnectivityService` was instantiated as `httpx.AsyncClient(transport=self.transport)` without the `verify` parameter set to the corporate CA bundle. As a result, Python defaulted to Mozilla's standard root CA store which does not trust corporate proxy intermediate certificates.

### Root Cause 2: STS GetCallerIdentity Response Format Mismatch (JSON vs XML)
- **Symptom:** Even when STS returned HTTP 200, `get_caller_identity` returned empty identity strings: `('', 'arn:aws:iam:::caller', '')`.
- **Root Cause:** In `auth_service.py`, `get_caller_identity` dispatched the HTTP request with:
  ```python
  headers = {
      "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
      "Accept": "application/json",
  }
  ```
  Because `Accept: application/json` was requested, AWS STS returned JSON (`{"GetCallerIdentityResponse": {"GetCallerIdentityResult": {"Account": "435305479688", ...}}}`).  
  However, the parser only executed regular expressions for XML tags:
  ```python
  acc_match = re.search(r"<Account>(\d{12})</Account>", text)
  arn_match = re.search(r"<Arn>([^<]+)</Arn>", text)
  ```
  Because the body was JSON, none of the regex matched, leaving `account_id` empty and ARN as `arn:aws:iam:::caller`.

### Root Cause 3: Dynamic Profile Resolution & Subprocess Environment Isolation
- **Symptom:** In restricted server processes, `aws configure export-credentials --profile finops-dev` failed with code 253: `The config profile (finops-dev) could not be found`.
- **Root Cause:** `parse_profile_credentials` invoked `subprocess.run` without explicitly passing `AWS_CONFIG_FILE`, `USERPROFILE`, or verifying the binary location `aws.exe`. When profile parsing failed to find static keys in `~/.aws/credentials`, it fell back to dummy example credentials (`AKIAIOSFODNN7EXAMPLE`), which failed against live AWS STS with `InvalidClientTokenId`.

---

## 3. Implemented Corrections

### 3.1 Corporate CA Trust & SSL Verification (`connectivity_service.py`)
Added deterministic resolution of the corporate CA bundle from profile config, environment variables (`AWS_CA_BUNDLE`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`), or default path (`C:\Users\pratik.bingewar\certificates\aws-combined-ca.pem`):
```python
def _get_client_kwargs(self, creds: AwsCredentials | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if self.transport is not None:
        kwargs["transport"] = self.transport
    ca_bundle = (
        getattr(creds, "ca_bundle", None)
        or os.environ.get("AWS_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
    )
    default_ca = Path(r"C:\Users\pratik.bingewar\certificates\aws-combined-ca.pem")
    if not ca_bundle and default_ca.is_file():
        ca_bundle = str(default_ca)
    if ca_bundle and Path(ca_bundle).is_file():
        kwargs["verify"] = ca_bundle
    return kwargs
```
Both `test_connection` and `discover_resources` now initialize clients with `**self._get_client_kwargs(creds)`.

### 3.2 Dual JSON/XML STS Response Parsing (`auth_service.py`)
Updated `get_caller_identity` to parse JSON responses when `application/json` is returned, with transparent XML fallback:
```python
# STS returns JSON when Accept: application/json is sent
try:
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type or resp.text.strip().startswith("{"):
        js = resp.json()
        caller_res = js.get("GetCallerIdentityResponse", {}).get("GetCallerIdentityResult", {})
        account_id = caller_res.get("Account") or account_id
        arn = caller_res.get("Arn") or arn
        user_id = caller_res.get("UserId") or user_id
except Exception:
    pass

# Fallback to XML regex parsing for standard/legacy endpoints and test fixtures
if not account_id or not arn or arn.endswith(":caller"):
    text = resp.text
    acc_match = re.search(r"<Account>(\d{12})</Account>", text)
    ...
```

### 3.3 Robust AWS CLI Profile Resolution (`auth_service.py`)
- Explicitly locates `aws.exe` via `shutil.which` and well-known installation paths (`%LOCALAPPDATA%\Programs\Amazon\AWSCLIV2\aws.exe`).
- Passes explicit environment variables (`AWS_CONFIG_FILE`, `USERPROFILE`) to `subprocess.run`.
- Extracts `ca_bundle` from `~/.aws/config` and passes it through `AwsCredentials`.

---

## 4. Live Verification Evidence

### 4.1 Direct Service Connectivity Probe
Invoking `AwsConnectivityService().test_connection` against live AWS account `435305479688` using profile `finops-dev`:
```
overall_status: Connected
success: True
arn: arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com
Services:
  sts: SUCCESS - STS GetCallerIdentity succeeded; identity verified.
  iam: SUCCESS - IAM query succeeded; 18 roles discovered.
  ec2: SUCCESS - EC2 query succeeded; 34 regions discovered.
  s3: SUCCESS - S3 query succeeded; 23 buckets listed.
  lambda: SUCCESS - Lambda query succeeded; 0 functions discovered in eu-north-1.
  rds: SUCCESS - RDS query succeeded; 0 database instances found.
  cloudwatch: SUCCESS - CloudWatch query succeeded; 181 metric descriptors sampled.
  cost_explorer: SUCCESS - AWS Cost Explorer is enabled and queryable.
  ecs: SUCCESS - ECS query succeeded; 0 clusters discovered.
  eks: SUCCESS - EKS query succeeded; 0 clusters discovered.
  pricing: SUCCESS - AWS Price List API is accessible; catalog queries supported.
```

### 4.2 Central Connection Creation (`POST /api/v1/connections`)
**Request:**
```http
POST /api/v1/connections HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "provider": "aws",
  "name": "Bizmetric AWS",
  "scope_id": "435305479688",
  "aws_auth_method": "profile",
  "aws_profile": "finops-dev",
  "aws_region": "eu-north-1"
}
```

**Response (HTTP 201 Created):**
```json
{
  "id": "061000b0-3641-4fb7-a3e7-5b26cb9fcdae",
  "name": "Bizmetric AWS",
  "provider": "aws",
  "scope_id": "435305479688",
  "display_name": "Bizmetric AWS (435305479688)",
  "tenant_or_org_id": "eu-north-1",
  "auth_method": "profile",
  "status": "connected",
  "last_verified_at": "2026-11-27T08:10:33.412000Z",
  "is_live": true,
  "capabilities": [
    "identity_verification",
    "iam_security",
    "compute_instances",
    "object_storage",
    "serverless_compute",
    "relational_databases",
    "monitoring_metrics",
    "cost_explorer"
  ],
  "access_limitations": [
    "Strictly read-only access; credentials are stored encrypted."
  ],
  "ownership": "owned",
  "integrations": [
    {
      "integration": "sts",
      "state": "connected",
      "message": "STS GetCallerIdentity succeeded; identity verified.",
      "required_permission": "sts:GetCallerIdentity",
      "details": {
        "arn": "arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com",
        "user_id": "AIDAWKWR2PYEN3OX6JOAV",
        "account_id": "435305479688"
      }
    },
    {
      "integration": "s3",
      "state": "connected",
      "message": "S3 query succeeded; 23 buckets listed.",
      "required_permission": "s3:ListAllMyBuckets, s3:GetBucketLocation",
      "details": {
        "bucket_count": 23
      }
    },
    {
      "integration": "cost_explorer",
      "state": "connected",
      "message": "AWS Cost Explorer is enabled and queryable.",
      "required_permission": "ce:GetCostAndUsage",
      "details": {
        "status": "ENABLED"
      }
    }
  ],
  "warnings": []
}
```

### 4.3 Connection Listing Verification (`GET /api/v1/connections`)
```
Status code: 200
aws  |  Bizmetric AWS  |  435305479688  |  connected
azure  |  Azure subscription 1  |  f718c261-ab85-49fd-907e-99c022cc2aeb  |  ready_to_connect
gcp  |  cloud-recommender-pricing-dev  |  cloud-recommender-pricing-dev  |  ready_to_connect
```

---

## 5. Regression Suite Summary

All test suites executed against Python 3.12:
- `backend/tests/test_aws_phase1.py` (15/15 passed)
- `backend/tests/test_aws_phase2.py` (10/10 passed)
- `backend/tests/test_aws_phase2_1.py` (12/12 passed)
- `backend/tests/test_aws_phase2_1a.py` (21/21 passed)
- `backend/tests/test_aws_phase2_2.py` (8/8 passed)
- `backend/tests/test_aws_connections_api.py` (3/3 passed)
- **Total:** **69 passing tests, 0 failed, 0 warnings**
- `ruff check`: All checks passed.
- `ruff format --check`: 20 files already formatted.
- `mypy`: Success (0 issues found).

---

## 6. Final Status & Conclusion

The AWS Backend Authentication Failure on `POST /api/v1/connections` has been **completely resolved and verified live** across all application layers. The AWS cloud provider is fully integrated into the multi-cloud FinOps platform with 100% read-only least-privilege compliance.

