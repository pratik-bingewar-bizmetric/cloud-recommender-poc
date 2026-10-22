@echo off
REM ==============================================================================
REM Cloud Recommender POC - Windows Batch Startup Script
REM ==============================================================================

cd /d "%~dp0"
echo ===================================================================
echo   Starting Cloud Recommender POC
echo ===================================================================

if not exist .env (
    if exist .env.example (
        echo [INFO] Creating .env from .env.example...
        copy .env.example .env >nul
    )
)

echo [INFO] Starting FastAPI Backend on http://127.0.0.1:8000 in background...
start "Cloud Recommender Backend" cmd /k "cd /d "%~dp0backend" && ..\backend\.venv\Scripts\python -m uvicorn cloud_recommender.main:app --port 8000 --reload"

echo [INFO] Starting Next.js Frontend on http://localhost:3000...
cd /d "%~dp0frontend"
npm run dev

