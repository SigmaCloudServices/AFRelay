#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

cd "$(dirname "$0")/.."
mkdir -p logs

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"
WORKERS="${WORKERS:-1}"
ACCESS_LOG="${AFRELAY_ACCESS_LOG:-logs/access.log}"
ERROR_LOG="${AFRELAY_ERROR_LOG:-logs/error.log}"

exec gunicorn \
    -w "$WORKERS" \
    -k uvicorn.workers.UvicornWorker \
    --bind "${HOST}:${PORT}" \
    --access-logfile "${ACCESS_LOG}" \
    --error-logfile "${ERROR_LOG}" \
    service.api.app:app
