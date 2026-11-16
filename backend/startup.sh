#!/bin/bash
# Azure App Service (Linux, Python 3.12) startup command for the Cloud Recommender API.
#
# Configure in App Service:  Configuration > General settings > Startup Command
#   bash startup.sh
#
# Single instance on purpose: live Azure connection sessions are held in process memory
# (one worker, one instance). Do not raise --workers or scale out for the demo.
set -euo pipefail

# The package lives in ./src (deploy the contents of the backend/ folder as the site root).
export PYTHONPATH="${PYTHONPATH:-}:${PWD}/src"

# App Service forwards the public port through WEBSITES_PORT (default 8000).
PORT_TO_BIND="${WEBSITES_PORT:-${PORT:-8000}}"

exec python -m uvicorn cloud_recommender.main:app \
  --host 0.0.0.0 \
  --port "${PORT_TO_BIND}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "*" \
  --log-level info
