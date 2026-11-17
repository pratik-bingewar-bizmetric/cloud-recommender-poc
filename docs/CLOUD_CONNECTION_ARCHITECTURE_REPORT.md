# Permanent Cross-Environment Cloud Connection Architecture: Report

- **Branch:** `feature/backend-security-hardening` (HEAD `902d220`, everything uncommitted; no push).
- **Status:** implemented and tested against mocks. **Not verified against real Azure, Databricks, Fabric, Key Vault or PostgreSQL** (see §11), and **the database migration is prepared but NOT applied**.
- **Not done (per restrictions):** no migration run, no provisioning, no Entra/Azure/Fabric change, no deployment, no commit/push, no ingestion or billing execution. `.env` was not touched in this task (the two `DEV_AUTH_*` lines were added earlier at your request).

---

## 0. Architecture and implementation gap analysis (before the change)

| # | Required capability | State before | Gap |
|---|---|---|---|
| G1 | Cloud credentials separate from the application login | Mixed: the connection API validated an SP, then **discarded the secret**; discovery used the server's own identity / Azure CLI | Credentials never stored or used per user |
| G2 | Persistent, owner-bound connections | `ConnectionService._custom_connections`: a **process-global in-memory dict**, no owner, lost on restart, shared by all users | No table, no ownership, no persistence |
| G3 | Encrypted credential storage + key management | None | No cipher, no key provider, no Key Vault integration |
| G4 | Azure SP validation workflow (tenant/subscription/permissions) | Entra token test + ARM subscription probe only | No tenant-match check, no per-integration permission check, no write-permission screening |
| G5 | Per-integration status (ARM / Cost / Monitor / Databricks / Fabric) | None (single `status`) | Authentication success implied everything |
| G6 | Databricks and Fabric connection validation per user | Databricks: server-level registry only; Fabric: UDF prototype | No user-supplied-credential validation |
| G7 | Edit / reconnect / rotate / delete own connections | Frontend edit/delete changed **local React state only**; no API | No PATCH/DELETE/validate endpoints |
| G8 | Frontend/backend schema agreement | Next.js form sent `provider, name, scope_id, azure_tenant_id` only | Backend required client id + secret |
| G9 | Meaningful auth vs permission errors in the UI | Generic message; client-side checks returned silently | No classification |
| G10 | Same logic local / Fabric / App Service | Next.js local app had no auth; Fabric app used UDF or a Rayfin token the backend rejects | Divergent paths |
| G11 | GCP persistence | In-memory, unvalidated | Out of scope for this step (see §10) |

---

## 1. Root cause of the HTTP 400

The local (Next.js) **Add New Connection** form posted only `provider`, `name`, `scope_id` and `azure_tenant_id`. The backend's `create_connection` requires a **tenant ID, client ID and client secret** for Azure and answers `400 "Azure Service Principal requires Tenant ID, Client ID, and Client Secret."` The form had no client-ID or client-secret fields at all (the "authentication method" dropdown was never sent), and a client-side `return` silently skipped submission when name/subscription were empty. The backend and frontend contracts had drifted apart.

Fix: the form now has the credential fields (shown only for the service-principal method), sends an explicit `auth_method`, shows per-field validation, and classifies server errors; the backend request model includes `auth_method` and optional Databricks/Fabric configuration, and missing fields now return **422** with the list of missing fields (400 is reserved for rejected credentials).

---

## 2. Architecture after the change

```
Application login (WHO is using FinOps)                       Cloud credentials (WHAT is being connected)
 local: DEV_AUTH_* identity (development only)                 user-supplied Azure service principal
 Fabric/prod: Entra token (backend audience, azp, scope)       (tenant, client id, client secret, subscription)
 ─► get_current_user ─► owner_key = "<tid>:<oid>"              never derived from the login token
                          │                                             │
                          ▼                                             ▼
                  ConnectionManager (one implementation for local / Fabric frontend / App Service)
   create: validate fields ─► Entra token (client credentials) ─► subscription + tenant match
           ─► read the principal's OWN permissions (Microsoft.Authorization/permissions)
           ─► evaluate integrations (ARM, Cost, Monitor, Databricks, Fabric), reject write-capable principals
           ─► AES-256-GCM encrypt the secret (AAD = connection id | owner) ─► repository.add
   use:    GET /azure/connections/{id}/… ─► decrypt in memory ─► mint token ─► per-connection ARM calls
   delete: remove row + ciphertext + cached token
                          │
        ConnectionRepository (protocol):  SqlConnectionRepository (PostgreSQL, owner-scoped on EVERY statement)
                                          InMemoryConnectionRepository (development/testing only, non-persistent)
        CredentialCipher ◄─ KeyProvider:  keyvault (managed identity) │ env (app setting / KV reference) │ local_file (dev only)
```

Key properties
- **Owner from the token only** (`tid:oid`); request fields such as `owner` are ignored (tested). Other users' ids behave exactly like unknown ids (404, identical body).
- **Secrets**: stored only as ciphertext; never in any response, log, exception or `repr`; the login token is never used as a cloud credential (tested).
- **No silent method switching**: `service_principal` (default), `azure_cli` (only when `ALLOW_CLI_CONNECTIONS=true`, development/testing), `managed_identity` (only if the host has an identity). A failed method returns its own error; nothing falls back to another identity.
- **Integrations are independent** (`connected | permission_denied | not_configured | unavailable | error`); missing cost permission is a state with the required role, never a zero.
- **Read-only policy**: the principal's own effective permissions are read; Contributor/Owner/write grants are **rejected** by default (`CONNECTION_REJECT_WRITE_PRINCIPALS=false` downgrades to a warning). The ARM client itself only issues GET (plus the Cost Management read query).
- **Persistence/restart**: saved connections are read from the database; the Azure token is re-minted from the stored credential whenever needed (token expiry or backend restart are transparent).
- **Same code everywhere**: environment differences are only API base URL, auth configuration, database, key source, CORS origins.

---

## 3. Files changed

### Backend
| File | Change |
|---|---|
| `core/secret_vault.py` | **New**: AES-256-GCM cipher with key ring/rotation; key providers `keyvault` (managed identity → Key Vault secret), `env`, `local_file` |
| `db/models.py` | **New** `CloudConnectionModel` (`cloud_connections`) |
| `alembic/versions/2026_11_16_0005_cloud_connections.py` | **New migration, PREPARED, NOT APPLIED** (guarded downgrade) |
| `db/repositories/connection_repo.py` | **New**: owner-scoped SQL + in-memory repositories, duplicate detection |
| `services/connections/connection_manager.py` | **New**: create / list / get / validate / update (rotation) / delete / activate session |
| `services/connections/integration_checks.py` | **New**: permission evaluation, Databricks and Fabric probes |
| `services/azure_live/credentials.py` | Token acquisition for other audiences (Databricks, Fabric); managed-identity and CLI methods (explicit only) |
| `services/azure_live/session_store.py` | Persistent ids, `discard` |
| `api/connection_deps.py` | **New**: shared dependencies (repository, cipher, manager, transport, session store) |
| `api/routes/connections.py` | Rewritten: owned + organization listing, create/get/patch/delete/validate (see §4) |
| `api/routes/azure_live.py` | Data endpoints accept **saved connection ids** (credential decrypted, token minted per request) |
| `schemas/connections.py` | `IntegrationStatus`, `auth_method`, Databricks/Fabric fields, `UpdateConnectionRequest`, `SecretStr` secret |
| `services/connections/connection_service.py` | Legacy Azure path adapted to `SecretStr` (GCP path untouched) |
| `core/config.py` | New settings (§5); production requirements for the store/key |
| `core/auth.py` | The 5 connection operations classified as user (owner-bound) operations |
| `main.py` | Database problems → explicit `503 DATABASE_UNAVAILABLE` |
| `.gitignore` | `backend/.local-secrets/` (local dev key) |

### Next.js (local) frontend
`components/ConnectCloudView.tsx` (credential fields, auth-method values, validation, error panel, integration chips, server-side edit/rotate/delete), `lib/api.ts` (PATCH/DELETE/revalidate), `lib/authErrors.ts` (error classification), `types/index.ts`.

### Fabric (Vite) frontend
`components/ConnectCloudView.tsx` (explicit `auth_method`, required-field errors, classified errors, secret cleared, integration chips + Delete for owned), `lib/connectionErrors.ts` (new), `lib/api.ts` (DELETE 204), `types/index.ts`, Azure Live view: **Saved connections** list + `openSaved` (no secret needed after a refresh).

### Tests added/changed
`test_persistent_connections.py` (33), `test_secret_vault_and_store.py` (22 + 1 opt-in), `test_env_list_parsing.py` (27, from the DEV_AUTH_ROLES fix), frontend `connection-form.test.ts` (8), `connection-persistence-ui.spec.tsx` (6), `azure-live.spec.tsx` (+1); updated frozen route-policy lists and 4 existing tests whose expectations changed on purpose (connections no longer restricted to `FinOpsAdmin`).

---

## 4. API changes (`/api/v1`, application authentication required)

| Method and path | Purpose | Codes |
|---|---|---|
| `GET /connections` | Your **owned** connections (with per-integration status) + organization connections. No secrets. If the store is down: organization list + header `X-Owned-Connections: unavailable` | 200, 401, 403 |
| `POST /connections` | Create (Azure): validate → encrypt → save. Body adds `auth_method`, `databricks_workspace_url/id`, `fabric_workspace_id` | **201**, 400 (credentials, subscription, tenant mismatch, write permissions), 401, 403, 409 (duplicate/limit), **422** (missing/invalid fields, lists `fields`), 502/503 |
| `GET /connections/{id}` | One of your connections | 200, 404 |
| `PATCH /connections/{id}` | Edit, reconnect, **rotate secret** (validated before saving; old secret kept on failure) | 200, 400, 404, 409 |
| `DELETE /connections/{id}` | Delete row, ciphertext and cached token | 204, 404 |
| `POST /connections/{id}/validate` | Re-validate with the stored credential; refreshes integration statuses | 200, 404, 409 (`CREDENTIAL_UNREADABLE`) |
| `POST /connections/validate` (existing) | Unchanged contract; for an owned GUID id it validates the stored credential | 200 |
| `GET /azure/connections/{id}/…` (existing live endpoints) | Now also accept saved ids; **404 for other users** | 200/404 |

Integration status object: `{integration, state, message, required_permission, details}` for `resource_manager`, `cost_management`, `monitor`, `databricks`, `fabric`.

Unchanged: GCP create/validate (legacy, not persistent), Databricks and FinOps endpoints, organization connections, Fabric UDF path.

---

## 5. Environment variables (names and purpose only)

| Variable | Purpose |
|---|---|
| `CONNECTION_STORE` | `database` (default, persistent) or `memory` (development/testing only, **not persistent**) |
| `CONNECTION_KEY_PROVIDER` | `keyvault` (production), `env`, or `local_file` (development only; default) |
| `KEY_VAULT_URL`, `CONNECTION_KEY_SECRET_NAME` | Key Vault holding the base64 32-byte master key (managed identity required) |
| `CONNECTION_ENCRYPTION_KEYS`, `CONNECTION_ACTIVE_KEY_ID` | Key ring for the `env` provider (value is a secret) |
| `CONNECTIONS_MAX_PER_USER` | Connections per user (default 10) |
| `CONNECTION_REJECT_WRITE_PRINCIPALS` | Reject principals with write permissions (default true) |
| `ALLOW_CLI_CONNECTIONS` | Enable the explicit Azure CLI method (development/testing only) |
| `FABRIC_API_BASE_URL` | Fabric REST base (default public cloud) |
| `DATABASE_URL`, `DB_SSL_MODE` | Existing database settings (now required for persistence) |
| Existing | `APP_ENV`, `ENTRA_*`, `CORS_ORIGINS`, `SECRET_KEY`, `FINOPS_SIGNING_SECRET`, `DEV_AUTH_*` (local only), `VITE_API_BASE_URL`, `VITE_ENTRA_*` |

Production startup now **refuses** to run with `CONNECTION_STORE=memory`, `local_file` keys, a missing key configuration, or `ALLOW_CLI_CONNECTIONS=true`.

---

## 6. Database and encryption requirements

**Migration `2026_11_16_0005` (prepared, not applied)** creates `cloud_connections`: owner (`owner_tid`, `owner_oid`), provider, auth method, name, scope id, credential tenant/client ids, `secret_ciphertext` (bytea) + `secret_kid`, `integration_config` / `last_validation` (jsonb), status and timestamps; unique `(owner_tid, owner_oid, provider, scope_id, credential_client_id)`; owner index. Requires PostgreSQL 13+ (`gen_random_uuid()`); no existing table is touched; the downgrade refuses to run if rows exist. **Approval required before running** `python backend/scripts/run_migrations.py`.

**Encryption:** AES-256-GCM, random nonce per record, AAD binds ciphertext to its row id and owner (a copied ciphertext fails), key ring with ids for rotation. Master key: 32 random bytes, base64. Generate one with `python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"` and store it as a Key Vault secret (production) or app setting (env provider).
Note: this is a master-key design (Key Vault secret read once with the managed identity), not per-record wrapping through Key Vault keys. It is a deliberate trade-off (no Key Vault call per decrypt); per-record envelope wrapping is a possible hardening step.

---

## 7. Platform-wise test results (all with mocks, no network)

| Platform | Check | Result |
|---|---|---|
| **Backend** | `pytest backend/tests` | **923 passed, 9 skipped** (the new skip is the opt-in real-database test), coverage 87%; 1 pytest warning in the full run, not reproduced in the new test files |
| | `ruff check` / `ruff format --check` / `mypy src` | pass (172 files; 106 source files) |
| **Azure** | Valid SP; invalid secret / app / tenant; invalid & inaccessible subscription; tenant mismatch; Cost and Monitor permission denied (never zero); unreadable permissions; write-principal rejected/flagged; duplicate/limit; secret rotation; stored credential rejected | pass |
| **Fabric API** | Valid workspace (name, capacity, lakehouses); 403 permission denied; 404 unavailable; invalid workspace id (no call made) | pass |
| **Databricks** | Valid workspace (warehouses visible; system tables explicitly "not verified: needs approved SQL"); 403; 404; non-Azure-Databricks URL rejected with no call | pass |
| **GCP** | Existing behaviour untouched (existing suites green); **no new GCP persistence** | unchanged |
| **Cross-environment** | Restart persistence (second app instance + empty sessions, same store); token expiry → transparent re-mint; refresh = list from store; user isolation on every route; credential rotation; invalid/forged/expired app token → 401; scope/client → 403; production enforcement (route sweep); no secrets in logs/responses; Azure CLI and managed identity never used as fallback | pass |
| **Persistence layer** | SQL repository emits an owner predicate on **every** statement; migration columns == model; revision chain; guarded downgrade; **real PostgreSQL not exercised** | pass (unit); live DB unverified |
| **Next.js frontend** | `tsc --noEmit`, eslint, `npm test` (16 suites; new: error classification, form contract, secret handling, no browser storage) | pass |
| **Fabric (Vite) frontend** | `vitest` **157 passed** (16 files); `vite build` success; eslint clean on new files (1 pre-existing `any` error and 1 pre-existing warning remain; 55 pre-existing `tsc -b` errors in other files, none in changed files) | pass |

---

## 8. Local testing instructions (Windows)

1. Backend env: `DEV_AUTH_ENABLED=true` and `DEV_AUTH_ROLES=["FinOpsAdmin"]` are already in your `.env`; `APP_ENV=development`.
2. **Choose where connections are stored** (no `.env` change was made):
   - *Quick test, non-persistent:* set `CONNECTION_STORE=memory` for the backend process (connections vanish on restart).
   - *Persistent:* have an administrator approve and run the migration against a local PostgreSQL, set `DATABASE_URL`, keep `CONNECTION_STORE=database`.
   - Without either, **Add New Connection returns `503 DATABASE_UNAVAILABLE` ("Nothing was saved")**, which the form shows.
3. Encryption key: with `CONNECTION_KEY_PROVIDER=local_file` (default) a random key is generated once into `backend/.local-secrets/connection.key` (git-ignored, development only).
4. Start the backend (`startup.bat` or `uvicorn`), then the frontend. Open **Add New Cloud Connection**: choose Azure + *Service Principal*, enter name, subscription, tenant, client ID, secret. Expect per-integration chips; refresh the page: the connection is still listed (persistent store only).
5. Use a read-only service principal (Reader, Cost Management Reader, Monitoring Reader). A Contributor/Owner principal is rejected by design.

## 9. Fabric deployment instructions

1. Backend (App Service, single instance for now): settings from §5 plus the existing Entra settings; `CONNECTION_KEY_PROVIDER=keyvault`, `KEY_VAULT_URL`, `CONNECTION_KEY_SECRET_NAME`; assign the App Service a managed identity with **Key Vault Secrets User** on that vault; `DATABASE_URL` to the production PostgreSQL; `CORS_ORIGINS` = the Fabric hosting origin.
2. Apply the approved migration once (operator step).
3. Frontend: build with `VITE_API_BASE_URL=https://<app>.azurewebsites.net/api/v1`, `VITE_USE_FABRIC_UDF=false` (the connection workflow targets the FastAPI backend; the UDF path remains available but is a separate implementation), and `VITE_ENTRA_CLIENT_ID/TENANT_ID/API_SCOPE`; deploy with the existing Rayfin process.
4. Users sign in (Entra), open Add New Connection (Fabric app) or Azure Live, and save/open connections.

## 10. Remaining manual configuration and known gaps

**Manual (administrator):** Entra app registrations and consent (see `AZURE_LIVE_CONNECTION_DEMO_REPORT.md` §8); Key Vault + master key + managed-identity role; PostgreSQL + migration approval; Fabric tenant setting "Service principals can use Fabric APIs" and workspace membership for the SP; Databricks workspace membership for the SP; CORS origin; real-tenant verification (§11).

**Known gaps (explicit):**
1. **GCP** is unchanged and **not persistent** (no encrypted service-account storage yet).
2. **`POST /configuration`** (saving selected scope) and organization ingestion remain restricted (`FinOpsAdmin`) and are not yet bound to owned connections; subscription-scoped inventory/monitoring endpoints for *organization* connections still use the platform identity by design.
3. Databricks system-table access is reported as "not verified" (it requires an approved SQL execution, which this task must not trigger).
4. Fabric/Databricks checks reuse the same service principal; tenant-level Fabric settings can make a correct principal show `permission_denied`.
5. Master-key design (not per-record Key Vault wrapping); key rotation needs `extra` key versions configured.
6. In-memory session tokens and rate limiters are per process (single instance); persistent connections are unaffected (tokens re-minted).
7. The Fabric (Vite) UI has Delete and Open for saved connections but **no edit/rotate dialog** (rotation is available through the API and the Next.js UI).
8. Frontend UDF mode (`VITE_USE_FABRIC_UDF=true`) still stores connections in the Fabric UDF store, a separate implementation, as before.

## 11. Production deployment readiness assessment

**Verdict: NOT ready for production yet; ready for a controlled pilot once the items below are done.**

| Area | Assessment |
|---|---|
| Code paths (create/list/validate/rotate/delete/use, ownership, encryption, integrations) | Implemented and covered by mocked tests |
| Authentication/authorization (app login separate from cloud credentials, owner isolation, 401/403) | Verified in tests; Entra registration not yet created, interactive sign-in untested |
| Persistence | **Blocked on approval**: migration not applied; SQL repository not run against PostgreSQL (statement-level checks only; an opt-in integration test exists) |
| Encryption/key management | Implemented; **Key Vault path untested against a real vault**; no key exists yet |
| Real cloud behaviour | **Unverified**: Entra errors, ARM permissions API shape, Cost/Monitor, Databricks SCIM, Fabric REST were modeled from documentation. Verify with an authorized test subscription, Databricks workspace and Fabric workspace before relying on it |
| Operational | Single instance recommended; no backup/restore runbook for connection data; no audit log table (events are logged without secrets) |
| Security review | Re-run the route sweep and cross-user suite after deployment; consider per-record envelope encryption and a rotation drill |

**Acceptance criterion** ("sign in → Add New Connection → validate → save → refresh → keep using it, locally and on Fabric"): implemented end to end and demonstrated in automated tests with mocked cloud services and an in-memory store; **it still has to be demonstrated live** after the migration, key, Entra registrations and an authorized test account are in place.
