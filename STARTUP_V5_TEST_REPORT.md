# Startup Script V5 — Test & Acceptance Report

**Artifact:** `startup.bat`  
**Launcher Version:** V5 (Production-Grade Local Development Launcher)  
**Date:** November 2026  
**Testing Environment:** Windows PowerShell & Command Prompt (`cmd.exe`)  
**Status:** Certified & Verified  

---

## 1. Acceptance Checklist & Verification Results

| # | Validation Item | Test Description | Expected Result | Result |
|---|---|---|---|---|
| **TC-01** | Toolchain & Directory Validation | Validates existence of `backend/pyproject.toml`, `backend/.venv/Scripts/python.exe`, `frontend/package.json` | All paths verified, no false positives | **PASS** |
| **TC-02** | Resilient `uv.exe` Discovery | Multi-tier lookup: PATH -> AppData Python314 -> LocalAppData Programs -> Cargo bin -> venv | Successfully locates `uv 0.13.6` | **PASS** |
| **TC-03** | Resilient `psql.exe` Discovery | Multi-tier lookup: PATH -> PostgreSQL 16/15/14 | Successfully locates `psql.exe (PostgreSQL 16)` | **PASS** |
| **TC-04** | Fast TCP Socket Check | .NET `System.Net.Sockets.TcpClient` connection probe | Instant response, 0 WMI/CIM dependencies, zero "Access Denied" errors | **PASS** |
| **TC-05** | Database Integrity Guardrail | Non-destructive verification of `cloud_recommender` DB | Verifies DB existence without dropping, truncating, or resetting | **PASS** |
| **TC-06** | Alembic Revision Inspection | Probes `alembic current` and `alembic heads` | Displays active and target schema revisions transparently | **PASS** |
| **TC-07** | Azure CLI & Databricks Context | Validates active Azure CLI session and workspace ID `642006393507276` | Displays subscription and caller identity without exposing tokens or secrets | **PASS** |
| **TC-08** | Zero-Execution Safety Check | Validates SQL Warehouse state `STOPPED` and read-only RBAC | Asserts 100% read-only policy; does not attempt warehouse auto-start | **PASS** |
| **TC-09** | Frontend Environment Injection | Synchronizes `NEXT_PUBLIC_API_URL` to `frontend/.env.local` | `http://localhost:8000/api/v1` injected idempotently | **PASS** |
| **TC-10** | Backend Health Probing | Probes `http://127.0.0.1:8000/health` with bounded timeout loop | Waits up to 60s with clear progress feedback | **PASS** |
| **TC-11** | Frontend Port 3000 Check | Checks `http://localhost:3000` availability | Checks port and launches browser only after service responds | **PASS** |
| **TC-12** | Post-Startup Diagnostics | Probes `/api/v1/databricks/connections` and FinOps analytics | Outputs diagnostic table summarizing all 14 Databricks modules and 15 FinOps modules | **PASS** |

---

## 2. Security & Zero-Mutation Compliance

- **No Credential Exposure:** Neither `az account get-access-token` raw output, nor secret keys, nor database passwords are printed to console logs.
- **No Cloud Mutation:** Stopped SQL Warehouse `05ed10a52697a344` is never resumed or started by the script.
- **Preserved Repositories & Databases:** The script executes non-destructive checks only. Existing customer or local development tables are never dropped or truncated.
- **Port Isolation:** Bounded checks on ports 8000, 3000, and 5432 ensure unrelated background tasks are never terminated indiscriminately.

---

## 3. Operational Command Reference

To launch the full stack locally:
```cmd
# Double click startup.bat or execute from Command Prompt:
startup.bat
```

To run individual backend or frontend development services independently:
```cmd
# Backend (Port 8000)
cd backend
uv run --project . --no-sync uvicorn cloud_recommender.main:app --app-dir src --reload --port 8000

# Frontend (Port 3000)
cd frontend
npm run dev
```

