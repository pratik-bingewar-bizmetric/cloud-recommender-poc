# Simplified Authorization Design — Authenticated User + Connection Ownership

- **Status:** design / review only. **No code, configuration, `.env`, database or cloud change was made.**
- **Branch:** `feature/backend-security-hardening` (HEAD `902d220`, working tree uncommitted, all prior changes preserved).
- **Inputs:** `docs/SECURITY_REVIEW_REMEDIATION.md`, `docs/SECURITY_IMPLEMENTATION_REVIEW.md`, and a fresh read of the connection, configuration, ingestion, inventory, Databricks and FinOps code on this branch.
- **Goal:** a simple model (sign in → add Azure connection → validate → pick subscriptions → discover → see inventory, monitoring, FinOps data) with no enterprise RBAC, while keeping every authentication control.

---

## 0. Executive summary

1. **Authentication controls stay exactly as they are** (Entra JWT, issuer/audience/tenant/exp/nbf, approved client `azp`/`appid`, required scope, no dev auth in production, no anonymous access). Only *authorization after authentication* is simplified.
2. **Of the 14 write-gated operations, 12 can be opened to any authenticated user** (several with connection-ownership or attribution), and **2 must stay restricted**: `POST /finops/ingestion/run` (billing execution) and `POST /finops/ingestion/approval-token`. That reduces six roles to **one** (`FinOpsAdmin`).
3. **Critical finding: "connection ownership" does not exist yet and cannot be enforced by a route-level change alone.** In the current code:
   - user-created connections live in a **process-wide in-memory dict** (`ConnectionService._custom_connections`, a class attribute): no owner, shared by every user, lost on restart, invisible to other replicas;
   - the **service-principal secret a user submits is validated against Entra and then discarded**; nothing stores or encrypts it, and nothing else in the backend reads `_custom_connections`;
   - all inventory, monitoring and cost calls use **one server-level Azure identity** (configured service principal or `az login`) and **one server-level Databricks service principal**. A user-created connection therefore changes nothing about what data is fetched, and any authenticated user can request **any subscription ID the server identity can read** (confused-deputy / IDOR).
4. Therefore the simplified model has two parts: **(a)** a small authorization change (easy, low risk), and **(b)** a **new persistent, encrypted, owner-bound connection layer** that the discovery and monitoring paths must actually use (a real feature with a DB migration). The requirement "encrypted credential storage" is **not met today** because nothing is stored.
5. Decisions needed from you are listed in §11. Recommended defaults are given for each.

---

## 1. Proposed authorization model

### 1.1 Principals and layers

Unchanged layers 1–3 (authentication, approved client, required scope). The previous layer 4 ("write role for every non-GET") is **replaced** by an operation class:

| Class | Name | Who may call | How enforced |
|---|---|---|---|
| **P** | Public | anyone | explicit frozen allow-list (health, catalog, `/`) |
| **U** | Authenticated-user operation | any caller passing layers 1–3 | default for reads and read-only/low-impact actions |
| **O** | Owner operation | the connection's owner (or any user for *organization* connections, read/refresh only) | ownership dependency, **404 for other users' connections** |
| **R** | Restricted high-impact | holders of the single role `FinOpsAdmin` | role check (kept), human approval token where it exists today |

Default for a **new** non-GET route stays **secure by default = R**; moving it to U or O is a deliberate edit guarded by tests (same mechanism as today's allow-list).

### 1.2 Two kinds of connections (needed to avoid hiding data)

| Kind | Examples | Visible to | Mutable by |
|---|---|---|---|
| **Owned** (new) | Azure connection the user created with their own service principal | its owner only | its owner only |
| **Organization** (today's behaviour) | subscriptions visible to the server's identity; Databricks workspaces from the server registry | every authenticated user (read/discover) | nobody through the API (configuration/ops only) |

This keeps current capabilities ("do not hide available cloud data") while giving users private connections.

### 1.3 Ownership key

`(tid, oid)` from the validated token (stable per user within a tenant; for app tokens `oid` is the service principal). Never `sub` (pairwise per app) and never a client-supplied field. A token without `oid` cannot create connections.

### 1.4 Roles after simplification

| Role | Today | Proposed |
|---|---|---|
| `Admin`, `FinOpsAdministrator`, `PlatformAdministrator` | write set / approval-token set | **remove** (aliases of the same privilege) |
| `FinOpsAdmin` | write set | **keep, only role**: restricted operations (R) |
| `Reader`, `FinOpsReader` | alternative to the delegated scope (for application tokens) | **remove**; API access = delegated scope `access_as_user` only. Consequence: application-only (daemon) tokens get 403; add a single app role later only if a daemon client appears |
| Dev identity roles (`DEV_AUTH_ROLES`) | default `Reader` | dev identity is an ordinary authenticated user with fixed `oid`; optionally add `FinOpsAdmin` for testing restricted routes |

Entra setup shrinks to: one API scope (`access_as_user`), approved client IDs, one optional app role (`FinOpsAdmin`).

---

## 2. Review of the 14 write-gated operations

Classification: **U** user, **O** owner, **R** restricted. "Role needed?" answers whether ownership/authentication alone is sufficient.

| # | Operation | Today | Class | Role needed? | Rationale and required controls |
|---|---|---|---|---|---|
| 1 | `POST /connections` | write role | **O (create)** | **No** | Caller becomes owner. Needs: GUID validation of tenant/client/subscription IDs, per-user quota (e.g. 10), **per-user rate limit** (the endpoint is an oracle that tests arbitrary SP credentials against Entra from the server), encrypted storage, audit entry without secrets |
| 2 | `POST /connections/validate` | write role | **O** | **No** | Must take and verify a `connection_id` the caller owns (or an organization connection). Today it validates the *server identity* for any `provider`/`scope_id` |
| 3 | `POST /configuration` | write role | **O** | **No** | `connection_id` in body must be owned/organization. `created_by` is currently **client-supplied** (spoofable); derive from token |
| 4 | `POST /databricks/connections/{id}/test` | write role | **U** on organization connection | **No** | Read-only identity/connectivity check on the shared registry; not user-owned. Add short per-user cooldown |
| 5 | `POST /databricks/connections/{id}/discovery/refresh` | write role | **U** on organization connection | **No** | REST discovery only, no SQL, no compute. Risk is load amplification on the shared service principal: enforce a per-connection minimum refresh interval (a background refresher already exists) |
| 6 | `POST /ingestion/{connection_id}/runs` | write role | **O** (owned) / **U** (organization, with cooldown) | **No** | Read-only extraction bounded to the saved scope, writes run records to the app DB. Existing conflict/readiness guards stay. Not billing execution |
| 7 | `POST /ingestion/runs/{run_id}/retry` | write role | **O** | **No** | Resolve run → connection → owner. Same guards as #6 |
| 8 | `POST /finops/ingestion/validate` | write role | **U** | **No** | Validates parameters/warehouse accessibility **without executing SQL** (docstring). Add a test that no SQL/warehouse start occurs |
| 9 | `POST /finops/ingestion/preview` | write role | **U** | **No** | "Preview … without starting the SQL warehouse". Same test requirement; limit parameter already bounded (≤ 1000) |
| 10 | `POST /finops/ingestion/run` | write role | **R** | **Yes, `FinOpsAdmin`** | Billing ingestion execution; already requires a signed approval token; AGENTS.md human-approval policy. Authentication is not sufficient |
| 11 | `POST /finops/ingestion/approval-token` | write role + approval set | **R** | **Yes, `FinOpsAdmin`** | Issues the credential that authorizes #10. Collapse `{Admin, FinOpsAdministrator, PlatformAdministrator}` to `{FinOpsAdmin}` |
| 12 | `POST /finops/optimization-advisor/{id}/action` | write role | **U + attribution** | **No (recommended)** | Records Approved/Deferred on an *advisory* recommendation; nothing is executed (zero-execution holds). Today the state is a **process-wide in-memory dict with no actor**; must record actor (`oid`/UPN) in the audit trail. Residual risk: shared state visible to everyone (see D4) |
| 13 | `POST /finops/anomalies/{id}/status` | write role | **U + attribution** | **No (recommended)** | Same as #12 |
| 14 | `POST /pricing/refresh` | write role | **U with global cooldown** (alt: **R**) | **No if throttled** | Refreshes the shared cache from the official public pricing API; data is public and deterministic, but it is shared mutable state and an outbound-call amplifier. Allow with a global minimum interval; keep **R** until the cooldown exists |

**Net:** roles remain required only for #10 and #11. Existing role checks are *not* dropped blindly: #1–#9, #12–#14 are replaced by stronger, narrower checks (ownership, quotas, cooldowns, attribution).

### 2.1 The 11 read-style POSTs (already class U, no role)

`analysis/requirements`, `architecture/generate`, `finops/forecast-budgets/simulate`, `inventory/azure/analyze`, `inventory/gcp/analyze`, `inventory/compare`, `monitoring/overview|resource|logs|token-economics`, `pricing/simulate`. Inventory and monitoring ones accept a subscription/project; they must additionally be **bound to the caller's accessible scope** (§3).

---

## 3. Route-by-route authorization matrix (target)

Legend: **P** public, **U** authenticated user, **O** owner (404 if not yours), **O\*** owner for owned connections / any user for organization connections, **R** `FinOpsAdmin`. All rows except **P** require layers 1–3.

| Group | Operations | Target |
|---|---|---|
| Health / catalog / root | `GET /`, `/health`, `/health/ready`, `/api/v1/health[/ready]`, `/api/v1/catalog/services[…]` | **P** |
| Connections | `GET /connections` (filtered: caller's owned + organization), `POST /connections` (create), `POST /connections/validate` | **O** (list filtered by owner; create = caller becomes owner) |
| Connections (**new**, required by the business flow) | `PATCH /connections/{id}` (rename/rotate secret), `DELETE /connections/{id}` | **O** (owned only; organization connections → 403) |
| Azure inventory | `GET /inventory/azure/subscriptions`, `…/{sub}/resource-groups`, `…/{sub}/resources`, `POST /inventory/azure/analyze`, `POST /inventory/compare`, `GET /inventory/gcp/projects`, `POST /inventory/gcp/analyze`, `GET /inventory/providers/status` | **O\*** : subscription/project must belong to a connection the caller may use; subscription list = union(own connections, organization) |
| Monitoring | `GET /monitoring/sources`, `POST /monitoring/overview|resource|logs|token-economics` | **O\*** (scope-bound) |
| Configuration | `GET /configuration/{connection_id}[/selected|/status|/workspaces]`, `GET /configuration/scopes/discover`, `POST /configuration` | **O\*** |
| Ingestion (scope-aware) | `GET /ingestion/{id}/readiness`, `GET /ingestion/{id}/runs`, `GET /ingestion/runs/{run_id}`, `POST /ingestion/{id}/runs`, `POST /ingestion/runs/{run_id}/retry` | **O\*** (run → connection → owner) |
| Databricks (organization registry) | all `GET /databricks/connections/**`, `POST …/test`, `POST …/discovery/refresh` | **U** (organization resources; existing registry/workspace validation retained; cooldown on POSTs) |
| FinOps reads | all `GET /finops/**` (overview, cost-explorer, cost-allocation, compute, AI economics, storage, network, optimization-advisor, forecast, anomaly, governance, showback, workload, reports, settings, billing/*, ingestion/status|runs, system-tables, query-history, kpis, ai-analysis) | **U** (`connection_id`/`workspace_id` validated against the server registry as today) |
| FinOps light writes | `POST /finops/optimization-advisor/{id}/action`, `POST /finops/anomalies/{id}/status`, `POST /finops/forecast-budgets/simulate`, `POST /finops/ingestion/validate`, `POST /finops/ingestion/preview` | **U** (actions carry actor attribution) |
| **FinOps billing execution** | `POST /finops/ingestion/run`, `POST /finops/ingestion/approval-token` | **R** (`FinOpsAdmin`; approval token still required for `run`) |
| Pricing | `POST /pricing/simulate` | **U**; `POST /pricing/refresh` | **U + global cooldown** (or **R** until implemented) |
| Analysis / architecture | `POST /analysis/requirements`, `POST /architecture/generate` | **U** |
| Any new non-GET route | — | **R by default** |
| API docs | `/docs`, `/redoc`, `/openapi.json` | development/testing only (404 in production), unchanged |

---

## 4. Connection ownership — implementation requirements

### 4.1 Persistence (replaces the in-memory dict)

New table `cloud_connections` (Alembic migration; **not** created now): `id` (UUID PK), `owner_tid`, `owner_oid`, `provider`, `scope_id`, `display_name`, `auth_method`, `status`, `azure_tenant_id`, `azure_client_id`, `secret_ciphertext` (bytea), `key_id`, `created_at`, `updated_at`, `last_verified_at`, `deleted_at`. Index on `(owner_tid, owner_oid)`; unique `(owner_oid, provider, scope_id)`. Related tables (`resource_configurations`, `ingestion_runs`) already carry `connection_id`; ownership is resolved by join, so no schema change is needed there.
The service must stop using class-level mutable state: it breaks with more than one replica and across restarts.

### 4.2 Encrypted credential storage

- Authenticated encryption (AES-256-GCM, or Fernet/MultiFernet) with **associated data = connection id + owner oid** so a ciphertext cannot be moved between rows or users.
- Key from a managed secret store (Key Vault via managed identity) or `CONNECTION_ENCRYPTION_KEYS` (key ring for rotation); strength/format checked by `validate_for_serving()` in production; **if no key is configured, the API refuses to accept a secret (503); it never stores plaintext.**
- Secrets are decrypted only inside one `ConnectionCredentialProvider`, used to mint short-lived ARM tokens (cached per connection in memory, never persisted), never logged, never serialized into any response model; exceptions redact the secret (the existing redaction pattern in `azure_inventory.py` is the model).
- Delete = delete ciphertext (hard delete of the secret even if the row is soft-deleted). Rotation = `PATCH` with new secret, re-validation required.

### 4.3 Access resolution

- Dependency `get_accessible_connection(connection_id, user)`: owned by caller → allowed; organization connection → allowed for read/refresh; anything else → **404** (not 403, to prevent ID enumeration).
- `GET /connections` returns only owned + organization connections. IDs of owned connections are opaque UUIDs. Organization IDs (`azure-<first 8 chars of subscription>`) are derived from subscription IDs and can collide; keep them for compatibility but resolve via a registry lookup, never by prefix.
- **Subscription binding:** every route taking a `subscription_id`/`scope_id`/project must verify it belongs to a connection the caller may use, then use **that connection's credential**. Without this, user-created connections have no effect and the server identity remains a confused deputy.
- `created_by` and any actor field are derived from the token, never from the request body.

### 4.4 Distinguish inaccessible data from empty data (requirement)

Today `ConnectionService.list_connections` catches provider exceptions, logs a warning and returns fewer/zero items, which the UI cannot tell from "genuinely empty". Add an explicit `data_access` state to list/discovery responses (additive field):

| State | Meaning | HTTP/UI |
|---|---|---|
| `accessible` + items | data available | 200 |
| `accessible` + empty | the subscription really has none | 200, empty list |
| `forbidden` | credential valid but lacks role (e.g. no Reader / Cost Management Reader) | 200 with state + actionable message naming the missing role |
| `unauthenticated` | stored credential invalid/expired | 200 with state, prompt to update the connection |
| `not_configured` | no connection / no server identity | 200 with state |
| `error` | provider failure | 502/200 with state, never presented as empty |

No metric or cost value is invented; unavailable sections report the state rather than zero.

### 4.5 Read-only guarantees for user-supplied credentials

- Validation checks the principal's effective permissions on the subscription (`Microsoft.Authorization/permissions`, a GET on the principal's own rights) and **rejects or flags** Contributor/Owner/write grants, consistent with AGENTS.md rule 3 (read-only roles only).
- The ARM/Cost/Monitor HTTP client wrapper allows **GET only** (plus the existing POST query endpoints that are read-only, explicitly listed) so a bug cannot mutate a customer subscription even if the principal could.

### 4.6 Policy mechanism (how the routes declare their class)

Keep the existing default-deny engine and extend it: classes `P/U/O/R` declared per endpoint (frozen lists in code and in the route-policy test); undeclared non-GET → **R**; owner routes use the ownership dependency and are verified by cross-user tests. `READ_STYLE_NON_GET_ENDPOINTS` becomes `USER_OPERATIONS`; `WRITE_ROLES` shrinks to `("FinOpsAdmin",)`; `READ_ROLES` is removed.

---

## 5. Security risks of the simplified model (and mitigations)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| S1 | **IDOR / confused deputy:** any user can query any subscription the server identity can read | High (exists today) | Subscription binding to caller-accessible connections (§4.3) |
| S2 | **Credential oracle:** `create/validate` lets a user test arbitrary tenant/client/secret combinations from the server | High | Per-user rate limit and quota, GUID validation (also prevents injection into the Entra token URL), lockout on repeated failures, audit |
| S3 | Secrets at rest / in memory / logs | High | §4.2; no secret in responses, logs or exceptions; encryption-key presence enforced in production |
| S4 | Over-privileged user-supplied principal (Owner/Contributor) | Medium | §4.5 permission check and GET-only client |
| S5 | Shared mutable state (`_action_overrides`, `_anomaly_overrides`, `_audit_events`, `_custom_connections`, refresher caches) wrongly reused across users and replicas | Medium | Move to DB with actor; key caches by connection id; single-replica note until done |
| S6 | Any authenticated user can trigger Databricks REST refresh / pricing refresh / ingestion (load, cost) | Medium | Cooldowns, per-user rate limits, existing conflict guards |
| S7 | Removing `Reader` role breaks app-only clients | Low | Documented; add a single app role only if needed |
| S8 | Shared recommendation/anomaly state edited by any user | Medium | Actor attribution + audit; alternative: per-user decision records (D4) |
| S9 | Org connection ID collisions (`azure-<8 chars>`) | Low | Registry lookup instead of prefix |
| S10 | Ownership bugs (missing check on one route) | High if present | Route-policy test extended with a **cross-user sweep** (§7) |
| S11 | Tenant isolation: token `tid` must stay equal to the configured tenant | Low | Already enforced; keep single-tenant until multi-tenant design |

Controls that remain untouched: all five authentication controls in the brief, `validate_for_serving`, dev-auth bans, CORS, health sanitisation, docs disabled in production.

---

## 6. Backward compatibility impact

| Area | Impact |
|---|---|
| API paths/payloads | **Unchanged.** Additions only: `data_access` field, optional `owner`/`scope` (`owned`/`organization`) flag, `PATCH`/`DELETE /connections/{id}`. `created_by` becomes server-derived (client value ignored) |
| Connection IDs | Organization IDs unchanged. Owned IDs change from `custom-az-xxxxxxxx` to UUIDs; existing custom connections were in memory only (lost on restart), so there is no persisted user data to migrate. Configuration/ingestion rows referencing old custom IDs become orphans (cleanup note) |
| Databricks / FinOps | No functional change; routes become class **U** (more permissive than today's write-gating for the 5 light operations, equal for reads). Billing run/approval token unchanged apart from the role name |
| Roles in Entra | Fewer: only `FinOpsAdmin`. Tokens that carry `Admin`/`FinOpsAdministrator`/`PlatformAdministrator` lose access to restricted operations until they get `FinOpsAdmin` (no such assignments can exist yet; Entra is not integrated) |
| Tests | ~60–80 test updates expected: `WRITE_ROLES`/dev-role fixtures (`Admin` in `conftest.py`), billing-hardening tests that pass `FinOpsAdministrator` as approver role, route-policy frozen lists, plus new ownership suites |
| Environment | New production variable for the connection encryption key (names only: `CONNECTION_ENCRYPTION_KEYS`); `ENTRA_*` list unchanged |
| Database | One new table + migration (not run here); no change to existing tables |
| Frontend | None required for authorization; UI will benefit from `data_access` and delete/update endpoints; `created_by` field becomes ignored |
| Azure / Databricks / FinOps behaviour | Preserved; Azure discovery will additionally use per-connection credentials when a connection is selected, falling back to the organization identity for organization connections |

---

## 7. Test requirements

1. **Route-policy sweep (extend existing):** frozen lists per class P/U/O/R; undeclared non-GET defaults to R; every O route has an ownership dependency; every operation 401 without token.
2. **Cross-user (IDOR) suite, for every owner route:** user A creates; user B gets **404** on read/validate/refresh/update/delete/ingest/retry/config/inventory-by-subscription; B's list never contains A's connection; A sees only own + organization; unknown ID and foreign ID return identical 404 bodies.
3. **Organization connections:** readable/refreshable by any user, **not** updatable/deletable (403).
4. **Restricted:** `POST /finops/ingestion/run` and `approval-token` → 403 for a normal user, pass for `FinOpsAdmin`; `run` additionally fails without a valid approval token; no SQL/warehouse activity in `validate`/`preview` (assert via mock).
5. **Credential handling:** secret never appears in any response, log record, exception text or repr; ciphertext round-trip; AAD mismatch (ciphertext copied to another row/owner) fails; missing key → 503 and nothing stored; rotation; delete removes ciphertext.
6. **Abuse controls:** per-user rate limit and quota; GUID validation rejects path-injection in tenant/client IDs; repeated bad credentials throttled.
7. **Read-only guard:** write-capable principal rejected/flagged; GET-only client refuses mutating verbs.
8. **Access states:** forbidden vs empty vs unauthenticated vs error produce distinct `data_access` values; no zero-filled metrics when inaccessible.
9. **Attribution:** `created_by`/actor is taken from the token even if the body supplies another value; audit event contains actor, not secrets.
10. **Auth controls regression:** the existing 100+ authentication tests (issuer, audience, tenant, exp, nbf, `azp`, scope, dev-auth bans, production startup guards) must pass unchanged.
11. **Concurrency/replica:** no module/class-level per-user state; two app instances sharing the DB behave identically.

---

## 8. What is removed and what is retained

| Removed | Retained |
|---|---|
| Roles `Admin`, `FinOpsAdministrator`, `PlatformAdministrator`, `Reader`, `FinOpsReader` | Roles: `FinOpsAdmin` only |
| Blanket "every non-GET needs a write role" | Secure-by-default **R** for undeclared routes |
| In-memory `_custom_connections` | Persistent owner-bound, encrypted connections |
| Client-supplied `created_by` | Token-derived actor |
| — | All authentication, client approval, scope, production startup guards, CORS, docs-off, health sanitisation, approval-token requirement for billing execution |

---

## 9. Implementation plan (for the next stage, after approval)

1. **Stage A: authorization simplification (small):** class-based policy, role collapse, attribution for #12/#13/#6/#3, cooldowns, route-policy test update. No new storage.
2. **Stage B: connection layer (main work):** migration, repository, encryption, `ConnectionCredentialProvider`, ownership dependency, list/validate/create/update/delete, `data_access` states, per-user limits.
3. **Stage C: bind discovery/monitoring/ingestion to connections:** subscription binding, per-connection credentials, cross-user test suite.
4. Re-run the security review, then Entra app registration and the SPA token flow.

Stage A can ship alone, but **ownership guarantees only exist after Stage B and C**. Until then the "simple user model" should be described as *shared server identity, any authenticated user sees the same organization data*.

---

## 10. Open observations discovered during this review

- `ConnectionService.create_connection` states "credentials stored securely in server memory only", yet the secret is not retained at all; the UI's "connected" state does not change which credentials are used afterwards.
- `list_connections` swallows provider errors (inaccessible looks empty).
- Decision/anomaly overrides and audit events are per-process lists with no actor.
- `ResourceConfigurationCreate.created_by` defaults to `"system"` and is client-controlled.
- `finops` routes default `connection_id="databricks-azure-dev"` and `workspace_id="642006393507276"` (hard-coded environment IDs) in query defaults.

---

## 11. Decisions requested

| ID | Question | Recommended |
|---|---|---|
| **D1** | Identity model for user Azure access: (A) user-supplied service principal stored encrypted per owner; (B) delegated On-Behalf-Of using the signed-in user's own Azure RBAC (no stored secrets, but needs an ARM delegated permission and admin consent later, and the user's token may carry broader rights than Reader, so GET-only enforcement is essential); (C) keep the shared server identity (ownership then meaningless) | **A now** (matches the existing `CreateConnectionRequest` and your "encrypted credential storage" requirement; works across tenants); evaluate B later |
| **D2** | Single restricted role name | `FinOpsAdmin` (existing, no new name) |
| **D3** | Ingestion on *organization* connections by any user (with cooldown) vs owner/admin only | Any user with cooldown (matches "refresh their own/available data") |
| **D4** | Recommendation/anomaly status: shared state with actor attribution vs per-user records vs keep restricted | Shared with attribution + audit (advisory only, no execution) |
| **D5** | `POST /pricing/refresh`: user-callable with global cooldown vs keep restricted | Cooldown; keep restricted until implemented |
| **D6** | Drop app-only (daemon) access (remove `Reader`/`FinOpsReader`) | Yes, until a daemon client exists |
| **D7** | Maximum owned connections per user and validation attempts per minute | 10 connections; 5 validation attempts/minute/user |

---

*Stopping after this design document as instructed. No code or configuration was changed, no cloud or database call was made.*
