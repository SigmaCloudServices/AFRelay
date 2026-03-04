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

GUNICORN_LOG_ARGS=()
LOG_TO_FILE="${LOG_TO_FILE:-0}"
if [ "${LOG_TO_FILE}" = "1" ] || [ "${LOG_TO_FILE}" = "true" ] || [ "${LOG_TO_FILE}" = "TRUE" ]; then
  GUNICORN_LOG_ARGS+=(--access-logfile "${ACCESS_LOG}" --error-logfile "${ERROR_LOG}")
else
  GUNICORN_LOG_ARGS+=(--access-logfile - --error-logfile -)
fi

exec -a afrelay gunicorn \
    -w "$WORKERS" \
    -k uvicorn.workers.UvicornWorker \
    --name afrelay \
    --bind "${HOST}:${PORT}" \
    "${GUNICORN_LOG_ARGS[@]}" \
    service.api.app:app
