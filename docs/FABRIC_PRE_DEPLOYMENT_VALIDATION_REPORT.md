# Cloud Recommender V5.1 — Fabric Pre-Deployment Validation Report

> **Date:** 2026-11-16 · **Branch:** `feature/live-finops-kpi-integration` · **Mode:** strictly read-only
> **Azure context used:** subscription `Microsoft Azure India` (`9636348b-8445-4441-94d2-f6191f131721`), tenant `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`, signed in as a user account via the existing Azure CLI session.
> **Legend:** **[VERIFIED]** = observed directly in this run (code read or live read-only Azure CLI output). **[ASSUMPTION]** = inferred, not observed. Nothing was deployed, created, updated, deleted, migrated or committed. No token or secret value was read, printed or stored.

---

## 1. Executive Summary

| Check | Status | Evidence | Action Required |
|---|---|---|---|
| Entra authentication | **FAIL** | `entra_auth_enabled` defaults to `False` (`core/config.py`); no `ENTRA_*` key is present in the local `.env` (key names only inspected); no hosted backend exists to carry a production setting. When disabled, every caller gets an `Admin` dev identity (`core/auth.py:247-257`). Separately, even when enabled, an unset `ENTRA_AUDIENCE` disables audience verification. | Set `ENTRA_AUTH_ENABLED=true`, `ENTRA_AUDIENCE`, `ENTRA_TENANT_ID` in the hosted backend; add a production fail-fast guard. |
| Token audience | **NOT VERIFIED** (static analysis indicates **likely FAIL**) | No safe token was obtainable (see §3). The SPA sends the **Rayfin session** access token; the backend expects an **Entra** RS256 JWT for tenant issuer + `ENTRA_AUDIENCE`. | Run the token test from an authenticated Fabric session (prerequisites in §3.5), or acquire a backend-audience Entra token (MSAL) in the SPA. |
| Backend hosting | **NOT AVAILABLE** | In the subscription: 0 Container Apps environments, 0 Container Apps, 0 App Service plans, 0 Web Apps, 0 ACR registries, 0 managed identities. Only resource group: `rg-deaccelerator-dev`. | Provision hosting (needs your approval); nothing existing can host the backend. |
| PostgreSQL | **NOT AVAILABLE** | `az postgres flexible-server list` and `az resource list --resource-type Microsoft.DBforPostgreSQL/flexibleServers` return nothing; `show psql-finops-prod` → `ResourceNotFound`. | Provision PostgreSQL Flexible Server or point to a different, confirmed server. |
| Database connectivity | **NOT VERIFIED** | Target server does not exist, so no meaningful test is possible. No connection attempted. | Re-test after provisioning. |
| Production security | **FAIL** | Auth off by default; audience check optional; insecure default `SECRET_KEY`; permissive CORS defaults; no hosted HTTPS endpoint; no DB. Details §6. | Close blockers in §7 before deployment. |

**Overall:** **NO-GO to deploy now.** The Azure subscription has none of the prerequisites (hosting, database), and the Fabric-to-backend token path is unproven and probably incompatible. All gaps are fixable but need approvals and some code/config change.

---

## 2. Repository Authentication Findings

### 2.1 Backend authentication implementation [VERIFIED]

| Item | Finding | Location |
|---|---|---|
| Mechanism | `HTTPBearer(auto_error=False)` + `EntraTokenValidator` (PyJWT, RS256 only, JWKS from `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys`, cached) | `backend/src/cloud_recommender/core/auth.py` |
| Router wiring | `require_authenticated_user` applied as a router-level dependency to connections, configuration, ingestion, databricks, **finops**, analysis, architecture, pricing, inventory, monitoring | `api/v1/router.py` |
| Public routes | `/health` (root + `/api/v1`), `/api/v1/catalog`, `/`, `/docs`, `/redoc`, `/openapi.json` | `router.py`, `main.py` |
| Role enforcement | `require_roles()` exists, but the router only applies `require_authenticated_user`; per-route role enforcement was **not** found at router level (not exhaustively checked per route) | `auth.py`, `router.py` |
| `ENTRA_*` use elsewhere | None outside `core/auth.py` and `core/config.py` | grep over `backend/src` |

### 2.2 Does `ENTRA_AUTH_ENABLED` default to false? **YES** [VERIFIED]

`core/config.py`: `entra_auth_enabled: bool = Field(default=False, …)`.
The local `.env` contains **no `ENTRA_*` keys** (key-name check only), so a locally started backend runs with auth disabled. `app.yaml` (Databricks Apps) sets no `ENTRA_*` variables either, so that deployment path also runs with auth disabled.

### 2.3 Exact code path that allows unauthenticated requests [VERIFIED]

`backend/src/cloud_recommender/core/auth.py`, `get_current_user()`:

```
247  if not settings.entra_auth_enabled:
248      # If disabled (local dev / test), allow optional token parsing or fall back to dev identity
249      if credentials and credentials.credentials:
250          try:    return validator.validate_token(credentials.credentials)
251          except Exception:  pass            # an INVALID token is silently ignored
253      return AuthenticatedUser(sub="local-dev-user", …,
255          roles=["Admin", "Reader", "CostManagementReader"], is_authenticated=True)
```

Consequences: with the default, (a) no `Authorization` header → authenticated as `local-dev-user` with `Admin` role; (b) a **malformed/expired/forged** token is swallowed and the same identity is granted. `require_authenticated_user` → `get_current_user`, so every protected router (including all FinOps cost endpoints) is reachable anonymously.

### 2.4 Second weakness when auth *is* enabled [VERIFIED]

`EntraTokenValidator.validate_token` sets `verify_aud = bool(self.audience)` and `audience = settings.entra_audience or None`. **If `ENTRA_AUDIENCE` is unset, audience is not verified**: any RS256 token signed by the tenant's keys with the right issuer/tenant (for example a token issued for Microsoft Graph or Fabric to any user in the tenant) would be accepted. The `scp` and `roles` claims are parsed but not enforced by the router.

### 2.5 Expected JWT properties [VERIFIED from code]

| Claim | Expectation |
|---|---|
| `alg` | `RS256` only |
| `iss` | `https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0` **or** `https://sts.windows.net/{ENTRA_TENANT_ID}/` |
| `aud` | `ENTRA_AUDIENCE` (client ID or API URI) — **default `None` = not checked** |
| `tid` | must equal `ENTRA_TENANT_ID` (default `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`, hard-coded) |
| `exp`, `nbf`, `iat` | all verified |
| `scp` / `roles` | parsed into the user object; not required |

### 2.6 CORS [VERIFIED from code defaults; deployed value NOT VERIFIED]

`main.py`: `CORSMiddleware(allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`.
Default `cors_origins` = localhost:3000/5173/5174 (+127.0.0.1), `https://app.fabric.microsoft.com`, `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`. A `CORS_ORIGINS` key exists in the local `.env`; its value was deliberately not read.

### 2.7 PostgreSQL configuration [VERIFIED from code]

`DATABASE_URL` (default `postgresql+asyncpg://postgres:postgres@localhost:5432/cloud_recommender`), `DB_SSL_MODE` default `prefer` (`app.yaml` sets `require`), pool 10/20, `pool_pre_ping`, recycle 1800 s. A `DATABASE_URL` key exists in the local `.env`; value not read. Migrations are never run at startup (`backend/scripts/run_migrations.py`).

### 2.8 Hosting references in the repo [VERIFIED]

There is **no** Azure Container Apps or App Service definition, Dockerfile or IaC in the repo. The only hosting artifact is the **Azure Databricks Apps** manifest (`app.yaml` + `run_databricks_app.py`). `app.yaml` and docs mention `psql-finops-prod`, which does not exist (§5).

### 2.9 Environment variable names (production requirements)

Unchanged from the earlier readiness report §7.4. Minimum for a hosted backend: `APP_ENV`, `DEBUG`, `SECRET_KEY`, `ENTRA_AUTH_ENABLED`, `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE`, `CORS_ORIGINS`, `DATABASE_URL`, `DB_SSL_MODE`, `AZURE_AUTH_METHOD`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_SUBSCRIPTION_ID`, `DATABRICKS_AUTH_TYPE`, `DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`, `FINOPS_SIGNING_SECRET`.

---

## 3. Entra Token Compatibility Test

### 3.1 Result: **NOT VERIFIED** (static analysis points to FAIL)

### 3.2 What the frontend actually sends [VERIFIED from code and installed SDK docs]

1. `use-auth.tsx` registers `setAuthTokenProvider(() => rayfinAuthService.getAccessToken())`.
2. `lib/api.ts` `getAuthToken()` order: (1) `fabric_entra_access_token` from storage via `setStoredEntraToken` → **never called anywhere in app code** (grep), (2) the provider above, (3) a `localStorage` scan for `authSession` → `accessToken`.
3. That token is a **Rayfin session token**. Per the installed Rayfin docs (`auth/fabric.md`), the Fabric popup/embedded flow exchanges a handoff code for "Rayfin session tokens"; it is **not** documented as an Entra access token for a custom API.
4. The only Entra token Rayfin documents is the *input* to its optional direct exchange: a delegated token for the **Fabric/Power BI audience** with `Item.Execute.All` (`auth/direct-entra-auth.md`) — i.e. intended for Fabric/Rayfin, not for our FastAPI backend.

### 3.3 Claim comparison

| Claim | Frontend token (static analysis) | Backend expects | Compatible? |
|---|---|---|---|
| Identity provider / `iss` | Rayfin session issuer **[ASSUMPTION – claims not decoded]**; the Entra token in the Fabric flow comes from `login.microsoftonline.com/fe82a67c-…` | `login.microsoftonline.com/{tid}/v2.0` or `sts.windows.net/{tid}/` | Unknown; likely **no** for Rayfin token |
| `aud` | Rayfin/Fabric (Power BI) audience **[ASSUMPTION]** | `ENTRA_AUDIENCE` (custom API) | **No** once audience is set; only "passes" today because auth is disabled or audience unchecked |
| `exp` | Not observable | verified | Not verified |
| `scp` / `roles` | Fabric `Item.Execute.All` for the Entra input token | none required | n/a |
| Intended for | Fabric / Rayfin | custom backend API | **Mismatch** |

Note: today a Fabric-originated call would "work" only because the backend ignores invalid tokens (§2.3). That is a false positive, not compatibility.

### 3.4 Why no live test was run

- The SPA's session lives in the **browser's `localStorage`** (`authSession`); the CLI session cannot read it, and reading it would expose a raw token.
- `~/.rayfin/` holds the Rayfin **CLI** sign-in (`auth.json`, `cache.bin`) for deployment; it is a Fabric-audience developer token, not the SPA's runtime token. Only key names of `auth.json` were listed; `cache.bin` was not opened.
- Minting a different token with `az account get-access-token` would test an Azure CLI token, not the Fabric/Rayfin frontend token, and was not done (it also risks token exposure).
- No backend is deployed to receive a request.

### 3.5 Missing prerequisites to complete the test

1. A deployed or locally running backend with `ENTRA_AUTH_ENABLED=true` and `ENTRA_AUDIENCE` set (local run is fine and non-destructive).
2. A signed-in Fabric/Rayfin session in a browser, plus a way to run a **local, in-browser** check that decodes only non-secret claims (`iss`, `aud`, `exp`, `scp`, `roles`) and discards the token, or an approved diagnostic in the SPA that logs claims only.
3. An Entra app registration for the backend API (exposed scope/audience) — **not created** here (restricted).
4. Decision on the token strategy: acquire a backend-audience Entra token (MSAL) in the SPA instead of forwarding the Rayfin token.

---

## 4. Azure Backend Hosting Availability

### 4.1 Commands run (all read-only) [VERIFIED]

`az version`, `az account show`, `az account list [--all]`, `az group list`, `az containerapp env list`, `az containerapp list`, `az appservice plan list`, `az webapp list`, `az acr list`, `az identity list`, `az resource list`, `az provider show -n <ns>` (registration state), `az keyvault show` (two network properties only), `az network vnet show`, `az role assignment list`.

### 4.2 Results

| Item | Result |
|---|---|
| Subscription / tenant | `Microsoft Azure India` (Enabled) / `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41`. A second subscription, `Azure subscription 1`, is **Disabled**. |
| Resource groups | **1**: `rg-deaccelerator-dev` (centralindia) |
| Container Apps environments / apps | **None** |
| App Service plans / Web Apps | **None** |
| Azure Container Registry | **None** |
| User-assigned managed identities | **None** |
| Resource providers | `Microsoft.App`, `Microsoft.ContainerRegistry`, `Microsoft.DBforPostgreSQL`, `Microsoft.Web` are **Registered** (provisioning is not blocked by registration) |
| Existing resources (all in `rg-deaccelerator-dev`) | VNet `vnet-deaccelerator-dev`, NSG, Data Factory, Key Vault `akv-deaccelerator-dev`, Logic App, Storage `sadeacceleratordev`, SQL server + 5 DBs, **Databricks workspaces `adb-deaccelerator-dev` and `adb-deaccelerator-dev-prod`**, access connector, API connections, Event Grid topic, App Insights `FuncAppIngestOneDriveFiles`, private DNS zone `privatelink.vaultcore.azure.net` |
| Role assignments for the signed-in user | `az role assignment list` returned **no rows** — inconclusive (could be no direct assignment, group-based access, or insufficient read rights). **Ability to create resources is NOT VERIFIED.** |

### 4.3 Which existing resource could host the FastAPI backend?

**None** [VERIFIED]. The resource group appears to belong to a different project ("deaccelerator"); its Data Factory, Logic App, SQL and Key Vault are not hosting targets and were not touched. The VNet (`172.16.0.0/16`) has no subnet delegated for Container Apps or PostgreSQL Flexible Server (delegations observed: only `Microsoft.PowerPlatform/vnetaccesslinks` on `vnet-data-gateway`); reuse would need new subnets (modification, not done).

---

## 5. PostgreSQL Availability

| Check | Result [VERIFIED] |
|---|---|
| `psql-finops-prod` exists | **No** — `az postgres flexible-server show … -g rg-deaccelerator-dev` → `ResourceNotFound` |
| Any Flexible Server in the subscription | **None** (`flexible-server list` and `az resource list --resource-type Microsoft.DBforPostgreSQL/flexibleServers` both empty) |
| Server state / version / region / SKU / storage / networking / firewall | **Not applicable** — nothing to inspect |
| Databases listed | Not applicable |
| Reachability from backend host | Not applicable (neither exists) |
| Connectivity test | **Not performed** — no target; local `.env` `DATABASE_URL` value was not read and no connection to any database was attempted |

Where the name appears: `app.yaml` comments and docs (e.g. "e.g. …psql-finops-prod.postgres.database.azure.com"). It is an **example**, not evidence of a provisioned server. Searching other subscriptions was not possible: the only other one is Disabled. A server in a different tenant/subscription that this login cannot see is possible but **[ASSUMPTION]**.

---

## 6. Security Readiness

| Question | Status | Evidence / Notes |
|---|---|---|
| Is backend Entra auth enabled? | **FAIL** | Default `False`; no `ENTRA_*` in local `.env` keys; `app.yaml` doesn't set it. [VERIFIED] |
| Does the backend reject unauthenticated requests? | **FAIL (as configured)** | Only when `ENTRA_AUTH_ENABLED=true`; otherwise `local-dev-user` Admin (§2.3). Code path for rejection exists: 401 `MISSING_BEARER_TOKEN`. [VERIFIED] |
| Audience enforced? | **FAIL** | Unset audience ⇒ `verify_aud=False` (§2.4). [VERIFIED] |
| Production secret key secure? | **NOT VERIFIED** | Code default is `insecure-default-development-secret-key-change-in-production`. `SECRET_KEY` key exists locally; the value was not read. No production runtime exists to inspect. No fail-fast guard in code. |
| CORS restricted to the actual Fabric origin? | **FAIL (defaults) / NOT VERIFIED (deployed)** | Defaults include localhost origins and `allow_credentials=True` with wildcard methods/headers. The Fabric hosting origin is present in defaults. The hosting URL itself comes from `.deployments.json`; whether it's live is unverified. |
| Secrets outside frontend `VITE_` variables? | **PASS** (for inspected files) | `VITE_*` names in `.env.production` / `.env.local` are IDs, flags and the Rayfin publishable key (`pk-…`, public by design). No client secrets/passwords among key names. Values not printed. |
| Databricks prod auth suitable for hosted backend? | **PARTIAL / NOT VERIFIED** | Code default is `azure-cli` (not usable in a container). Production path `oauth` + client id/secret exists (`app.yaml`), but `app.yaml` uses Databricks-only `{{secrets/…}}` references, which are not portable to Container Apps. Defaults point at the dev workspace. |
| HTTPS? | **NOT VERIFIED** | Uvicorn serves plain HTTP; TLS would be terminated by the hosting platform. No hosted endpoint exists. No HTTPS redirect/HSTS in app code. |
| PostgreSQL protected from public access? | **NOT VERIFIED / N/A** | No server exists. Code supports `DB_SSL_MODE=require`. Default is `prefer`. |
| Key Vault (existing) | Observation | `akv-deaccelerator-dev`: public network access **Enabled**, access-policy model (RBAC disabled). Belongs to another project; no secret values retrieved. |

---

## 7. Blockers and Missing Permissions

**Blockers (must be resolved before deployment)**

| # | Blocker | Needs |
|---|---|---|
| B1 | No backend hosting exists | Approval + permission to create Container Apps env/app, ACR, identity (rights **NOT VERIFIED**; role listing empty) |
| B2 | No PostgreSQL server (`psql-finops-prod` absent) | Approval + rights to create a Flexible Server and subnet/private access |
| B3 | Backend auth off by default and audience optional | Config change (`ENTRA_AUTH_ENABLED=true`, `ENTRA_AUDIENCE`) and ideally code guard — **not changed here** |
| B4 | Fabric/Rayfin token not shown to be valid for backend | Entra app registration for backend API (needs a Entra permission such as Application Developer; admin consent may be required) + SPA change to request that audience |
| B5 | Production secrets undefined | Key Vault (new, or approved reuse) + managed identity access |
| B6 | Hosted Databricks auth | Databricks service principal with read-only entitlements; OAuth secret store compatible with the new host |

**Missing permissions / access to confirm**

- Azure RBAC at subscription or a new resource group (Contributor-equivalent *for the deployer only*; the application itself stays read-only).
- Entra: ability to create an app registration and expose an API scope; admin consent path.
- Fabric: confirm the existing app item and capacity state (no Fabric API call was made).
- Databricks: grants for the service principal (not checked).

---

## 8. Recommended Next Steps

1. **Decide the hosting/DB target and approve provisioning** (new resource group recommended, separate from `rg-deaccelerator-dev`): Container Apps + ACR + PostgreSQL Flexible Server (TLS, restricted network) + Key Vault.
2. **Create the backend Entra app registration** and decide the token strategy (MSAL backend-audience token in the SPA vs another approved approach). Then run the token compatibility test (§3.5) against a local backend with auth enabled.
3. **Harden backend config** (needs your go-ahead for code changes): fail-fast in production when auth is disabled, `ENTRA_AUDIENCE` empty, `SECRET_KEY`/`FINOPS_SIGNING_SECRET` default or missing; stop swallowing invalid tokens when disabled; restrict CORS to the real Fabric origin.
4. **Fix the Fabric build routing** (`VITE_USE_FABRIC_UDF=false`, `VITE_API_BASE_URL=https://<backend>/api/v1`).
5. **Databricks:** provision a read-only service principal and use `DATABRICKS_AUTH_TYPE=oauth` with secrets from Key Vault.
6. **Re-run this validation** after provisioning to verify DB connectivity (TLS, firewall, private path from the backend), HTTPS, and token compatibility. Only then consider `rayfin up`.

---

## 9. What Was Tested, What Was Not, and Why

**Tested (read-only)**
- Source inspection: `core/auth.py`, `core/config.py`, `main.py`, `api/v1/router.py`, `db/session.py`, `app.yaml`, the Fabric SPA's `lib/api.ts`, `hooks/use-auth.tsx`, `services/rayfin-auth.service.ts`, `rayfin.yml`, and the installed Rayfin auth docs.
- Env-file **key names only** (`.env`, `.env.production`, `.env.local`); no secret values.
- Azure CLI read-only listings and `show` calls listed in §4.1, including existence checks for PostgreSQL.

**Not tested**
| Item | Reason |
|---|---|
| Real token claims (`iss`/`aud`/`exp`/`scp`/`roles`) | Raw SPA token is in browser storage; reading/printing it is prohibited; no safe in-session mechanism available; no backend to receive it |
| Backend validation of a real token | No hosted backend; no backend-audience app registration |
| DB connectivity, networking, firewall, SKU | Server does not exist |
| Existence/state of the Fabric app, capacity, Rayfin service | No Fabric API call made (outside the Azure-CLI-only scope and a deploy-adjacent path) |
| Databricks grants and SP access | No Databricks call made |
| Subscription write rights | `az role assignment list` returned no rows; not testable without writing |
| Local `.env` values (`SECRET_KEY`, `CORS_ORIGINS`, `DATABASE_URL`) | Secret-bearing; one attempt to print them was blocked by the session's permission guard and was not retried |

**Not done by design:** no `rayfin up` / deployment, no resource creation/update, no migrations, no DB writes, no Entra registrations, no consent changes, no secret rotation, no Key Vault secret retrieval, no edits to `.env`/YAML/Python/TypeScript, no Git operations. This report is the only file created.
