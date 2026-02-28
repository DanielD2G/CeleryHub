# ── Stage 1: Install dependencies ────────────
FROM oven/bun:1-alpine AS deps

WORKDIR /build
COPY package.json bun.lock ./
COPY packages/web/package.json packages/web/
COPY packages/server/package.json packages/server/
RUN bun install --frozen-lockfile

# ── Stage 2: Build frontend (Vite) ──────────
FROM deps AS web-builder

COPY packages/web/ packages/web/
RUN bun run --filter @celeryhub/web build

# ── Stage 3: Build server (TypeScript) ───────
FROM deps AS server-builder

COPY packages/server/ packages/server/
RUN bun run --filter @celeryhub/server build

# ── Stage 4: Final image (Python + Bun) ─────
FROM python:3.12-slim

# Install bun runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl unzip && \
    curl -fsSL https://bun.sh/install | bash && \
    ln -s /root/.bun/bin/bun /usr/local/bin/bun && \
    apt-get purge -y curl unzip && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Install celery-gateway Python deps
WORKDIR /app/gateway
COPY services/celery-gateway/ .
RUN pip install --no-cache-dir .

# Copy server build + node_modules
WORKDIR /app
COPY --from=server-builder /build/node_modules node_modules/
COPY --from=server-builder /build/packages/server/dist packages/server/dist/
COPY --from=server-builder /build/packages/server/package.json packages/server/

# Copy frontend build
COPY --from=web-builder /build/packages/web/dist packages/web/dist/

# Create data directory for SQLite
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Entrypoint
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 3000

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
ENV CELERYHUB_DB_PATH=/app/data/celeryhub.db

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:3000/ || exit 1

CMD ["./entrypoint.sh"]
