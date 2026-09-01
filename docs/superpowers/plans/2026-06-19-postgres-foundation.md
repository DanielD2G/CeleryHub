# Postgres Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `services/celery-gateway` from embedded SQLite to an external PostgreSQL database (driver `asyncpg`), introduce Alembic migrations, and run the entire existing test suite against Postgres — with no new product features.

**Architecture:** Replace the SQLite async engine with an `asyncpg` engine driven by a `DATABASE_URL` setting. Drop the hand-rolled `_run_migrations` and `create_all`-on-startup in favor of Alembic. Existing models keep their current column types (JSON-as-text); JSONB is reserved for the high-volume events table introduced in Plan 2. Test fixtures switch from in-memory SQLite to a real Postgres test database.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, PostgreSQL 16, pytest / pytest-asyncio.

## Global Constraints

- Python `>=3.11`; type-annotate everything; `_` prefix for private vars/functions.
- API responses are camelCase via Pydantic `CamelModel` (`alias_generator=to_camel`). No change in this plan.
- No `"use client"`/`"use server"`/`server-only` anywhere (frontend rule — not touched here).
- No backward-compatibility / data migration from the old SQLite file (greenfield Postgres).
- Commit messages: do NOT include a `Co-Authored-By` trailer.
- Deviation from spec, applied deliberately: workflow tables keep JSON-as-text columns; JSONB is used only for `celery_events.payload` in Plan 2.

---

### Task 1: Dependencies and `database_url` setting

**Files:**
- Modify: `services/celery-gateway/pyproject.toml`
- Modify: `services/celery-gateway/src/celery_gateway/config.py`
- Test: `services/celery-gateway/tests/unit/test_config.py`

**Interfaces:**
- Produces: `settings.database_url: str` (default `postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_config.py`:

```python
from __future__ import annotations

import importlib


def test_database_url_defaults_to_asyncpg(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import celery_gateway.config as config

    config = importlib.reload(config)
    assert config.settings.database_url.startswith("postgresql+asyncpg://")


def test_database_url_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    import celery_gateway.config as config

    config = importlib.reload(config)
    assert config.settings.database_url == "postgresql+asyncpg://u:p@db:5432/x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/unit/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'database_url'`

- [ ] **Step 3: Add the setting**

In `config.py`, inside `class Settings`, add the field (place it next to the other `celeryhub_*` settings) and remove the now-unused `celeryhub_db_path`:

```python
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub"
```

Delete this line:

```python
    celeryhub_db_path: str = "./data/celeryhub.db"
```

- [ ] **Step 4: Update dependencies in `pyproject.toml`**

In `[project].dependencies`, remove `"aiosqlite>=0.20",` and add:

```toml
    "asyncpg>=0.30",
    "alembic>=1.14",
```

In `[project.optional-dependencies].test`, add:

```toml
    "psycopg[binary]>=3.2",
```

(psycopg is used by Alembic's synchronous migration runner in Task 3; asyncpg is the app runtime driver.)

- [ ] **Step 5: Install and run the test**

Run: `cd services/celery-gateway && pip install -e ".[test]" && pytest tests/unit/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add services/celery-gateway/pyproject.toml services/celery-gateway/src/celery_gateway/config.py services/celery-gateway/tests/unit/test_config.py
git commit -m "feat(db): add database_url setting and Postgres deps"
```

---

### Task 2: Switch the database engine to Postgres

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/db/__init__.py`

**Interfaces:**
- Consumes: `settings.database_url` (Task 1).
- Produces: `init_db()`, `close_db()`, `get_session()` unchanged in signature; engine now `postgresql+asyncpg`. `_run_migrations` and `_set_sqlite_pragmas` removed. `init_db()` no longer calls `create_all` (schema is owned by Alembic, Task 3).

- [ ] **Step 1: Rewrite `db/__init__.py`**

Replace the full contents with:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    global _engine, _session_factory

    _engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
```

Note: the `Base.metadata.create_all` call is intentionally gone — Alembic (Task 3) owns the schema for deployments; tests create the schema themselves (Task 4).

- [ ] **Step 2: Verify import still works**

Run: `cd services/celery-gateway && python -c "from celery_gateway.db import init_db, get_session, close_db; print('ok')"`
Expected: prints `ok` (no SQLite/aiosqlite import errors).

- [ ] **Step 3: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/db/__init__.py
git commit -m "feat(db): use asyncpg engine, remove SQLite pragmas and create_all"
```

---

### Task 3: Alembic setup and initial migration

**Files:**
- Create: `services/celery-gateway/alembic.ini`
- Create: `services/celery-gateway/migrations/env.py`
- Create: `services/celery-gateway/migrations/script.py.mako`
- Create: `services/celery-gateway/migrations/versions/0001_initial_schema.py`

**Interfaces:**
- Consumes: `celery_gateway.db.models.Base.metadata`, `settings.database_url`.
- Produces: `alembic upgrade head` creates `workflows`, `workflow_steps`, `workflow_runs`, `step_runs`, `task_runs` with their existing columns and indexes.

- [ ] **Step 1: Create `alembic.ini`**

```ini
[alembic]
script_location = migrations
prepend_sys_path = src

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create `migrations/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 3: Create `migrations/env.py`**

The app uses an async URL (`postgresql+asyncpg`). Alembic runs migrations synchronously, so convert the URL to the sync `psycopg` driver here.

```python
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from celery_gateway.config import settings
from celery_gateway.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    return settings.database_url.replace("+asyncpg", "+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create the initial migration `migrations/versions/0001_initial_schema.py`**

This mirrors the current models exactly (column types as they are today — `String`/`Text`/`Integer`/`Boolean`/`DateTime(timezone=True)`), including indexes.

```python
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schedule_type", sa.String(), nullable=False, server_default="none"),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("cron_expression", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_run_count", sa.Integer(), nullable=True),
        sa.Column("total_run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_workflows_schedule",
        "workflows",
        ["enabled", "schedule_type", "next_run_at"],
    )

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.String(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("task_names", sa.String(), nullable=False, server_default="[]"),
        sa.Column("args", sa.String(), nullable=True, server_default="[]"),
        sa.Column("kwargs", sa.String(), nullable=True, server_default="{}"),
        sa.Column("queue", sa.String(), nullable=True, server_default="celery"),
        sa.Column("depends_on", sa.String(), nullable=False, server_default="[]"),
        sa.Column(
            "condition", sa.String(), nullable=False, server_default="all_succeeded"
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"]
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.String(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("trigger", sa.String(), nullable=False, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("idx_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "step_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("step_label", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_step_runs_workflow_run_id", "step_runs", ["workflow_run_id"])

    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "step_run_id",
            sa.String(),
            sa.ForeignKey("step_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("args", sa.String(), nullable=True),
        sa.Column("kwargs", sa.String(), nullable=True),
        sa.Column("queue", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="SENT"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_task_runs_step_run_id", "task_runs", ["step_run_id"])
    op.create_index("idx_task_runs_task_id", "task_runs", ["task_id"])


def downgrade() -> None:
    op.drop_table("task_runs")
    op.drop_table("step_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflow_steps")
    op.drop_table("workflows")
```

- [ ] **Step 5: Apply the migration against a local Postgres**

Start a throwaway Postgres and run the migration:

```bash
docker run -d --name ch-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=celeryhub -p 5432:5432 postgres:16
cd services/celery-gateway && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub alembic upgrade head
```

Expected: `INFO [alembic.runtime.migration] Running upgrade -> 0001, initial schema` and exit 0.

- [ ] **Step 6: Verify tables exist**

Run: `docker exec ch-pg psql -U postgres -d celeryhub -c "\dt"`
Expected: lists `workflows`, `workflow_steps`, `workflow_runs`, `step_runs`, `task_runs`.

- [ ] **Step 7: Commit**

```bash
git add services/celery-gateway/alembic.ini services/celery-gateway/migrations
git commit -m "feat(db): add Alembic with initial Postgres schema"
```

---

### Task 4: Migrate test infrastructure to Postgres

**Files:**
- Modify: `services/celery-gateway/tests/conftest.py`
- Create: `services/celery-gateway/tests/_db.py`

**Interfaces:**
- Consumes: `Base.metadata`, env var `TEST_DATABASE_URL` (default `postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub_test`).
- Produces: `db_engine` / `db_session` fixtures now bound to Postgres; each test run starts from a clean schema (`drop_all` + `create_all`). Existing per-module patches preserved.

- [ ] **Step 1: Create `tests/_db.py`**

```python
from __future__ import annotations

import os


def test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub_test",
    )
```

- [ ] **Step 2: Update the `db_engine` fixture in `conftest.py`**

Replace the current `db_engine` fixture with one that points at Postgres and resets the schema. Add the import `from tests._db import test_database_url` near the top.

```python
@pytest.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(test_database_url(), echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

The `db_session` fixture body (the `patch(...)` block and factory) stays exactly as it is — only the engine source changed.

- [ ] **Step 3: Create the test database**

```bash
docker exec ch-pg psql -U postgres -c "CREATE DATABASE celeryhub_test;"
```

- [ ] **Step 4: Run the full existing suite against Postgres**

Run: `cd services/celery-gateway && pytest -q`
Expected: the entire existing suite passes (same count as before the migration, 0 failures). If a test relied on SQLite-only behavior, fix that test to be dialect-neutral.

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/tests/conftest.py services/celery-gateway/tests/_db.py
git commit -m "test(db): run suite against Postgres test database"
```

---

### Task 5: docker-compose, environment, and docs

**Files:**
- Modify (or create): `docker-compose.yml` (repo root)
- Create: `services/celery-gateway/.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces: a `postgres` service + `DATABASE_URL` wired into the app service; documented setup.

- [ ] **Step 1: Add the `postgres` service to `docker-compose.yml`**

Add (or merge) the following. Keep any existing `redis`/app services intact; add `postgres` and the `DATABASE_URL` env + `depends_on` to the gateway service.

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: celeryhub
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

  celery-gateway:
    # ...existing build/image config...
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/celeryhub
      # ...existing env (CELERY_BROKER_URL, etc.)...
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 2: Create `services/celery-gateway/.env.example`**

```bash
# Celery broker (Redis)
CELERY_BROKER_URL=redis://localhost:6379/0

# PostgreSQL (SQLAlchemy async URL)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub

# Optional
CELERYHUB_AUTH_TOKEN=
PORT=3000
```

- [ ] **Step 3: Document migrations in `README.md`**

Add a short "Database" subsection stating: Postgres is required; set `DATABASE_URL`; run `alembic upgrade head` before first start (and after pulling new migrations). Note that the container entrypoint should run `alembic upgrade head` on boot.

- [ ] **Step 4: Run migration on compose to verify wiring**

Run: `docker compose up -d postgres && sleep 5 && cd services/celery-gateway && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub alembic upgrade head`
Expected: exit 0, migration `0001` applied.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml services/celery-gateway/.env.example README.md
git commit -m "chore(db): add postgres service, env example, and migration docs"
```

---

## Verification (end of plan)

- [ ] `pytest -q` green against Postgres.
- [ ] `alembic upgrade head` then `alembic downgrade base` both succeed (migration is reversible).
- [ ] App boots: `DATABASE_URL=... uvicorn celery_gateway.main:app` starts with no SQLite references and `/health` responds.
- [ ] `grep -rn "sqlite\|aiosqlite\|celeryhub_db_path" src/` returns nothing.
