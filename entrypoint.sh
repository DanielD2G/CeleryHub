#!/bin/sh
set -e

GATEWAY_PORT="${CELERY_GATEWAY_PORT:-8000}"

# Start celery-gateway in background
uvicorn celery_gateway.main:app \
  --host 0.0.0.0 --port "$GATEWAY_PORT" \
  --app-dir /app/gateway/src &

# Start Hono server in foreground
CELERY_GATEWAY_URL="${CELERY_GATEWAY_URL:-http://127.0.0.1:$GATEWAY_PORT}" \
  bun run /app/packages/server/dist/index.js
