#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

cd "$(dirname "$0")/.."

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"
WORKERS="${WORKERS:-1}"

exec gunicorn \
    -w "$WORKERS" \
    -k uvicorn.workers.UvicornWorker \
    --bind "${HOST}:${PORT}" \
    --access-logfile - \
    --error-logfile - \
    service.api.app:app
