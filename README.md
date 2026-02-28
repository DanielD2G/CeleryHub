# CeleryHub

Real-time monitoring, control, and scheduling for [Celery](https://docs.celeryq.dev/) clusters.

CeleryHub gives you a modern web dashboard to observe your Celery workers, inspect tasks, send jobs, manage queues, and configure periodic schedules — all from your browser.

## Features

- **Live dashboard** — KPIs, throughput charts, task status breakdown, worker load, and event timeline updated in real time via SSE
- **Task management** — Browse registered tasks, view active/completed executions, retry, revoke, and inspect results or tracebacks
- **Send tasks** — Dispatch any task to any queue with custom args/kwargs from the UI
- **Workers & queues** — Monitor connected workers, pool stats, uptime, and queue depth
- **Beat scheduler** — Create and manage periodic tasks (cron or interval) with run history, max run limits, and enable/disable toggles
- **History** — Search and filter completed tasks with results and exceptions

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    Browser                      │
│              React SPA (Vite)                   │
└────────────────────┬────────────────────────────┘
                     │ HTTP + SSE
┌────────────────────▼────────────────────────────┐
│              Hono Server (Bun)                  │
│   REST API · SSE stream · Beat scheduler        │
│   SQLite (Drizzle ORM) · Redis pub/sub          │
└────────────────────┬────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────┐
│          Celery Gateway (FastAPI)                │
│     Celery inspect / control bridge              │
└────────────────────┬────────────────────────────┘
                     │
              ┌──────▼──────┐
              │    Redis     │
              │   (broker)   │
              └──────┬───────┘
                     │
              ┌──────▼──────┐
              │   Celery     │
              │   Workers    │
              └─────────────┘
```

| Layer | Stack |
|---|---|
| Frontend | React 19, Vite, React Router v7, shadcn/ui, Recharts, Tailwind CSS v4 |
| Backend | Hono, Bun, Drizzle ORM, SQLite, ioredis |
| Gateway | FastAPI, Celery, Pydantic |

## Quick Start

### Docker Compose (recommended)

The fastest way to get CeleryHub running:

```bash
docker compose up
```

This starts Redis and CeleryHub. Open [http://localhost:3000](http://localhost:3000) in your browser.

> **Note:** You still need Celery workers connected to the same Redis. Point your workers at `redis://localhost:6379/0`.

### Docker (standalone)

If you already have Redis running:

```bash
make docker
docker run -e CELERY_BROKER_URL=redis://your-redis:6379/0 -p 3000:3000 celeryhub
```

The Docker image bundles all three services into a single container and serves the React app as static files on port 3000.

### Development

#### Prerequisites

- [Bun](https://bun.sh/) >= 1.0
- [Python](https://www.python.org/) >= 3.11 with [uv](https://docs.astral.sh/uv/)
- A running Redis instance (used as Celery broker)
- Celery workers connected to that Redis

#### Install

```bash
make install
```

This installs the Bun workspace packages and the Python gateway dependencies.

#### Configure

Copy the example env file and edit it:

```bash
cp .env.example .env.local
```

See [`.env.example`](.env.example) for all available variables.

| Variable | Default | Description |
|---|---|---|
| `CELERY_BROKER_URL` | — | Redis URL for the Celery broker **(required)** |
| `CELERY_RESULT_BACKEND` | same as broker | Redis URL for task results |
| `CELERY_GATEWAY_URL` | `http://localhost:8000` | Gateway service URL |
| `CELERY_GATEWAY_PORT` | `8000` | Gateway listen port |
| `SERVER_PORT` | `3000` | Hono server port |
| `VITE_PORT` | `5173` | Vite dev server port |
| `CELERYHUB_DB_PATH` | `./data/celeryhub.db` | SQLite database path |
| `CELERYHUB_TASK_TTL` | `0` (no expiration) | Redis TTL in seconds for task metadata. `0` = persist forever, `604800` = 7 days |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed CORS origins |

#### Run

```bash
make dev
```

This starts all three services concurrently:

- **Celery Gateway** on `:8000` — FastAPI bridge to Celery inspect/control
- **Hono Server** on `:3000` — API, SSE events, beat scheduler
- **Vite** on `:5173` — React app with HMR

Open [http://localhost:5173](http://localhost:5173) in your browser.

You can also run services individually:

```bash
make gateway   # Only the Python gateway
make server    # Only the Hono server
make web       # Only the Vite dev server
```

## Build

```bash
make build
```

Builds the frontend (Vite) and compiles the server TypeScript.

## Project Structure

```
CeleryHub/
├── packages/
│   ├── web/                    # React SPA
│   │   └── src/
│   │       ├── pages/          # Dashboard, Tasks, Workers, Beats, ...
│   │       ├── components/     # Charts, dialogs, tables
│   │       ├── hooks/          # Data fetching hooks
│   │       └── lib/            # Types, utils, event handling
│   └── server/                 # Hono backend
│       └── src/
│           ├── routes/         # API endpoints
│           └── lib/
│               ├── scheduler/  # Beat scheduler (cron + interval)
│               └── db/         # SQLite schema (Drizzle ORM)
├── services/
│   └── celery-gateway/         # FastAPI <-> Celery bridge
│       └── src/celery_gateway/
├── Makefile
├── Dockerfile
└── entrypoint.sh
```

## API

All endpoints are under `/api`:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/tasks` | List completed tasks |
| `GET` | `/api/tasks/:id/status` | Get task status |
| `POST` | `/api/tasks/send` | Send a new task |
| `POST` | `/api/tasks/:id/revoke` | Revoke a task |
| `GET` | `/api/workers` | List workers and stats |
| `GET` | `/api/queues` | List queues and depth |
| `GET` | `/api/beats` | List beat schedules |
| `POST` | `/api/beats` | Create a beat schedule |
| `PUT` | `/api/beats/:id` | Update a beat schedule |
| `DELETE` | `/api/beats/:id` | Delete a beat schedule |
| `POST` | `/api/beats/:id/toggle` | Enable/disable a beat |
| `GET` | `/api/events` | SSE event stream |
| `POST` | `/api/control/:action` | Celery control actions |

## Health Check

```bash
make health
```

## Security

CeleryHub is a monitoring tool typically deployed on private or internal networks. It does **not** include built-in authentication.

For production deployments, place CeleryHub behind a reverse proxy that handles auth:

- **nginx** with `auth_basic` or OAuth2 proxy
- **Traefik** with middleware
- **Cloudflare Tunnel** with Access policies

CeleryHub includes CORS controls (`CORS_ORIGINS`), request body size limits, and input validation on task names and signals. Redis TLS is supported — use a `rediss://` broker URL.

## License

MIT
