# ── Stage 1: Build frontend (Vite) ──────────
FROM node:22-alpine AS web-builder

WORKDIR /build
COPY package.json ./
COPY packages/web/package.json packages/web/
RUN npm install --ignore-scripts

COPY packages/web/ packages/web/
RUN cd packages/web && npx tsc -b && npx vite build

# ── Stage 2: Build Python dependencies ─────
FROM alpine:3.21 AS py-builder

RUN apk add --no-cache python3 binutils
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build
COPY services/celery-gateway/ ./gateway/
RUN uv venv /opt/venv --python /usr/bin/python3 && \
    VIRTUAL_ENV=/opt/venv uv pip install --no-cache --compile-bytecode ./gateway/ && \
    # Strip debug symbols from native extensions
    find /opt/venv -name '*.so' -exec strip -s {} + 2>/dev/null; \
    # Remove unnecessary files from venv (keep *.dist-info — needed by importlib.metadata)
    find /opt/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv \( -type d -name tests -o -type d -name test \) -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv -name '*.pyi' -delete 2>/dev/null; \
    rm -rf /opt/venv/lib/python*/site-packages/pytz/zoneinfo 2>/dev/null; \
    true

# ── Stage 3: Runtime ───────────────────────
FROM alpine:3.21

RUN apk add --no-cache python3 tini && \
    find /usr/lib/python3.12 -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

RUN addgroup -S celeryhub && adduser -S celeryhub -G celeryhub

WORKDIR /app

COPY --from=py-builder /opt/venv /opt/venv
COPY --from=web-builder /build/packages/web/dist /app/packages/web/dist/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=3000 \
    CELERYHUB_DB_PATH=/app/data/celeryhub.db

RUN mkdir -p /app/data && chown -R celeryhub:celeryhub /app/data
VOLUME ["/app/data"]

USER celeryhub

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["sh", "-c", "exec python3 -m uvicorn celery_gateway.main:app --host 0.0.0.0 --port ${PORT:-3000}"]
