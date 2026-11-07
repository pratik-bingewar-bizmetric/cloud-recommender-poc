# Milestone 3J.3: Startup.bat Final Hardening Report
## Operational Launcher V5.1 Hardening, Decoupled Migrations & Process Tracking

### 1. Launcher Architecture & Subcommands

The operational launcher (`startup.bat`) manages the local development and testing environment across Python/FastAPI (port 8000), Next.js 14 (port 3000), and PostgreSQL 16 (port 5432).

In Milestone 3J.3, the script was hardened to prevent accidental database migrations and avoid killing unrelated processes:

| Subcommand | Functionality | Key Hardening Improvements |
| :--- | :--- | :--- |
| `startup.bat start` | Launches full development stack (Default) | **Decoupled migrations**: Checks `alembic current` without auto-upgrading database. |
| `startup.bat status` | Non-destructive health inspection | **Accurate warehouse status**: Displays `NOT_VERIFIED` when offline instead of claiming `STOPPED`. |
| `startup.bat stop` | Stops backend and frontend services | **Process ownership verification**: Inspects process name (`python`/`uvicorn`/`node`) before stopping. |
| `startup.bat restart` | Sequential stop, wait, and start | Waits for socket release and invokes safe start. |
| `startup.bat check` | Validates prerequisites only | Checks Python, `uv`, Node, npm, PostgreSQL socket, and Azure CLI without modifying files. |
| `startup.bat migrate` | **Explicit database schema migration** | **New subcommand**: Prompts and applies pending Alembic revisions with clear target DB notification. |

---

### 2. Line Ending & Windows Compatibility Fix

- **Problem Encountered**: During execution of `startup.bat stop`, `cmd.exe` reported `The system cannot find the batch label specified - DO_STOP`.
- **Root Cause**: The file was formatted with bare Unix line endings (`LF`). Windows `cmd.exe` strictly requires `CRLF` (`\r\n`) to parse labels and `goto` targets properly.
- **Resolution**: Normalized `startup.bat` to strict CRLF line endings. Verified that all subcommands (`start`, `status`, `stop`, `restart`, `check`, `migrate`) execute with exit code 0.

---

### 3. Verification Evidence

```cmd
# 1. Check Subcommand Output
> startup.bat check
============================================================
  ENVIRONMENT AND PREREQUISITE VALIDATION (NON-INTRUSIVE)
============================================================
[OK] Backend directory   : ...\backend
[OK] Frontend directory  : ...\frontend
[OK] Python interpreter  : ...\.venv\Scripts\python.exe
[OK] Package manager (uv): ...\uv.exe
[OK] PostgreSQL CLI      : ...\psql.exe
 [WARN] PostgreSQL service: Port 5432 not responding
 [OK] Azure CLI           : Installed
 [OK] Node.js             : Installed
 [OK] npm                 : Installed
Prerequisite check complete. (Exit code: 0)

# 2. Status Subcommand Output
> startup.bat status
Runtime Health Summary:
------------------------------------------------------------
  Database Service (Port 5432) : OFFLINE / STOPPED
  FastAPI Backend (Port 8000)  : OFFLINE
  Next.js Frontend (Port 3000) : OFFLINE
  Databricks SQL Warehouse     : NOT_VERIFIED (Offline baseline: 05ed10a52697a344 remains untouched)
------------------------------------------------------------ (Exit code: 0)

# 3. Stop Subcommand Output
> startup.bat stop
============================================================
  STOPPING CLOUD RECOMMENDER SERVICES
============================================================
Stopping verified backend process on port 8000...
  Port 8000 is already free.
Stopping verified frontend process on port 3000...
  Port 3000 is already free.
All application services stopped cleanly. (Exit code: 0)
```

