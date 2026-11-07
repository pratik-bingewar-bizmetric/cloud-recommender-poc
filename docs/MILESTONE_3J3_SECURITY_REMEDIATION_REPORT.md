# Milestone 3J.3: Security Remediation Report
## Comprehensive Security Audit, Vulnerability Elimination & Fail-Closed Guardrails

### 1. Scope & Security Threat Modeling

The security model of the Databricks FinOps Command Center governs read-only billing queries against Azure Databricks System Tables (`system.billing.usage`, `system.billing.list_prices`). Because live System Tables queries require waking stopped SQL warehouses or incurring serverless DBU charges, the platform enforces three independent security boundaries:
1. **Authentication & Identity Boundary**: Who is requesting authorization?
2. **Cryptographic Signing Boundary**: Has the query, target warehouse, and scope been signed by an authorized server key?
3. **Execution & Consumption Boundary**: Is the token single-use, unexpired, and atomically consumed before any live driver statement execution?

---

### 2. Forensic Vulnerability Analysis & Remediations

#### Vulnerability SEC-3J3-01: Client Privilege Escalation in Token Issuance
- **Severity**: High (CVSS 8.4)
- **Previous Implementation**: `BillingApprovalTokenRequest` accepted optional `approver_sub` and `approver_roles` parameters from the HTTP request body, defaulting to `["FinOpsAdministrator"]` if omitted.
- **Attack Vector**: Any caller (including an unauthenticated caller or a user with `Viewer` role) could POST a JSON payload specifying `{"approver_roles": ["FinOpsAdministrator"]}` and mint a valid HMAC authorization token.
- **Remediation**:
  1. Updated `BillingApprovalTokenRequest` schema to ignore/deprecate client-supplied role claims.
  2. Integrated FastAPI `current_user: AuthenticatedUser = Depends(get_current_user)` in `/api/v1/finops/ingestion/approval-token`.
  3. Server validates that `current_user.is_authenticated` is True (returning HTTP 401 if missing).
  4. Server validates that `current_user.roles` intersects with `{"Admin", "FinOpsAdministrator", "PlatformAdministrator"}` (returning HTTP 403 if unauthorized).
  5. The token's subject and role claims are populated strictly from `current_user.sub` / `current_user.preferred_username` and `current_user.roles`.

#### Vulnerability SEC-3J3-02: Predictable HMAC Salt Fallback
- **Severity**: High (CVSS 7.5)
- **Previous Implementation**: If `settings.finops_signing_secret` was empty or None, `_get_signing_keys()` generated an HMAC secret using `hashlib.sha256(f"{app_name}:finops-canonical-hmac-salt-2026")`.
- **Attack Vector**: An attacker with knowledge of the open-source or repository application name could independently compute the HMAC signature for arbitrary SQL statements without needing the production secret.
- **Remediation**:
  1. Removed the fallback salt entirely.
  2. Implemented strict fail-closed behavior: if `settings.finops_signing_secret` is unset or empty, `_get_signing_keys()` raises a `RuntimeError("Cryptographic signing secret 'finops_signing_secret' is not configured. Token issuance is disabled to enforce fail-closed security.")`.
  3. Added explicit setting `finops_signing_kid: str = "k1-2026"` and `finops_verification_keys: str | None = None` for seamless key rotation.

#### Vulnerability SEC-3J3-03: Partial Scope Authorization Binding
- **Severity**: Medium (CVSS 6.1)
- **Previous Implementation**: Tokens were serialized as 7-part strings (`wh:qhash:start:end:nonce:exp:sig`). Workspace ID, bounded `max_rows`, key ID, and authorization purpose were not cryptographically bound.
- **Attack Vector**: A token issued for a small exploratory test query could be reused across different workspaces, or applied to queries returning millions of rows, circumventing FinOps billing safety limits.
- **Remediation**:
  1. Implemented a 15-parameter canonical payload structure serialized as sorted JSON (`sort_keys=True, separators=(",", ":")`).
  2. Bound parameters:
     - `token_id`: Unique identifier (`tok-{nonce[:12]}-{qhash[:12]}`)
     - `nonce`: Cryptographically secure 32-character hex string (`secrets.token_hex(16)`)
     - `approver_sub`: Server-verified user identity
     - `approver_roles`: Server-verified role assignments
     - `workspace_id`: Databricks workspace ID (`642006393507276`)
     - `warehouse_id`: Databricks SQL warehouse ID (`05ed10a52697a344`)
     - `query_hash`: SHA-256 digest of exact query string
     - `requested_operation`: `"READ_ONLY_SYSTEM_TABLES_SELECT"`
     - `allowed_tables`: `["system.billing.list_prices", "system.billing.usage"]`
     - `date_start`: ISO date scope (`2026-10-01`)
     - `date_end`: ISO date scope (`2026-11-04`)
     - `max_rows`: Bounded row limit (default 1000, max 50000)
     - `issued_at`: ISO 8601 UTC timestamp
     - `expires_at`: ISO 8601 UTC timestamp
     - `kid`: Key identifier (`k1-2026`)
     - `approval_purpose`: Explicit operational justification
  3. Token format: `v2:<kid>:<base64url_canonical_json>:<hmac_sha256_hex>`.
  4. Any modification to date bounds, row limit, warehouse, or query invalidates the signature.

#### Vulnerability SEC-3J3-04: Concurrency Race Condition in Token Replay Prevention
- **Severity**: Medium (CVSS 6.8)
- **Previous Implementation**: Token consumption verified `is_consumed == False` via a `SELECT` statement and then issued an `UPDATE`. Under concurrent requests, two threads could execute the `SELECT` simultaneously before either committed.
- **Remediation**:
  1. Replaced check-then-act with an atomic conditional SQL update:
     ```python
     stmt = (
         update(BillingApprovalTokenModel)
         .where(
             BillingApprovalTokenModel.token_id == token_id,
             BillingApprovalTokenModel.is_consumed == False,
         )
         .values(is_consumed=True, consumed_at=datetime.now(UTC))
         .returning(BillingApprovalTokenModel.id)
     )
     res = session.execute(stmt)
     if res.scalar_one_or_none() is None:
         # Token was already consumed or nonexistent; rollback and reject
         return False
     ```
  2. Multi-threaded stress testing (`test_concurrent_token_consumption`) confirmed that with 5 concurrent threads, exactly 1 thread succeeds (returning `True`) while the other 4 are atomically rejected (returning `False`).

---

### 3. Security Verification Matrix

| Test Function | Security Property Validated | Result |
| :--- | :--- | :--- |
| `test_rbac_server_derived_identity_authorized_roles` | Admin, FinOpsAdministrator, PlatformAdministrator authorized | **PASSED** |
| `test_rbac_unauthenticated_and_unauthorized_rejections` | 401 for anonymous, 403 for Viewer/Developer/FinOpsAnalyst | **PASSED** |
| `test_anti_spoofing_client_payload_ignored` | Client role-injection attempt in request body strictly ignored | **PASSED** |
| `test_missing_signing_key_fails_closed` | Missing `finops_signing_secret` throws `RuntimeError` | **PASSED** |
| `test_key_rotation_verification` | Active `kid` verifies; unknown or tampered `kid` fails | **PASSED** |
| `test_canonical_payload_tamper_rejection` | Tampering with query, warehouse, dates, or row limit fails | **PASSED** |
| `test_atomic_token_consumption_and_replay_prevention` | Database enforces single-use across restarts | **PASSED** |
| `test_concurrent_token_consumption` | Atomic conditional update allows exactly 1 of 5 concurrent callers | **PASSED** |

