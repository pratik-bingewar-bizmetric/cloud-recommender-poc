# Cloud Recommender V5.1 — Fabric Apps Deployment Readiness Report

> **Date:** 2026-11-16 · **Branch:** `feature/live-finops-kpi-integration` · **Type:** Read-only analysis (no code, config, credential, cloud or database change was made)
> **Method:** Static inspection of the repository and of the installed `@microsoft/rayfin-guide@1.36.2` docs. No cloud, Fabric, Databricks or database endpoint was contacted, and no secret values were read (only `.env` key names).
> **Not verified:** live state of the Fabric tenant, capacity, Entra app registrations, Databricks grants, or the currently deployed Fabric App. Items depending on these are marked **[UNVERIFIED]**.

---

## 0. Executive Summary

| Question | Answer |
| :--- | :--- |
| Can the existing Next.js frontend run on Fabric Apps? | **No.** Fabric Apps static hosting serves a pre-built static folder only. `frontend/` is Next.js 14 with server-side `rewrites()` and needs a Node server. |
| Is there already a Fabric-compatible frontend? | **Yes, but it is a second codebase**: `fabric-integration/finops-app` (React 19 + Vite 8 + Tailwind 4 + Rayfin auth). It has already been deployed once (hosting URL and item recorded in `rayfin/.deployments.json`). |
| Can the FastAPI backend run on Fabric Apps? | **No.** Fabric Apps offers static hosting, Rayfin data (SQL/GraphQL), auth and TypeScript functions. It has no runtime for a long-running Python ASGI service. **Separate hosting is required.** |
| Can the existing PostgreSQL be used from Fabric? | Not by the Fabric App directly. Only the FastAPI backend talks to PostgreSQL. The database must be a network-reachable managed PostgreSQL (none is provisioned by this repo). |
| Will Databricks FinOps keep working? | **Only if the Fabric frontend calls the FastAPI backend.** The Fabric User Data Function (UDF) contains **zero** Databricks code. The shipped Fabric build has `VITE_USE_FABRIC_UDF=true`, which routes the API base URL to the UDF, where none of the 15 FinOps / Databricks endpoints exist. As configured, those screens would fail. |
| Will Azure integration keep working? | Yes, via the FastAPI backend with a service principal (read-only). The UDF has its own partial Azure client; it is a separate implementation. |

**Recommendation: CONDITIONAL GO** for a *hybrid* deployment (Fabric App = static frontend + Entra sign-in; FastAPI + PostgreSQL hosted on Azure). **NO-GO** for deploying "the whole app" onto Fabric Apps, because that is not technically possible. See §13.

---

## 1. Current Application Architecture

### 1.1 Components found

| Component | Location | Stack | Runtime needs |
| :--- | :--- | :--- | :--- |
| **Backend API** | `backend/src/cloud_recommender` | FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, LangGraph, structlog, Databricks SDK, deltalake/pyarrow; Python `>=3.12,<3.13` (`pyproject.toml`) | Long-running ASGI process, outbound HTTPS, PostgreSQL |
| **Primary frontend** | `frontend/` | Next.js 14.2.35 (App Router), React 18, Tailwind 3, Mermaid, Cytoscape | Node server (uses `rewrites()`; no `output: export`) |
| **Fabric frontend** | `fabric-integration/finops-app/packages/frontend` | Vite 8, React 19, Tailwind 4, Rayfin auth SDK 1.36, Mermaid, Cytoscape | Static hosting only |
| **Fabric UDF** | `fabric-integration/fabric-udf` | Fabric Python User Data Functions (`function_app.py`, ~4.8k lines); SQLite at `/tmp/lakehouse_finops.db`; Fernet-encrypted connection store | Fabric UDF runtime |
| **Sync agent** | `fabric-integration/sync-agent` | Python CLI: Azure ARM / Cost / Monitor → Delta tables in OneLake | Manually invoked; **no scheduler** |
| **Lakehouse scripts** | `fabric-integration/lakehouse` | Provision `finops_lakehouse` and 5 Delta tables | One-off CLI |
| **Databricks Apps packaging** | `app.yaml`, `run_databricks_app.py`, root `requirements.txt` | Supervisor starting uvicorn (internal) + Next.js (public) | Databricks Apps runtime |
| **Local startup** | `startup.bat` | Windows launcher | Dev only |

### 1.2 Request flow today

```
Databricks Apps (current prod target)          Local dev
Browser → Next.js :PORT → /api/* rewrite →     Browser → Next.js :3000 → FastAPI :8000 → PostgreSQL
          FastAPI 127.0.0.1:8000 → PostgreSQL
          (external, SSL=require)
FastAPI → Azure ARM / Cost Mgmt  (service principal, or az CLI locally)
FastAPI → Databricks workspaces  (OAuth SP in prod; az CLI/profile locally)
```

### 1.3 Database

- PostgreSQL via `DATABASE_URL` (`postgresql+asyncpg://…`), pool 10/20, `pool_pre_ping`, recycle 1800 s, TLS via `DB_SSL_MODE` (`backend/.../db/session.py`).
- 4 Alembic revisions (`2026_10_12_0001` … `2026_11_13_0004`). Migrations are **never run on startup** by design; they run via `backend/scripts/run_migrations.py` (good, matches policy).
- Repo does not provision a database. `app.yaml` comments reference an Azure Database for PostgreSQL Flexible Server (`psql-finops-prod`) that is **[UNVERIFIED]** as existing.

### 1.4 Authentication

| Layer | Mechanism | State |
| :--- | :--- | :--- |
| User → backend | Entra ID RS256 JWT validation (`core/auth.py`), `entra_auth_enabled` | **Default `False`** → all `/api/v1/*` routes are effectively open unless enabled. Tenant default hard-coded; audience default `None`. |
| User → Fabric frontend | Rayfin Fabric auth provider (SSO inside portal, popup outside) | Implemented in `rayfin-auth.service.ts` |
| Backend → Azure | `AZURE_AUTH_METHOD`: `service_principal` (default) / `default_azure_credential` / `azure_cli` | Read-only by policy |
| Backend → Databricks | `DATABRICKS_AUTH_TYPE`: `oauth` (SP, prod), `azure-cli`/profile (default, local only) | Default is local-dev only |
| Backend → Fabric/OneLake | `FABRIC_*` SP settings, `fabric_enabled=False` | **Disabled by flag**; core app does not call the Lakehouse |
| Approval tokens | HMAC signing (`finops_signing_secret`, kid ring) | Secret optional in config; must be explicit in prod |

### 1.5 Background work and external dependencies

- **In-process asyncio refresher** (`services/databricks/refresher.py`), started in FastAPI `lifespan` every 60 s (inventory) / 600 s (metadata) for recently used connections. Needs an **always-on** instance; it is per-process (not shared across replicas).
- No Celery/APScheduler/cron. Sync agent and lakehouse scripts are manual CLIs.
- Outbound calls: Azure ARM, Azure Cost Management, Azure Retail Prices, Databricks workspace REST + SQL warehouse, optional Azure AI Foundry (`LLM_PROVIDER=mock` by default), optional GCP Billing Catalog, `login.microsoftonline.com` (JWKS).
- **No Dockerfile / docker-compose exists** in the repository.
- CI (`.github/workflows/ci.yml`) covers `backend/` and `frontend/` only; **`fabric-integration/` is not in CI**.

---

## 2. What Is Already Ready

1. **Fabric App item deployed once**: `rayfin/.deployments.json` records item `finops-app` (`31c70ef5-…`), workspace `672a6995-4190-4000-befd-5cc6479c3f74`, hosting URL `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net`, deployed 2026-11-05. Whether it is still live is **[UNVERIFIED]**.
2. **Rayfin config** (`rayfin/rayfin.yml`): auth enabled with Fabric + `externalEntraExchange`, password auth disabled, static hosting wired to `packages/frontend/dist`, redirect URI for the hosting URL present.
3. **Fabric-ready SPA** with Rayfin auth gate, a typed API layer (`lib/api.ts`) with `VITE_API_BASE_URL` override and Bearer-token forwarding, and Vitest suites.
4. **Backend CORS already allows** `https://app.fabric.microsoft.com` and the existing `*.webapp.fabricapps.net` host (`core/config.py`).
5. **Backend is production-shaped**: structured logging, TLS-capable pool settings, migrations decoupled from startup, Entra JWT validator with JWKS cache, credential redaction in Databricks auth, offline/mock modes, health endpoints at `/health` and `/api/v1/health`.
6. **Databricks Apps packaging** (`app.yaml` + supervisor) proves the backend runs headless in a container-like runtime with env-injected secrets.
7. **Lakehouse**: `finops_lakehouse` (`4bba3647-…`) and 5 Delta tables scripted and verified locally per `docs/FABRIC_L2_IMPLEMENTED_ARCHITECTURE.md`.
8. Existing runbooks to build on: `docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md`, `PRODUCTION_DATABASE_CONFIGURATION.md`, `PRODUCTION_SECRETS_AND_SECURITY.md`.

---

## 3. What Is Missing

| # | Gap | Impact |
| :--- | :--- | :--- |
| M1 | **No backend hosting target** (no Dockerfile, no IaC, no App Service / Container Apps definition). | Blocker |
| M2 | **No provisioned PostgreSQL** confirmed; no private-network design. | Blocker |
| M3 | **Fabric frontend is wired to the UDF, not the backend** (`VITE_USE_FABRIC_UDF=true` in `.env.production`, `rayfin/.env`, `.env.local`). `getApiBaseUrl()` returns the UDF URL in that mode, and 30+ `/finops/*`, `/databricks/*`, `/configuration/*`, `/ingestion/*` calls use `${API_BASE_URL}/…`, which do not exist on the UDF. | Blocker (functional) |
| M4 | **UDF has no Databricks capability** (0 occurrences of "databricks" in `function_app.py`; 16 functions: connections, inventory, cost-waste, metrics, token economics, pricing, cost analytics, sync/lakehouse health). | Major functional gap if UDF path is used |
| M5 | **Token audience not proven.** The Fabric frontend must send a token the FastAPI validator accepts (`entra_audience`, issuer v1/v2). `api.ts` falls back to scanning `localStorage` for a Rayfin session. A Rayfin/Fabric session token is not guaranteed to carry the backend's audience. | Blocker for secure prod **[UNVERIFIED]** |
| M6 | **No Entra app registration for the backend API** (audience/scope/app roles) documented as created. | Blocker |
| M7 | **No secret store design** for the backend (Key Vault + managed identity). `app.yaml` uses Databricks-only `{{secrets/…}}` syntax that is not portable. | Major |
| M8 | **No scheduler** for the sync agent / lakehouse ingestion. | Only if Lakehouse path is in scope |
| M9 | **Frontend parity not confirmed** between Next.js `frontend/` and Vite `finops-app` (separate codebases, different React/Tailwind majors). | Risk of functional regression |
| M10 | **Frontend tests/CI** for `fabric-integration/finops-app` not in CI; AGENTS.md validation sequence only covers `frontend/`. | Process gap |
| M11 | **Tech-stack lock**: AGENTS.md locks the frontend to Next.js. The Vite/Rayfin app deviates; it needs explicit approval (ideally an ADR). | Governance |
| M12 | No observability for the hosted backend (Log Analytics / App Insights wiring). | Major |

---

## 4. Fabric Apps Compatibility Assessment

Basis: installed Rayfin docs (`hosting/index.md`, `app-backend/deploy.md`, `pricing.md`, `known-limitations.md`) and `rayfin.yml`.

| Component | Compatible with Fabric Apps? | Verdict / Reason |
| :--- | :---: | :--- |
| Vite/React frontend (`finops-app`) | **Yes** | Built to `packages/frontend/dist`, zipped (100 MB max) and served from OneLake by Rayfin static hosting. Current `dist` is small. |
| Next.js 14 frontend (`frontend/`) | **No** | Needs a Node server and server-side rewrites. Converting to `output: export` would drop the `/api` rewrite and any server features and must be re-tested; the Vite app is the supported route. |
| FastAPI backend | **No (separate hosting)** | No Python web-service runtime in Fabric Apps. Rayfin Functions are TypeScript (Azure Functions kit), not a host for this FastAPI codebase. Rewriting 12 route modules in TS is out of scope and would violate "focused, incremental changes". |
| PostgreSQL | **No (external)** | Fabric Apps' own data module uses Fabric SQL (mssql/postgresql dialect via Rayfin) and is `enabled: false`. Existing app data stays in external PostgreSQL behind FastAPI. |
| Fabric UDF | **Yes, but partial** | Runs in Fabric, but provides a different, smaller API surface; operational store is ephemeral SQLite in `/tmp`. Not a substitute for the backend. |
| Databricks integration | **Yes, via backend** | Backend → Databricks REST/SQL warehouse is unchanged. Not reachable from the browser directly or from the UDF. |
| Azure integration | **Yes, via backend** | Unchanged. |
| Fabric Lakehouse integration | **Optional** | Already feature-flagged off (`fabric_enabled=False`, `ENABLE_MICROSOFT_FABRIC=false`). Keep off for V1. |
| Background refresher | **Backend only** | Requires an always-on host (no scale-to-zero). |
| Rayfin auth | **Yes** | Fabric SSO in portal, popup outside. Passwords disabled. |

### Hosting-setting concern
`rayfin.yml` has `staticHosting.assetAccess: public`, whereas the template README says the intended default is `protected`. A public asset host means the SPA bundle (including any embedded IDs) is downloadable without sign-in. Decide deliberately (see Risk R9).

---

## 5. Recommended Deployment Architecture

**Hybrid: Fabric Apps for the UI shell and identity, Azure for compute and data.**

```
                     ┌──────────────────────── Microsoft Fabric (workspace 672a6995…, capacity F-SKU) ────────────────────────┐
 User ──SSO──►       │  Rayfin static hosting (OneLake)  ←  packages/frontend/dist (Vite SPA, VITE_USE_FABRIC_UDF=false)     │
 (Entra ID)          └──────────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                                        │ HTTPS + Entra Bearer token (CORS: hosting URL only)
                                                                        ▼
                                     Azure Container Apps (or App Service Linux), min replicas = 1, system-assigned managed identity
                                     FastAPI (uvicorn), entra_auth_enabled=true, refresher on
                                        │                │                    │                      │
                           Key Vault ◄──┘      PostgreSQL Flexible      Azure ARM / Cost       Databricks workspaces
                       (secrets via MI)        Server (TLS, private)     (Reader roles only)    (OAuth SP, CAN_USE warehouse)
```

Key decisions:

1. **Backend host:** Azure Container Apps (preferred; matches Python 3.12 container, secrets from Key Vault) or App Service Linux. Single replica initially, because the refresher cache and in-memory state are per-process.
2. **Database:** Azure Database for PostgreSQL Flexible Server, TLS required, with VNet integration or firewall limited to the backend's egress; separate least-privilege app user; migrations run by an operator step, not at startup.
3. **API URL:** set `VITE_API_BASE_URL=https://<backend-fqdn>/api/v1` and `VITE_USE_FABRIC_UDF=false` for the production Fabric build. Frontend code change required only if a hybrid (UDF for some calls, backend for others) is wanted (see §6).
4. **Auth:** register a backend API app in Entra; set `ENTRA_AUTH_ENABLED=true`, `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE`. Validate (spike, Step 4 below) which token the Rayfin SDK exposes and request the backend scope explicitly if needed.
5. **Keep UDF/Lakehouse out of the V1 path** (flag-off). They can be a V2 phase with a scheduler.

---

## 6. Application Changes Required (all need your approval; none made)

| ID | Change | File(s) | Size | Protected-area note |
| :--- | :--- | :--- | :---: | :--- |
| C1 | Add backend `Dockerfile` (python:3.12-slim, `uv`/pip install, `uvicorn cloud_recommender.main:app`, non-root, `/health` probe) and `.dockerignore` | new files | S | New files only |
| C2 | Production Fabric build env: `VITE_API_BASE_URL`, `VITE_USE_FABRIC_UDF=false` | `packages/frontend/.env.production`, `rayfin/.env` | XS | Config only |
| C3 | Acquire backend-audience Entra token in the SPA (MSAL scope or Rayfin broker) and stop relying on the `localStorage` scan | `lib/api.ts`, `services/rayfin-auth.service.ts` | M | Needs design after spike |
| C4 | Make `getApiBaseUrl()` not return the UDF URL for non-UDF routes (hybrid-safe), or remove the UDF branch for FinOps routes | `lib/api.ts` | S | – |
| C5 | Parametrize CORS (`CORS_ORIGINS` env, already supported) with only the real Fabric host; drop localhost in prod | env only | XS | – |
| C6 | Replace hard-coded IDs (workspace/UDF/tenant defaults) with env-required values in prod | `core/config.py`, `fabric-udf-client.ts` | S | `config.py` is not in the protected list, `schemas/domain.py` is untouched |
| C7 | Fail-fast on insecure defaults when `APP_ENV=production` (`SECRET_KEY`, missing `FINOPS_SIGNING_SECRET`, `ENTRA_AUTH_ENABLED=false`) | `core/config.py` | S | – |
| C8 | Add `fabric-integration/finops-app` lint/typecheck/test/build to CI | `.github/workflows/ci.yml` | S | – |
| C9 | ADR approving Vite/Rayfin as the Fabric-hosted frontend (tech-stack boundary) | `docs/ADR/` (new file; existing ADRs untouched) | S | **Requires your consent per AGENTS.md** |
| C10 | Decide `assetAccess: protected` vs `public` | `rayfin/rayfin.yml` | XS | – |

If you prefer **no code change**, the only no-code path is: C2 + C5 + C1 are config/new files, but M5/C3 (token audience) may still force a code change. This is the single largest unknown.

---

## 7. Deployment Requirements

### 7.1 Software and CLI tools
| Tool | Version | Used for |
| :--- | :--- | :--- |
| Node.js | 20 LTS+ | Fabric SPA build, Rayfin CLI |
| npm | 10+ | workspace install |
| `@microsoft/rayfin-cli` | 1.36.x (devDependency; `npx rayfin …`) | Fabric deploy |
| Python | 3.12 | backend, migrations |
| `uv` (or pip) | current | backend deps (`uv.lock` present) |
| Azure CLI (`az`) | 2.60+ | provisioning backend hosting, Key Vault, PostgreSQL |
| Docker (or `az acr build`) | current | build backend image |
| `psql` client | 16 | verify DB connectivity |
| Git | any | – |

### 7.2 Fabric workspace and capacity
- Existing workspace `672a6995-4190-4000-befd-5cc6479c3f74` (north central US) with a capacity assigned (`c456892f-…` recorded) **[UNVERIFIED: still active / not paused / not trial-expired]**.
- Capacity SKU: F2 is enough for static hosting only; the Lakehouse/UDF path adds consumption.
- Tenant admin settings that must allow: Fabric data apps / Rayfin preview, user-data-function and service-principal API access (if SP login is used for CI).

### 7.3 Permissions (all least-privilege and read-only for customer cloud)
| Principal | Where | Role |
| :--- | :--- | :--- |
| Deployer (human or SP) | Fabric workspace | Member or Contributor (needed to create/update the app item) |
| Backend managed identity | Key Vault | Key Vault Secrets User |
| Backend SP / identity | Azure subscription(s) | **Reader**, **Cost Management Reader**, **Monitoring Reader** only |
| Backend Databricks SP | Databricks workspace | Entitlement to use the SQL warehouse (CAN USE), `SELECT` on required `system.*` tables, workspace read. No admin, no cluster create |
| DB app user | PostgreSQL | CONNECT + DML on app schema; separate migration user with DDL |
| End users | Entra app roles | As defined by `core/auth.py` role checks |

Never assign Contributor/Owner on customer subscriptions (AGENTS.md rule 3).

### 7.4 Environment variables

**Backend (Container App) — secrets go to Key Vault, never to repo:**

| Variable | Secret? | Notes |
| :--- | :---: | :--- |
| `APP_ENV=production`, `DEBUG=false`, `LOG_FORMAT=json` | – | |
| `API_HOST=0.0.0.0`, `API_PORT=8000` | – | |
| `CORS_ORIGINS` | – | exactly the Fabric hosting URL |
| `SECRET_KEY` | ✔ | replace the insecure default |
| `ENTRA_AUTH_ENABLED=true`, `ENTRA_TENANT_ID`, `ENTRA_AUDIENCE` | – | |
| `DATABASE_URL`, `DB_SSL_MODE=require`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | ✔ (URL) | |
| `AZURE_AUTH_METHOD=service_principal`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_SUBSCRIPTION_ID` | – | |
| `AZURE_CLIENT_SECRET` | ✔ | |
| `DATABRICKS_AUTH_TYPE=oauth`, `DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID`, `DATABRICKS_PROD_*`, `DATABRICKS_WORKSPACES_JSON` | – | production defaults in `config.py` point at the dev workspace; set explicitly |
| `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` | ✔ | |
| `FINOPS_SIGNING_SECRET`, `FINOPS_SIGNING_KID`, `FINOPS_VERIFICATION_KEYS` | ✔ | explicit; shared if >1 replica |
| `FINOPS_MONTHLY_BUDGET_USD` | – | |
| `LLM_PROVIDER=mock` (or `azure_openai` + `AZURE_AI_FOUNDRY_*`) | key ✔ | |
| `OFFLINE_PRICING_MODE`, `PRICING_CACHE_TTL_HOURS` | – | |
| `DATABRICKS_INVENTORY_REFRESH_SECONDS`, `DATABRICKS_METADATA_REFRESH_SECONDS` | – | |
| `FABRIC_ENABLED=false` | – | keep off for V1 |

**Fabric SPA (build-time `VITE_*`, public by nature — no secrets):**
`VITE_API_BASE_URL`, `VITE_USE_FABRIC_UDF=false`, `VITE_FABRIC_WORKSPACE_ID`, `VITE_FABRIC_TENANT_ID`, plus the Rayfin vars generated by `rayfin env` (`VITE_RAYFIN_API_URL`, `VITE_RAYFIN_PUBLISHABLE_KEY`, `VITE_FABRIC_ITEM_ID`, `VITE_FABRIC_PORTAL_URL`).

### 7.5 Configuration files
| File | Action |
| :--- | :--- |
| `fabric-integration/finops-app/rayfin/rayfin.yml` | keep; add the final redirect URIs; decide `assetAccess` |
| `fabric-integration/finops-app/packages/frontend/.env.production` | set `VITE_API_BASE_URL`, `VITE_USE_FABRIC_UDF=false` |
| `backend/Dockerfile`, `.dockerignore` | **new** |
| IaC (Bicep/`az` script) for Container App, ACR, Key Vault, PostgreSQL, Log Analytics | **new** |
| `app.yaml`, `run_databricks_app.py` | unchanged (Databricks Apps path stays available) |

### 7.6 Build and deploy commands (reference; not executed)

```powershell
# --- Backend image ---
cd backend
uv sync --frozen --no-dev                       # or: pip install -r requirements.txt
az acr build -r <acr> -t cloud-recommender-api:5.1.0 .          # requires new Dockerfile (C1)

# --- Database (operator-run, once per release) ---
$env:DATABASE_URL = "postgresql+asyncpg://<migrator>:<pw>@<pg>.postgres.database.azure.com:5432/cloud_recommender"
$env:DB_SSL_MODE  = "require"
python backend/scripts/run_migrations.py        # review flags with --help; confirm approval first

# --- Fabric SPA ---
cd fabric-integration/finops-app
npm ci
npm run typecheck ; npm run lint ; npm test
npm run build:fabric
npx rayfin login status
npx rayfin up -n --workspace-id 672a6995-4190-4000-befd-5cc6479c3f74     # dry run / preview
npx rayfin up --json --workspace-id 672a6995-4190-4000-befd-5cc6479c3f74 # real deploy, after approval
```

Repo validation (AGENTS.md §5) before any release:
`ruff check backend/`, `ruff format --check backend/`, `mypy backend/`, `pytest backend/tests/ -v --cov=backend/app`, `npm --prefix frontend run lint|typecheck|build`, plus the equivalent for `fabric-integration/finops-app`.

---

## 8. Step-by-Step Deployment Plan

Each step that writes to a cloud resource requires your explicit approval first.

| # | Step | Output | Gate |
| :--: | :--- | :--- | :--- |
| 0 | Approve architecture (§5), ADR for Vite/Rayfin frontend (C9), and change list (§6) | signed-off scope | **You** |
| 1 | Verify Fabric prerequisites (read-only): `npx rayfin login status`, workspace + capacity state, tenant settings, whether the Nov-05 app is still live | checklist | read-only |
| 2 | **Spike (no deploy):** confirm which token the Rayfin SDK yields and whether it can carry a backend-audience Entra token; decide C3 | design note | blocker for step 8 |
| 3 | Provision Azure resources: resource group, Log Analytics, Key Vault, ACR, PostgreSQL Flexible Server (private/firewalled, TLS), Container Apps env | IaC applied | approval |
| 4 | Entra: backend API app registration (audience, scope/roles); optionally SPA registration; grant admin consent | IDs recorded | approval |
| 5 | Grant read-only roles: Azure Reader / Cost Management Reader / Monitoring Reader; Databricks SP entitlements + warehouse CAN USE + `system.*` SELECT | access verified with existing audit scripts (`backend/scripts/databricks_access_audit.py`) | approval |
| 6 | Load secrets into Key Vault; grant backend MI "Secrets User" | secret refs | approval |
| 7 | Build and push backend image; run migrations as a separate controlled step; deploy Container App (min 1 replica, `/health` probes) | live API | approval |
| 8 | Apply approved code changes C2–C8, run full validation checklist locally | green CI | – |
| 9 | Build Fabric SPA with production env; `rayfin up -n`; review target workspace/item; then `rayfin up --json` | hosting URL | approval |
| 10 | Update backend `CORS_ORIGINS` and Entra redirect URIs to final hosting URL | CORS/redirect OK | – |
| 11 | Smoke tests: sign-in; `/health`; Databricks connection test; Azure discovery; FinOps overview KPIs; cost explorer; zero-write verification (no Contributor/Owner anywhere) | evidence file | – |
| 12 | Enable monitoring and alerts; document runbook and rollback | ops docs | – |

**Rollback:** Fabric: redeploy previous `dist` (`rayfin up` from previous commit). Backend: previous image tag / Container Apps revision. DB: Alembic downgrade only with a verified backup (take PITR snapshot before step 7).

---

## 9. Database and Backend Hosting Plan

**Backend**
- Azure Container Apps, 1 vCPU / 2 GiB to start, `minReplicas=1`, `maxReplicas=1` until the refresher cache is made shareable.
- Ingress HTTPS only; health probes on `/health`; non-root container; secrets from Key Vault references; managed identity; egress to Azure ARM, Databricks and `login.microsoftonline.com` must be allowed (and `prices.azure.com` if live pricing is enabled).
- Python 3.12 (`pyproject` pins `>=3.12,<3.13`; AGENTS.md states 3.11+, so build for 3.12).

**Database**
- Azure Database for PostgreSQL Flexible Server (v16), Burstable B2s (or B1ms for demo), 32 GiB, TLS required, PITR enabled.
- Two roles: `finops_migrator` (DDL, used only in step 7) and `finops_app_user` (DML).
- Connectivity: either VNet-integrate Container Apps and PostgreSQL (private), or allow the Container Apps outbound IPs only. **Do not expose the DB to the Fabric SPA** — it is browser-side and must never hold a DB connection.
- Initial data: run the 4 migrations; catalog seed via existing `catalog/seeds.py` path if required **[confirm with owner]**.

**Fabric data / Lakehouse (V2, optional)**
- Keep `FABRIC_ENABLED=false`. If enabled later: schedule `sync-agent` via a Fabric pipeline or Container Apps job; do not use the UDF's `/tmp` SQLite as a system of record.

---

## 10. Security and Deployment Risks

| ID | Risk | Severity | Evidence | Mitigation |
| :--: | :--- | :---: | :--- | :--- |
| R1 | **Backend open to the internet without auth**: `entra_auth_enabled` defaults to `False`; all FinOps endpoints return cost data | **High** | `core/config.py`, `api/v1/router.py` | Enable Entra, fail-fast in prod (C7); network restriction as defence in depth |
| R2 | **Token audience mismatch** between Rayfin session and backend validator (M5) | **High** | `core/auth.py`, `lib/api.ts` | Step-2 spike; explicit scope |
| R3 | **Fabric frontend currently bypasses the backend** (UDF mode) → Databricks/FinOps modules broken | **High** | `.env.production`, `lib/api.ts` | C2/C4 |
| R4 | `localStorage` token scan fallback and stored Entra token are XSS-sensitive | Medium | `lib/api.ts` | Prefer in-memory token; CSP; minimize third-party scripts |
| R5 | Insecure default `SECRET_KEY`; optional `FINOPS_SIGNING_SECRET` (approval-token HMAC) | High | `core/config.py` | Mandatory in prod (C7); rotate via kid ring |
| R6 | Secrets in env/files: real credentials exist in local `.env` (gitignored); `app.yaml` commits subscription ID and workspace IDs | Medium | `.env`, `app.yaml`, `config.py` | Key Vault; never copy `.env`; rotate anything that was ever shared; remove hard-coded IDs (C6) |
| R7 | CORS `allow_credentials=True` with `allow_methods/headers=["*"]` and localhost origins in default list | Medium | `main.py`, `config.py` | Env-restrict origins in prod (C5) |
| R8 | CORS/redirect mismatch after any re-deploy (hosting URL is generated per item) | Medium | `rayfin.yml`, `config.py` | Pin in env; test in step 10 |
| R9 | `assetAccess: public` on Fabric static host | Medium | `rayfin.yml` | Switch to protected unless public bundle is intended |
| R10 | Corporate proxy blocked the previous Fabric static deploy (Zscaler 403 on `…/__private/webapp/deploy`, log dated 2026-11-02) | Medium | `fabric-deployment-error.log` | Allow-list `api.fabric.microsoft.com` for deployer, or deploy from a CI runner/Cloud Shell. A later deploy succeeded on 2026-11-05, but the network dependency remains |
| R11 | Rayfin is **alpha/preview** (`^1.36.0-alpha`): API/behaviour may change; no SLA assumed | Medium | `package.json` | Pin versions, lockfile, test before each deploy |
| R12 | Refresher is per-process and always-on; scale-out or scale-to-zero gives stale or cold caches and duplicate Databricks REST calls | Medium | `refresher.py` | Single replica, `minReplicas=1` |
| R13 | Databricks defaults point to dev workspace and `azure-cli` auth (not available in containers) | Medium | `config.py` | Explicit prod env, `oauth` |
| R14 | SQL warehouse cost: dashboards may wake a stopped warehouse | Medium | AGENTS.md policy mentions "stopped warehouse remains stopped" | Keep read-only/no-wake behaviour; budget alert |
| R15 | Two diverging frontends (Next.js vs Vite) and two API clients (backend vs UDF) | Medium | repo structure | Declare Vite as Fabric UI; add parity test checklist; CI (C8) |
| R16 | UDF stores connection secrets encrypted with Fernet but in `/tmp` SQLite (ephemeral, per-instance) | Medium | `function_app.py:2348` | Keep UDF out of V1 |
| R17 | Zero-execution boundary | Low | Backend has no write paths to customer clouds; all integrations read-only by design | Keep; verify role assignments at step 5 |
| R18 | No DR/backup design yet | Medium | – | PITR + documented restore |
| R19 | Mixed Python version statements (3.11+ vs `<3.13` pin) | Low | `AGENTS.md`, `pyproject.toml` | Build 3.12 image |

Existing-functionality regression risk is **Medium**: the Fabric SPA has not been proven to cover every screen of the Next.js app (M9).

---

## 11. Estimated Costs and Assumptions

> Figures are **indicative US list prices from general knowledge, not retrieved from the Azure Retail Prices API.** Per project rule 2, re-verify with the deterministic pricing engine (`services/pricing`) or the official calculator before committing a budget. Region assumed: North Central US / East US.

| Item | Assumption | Indicative USD / month |
| :--- | :--- | ---: |
| Fabric capacity (static hosting only) | F2 pay-as-you-go, 24×7 (can be paused outside demos) | ~260 (≈ 65–100 if paused to ~25–40 % uptime) |
| Fabric static hosting / OneLake | small bundle, low traffic | included in CU use, negligible |
| Container Apps (backend) | 1 vCPU / 2 GiB always-on, 1 replica | 45–70 |
| Azure Container Registry | Basic | ~5 |
| PostgreSQL Flexible Server | Burstable B2s, 32 GiB, PITR | 35–60 (B1ms demo: ~15–25) |
| Key Vault | < 10k operations | < 2 |
| Log Analytics / App Insights | < 5 GB/month | 10–15 |
| Entra ID | existing tenant | 0 |
| Databricks SQL warehouse (queries issued by the app) | usage-driven, serverless; **largest variable** | usage-based; set budget alert |
| Azure Cost Management / ARM / Retail Prices APIs | read-only | 0 |
| Optional Azure AI Foundry | only if `LLM_PROVIDER` is not `mock` | usage-based |
| Optional Lakehouse/UDF path | extra CU consumption | not included |

**Estimated steady-state total (excluding Databricks warehouse usage):** roughly **US$ 360–420 / month** with an always-on F2; **US$ 160–220 / month** if the Fabric capacity is paused when idle (note: a paused capacity makes the hosted UI unavailable). **One-time:** engineering effort only (§12); no licence purchase identified.

Cost drivers to monitor: Fabric CU consumption (Capacity Metrics app), warehouse DBUs, DB tier, log ingestion.

---

## 12. Estimated Deployment Time

| Phase | Effort (1 engineer + occasional admin) |
| :--- | :---: |
| Approvals, ADR, prerequisites verification (steps 0–1) | 0.5–1 day |
| Token/auth spike (step 2) | 1 day |
| Azure provisioning, Entra, role grants (3–6) | 1.5–2 days (admin lead times may extend) |
| Backend containerisation + migrations + deploy (7) | 1–1.5 days |
| Frontend changes C2–C8 + tests (8) | 1.5–3 days (depends on C3 outcome) |
| Fabric deploy + CORS/redirect fix-ups (9–10) | 0.5 day |
| Smoke/regression, security review, runbook (11–12) | 1.5–2 days |
| **Total** | **~7–11 working days** (≈ 2 calendar weeks); 3–4 days if the token spike proves no code change is needed and Azure resources already exist |

---

## 13. Final Recommendation

### **CONDITIONAL GO — hybrid architecture only**

- **NO-GO** for "deploy the existing application to Fabric Apps as-is": the FastAPI backend and PostgreSQL cannot run on Fabric Apps, the Next.js frontend cannot be statically hosted as-is, and the current Fabric build routes to a UDF that lacks all Databricks FinOps endpoints.
- **GO** for: Vite/React SPA on Fabric Apps + FastAPI on Azure Container Apps + Azure PostgreSQL Flexible Server, **provided** these gates are closed first:
  1. Your approval of the architecture and of the Vite/Rayfin deviation from the locked frontend stack (ADR).
  2. Token-audience spike (M5/R2) succeeds, with backend Entra validation **enabled**.
  3. Production env fixes (R3, R5, R7, R13) applied, no secrets in the repo.
  4. Read-only roles confirmed for Azure and Databricks.
  5. Network path for `rayfin up` is allowed from the deploying machine (R10).

Alternative if the goal is simply a hosted internal demo: the existing **Databricks Apps** package (`app.yaml`, `run_databricks_app.py`) already runs frontend + backend together and avoids the split-hosting complexity; Fabric would then serve only as an optional front door.

---

## Appendix A — Evidence Index

| Finding | Source |
| :--- | :--- |
| Next.js rewrites, no static export | `frontend/next.config.mjs` |
| Fabric hosting config | `fabric-integration/finops-app/rayfin/rayfin.yml` |
| Prior deployment record | `fabric-integration/finops-app/rayfin/.deployments.json` (git-ignored) |
| UDF mode flag | `packages/frontend/.env.production`, `rayfin/.env` |
| Base URL logic | `packages/frontend/src/lib/api.ts:28-51` |
| UDF function inventory | `fabric-integration/fabric-udf/function_app.py:4590-4840` |
| Auth default off | `backend/src/cloud_recommender/core/config.py` (`entra_auth_enabled`) |
| Refresher in lifespan | `backend/src/cloud_recommender/main.py`, `services/databricks/refresher.py` |
| Migrations never at startup | `backend/scripts/run_migrations.py` |
| Static hosting limits and pricing | `@microsoft/rayfin-guide/assets/docs/hosting/index.md`, `app-backend/pricing.md`, `app-backend/deploy.md` |
| Fabric subsystem status | `docs/FABRIC_L2_IMPLEMENTED_ARCHITECTURE.md` |
| Failed deploy (proxy) | `fabric-integration/finops-app/fabric-deployment-error.log` |

## Appendix B — Open Questions for You

1. Is the goal a **Fabric-hosted UI** (hybrid) or just "somewhere accessible in the Microsoft ecosystem" (Databricks Apps already works)?
2. Do you approve **Vite/Rayfin** as the Fabric UI (ADR) given the Next.js stack lock?
3. Which Azure subscription/resource group may host the backend and PostgreSQL, and who can create Entra app registrations and grant admin consent?
4. Is the existing Fabric App (Nov-05 deployment) to be updated in place or replaced?
5. Should the Lakehouse/UDF path stay off for V1?

*Stopping here as instructed. No changes will be made until you approve.*
