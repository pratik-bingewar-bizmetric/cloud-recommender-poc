# Milestone 3J.2 — Local Operations & Startup Guide
## Operational Runbook for Launcher V5.1, CLI Subcommands & Runtime Management

| Parameter | Specification |
| :--- | :--- |
| **Tool** | `startup.bat` (Version 5.1 Production-Grade) |
| **Backup Script** | `startup_v5_backup.bat` |
| **Backend Target** | FastAPI / Uvicorn (Port 8000) |
| **Frontend Target** | Next.js 14 App Router (Port 3000) |
| **Database Target** | PostgreSQL 16 (Port 5432) |
| **Databricks Target** | Azure Databricks `642006393507276` |

---

## 1. CLI Commands & Subcommands

Launcher script `startup.bat` provides comprehensive command-line arguments for development and operations teams:

```cmd
startup.bat [subcommand]
```

### Supported Subcommands

| Subcommand | Description | Modifies State? | Opens Browser? |
| :--- | :--- | :--- | :--- |
| `startup.bat start` (or `startup.bat`) | Full end-to-end launch: checks dependencies, verifies/starts PostgreSQL, runs pending Alembic migrations, starts backend on 8000, starts frontend on 3000, opens browser. | **YES** (starts processes, runs migrations) | **YES** (3000 and 8000/docs) |
| `startup.bat status` | Non-intrusively queries the status of PostgreSQL, FastAPI backend, Next.js frontend, and Databricks SQL Warehouse safety gate. Prints a clean status table. | **NO** (read-only query) | **NO** |
| `startup.bat stop` | Cleanly terminates processes currently listening on ports 8000 (FastAPI) and 3000 (Next.js). Leaves PostgreSQL running. | **YES** (stops processes) | **NO** |
| `startup.bat restart` | Executes `stop`, pauses for socket cleanup (2 seconds), then calls `start`. | **YES** | **YES** |
| `startup.bat check` | Validates environment prerequisites: Python venv, `uv`, `psql`, Node.js, `npm`, Azure CLI. Non-intrusive. | **NO** | **NO** |

---

## 2. Command Usage Examples

### 2.1 Checking Runtime Health
```cmd
C:\Workspace\cloud-recommender-poc> .\startup.bat status

============================================================
  CLOUD RECOMMENDER RUNTIME STATUS INSPECTION
============================================================
Runtime Health Summary:
------------------------------------------------------------
  Database Service (Port 5432) : ONLINE (127.0.0.1:5432)
  FastAPI Backend (Port 8000)  : ONLINE (http://127.0.0.1:8000/health)
  Next.js Frontend (Port 3000) : ONLINE (http://localhost:3000)
  Databricks SQL Warehouse     : STOPPED (Serverless Starter Warehouse)
  Zero-Execution Guardrail     : ENFORCED (Compute mutations blocked)
------------------------------------------------------------
```

### 2.2 Validating Prerequisites Before Launch
```cmd
C:\Workspace\cloud-recommender-poc> .\startup.bat check

============================================================
  ENVIRONMENT AND PREREQUISITE VALIDATION (NON-INTRUSIVE)
============================================================
[OK] Backend directory   : C:\Workspace\cloud-recommender-poc\backend
[OK] Frontend directory  : C:\Workspace\cloud-recommender-poc\frontend
[OK] Python interpreter  : C:\Workspace\cloud-recommender-poc\backend\.venv\Scripts\python.exe
[OK] Package manager (uv): C:\Users\user\AppData\Roaming\Python\Python314\Scripts\uv.exe
[OK] PostgreSQL CLI      : C:\Program Files\PostgreSQL\16\bin\psql.exe
 [OK] PostgreSQL service  : Responding on 127.0.0.1:5432
 [OK] Azure CLI           : Installed
 [OK] Node.js             : Installed
 [OK] npm                 : Installed

Prerequisite check complete.
```

### 2.3 Stopping Running Services
```cmd
C:\Workspace\cloud-recommender-poc> .\startup.bat stop

============================================================
  STOPPING CLOUD RECOMMENDER SERVICES
============================================================
Stopping backend process on port 8000...
  Killed process 14820 on port 8000
Stopping frontend process on port 3000...
  Killed process 19284 on port 3000
All application services stopped cleanly.
```

---

## 3. Security & Data Protection Guarantees

1. **Zero Credential Exposure**:
   - `startup.bat` never displays tokens, passwords, or connection strings.
   - Azure CLI tokens are queried silently with exit-code inspection only (`az account get-access-token ... >nul 2>&1`).
2. **Non-Destructive Database Migrations**:
   - Schema updates are managed strictly through Alembic (`alembic upgrade head`).
   - The launcher never issues `DROP TABLE` or destructive database commands.
   - If PostgreSQL is unconfigured, it safely provisions the empty `cloud_recommender` database without altering any existing databases.
3. **Decoupled Databricks Compute**:
   - `startup.bat` inspects registered Databricks workspaces via read-only REST endpoints.
   - SQL Warehouse `05ed10a52697a344` remains untouched in state `STOPPED`.

---

## 4. Operational Troubleshooting

| Symptom | Root Cause | Remedy |
| :--- | :--- | :--- |
| `PostgreSQL service: Port 5432 not responding` | Windows service `postgresql-x64-16` is stopped. | Run `startup.bat start` (which attempts auto-start) or start via `net start postgresql-x64-16`. |
| `FastAPI Backend: OFFLINE` | Port 8000 occupied or backend failed to start. | Inspect the separate backend command window for Python stack traces, or run `startup.bat stop` and restart. |
| `Frontend dependencies are missing` | `node_modules` directory was deleted. | Run `startup.bat start`, which automatically triggers `npm install` with system CA trust. |
| `Azure interactive login required` | Local Azure CLI session token expired. | Run `az login` to re-authenticate with `Reader` permissions. |

