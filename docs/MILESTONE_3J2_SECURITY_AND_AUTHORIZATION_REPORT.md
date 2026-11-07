# Milestone 3J.2 — Security & Authorization Report
## Cryptographic Token Integrity, RBAC Governance & Replay Defense

| Parameter | Specification |
| :--- | :--- |
| **System** | Databricks FinOps Command Center |
| **Security Layer** | Multi-Tier Authorization & Execution Gate |
| **Cryptographic Scheme** | HMAC-SHA256 (32-character hex signature truncation) |
| **Persistence Engine** | PostgreSQL 16 `billing_approval_tokens` |
| **Audience** | Security Officers, FinOps Administrators, Platform Architects |

---

## 1. Role-Based Access Control (RBAC) Specification

To comply with enterprise security principles, execution tokens authorizing live queries against Databricks System Tables can only be minted by authorized principals.

### 1.1 Authorized Roles Matrix

| Role Name | Authority Level | Can Mint Tokens? | Can Execute Live Query? | Justification |
| :--- | :--- | :--- | :--- | :--- |
| `FinOpsAdministrator` | FinOps Operations Lead | **YES** | **YES** | Designated authority over financial telemetry and cloud spend. |
| `Admin` | System Administrator | **YES** | **YES** | Full platform administrative oversight. |
| `PlatformAdministrator` | Infrastructure Engineer | **YES** | **YES** | Responsible for cloud infrastructure and compute operations. |
| `FinOpsAnalyst` | Spend Analyst | NO | NO | Read-only reporting access; cannot trigger live compute. |
| `Developer` | Application Engineer | NO | NO | Cannot authorize cloud spend or warehouse resume. |
| `Viewer` | General Stakeholder | NO | NO | Visual dashboard access only. |

### 1.2 Enforcement Implementation
RBAC validation occurs synchronously at the beginning of `DatabricksSqlService.issue_approval_token`:
```python
roles = approver_roles if approver_roles is not None else ["FinOpsAdministrator"]
if not any(r in self.ALLOWED_APPROVER_ROLES for r in roles):
    raise PermissionError(
        f"Approver '{approver_sub}' with roles {roles} is not authorized to issue approval tokens. "
        f"Requires one of: {sorted(self.ALLOWED_APPROVER_ROLES)}"
    )
```
API endpoint `POST /api/v1/finops/ingestion/approval-token` maps any `PermissionError` to an HTTP `403 Forbidden` response.

---

## 2. Cryptographic Token Structure & Signing Protocol

### 2.1 Token Payload Format
Approval tokens are composed of 7 colon-separated segments:
```
<warehouse_id>:<query_hash>:<start_date>:<end_date>:<nonce>:<expiry_timestamp>:<hmac_signature>
```

| Segment | Type | Description | Security Purpose |
| :--- | :--- | :--- | :--- |
| `warehouse_id` | String | Target SQL Warehouse ID e.g. `05ed10a52697a344` | Binds execution strictly to authorized compute. |
| `query_hash` | SHA-256 Hex | SHA-256 digest of exact SQL statement | Prevents query modification or parameter tampering. |
| `start_date` | Date String | Scope window start date `YYYY-MM-DD` | Enforces temporal bounds on data extraction. |
| `end_date` | Date String | Scope window end date `YYYY-MM-DD` | Enforces temporal bounds on data extraction. |
| `nonce` | 8-char Hex | Cryptographically generated random string | Ensures token uniqueness even with identical queries. |
| `expiry_timestamp`| Epoch Seconds| Wall-clock timestamp (typically `now + 300s`) | Limits exposure window to a maximum of 5 minutes. |
| `hmac_signature` | 32-char Hex | HMAC-SHA256 signature across segments 1-6 | Verifies authenticity and server issuance. |

### 2.2 Key Ring & Rotation Management
Key resolution supports both active signing secrets and zero-downtime key rotation:
1. Primary secret: retrieved from `settings.finops_signing_secret`.
2. Application salt fallback: deterministic SHA-256 salt derived from isolated application configuration.
3. Legacy fallback: rotated secondary key evaluated during verification to permit seamless key rotation without invalidating in-flight requests.
4. Constant-time comparison: signatures are verified using `hmac.compare_digest` to prevent side-channel timing attacks.

---

## 3. Durable Database Persistence & Anti-Replay Architecture

### 3.1 Persistence Model
Tokens are persisted in the `billing_approval_tokens` table in PostgreSQL:

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key | Entity identifier. |
| `token_id` | String(128) | Unique, Index | Unique token ID `tok-<nonce>-<sig[:16]>`. |
| `approver_sub` | String(256) | Not Null | Subject ID / User Principal of the approver. |
| `approver_roles` | JSONB | Not Null | List of verified roles held at issuance time. |
| `workspace_id` | String(64) | Not Null, Index | Databricks Workspace ID. |
| `warehouse_id` | String(64) | Not Null, Index | Target SQL Warehouse ID. |
| `query_hash` | String(64) | Not Null | SHA-256 hash of certified SQL query. |
| `date_start` | String(32) | Nullable | Bounded start date. |
| `date_end` | String(32) | Nullable | Bounded end date. |
| `allowed_tables` | JSONB | Not Null | Snapshot of permitted system tables. |
| `requested_operation` | String(128) | Not Null | Operation tag `READ_ONLY_SYSTEM_TABLES_SELECT`. |
| `nonce` | String(64) | Not Null | Nonce string. |
| `issued_at` | Timestamptz | Not Null | Generation timestamp. |
| `expires_at` | Timestamptz | Not Null | Expiry timestamp. |
| `consumed_at` | Timestamptz | Nullable | Recorded at moment of query execution. |
| `is_consumed` | Boolean | Not Null, Index | False initially; True once consumed. |
| `approval_purpose` | String(256) | Not Null | Audit trail justification string. |

### 3.2 Dual-Layer Anti-Replay Defense
To defend against replay attacks across distributed workers and server restarts:
1. **In-Memory Fast Layer (`_consumed_tokens`)**: Tracks tokens consumed within the current worker process to reject immediate replays without database roundtrips.
2. **Durable Database Layer (`billing_approval_tokens`)**: When a token is presented, the verification engine queries `billing_approval_tokens` by `token_id`. If `is_consumed == True`, the token is immediately rejected as an attempted replay.
3. **Atomic Consumption**: When execution begins, `consume_approval_token` sets `is_consumed = True` and records `consumed_at = datetime.now(UTC)` in an atomic transaction.

---

## 4. Secret & Credential Scrubbing

1. **Repr / String Masking**: `DatabricksSqlService.__repr__` masks client secrets to `[REDACTED]`.
2. **Error Message Scrubbing**: `auth_service.scrub_sensitive` intercepts all exceptions before they reach logs or API responses, scrubbing tokens, bearer headers, client secrets, and sensitive query strings.
3. **CLI Output Protection**: `startup.bat` never prints tokens, access keys, or bearer tokens to stdout.

