# Azure App Service — Backend Production Readiness Checklist

Date 2026-11-17 · target `FinopsBackendApp` (resource group `bizmetric-central-platform-genai`, subscription `9636348b-8445-4441-94d2-f6191f131721`, Central India, Linux, Python 3.12, no deployment slots).
Read-only investigation. **Nothing was deployed, restarted, changed, migrated or generated.** No secret value appears in this document (only variable names). Awaiting your approval before any change.

## 0. Bottom line

| Finding | Evidence |
|---|---|
| The app returns **503** because `APP_ENV=production` is set but the production security settings are missing; `validate_for_serving()` refuses to start. | Azure has only 5 settings (below); `GET /health` → 503 after ~25 s. |
| **No database exists for the app yet** — no `DATABASE_URL`, no PostgreSQL server is visible in the subscription, so migrations cannot run. | `az postgres flexible-server list` → `[]`; default URL is `localhost`. |
| **Entra settings need IT**: a backend API app registration plus the SPA client ID (the same registration still pending for Fabric). | Needed by `ENTRA_*`; none exists in config. |
| **A TLS-inspection proxy (Zscaler) sits between this PC and `*.azurewebsites.net`.** It breaks Python-based Azure CLI calls to Kudu (`CERTIFICATE_VERIFY_FAILED`) and likely the browser SCM error. | Certificate issuer for `*.scm…azurewebsites.net` is *Zscaler Intermediate Root CA*; `az webapp log download` failed with `unable to get local issuer certificate`. |
| The configured **startup command is valid** for the ZIP layout; `startup.sh` is the more complete equivalent. | §3. |
| The ZIP is **functionally correct but contains ~41 MB of dev caches** and tests; no `.env`, no real secrets found. | §4. |

**Correction to my previous message:** I said `az webapp deploy` from this PC would work. A `curl` probe reached the SCM host (HTTP 401) because Windows trusts the Zscaler CA, but the Azure CLI uses its own certificate store and **fails verification** until the Zscaler root is supplied (§6.1). Use that fix or deploy from a network without TLS inspection.

## 1. Environment variables

Source of truth: `backend/src/cloud_recommender/core/config.py` (98 settings, all with defaults) plus `validate_for_serving()`. "Production-mandatory" means startup fails with `APP_ENV=production` if it is missing/unsafe. Secrets are marked 🔒 (store as App Service settings or Key Vault references; never in the ZIP).

### 1.1 Present in Azure today (names only; values of non-secrets checked)

| Name | Value | Assessment |
|---|---|---|
| `APP_ENV` | `production` | Triggers the strict checks below. |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` | OK (Oryx installs `requirements.txt`). |
| `LLM_PROVIDER` | `mock` | OK; use `azure_openai` only with the Foundry settings (§1.4). |
| `CATALOG_OFFLINE_MODE` | `true` | Safe default for a demo; live catalogue disabled. |
| `WEBSITE_HTTPLOGGING_RETENTION_DAYS` | — | Platform setting. |

### 1.2 Production-mandatory — all currently MISSING

| Variable | Expected format / rule | Where it comes from | Needs IT? |
|---|---|---|---|
| `ENTRA_AUTH_ENABLED` | `true` | You set it | No |
| `ENTRA_TENANT_ID` | Tenant GUID: `fe82a67c-faa7-4d9a-bbfa-7d25b7047b41` (from your tenant; not invented) | Known | No |
| `ENTRA_AUDIENCE` | Must **exactly equal the token `aud`**: normally the backend API app registration's **Application (client) ID GUID** (v2 tokens) or its `api://<id>` URI (v1 tokens) | Backend API app registration | **Yes** |
| `ENTRA_REQUIRED_SCOPES` | Comma list; default `access_as_user` (the scope the registration must expose) | Registration → *Expose an API* | **Yes** |
| `ENTRA_ALLOWED_CLIENT_IDS` | Comma list of **GUIDs** of approved SPA clients (the `azp` claim) | SPA registration client ID | **Yes** |
| `SECRET_KEY` 🔒 | ≥ 32 chars, ≥ 8 distinct characters, no placeholder words | You generate a random value; **I did not generate one** | No |
| `FINOPS_SIGNING_SECRET` 🔒 | Same rule; signs billing approval tokens | You generate | No |
| `CORS_ORIGINS` | Explicit `https://` origins only, no localhost or `*`, e.g. `https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net,https://app.fabric.microsoft.com` (must be set explicitly; the in-code default contains localhost and is rejected) | The Fabric app hosting URL (verified) | No |
| `DEBUG` | `false` (default) | — | No |
| `CONNECTION_STORE` | `database` (default) | — | No |
| `CONNECTION_KEY_PROVIDER` | `keyvault` **or** `env` (default `local_file` is rejected) | Decision | See §1.3 |
| `ALLOW_CLI_CONNECTIONS` | `false` (default) | — | No |

### 1.3 Credential-encryption key (one of two)

| Provider | Variables | Notes |
|---|---|---|
| `env` | `CONNECTION_ENCRYPTION_KEYS` 🔒 = JSON `{"<kid>":"<base64 of 32 bytes>"}`, `CONNECTION_ACTIVE_KEY_ID=<kid>` | Simplest; the key is an App Service secret. You generate the 32 random bytes. |
| `keyvault` | `KEY_VAULT_URL`, `CONNECTION_KEY_SECRET_NAME` (+ the secret in the vault) | Requires a **managed identity on the web app (currently none)** with *Key Vault Secrets User* and the vault's network access. The only vault visible is `akv-deaccelerator-dev` (another project's dev vault) — not recommended without IT. **IT needed.** |

### 1.4 Required for the database (not enforced at boot, but nothing persistent works without them)

| Variable | Expected | Source |
|---|---|---|
| `DATABASE_URL` 🔒 | `postgresql+asyncpg://<user>:<password>@<host>:5432/<db>` (the code adds SSL via `DB_SSL_MODE`) | **IT / your DBA**: no PostgreSQL server found |
| `DB_SSL_MODE` | `require` for Azure Database for PostgreSQL (default `prefer`) | You |

The database is connected lazily: the app **starts without it**, health works, and database endpoints answer `503 DATABASE_UNAVAILABLE`.

### 1.5 Optional / integration-specific

| Variable(s) | Purpose | Notes |
|---|---|---|
| `AZURE_AI_FOUNDRY_ENDPOINT`, `AZURE_AI_FOUNDRY_DEPLOYMENT_NAME`, `AZURE_AI_FOUNDRY_API_KEY` 🔒, `AZURE_AI_FOUNDRY_API_VERSION`, `AZURE_AI_FOUNDRY_AUTH_TYPE`, `LLM_PROVIDER=azure_openai` | AI architect features | Only if you switch off `mock` |
| `DATABRICKS_HOST`, `DATABRICKS_WORKSPACE_ID`, `DATABRICKS_WAREHOUSE_ID`, `DATABRICKS_AUTH_TYPE`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` 🔒, `DATABRICKS_PROD_*`, `DATABRICKS_WORKSPACES_JSON` | Databricks integration | Defaults point at your Dev workspace and use `azure-cli` auth, **which does not exist on App Service** — use a service principal (IT). To avoid a failing background refresher set `DATABRICKS_INVENTORY_REFRESH_SECONDS=0` until credentials exist. |
| `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` 🔒, `AZURE_SUBSCRIPTION_ID`, `AZURE_AUTH_METHOD` | Server-side Azure access | Not needed for user-entered connections |
| `FABRIC_ENABLED`, `FABRIC_*` (`CLIENT_SECRET` 🔒) | Fabric lakehouse sync | Default off |
| `GCP_*`, `GOOGLE_APPLICATION_CREDENTIALS` (🔒 keys) | GCP | Default off |
| `FINOPS_MONTHLY_BUDGET_USD`, `FINOPS_SIGNING_KID`, `FINOPS_VERIFICATION_KEYS` 🔒 | FinOps budget / signing key ring | Defaults safe |
| `OFFLINE_PRICING_MODE`, `ALLOW_DEMO_FIXTURES` (must stay `false`) , `LOG_LEVEL`, `LOG_FORMAT`, `API_*`, pool/timeout/size limits | Tuning | Defaults safe |
| `WEBSITES_PORT` | Not read by the app; App Service forwards the port | Only needed if the container port is not the default 8000 |

Other direct reads: `DATABRICKS_CLIENT_ID/SECRET`, `GCP_ACCESS_TOKEN`, `GOOGLE_APPLICATION_CREDENTIALS`, and the platform-provided `IDENTITY_ENDPOINT` / `IDENTITY_HEADER` (managed identity, set only when an identity is enabled).

## 2. Database

| Item | Finding |
|---|---|
| Type | PostgreSQL via SQLAlchemy 2 async + `asyncpg`; **PostgreSQL 13+** required (`gen_random_uuid()` used by migrations 0004 and 0005). |
| Host | **None configured** and none visible in this subscription (`flexible-server list` → `[]`; a server in another subscription/RG, or one you cannot list, is possible). |
| Connectivity | App outbound IPs (for a database firewall allow-list): `20.219.172.33, 20.219.172.222, 20.219.172.232, 20.219.172.234, 20.219.173.8, 20.219.173.11, 20.204.238.158, 20.204.238.240, 20.204.239.24, 20.204.239.60, 20.204.239.243, 20.207.65.31, 20.192.170.13`. No VNet integration exists. TLS: `DB_SSL_MODE=require`. |
| Alembic | `alembic.ini` + `alembic/` are in the ZIP; `env.py` reads `DATABASE_URL`. Linear chain, one head: `0001 initial → 0002 billing → 0003 approval tokens → 0004 billing precision/row identity → 0005 cloud_connections (2026_11_16_0005)`. |
| Initialised? | **Unknowable — no database is reachable/configured.** Assume empty. |
| Notes on migrations | `0004` refuses to run if `billing_usage_records` has rows (empty-table guard) and was marked "prepared, needs approval"; `0005` creates the connection tables and is also "prepared, needs approval". Migrations are **not** run by `startup.sh` or the startup command. |

**Prerequisites before running migrations (nothing was run):**
1. A PostgreSQL ≥ 13 server and an empty database owned by a dedicated user (IT/DBA).
2. Network path from wherever you run Alembic (your PC or Kudu SSH) — firewall rule or private access; the Zscaler/Entra consideration in §7 also applies (§6).
3. `DATABASE_URL` (+ `DB_SSL_MODE=require`) exported in that shell — **never** the app's production secret in a shared terminal history.
4. Your explicit schema-change approval for 0004/0005.
5. A backup (nothing to back up on a fresh database; mandatory afterwards).
6. Run `alembic upgrade head` once; verify with `alembic current`.

## 3. Startup command

| | Command | Verdict |
|---|---|---|
| Configured in Azure | `python -m uvicorn cloud_recommender.main:app --app-dir src --host 0.0.0.0 --port 8000` | **Valid.** ZIP layout has `src/cloud_recommender/main.py` with `app = create_app()` at the site root; `--app-dir src` makes the package importable. |
| `startup.sh` (in ZIP, LF line endings, correct) | same uvicorn with `PYTHONPATH=…/src`, port `${WEBSITES_PORT:-${PORT:-8000}}`, `--workers 1 --proxy-headers --forwarded-allow-ips "*"` | **Preferred.** The two extra flags matter behind App Service's front end: without `--forwarded-allow-ips "*"` uvicorn ignores `X-Forwarded-*` (wrong scheme/client IP in logs and redirects). Single worker is required: live Azure sessions are in process memory. |

Why they differ: the Azure command was set manually before `startup.sh` was added/updated (the app's last change is 2026-11-16). A newer copy of `startup.sh` in your working tree differs from the ZIP's (mixed line endings, includes debug `echo`s); **use the ZIP's.** Recommendation: set the startup command to `bash startup.sh`. (Not changed.)

## 4. ZIP package (`backend-deploy.zip`, 5.9 MB, 249 files, 44 MB uncompressed)

| Check | Result |
|---|---|
| Structure | Correct: `src/`, `alembic/`, `alembic.ini`, `requirements.txt`, `startup.sh`, `pyproject.toml` at the root (not nested). |
| Matches current source | Yes — every `src/` file is identical to the working tree (only `startup.sh` differs, see §3). |
| Entry point | `cloud_recommender.main:app` exists. |
| Dependencies | `requirements.txt` has 15 packages. Imports not listed directly (`cryptography`, `starlette`, `python-dotenv`) are installed transitively (`pyjwt[crypto]`, `fastapi`, `pydantic-settings`). `langgraph`, `deltalake`, `pyarrow` are **not imported by any source file** — they only lengthen the Oryx build (pyarrow is large); harmless but unnecessary. |
| Python | `.python-version` 3.12 matches the runtime. |
| Config files | Settings come only from environment; no required config file is missing. |
| Secrets | **No `.env`, keys or credentials.** A pattern scan matched only fake values in `tests/` and `scripts/` (e.g. test fixture strings). |
| Unnecessary files | **`.mypy_cache` (41 MB uncompressed, also `src/.mypy_cache`), `.ruff_cache`, `.coverage`, `tests/` (63 files), `uv.lock`, `scripts/`.** None harmful; slow the upload/extract and expose test code. |

The existing ZIP was not modified. If you approve, I would build a clean replacement (excluding caches/tests) as a **new** file.

## 5. Deployment checklist (nothing below has been executed)

### A. Prerequisites needing IT
1. **Entra:** backend API app registration (Expose an API: `access_as_user`; v2 tokens) + SPA registration (client ID) → gives `ENTRA_AUDIENCE`, `ENTRA_REQUIRED_SCOPES`, `ENTRA_ALLOWED_CLIENT_IDS`.
2. **PostgreSQL ≥ 13** (server, empty database, user, firewall for the outbound IPs above or private access).
3. If `keyvault` is chosen: managed identity + Key Vault + access. (Avoidable with the `env` provider.)
4. **Zscaler:** allow `*.azurewebsites.net` / `*.scm.centralindia-01.azurewebsites.net` without TLS inspection, or provide the corporate root certificate (§6.1).
5. Databricks service principal, only if Databricks features are wanted.

### B. Values you create yourself
`SECRET_KEY`, `FINOPS_SIGNING_SECRET` (≥ 32 random chars each) and, for the `env` provider, a 32-byte random key (base64) with a key ID. Generate them locally and keep them in a password manager. **No value was generated for you.**

### C. App Service configuration (Portal → FinopsBackendApp → Settings → Environment variables, or `az webapp config appsettings set`)
Add every row of §1.2, §1.3 and the database rows of §1.4. Use Key Vault references or deployment-slot-style secrets for 🔒 items where possible. Then Configuration → General settings → **Startup Command** = `bash startup.sh`. Keep exactly 1 instance (`numberOfWorkers: 1` today).

### D. Deploy
Preferably first set the corporate CA (§6.1), then, from `cloud-recommender-poc`:
```powershell
az account set --subscription 9636348b-8445-4441-94d2-f6191f131721
az webapp deploy --resource-group bizmetric-central-platform-genai --name FinopsBackendApp `
  --src-path ".\backend-deploy.zip" --type zip
```
SCM/FTP basic auth are **disabled**, so only Entra-token-based deploys work (you hold *Website Contributor*; confirmed).

### E. Migrations (only after approval and §2 prerequisites)
Run `alembic upgrade head` from a machine that can reach the database (or Kudu SSH), with `DATABASE_URL` set in that session.

### F. Health verification
```powershell
$h = "https://finopsbackendapp-f3a0dya4cpederg0.centralindia-01.azurewebsites.net"
(Invoke-WebRequest "$h/health" -SkipHttpErrorCheck).StatusCode     # expect 200
(Invoke-WebRequest "$h/api/v1/connections" -SkipHttpErrorCheck).StatusCode   # expect 401 (auth enforced), not 500/503
az webapp log tail --name FinopsBackendApp --resource-group bizmetric-central-platform-genai   # needs Kudu reachable
```
Expect log lines `application_starting`, `authentication_mode … entra`. A startup failure shows `Insecure security configuration: …` **naming the offending variables** (never their values). `/docs` is disabled in production by design. A 503 `DATABASE_UNAVAILABLE` from data routes means the database or migrations are missing, not a crash.

### G. Rollback
- Before any change save the current settings: `az webapp config appsettings list … > settings-backup.json` (**contains secrets — store securely, do not commit**).
- Code: redeploy the previous known-good ZIP (keep a copy of every ZIP deployed; earlier successful deployments on 2026-11-16 12:56 and 14:30 UTC are listed in the app's deployment history but their packages are not retrievable from Azure).
- Settings: re-apply the backup; to stop a crash loop quickly set `APP_ENV=staging` (relaxes only the startup checks; authentication is still required for protected routes — `DEV_AUTH_ENABLED` is refused on App Service).
- Database: migrations are not auto-reversible with data (0004's downgrade is guarded); restore from backup instead.
- No deployment slots exist, so there is no instant swap; consider one before production traffic.

## 6. Deployment connectivity (why the Kudu/SCM step failed)

| Check | Result |
|---|---|
| Access restrictions (main + SCM) | "Allow all" only; public network access Enabled; no private endpoint; no VNet integration. **Azure is not blocking.** |
| DNS | SCM host resolves to public `20.192.170.13`. |
| TLS path | The certificate presented for `*.azurewebsites.net` is issued by **Zscaler Intermediate Root CA** (TLS inspection). Windows trusts it, so `curl`/PowerShell/browsers may work, but the Azure CLI and any non-Windows-store client fail with `CERTIFICATE_VERIFY_FAILED`. |
| Browser SCM message | Consistent with Zscaler policy/inspection on the `scm` host. |

### 6.1 Smallest fix (client side, no Azure change)
Give the Azure CLI the corporate root certificate:
```powershell
# Export the Zscaler root from the Windows store to PEM (look for the root in the chain shown by certmgr/IT)
Get-ChildItem Cert:\LocalMachine\Root | Where-Object Subject -like "*Zscaler*" | Select Subject, Thumbprint
# Then (certificate file provided by IT, PEM format that also includes the standard Mozilla bundle):
$env:REQUESTS_CA_BUNDLE = "C:\certs\corporate-plus-public-bundle.pem"
az webapp deploy ...
```
Alternatively ask IT to exempt `*.azurewebsites.net` from SSL inspection, or deploy from a network without inspection (home/hotspot are not allowed to bypass policy without IT approval). Do **not** disable TLS verification (`AZURE_CLI_DISABLE_CONNECTION_VERIFICATION`) — it weakens security.

### 6.2 Safe diagnostics (PowerShell, read-only)
```powershell
$s = "finopsbackendapp-f3a0dya4cpederg0.scm.centralindia-01.azurewebsites.net"
Resolve-DnsName $s
Test-NetConnection $s -Port 443
$t = New-Object Net.Sockets.TcpClient($s,443); $ss = New-Object Net.Security.SslStream($t.GetStream(),$false,{$true}); $ss.AuthenticateAsClient($s)
(New-Object Security.Cryptography.X509Certificates.X509Certificate2($ss.RemoteCertificate)).Issuer   # shows Zscaler if inspected
az webapp config access-restriction show -g bizmetric-central-platform-genai -n FinopsBackendApp
```

## 8. Approval needed before I do anything further
1. OK to build a **new**, clean ZIP (no caches/tests/unused dependencies) next to the existing one?
2. Which encryption-key provider: `env` (recommended, no IT) or `keyvault` (needs identity + vault)?
3. Which database host will you use (IT must provision it)?
4. Do you want the startup command switched to `bash startup.sh` when we apply settings?
I will change no Azure setting, deploy nothing and run no migration until you approve each step.

## 9. Update 2026-11-17 — local verification before the GitHub push

- **Fixed:** a comma-separated `CORS_ORIGINS` (the App Service format) crashed startup with a JSON error; the field now accepts a comma list or a JSON array (`tests/test_cors_origins_env_parsing.py`).
- **Fixed:** with the database unreachable, `GET /api/v1/configuration/{id}` returned HTTP 500 (`generator didn't stop after athrow()`); database errors now reach the 503 `DATABASE_UNAVAILABLE` handler (`tests/test_configuration_dependency_db_failure.py`).
- **New clean ZIP (not deployed):** `backend-deploy-clean.zip` — `src/`, `alembic/`, `alembic.ini`, `requirements.txt`, `startup.sh` (LF), `scripts/run_migrations.py`; no tests, caches, `.env` or lock files (~0.4 MB). It contains the current `startup.sh` (changes directory to the app folder). The original `backend-deploy.zip` is unchanged.
- **Verified locally from the extracted ZIP, production mode, no PostgreSQL:** startup succeeds; `/health` 200; `/docs`, `/redoc`, `/openapi.json` 404; protected routes 401 without or with a malformed token; CORS preflight allowed only for the configured Fabric origins (localhost and unknown origins rejected). A clean venv built from `requirements.txt` imports the app. Unpinned dependencies resolve to the newest releases (e.g. SQLAlchemy 2.1, FastAPI 0.163) — they work, but consider pinning.
- **Not verifiable offline:** real Entra token validation (needs the registrations), any PostgreSQL behaviour, Databricks/Azure live calls from App Service.
- On Windows Git Bash, `--forwarded-allow-ips "*"` in `startup.sh` is glob-expanded by the shell/launcher; on Linux App Service it is passed literally. (Locally it was exercised through `FORWARDED_ALLOW_IPS`.)
