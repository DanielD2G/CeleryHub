#!/bin/sh
set -e

exec uvicorn celery_gateway.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-3000}"
