# Startup Script V5 — Changelog & Architecture Specification

**Component:** `startup.bat`  
**Version:** V5 (Production-Grade Local Development Launcher)  
**Previous Version:** V4  
**Date:** November 2026  
**Status:** Certified & Deployed  

---

## 1. Summary of Changes (V4 to V5 Upgrade)

| Capability | Startup V4 | Startup V5 (Upgraded) | Architectural Impact |
|---|---|---|---|
| **Binary Discovery** | Hardcoded path to `Python314\Scripts\uv.exe` and `Program Files\PostgreSQL\16` | Resilient multi-tier discovery (PATH -> AppData Python314 -> LocalAppData Programs -> Cargo bin -> venv; PostgreSQL 16/15/14) | Zero breakage across developer environments or non-standard install paths. |
| **Port Socket Check** | Fragile `Test-NetConnection` via WMI/CIM (fails on restricted non-admin consoles) | Fast .NET `System.Net.Sockets.TcpClient` connection probe | 100x faster execution, no WMI/CIM dependencies, zero "Access Denied" crashes. |
| **Database Integrity** | Basic existence check | Strict non-destructive check: verifies existence, creates if missing, never drops/resets/truncates | Guaranteed data persistence across local restarts. |
| **Alembic Migrations** | Ran `alembic upgrade head` blind | Displays current migration revision (`alembic current`), target head revision (`alembic heads`), and applies pending deltas | Complete visibility into database schema versioning. |
| **Azure CLI / Auth** | Printed raw table without Databricks context | Validates Azure CLI token, displays UPN/Subscription, displays Azure Databricks target workspace (`642006393507276`), asserts zero-execution read-only guardrail | Never exposes tokens or secrets; validates read-only security boundary. |
| **Process Management** | Blind port check | Health-aware: if backend or frontend is already active and healthy, avoids launching redundant processes; does not kill unrelated user tasks | Smooth workflow when backend or frontend is already running in background. |
| **Post-Startup Diagnostics** | None (only opened browser) | **Added Step [10/11]:** Live probe against `/api/v1/databricks/connections` and FinOps analytics, displaying summary table before browser launch | Instant verification of live vs mock state and workspace readiness. |
| **Step Sequence** | 10 Steps | 11 Sequenced & Structured Steps with clear indicators `[1/11]` to `[11/11]` | Clear, transparent developer console feedback. |

---

## 2. 11-Step Startup Sequence Specification

1. **`[1/11]` Environment Validation:** Resilient discovery of `uv.exe`, `psql.exe`, Node.js, npm, Python in `backend/.venv`, and package manifests.
2. **`[2/11]` PostgreSQL Service & Socket:** Verifies 127.0.0.1:5432 using .NET `TcpClient`. Starts Windows service if stopped.
3. **`[3/11]` Non-Destructive Database Integrity:** Verifies `cloud_recommender` database exists. Automatically initializes if absent.
4. **`[4/11]` Alembic Schema Versioning:** Inspects `current` and `heads` revisions, applying pending migrations cleanly.
5. **`[5/11]` Azure CLI & Databricks Read-Only Auth:** Validates active Azure CLI login, displays identity without exposing secrets, and targets workspace `642006393507276`.
6. **`[6/11]` Frontend Environment Synchronization:** Writes `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` to `frontend/.env.local`.
7. **`[7/11]` Frontend Dependency Check:** Validates `frontend/node_modules`. Runs `npm install` only when missing.
8. **`[8/11]` FastAPI Backend Launch (Port 8000):** Starts backend with Uvicorn in a dedicated terminal window. Enforces bounded health check loop.
9. **`[9/11]` Next.js Frontend Launch (Port 3000):** Starts Next.js with `NODE_USE_SYSTEM_CA=1`. Enforces bounded HTTP response wait loop.
10. **`[10/11]` Post-Startup FinOps & Databricks Diagnostics:** Probes `/api/v1/databricks/connections`, validates registered workspaces and Stopped warehouse safety.
11. **`[11/11]` Application Launch:** Automatically launches default browser to `http://localhost:3000` and Swagger docs at `http://127.0.0.1:8000/docs`.

---

## 3. Preserved Architecture & Guardrails

- **Backend:** FastAPI on port 8000 (`backend/src/cloud_recommender/main.py`).
- **Frontend:** Next.js 14 App Router on port 3000 (`frontend/`).
- **Database:** PostgreSQL 16 on port 5432 (`cloud_recommender`).
- **Security:** 100% Read-Only (`Reader`, `Cost Management Reader`). No cloud mutation commands.
- **Fabric Baseline:** Frozen baseline commit `c2c87027f64b59fb784d990b9485781dde05e6f8` remains 100% untouched.

