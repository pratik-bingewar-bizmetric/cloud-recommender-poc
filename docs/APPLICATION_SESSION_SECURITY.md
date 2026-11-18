# Application Session Security & Threat Model

**Document ID:** `SEC-SESS-001`  
**Status:** Approved & Enforced  
**Component:** Backend Core (`cloud_recommender.core.app_sessions`, `cloud_recommender.core.auth`)  
**Repository:** `cloud-recommender-poc`  
**Branch:** `feature/backend-security-hardening`

---

## 1. Overview & Security Objectives

This document establishes the security specifications, threat mitigations, and cryptographic controls governing application sessions within the FinOps Multi-Cloud Recommender Platform.

The core security objectives are:
1. **Zero Secret Persistence:** Sensitive customer cloud secrets (Service Principal client secrets) must never be retained, cached, or persisted on disk, database, or browser storage.
2. **Cryptographic Token Protection:** Application session tokens must be high-entropy and stored on the server exclusively in cryptographically hashed form (`SHA-256`).
3. **Multi-Tenant Memory Isolation:** State must be strictly partitioned by `owner_key` (`f"{tenant_id}:{account_id}"`) to prevent cross-tenant data leakage.
4. **Resilience Against Credential Stuffing & DoS:** All authentication entry points must be throttled with sliding window rate limiting.
5. **Strict Human Approval & Zero-Execution Policy:** All connected sessions operate under read-only privileges (`Reader`, `Cost Management Reader`, `Monitoring Reader`) with zero mutation capabilities.

---

## 2. Threat Modeling & Security Controls

| Threat Scenario | Potential Impact | Architecture Mitigation Control |
| :--- | :--- | :--- |
| **Server Memory Disclosure** | Attacker dumps server process memory to obtain active session credentials. | `AppSessionStore` stores only the `SHA-256` hash of session tokens. Plaintext tokens exist only on the client. |
| **Client Storage Infiltration** | XSS or unauthorized extension reads browser `localStorage` or `sessionStorage`. | Client secrets are never written to browser storage. Form fields are masked (`type="password"`) and cleared from state memory immediately upon submit. |
| **Credential Brute-Force / Oracle** | Attacker uses `/auth/connect` to validate stolen secrets against Azure. | IP / Tenant-Client sliding window rate limiter throttles connection attempts (default: 5 attempts/minute). |
| **Session Hijacking / Replay** | Stolen session token used after user logs out or session finishes. | Explicit revocation via `POST /api/v1/auth/logout` sets `revoked_at = now`. Fixed 8-hour TTL rejects expired tokens. |
| **Cross-Tenant Data Tampering** | User from Tenant A queries or mutates connections/resources of Tenant B. | Every protected API operation resolves `owner_key_for(user)`. Access to unowned connections immediately returns `404 Not Found`. |
| **Privilege Escalation** | Compromised session attempts to create, alter, or delete Azure resources. | Zero-Execution boundary: ARM client enforces read-only operations (`GET`, plus read-only Cost Management query `POST`). Any mutating verb triggers an immediate `PermissionError`. |

---

## 3. Cryptographic Token Design & Lifecycle

### 3.1 Token Generation
Session tokens are generated using cryptographically secure random bytes from Python's `secrets` module:
```python
raw_token = f"finops_sess_{secrets.token_urlsafe(32)}"
```
- **Prefix:** `finops_sess_` enables unambiguous token classification at the API gateway layer.
- **Entropy:** 32 URL-safe bytes provide $> 256$ bits of cryptographic entropy, preventing brute-force enumeration.

### 3.2 Token Hashing & Verification
When a session is created:
1. The backend calculates `token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()`.
2. The session record is indexed by `token_hash` in `_sessions_by_hash`.
3. The raw token is returned once in the `ServicePrincipalConnectResponse` payload and never logged.
4. When incoming requests arrive with `Authorization: Bearer finops_sess_<token>`, the backend hashes the incoming token and looks up the active session.
5. Constant-time comparison (`secrets.compare_digest`) is used during session ownership verification.

### 3.3 Session Expiration & Purging
- **TTL (Time-To-Live):** Configured via `default_ttl_seconds = 28800` (8 hours).
- **Activity Tracking:** Every authenticated request updates `session.last_used_at`.
- **Automatic Purge:** Expired sessions are lazily evicted during create and list operations via `_purge_expired_locked()`.
- **Revocation:** Explicit termination via `revoke_session(session_id)` records `revoked_at = datetime.now(UTC)`. Revoked tokens return `HTTP 401 Unauthorized` with error code `SESSION_REVOKED`.

---

## 4. Multi-Tenant Identity & Ownership Boundary

The platform enforces strict tenant isolation:

```
+-----------------------------------------------------------------------------------+
| Authenticated User Claims (Constructed from Active AppSession)                    |
|-----------------------------------------------------------------------------------|
| sub  : acc-e4b91012fa31 (Internal Account Identifier)                             |
| oid  : acc-e4b91012fa31                                                           |
| tid  : 72f988bf-86f1-41af-91ab-2d7cd011db47 (Microsoft Entra Tenant GUID)         |
| roles: ["FinOpsAdmin"]                                                            |
| scopes: ["access_as_user"]                                                        |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Derived Owner Key                                                                 |
| owner_key = f"{user.tid}:{user.oid}"                                              |
| e.g. "72f988bf-86f1-41af-91ab-2d7cd011db47:acc-e4b91012fa31"                     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Repository & Session Boundary                                                     |
| azure_session_store.get(connection_id, owner_key) -> 404 if mismatch              |
| connection_manager.list(owner_key)               -> Only caller's connections     |
+-----------------------------------------------------------------------------------+
```

---

## 5. Defense-in-Depth & Fail-Closed Policies

1. **Missing or Tampered Tokens:** Requests without an `Authorization` header fail closed with `HTTP 401 Unauthorized` (`MISSING_BEARER_TOKEN`).
2. **Expired Sessions:** Requests bearing expired session tokens fail closed with `HTTP 401 Unauthorized` (`SESSION_EXPIRED`).
3. **Revoked Sessions:** Terminated sessions fail closed with `HTTP 401 Unauthorized` (`SESSION_REVOKED`).
4. **Subscription Disabled:** If Azure reports a subscription is in `Disabled` state, session creation is refused with `HTTP 400 Bad Request` (`SUBSCRIPTION_DISABLED`).
5. **Database Unavailability:** If persistent connection storage is requested while PostgreSQL is unconfigured, the application returns `HTTP 503 Service Unavailable` (`DATABASE_UNAVAILABLE`) rather than risking unencrypted or ephemeral storage.

