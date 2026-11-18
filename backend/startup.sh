#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

export PYTHONPATH="$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

PORT_TO_BIND="${WEBSITES_PORT:-${PORT:-8000}}"

echo "APP_DIR=$APP_DIR"
echo "PYTHONPATH=$PYTHONPATH"
echo "APP_ENV=${APP_ENV:-NOT_SET}"

exec python -m uvicorn cloud_recommender.main:app \
  --host 0.0.0.0 \
  --port "${PORT_TO_BIND}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "*" \
  --log-level info
