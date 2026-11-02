
@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Cloud Recommender - Local Startup V4

REM ============================================================
REM CLOUD RECOMMENDER POC - LOCAL STARTUP V4
REM Backend : FastAPI - Port 8000
REM Frontend: Next.js - Port 3000
REM Database: PostgreSQL 16
REM ============================================================

REM 1. PROJECT PATHS
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"

set "UV=%APPDATA%\Python\Python314\Scripts\uv.exe"
set "PSQL=C:\Program Files\PostgreSQL\16\bin\psql.exe"
set "PG_SERVICE=postgresql-x64-16"
set "API_URL=http://localhost:8000/api/v1"

echo.
echo ============================================================
echo       CLOUD RECOMMENDER - STARTING APPLICATION
echo ============================================================
echo Project: %PROJECT_ROOT%
echo.

REM ============================================================
REM 2. VERIFY PROJECT STRUCTURE
REM ============================================================

echo [1/10] Checking project structure...

if not exist "%BACKEND_DIR%\pyproject.toml" (
    echo ERROR: Backend project not found.
    goto FAILED
)

if not exist "%BACKEND_DIR%\src\cloud_recommender\main.py" (
    echo ERROR: FastAPI entrypoint not found.
    goto FAILED
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo ERROR: Frontend project not found.
    goto FAILED
)

if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
    echo ERROR: Backend Python virtual environment not found.
    goto FAILED
)

if not exist "%UV%" (
    echo ERROR: uv.exe not found at %UV%
    goto FAILED
)

if not exist "%PSQL%" (
    echo ERROR: PostgreSQL psql.exe not found.
    goto FAILED
)

where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed.
    goto FAILED
)

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm is unavailable.
    goto FAILED
)

echo Project structure verified.

REM ============================================================
REM 3. START POSTGRESQL
REM ============================================================

echo.
echo [2/10] Checking PostgreSQL service...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-Service -Name '%PG_SERVICE%' -ErrorAction SilentlyContinue; if(-not $s){exit 2}; if($s.Status -ne 'Running'){Start-Service -Name '%PG_SERVICE%'; Start-Sleep -Seconds 3}; if((Get-Service -Name '%PG_SERVICE%').Status -ne 'Running'){exit 3}"

if errorlevel 1 (
    echo ERROR: Could not start PostgreSQL.
    echo Try running this script as Administrator.
    goto FAILED
)

powershell -NoProfile -Command "$r=Test-NetConnection 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue; if(-not $r.TcpTestSucceeded){exit 1}"

if errorlevel 1 (
    echo ERROR: PostgreSQL port 5432 is unavailable.
    goto FAILED
)

echo PostgreSQL is running.

REM ============================================================
REM 4. CHECK DATABASE
REM ============================================================

echo.
echo [3/10] Checking cloud_recommender database...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$r = & '%PSQL%' -h 127.0.0.1 -p 5432 -U postgres -d postgres -tAc 'SELECT 1 FROM pg_database WHERE datname=''cloud_recommender'';'; $c=$LASTEXITCODE; if($c -ne 0){exit 2}; if(($r -join '').Trim() -eq '1'){exit 0}else{exit 1}"

if errorlevel 2 (
    echo ERROR: PostgreSQL connection or authentication failed.
    goto FAILED
)

if errorlevel 1 (
    echo Database does not exist. Creating...

    "%PSQL%" -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "CREATE DATABASE cloud_recommender OWNER postgres;"

    if errorlevel 1 (
        echo ERROR: Database creation failed.
        goto FAILED
    )

    echo Database created successfully.
) else (
    echo Database cloud_recommender already exists.
    echo Skipping database creation.
)

REM ============================================================
REM 5. RUN ALEMBIC MIGRATIONS
REM ============================================================

echo.
echo [4/10] Running Alembic migrations...

pushd "%BACKEND_DIR%"

"%UV%" run --project . --no-sync alembic upgrade head

if errorlevel 1 (
    popd
    echo ERROR: Database migrations failed.
    goto FAILED
)

popd

echo Database migrations completed.

REM ============================================================
REM 6. AZURE CLI AUTHENTICATION
REM IMPORTANT: CALL prevents az.cmd from ending this batch script.
REM ============================================================

echo.
echo [5/10] Checking Azure CLI authentication...

where az >nul 2>&1

if errorlevel 1 (
    echo WARNING: Azure CLI is not installed.
) else (

    call az account get-access-token --resource https://management.azure.com/ --query expiresOn -o tsv >nul 2>&1

    if errorlevel 1 (
        echo Azure login required.
        call az login

        if errorlevel 1 (
            echo WARNING: Azure authentication failed.
        )
    ) else (
        echo Azure authentication is available.
    )

    call az account show --output table
)

echo Azure authentication check completed.
echo Continuing to frontend configuration...

REM ============================================================
REM 7. CONFIGURE FRONTEND API URL
REM ============================================================

echo.
echo [6/10] Configuring frontend API URL...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path '%FRONTEND_DIR%' '.env.local'; $line='NEXT_PUBLIC_API_URL=%API_URL%'; $items=@(); if(Test-Path $p){$items=Get-Content $p}; $found=$false; for($i=0;$i -lt $items.Count;$i++){if($items[$i] -match '^NEXT_PUBLIC_API_URL='){$items[$i]=$line;$found=$true}}; if(-not $found){$items+= $line}; Set-Content -Path $p -Value $items -Encoding utf8"

if errorlevel 1 (
    echo ERROR: Frontend API configuration failed.
    goto FAILED
)

echo Frontend API URL configured.

REM ============================================================
REM 8. CHECK FRONTEND DEPENDENCIES
REM ============================================================

echo.
echo [7/10] Checking frontend dependencies...

if not exist "%FRONTEND_DIR%\node_modules" (

    echo Installing npm dependencies...

    pushd "%FRONTEND_DIR%"

    set "NODE_USE_SYSTEM_CA=1"

    call npm install

    if errorlevel 1 (
        popd
        echo ERROR: npm install failed.
        goto FAILED
    )

    popd

) else (
    echo Frontend dependencies already installed.
)

REM ============================================================
REM 9. START BACKEND
REM ============================================================

echo.
echo [8/10] Checking and starting FastAPI backend...

powershell -NoProfile -Command "try{$r=Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2; if($r.status -eq 'ok'){exit 0}}catch{}; exit 1"

if errorlevel 1 (

    echo Starting backend in a separate terminal...

    start "Cloud Recommender - Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && ""%UV%"" run --project . --no-sync uvicorn cloud_recommender.main:app --app-dir src --reload --host 127.0.0.1 --port 8000"

) else (
    echo Backend is already running.
)

echo Waiting for backend health check...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 40;$i++){try{$r=Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2; if($r.status -eq 'ok'){$ok=$true;break}}catch{}; Start-Sleep -Seconds 2}; if(-not $ok){exit 1}"

if errorlevel 1 (
    echo ERROR: Backend health check failed.
    echo Inspect the backend terminal.
    goto FAILED
)

echo Backend is healthy.

REM ============================================================
REM 10. START FRONTEND
REM ============================================================

echo.
echo [9/10] Checking and starting Next.js frontend...

powershell -NoProfile -Command "$r=Test-NetConnection 127.0.0.1 -Port 3000 -WarningAction SilentlyContinue; if($r.TcpTestSucceeded){exit 0}else{exit 1}"

if errorlevel 1 (

    echo Starting frontend in a separate terminal...

    start "Cloud Recommender - Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && set NODE_USE_SYSTEM_CA=1 && npm run dev"

) else (
    echo Port 3000 is already occupied.
    echo Assuming frontend is already running.
)

echo Waiting for frontend...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 30;$i++){try{$r=Invoke-WebRequest 'http://localhost:3000' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){$ok=$true;break}}catch{}; Start-Sleep -Seconds 2}; if(-not $ok){exit 1}"

if errorlevel 1 (
    echo WARNING: Frontend did not respond within the wait period.
    echo Inspect the frontend terminal.
) else (
    echo Frontend is responding.
)

REM ============================================================
REM FINAL STATUS
REM ============================================================

echo.
echo ============================================================
echo       CLOUD RECOMMENDER STARTUP FINISHED
echo ============================================================
echo.
echo Frontend:        http://localhost:3000
echo Backend Swagger: http://127.0.0.1:8000/docs
echo Backend Health:  http://127.0.0.1:8000/health
echo.
echo Keep both terminal windows open.
echo.

echo [10/10] Opening application...

start "" "http://localhost:3000"
start "" "http://127.0.0.1:8000/docs"

echo.
echo Startup process completed.
pause
exit /b 0

REM ============================================================
REM ERROR HANDLER
REM ============================================================

:FAILED

echo.
echo ============================================================
echo STARTUP FAILED
echo ============================================================
echo.
echo Review the error above.
echo No database or project files were intentionally deleted.
echo.
pause
exit /b 1
