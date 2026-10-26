#!/usr/bin/env bash

# ==============================================================================
# Cloud Recommender POC - Application Startup Script
# Starts both FastAPI Backend (port 8000) and Next.js Frontend (port 3000)
# ==============================================================================

set -e

# Change directory to project root (where this script resides)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "==================================================================="
echo "  Starting Cloud Recommender POC"
echo "  Directory: $ROOT_DIR"
echo "==================================================================="

# 1. Ensure .env exists
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo "[INFO] Creating .env from .env.example..."
    cp .env.example .env
  else
    echo "[WARN] No .env or .env.example found. Continuing with default settings..."
  fi
fi

# 2. Determine Python interpreter
PYTHON_CMD=""
if [ -f "backend/.venv/Scripts/python.exe" ]; then
  # Windows venv (Git Bash / MSYS)
  PYTHON_CMD="backend/.venv/Scripts/python.exe"
elif [ -f "backend/.venv/bin/python" ]; then
  # Linux / macOS / WSL venv
  PYTHON_CMD="backend/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  # Fallback to uv
  PYTHON_CMD="uv run --directory backend python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "[ERROR] Python interpreter not found! Please create a virtual environment in backend/.venv or install python."
  exit 1
fi

echo "[INFO] Using Python: $PYTHON_CMD"

# 3. Start Backend Server (FastAPI on Port 8000)
echo "[INFO] Starting FastAPI Backend on http://127.0.0.1:8000..."
$PYTHON_CMD -m uvicorn cloud_recommender.main:app --app-dir backend/src --port 8000 --reload &
BACKEND_PID=$!

# 4. Start Frontend Dev Server (Next.js on Port 3000)
echo "[INFO] Starting Next.js Frontend on http://localhost:3000..."
(
  cd frontend
  npm run dev
) &
FRONTEND_PID=$!

# Cleanup function to kill both child processes on exit (Ctrl+C)
cleanup() {
  echo ""
  echo "==================================================================="
  echo "  Shutting down services..."
  echo "==================================================================="
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$FRONTEND_PID" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  # On Windows Git Bash, also ensure taskkill is invoked if needed
  if command -v taskkill >/dev/null 2>&1; then
    taskkill //F //IM uvicorn.exe 2>/dev/null || true
  fi
  echo "[INFO] All services stopped."
  exit 0
}

# Trap signals for graceful shutdown
trap cleanup SIGINT SIGTERM EXIT

echo ""
echo "==================================================================="
echo "  Cloud Recommender Services Running:"
echo "  - Backend API:       http://127.0.0.1:8000"
echo "  - Backend Docs:      http://127.0.0.1:8000/docs"
echo "  - Frontend App:      http://localhost:3000"
echo "  Press Ctrl+C to stop all services"
echo "==================================================================="
echo ""

# Wait for background processes
wait

