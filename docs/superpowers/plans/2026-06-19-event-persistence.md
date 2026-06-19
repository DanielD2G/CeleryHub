# Event Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every Celery event heard on the Redis pub/sub bus into a durable, append-only, time-partitioned PostgreSQL table, buffered through a Redis Stream, with a configurable retention window and a history query API.

**Architecture:** The existing `event_collector` keeps writing live state to Redis (unchanged) and additionally `XADD`s each parsed event to a Redis Stream. A new `event_persister` background task consumes that stream with a consumer group, bulk-inserts batches into `celery_events` (daily partitions, JSONB payload, dedup via `event_uid` + `ON CONFLICT DO NOTHING`), and `XACK`s only after commit — giving at-least-once delivery with no loss when Postgres is down. A retention task drops partitions older than the configured window. A `settings` table backs the UI-configurable retention value.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, asyncpg, PostgreSQL 16 (native range partitioning), redis.asyncio Streams, pytest.

**Prerequisite:** Plan `2026-06-19-postgres-foundation.md` is complete (app runs on Postgres + Alembic; test suite green on Postgres).

## Global Constraints

- Python `>=3.11`; type-annotate everything; `_` prefix for private vars/functions.
- API responses are camelCase via `CamelModel`.
- Existing live view (Redis + SSE on `GET /api/events`) must NOT change behavior. The historical endpoint uses a DIFFERENT path: `GET /api/event-log` (the `/events` path is the SSE stream).
- Commit messages: no `Co-Authored-By` trailer.
- At-least-once is acceptable; exactly-once is achieved at the row level via the `event_uid` unique constraint.
- Stream key: `celeryhub:events:stream`. Consumer group: `celeryhub-persisters`.

---

### Task 1: `CeleryEvent` model + partitioned-table migration

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/db/models.py`
- Create: `services/celery-gateway/migrations/versions/0002_celery_events.py`
- Create: `services/celery-gateway/migrations/versions/0003_settings.py`

**Interfaces:**
- Produces: ORM model `CeleryEvent` (table `celery_events`); ORM model `Setting` (table `settings`, columns `key: str` PK, `value: str`). Parent table `celery_events` is `PARTITION BY RANGE (event_time)` with a `UNIQUE (event_uid, event_time)` constraint.

- [ ] **Step 1: Add the models to `models.py`**

Add the imports `from sqlalchemy import BigInteger, Float` and `from sqlalchemy.dialects.postgresql import JSONB` at the top, then append:

```python
class CeleryEvent(Base):
    __tablename__ = "celery_events"

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True)
    event_uid: Mapped[str] = mapped_column(String, nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String, default=None)
    task_name: Mapped[str | None] = mapped_column(String, default=None)
    hostname: Mapped[str | None] = mapped_column(String, default=None)
    queue: Mapped[str | None] = mapped_column(String, default=None)
    runtime: Mapped[float | None] = mapped_column(Float, default=None)
    result: Mapped[str | None] = mapped_column(Text, default=None)
    exception: Mapped[str | None] = mapped_column(Text, default=None)
    traceback: Mapped[str | None] = mapped_column(Text, default=None)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Composite PK includes the partition key (required by Postgres for
    # partitioned tables). The actual DDL is authored in the migration;
    # this mapping exists so ORM reads/inserts work.
    __mapper_args__ = {"primary_key": [id, event_time]}


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
```

- [ ] **Step 2: Create `migrations/versions/0002_celery_events.py`**

`create_all` cannot express native partitioning, so the parent table is authored in raw SQL. Helper functions to create/drop partitions live here too (callable from app code via plain SQL — see Task 6/7).

```python
"""celery_events partitioned table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-19
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE celery_events (
            id          bigint GENERATED ALWAYS AS IDENTITY,
            event_uid   text        NOT NULL,
            event_time  timestamptz NOT NULL,
            event_type  text        NOT NULL,
            task_id     text,
            task_name   text,
            hostname    text,
            queue       text,
            runtime     double precision,
            result      text,
            exception   text,
            traceback   text,
            payload     jsonb       NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (id, event_time),
            UNIQUE (event_uid, event_time)
        ) PARTITION BY RANGE (event_time);
        """
    )
    op.execute(
        "CREATE INDEX idx_celery_events_task_id ON celery_events (task_id);"
    )
    op.execute(
        "CREATE INDEX idx_celery_events_name_time "
        "ON celery_events (task_name, event_time);"
    )
    op.execute(
        "CREATE INDEX idx_celery_events_type_time "
        "ON celery_events (event_type, event_time);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE celery_events;")
```

- [ ] **Step 3: Create `migrations/versions/0003_settings.py`**

```python
"""settings table

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("settings")
```

- [ ] **Step 4: Apply migrations**

Run: `cd services/celery-gateway && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub alembic upgrade head`
Expected: upgrades `0002` and `0003` run; exit 0.

- [ ] **Step 5: Verify partitioned table**

Run: `docker exec ch-pg psql -U postgres -d celeryhub -c "\d+ celery_events"`
Expected: shows `Partition key: RANGE (event_time)`.

- [ ] **Step 6: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/db/models.py services/celery-gateway/migrations/versions/0002_celery_events.py services/celery-gateway/migrations/versions/0003_settings.py
git commit -m "feat(events): add celery_events partitioned table and settings table"
```

---

### Task 2: Partition management helpers (pure logic + DDL)

**Files:**
- Create: `services/celery-gateway/src/celery_gateway/services/partitions.py`
- Test: `services/celery-gateway/tests/unit/test_partitions.py`

**Interfaces:**
- Produces:
  - `partition_name(day: date) -> str` → `"celery_events_YYYYMMDD"`.
  - `partition_bounds(day: date) -> tuple[str, str]` → ISO `from`/`to` (next day).
  - `partitions_to_drop(existing: list[str], today: date, retention_days: int) -> list[str]` → names whose day `< today - retention_days`.
  - `async def ensure_partitions(session, today: date, ahead_days: int = 2) -> None` → `CREATE TABLE IF NOT EXISTS ... PARTITION OF` for `[today, today+ahead_days]`.
  - `async def list_partitions(session) -> list[str]`.
  - `async def drop_partition(session, name: str) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_partitions.py`:

```python
from __future__ import annotations

from datetime import date

from celery_gateway.services.partitions import (
    partition_bounds,
    partition_name,
    partitions_to_drop,
)


def test_partition_name():
    assert partition_name(date(2026, 6, 19)) == "celery_events_20260619"


def test_partition_bounds_is_one_day_range():
    lo, hi = partition_bounds(date(2026, 6, 19))
    assert lo == "2026-06-19"
    assert hi == "2026-06-20"


def test_partitions_to_drop_keeps_window():
    existing = [
        "celery_events_20260601",  # 18 days old -> drop (retention 30? keep) ...
        "celery_events_20260510",  # 40 days old -> drop
        "celery_events_20260619",  # today -> keep
    ]
    today = date(2026, 6, 19)
    dropped = partitions_to_drop(existing, today, retention_days=30)
    assert dropped == ["celery_events_20260510"]


def test_partitions_to_drop_ignores_unparseable_names():
    dropped = partitions_to_drop(["not_a_partition"], date(2026, 6, 19), 30)
    assert dropped == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/unit/test_partitions.py -v`
Expected: FAIL with `ModuleNotFoundError: celery_gateway.services.partitions`.

- [ ] **Step 3: Implement `services/partitions.py`**

```python
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

_PREFIX = "celery_events_"


def partition_name(day: date) -> str:
    return f"{_PREFIX}{day.strftime('%Y%m%d')}"


def partition_bounds(day: date) -> tuple[str, str]:
    nxt = day + timedelta(days=1)
    return day.isoformat(), nxt.isoformat()


def _day_from_name(name: str) -> date | None:
    if not name.startswith(_PREFIX):
        return None
    stamp = name[len(_PREFIX):]
    try:
        return date(int(stamp[0:4]), int(stamp[4:6]), int(stamp[6:8]))
    except (ValueError, IndexError):
        return None


def partitions_to_drop(
    existing: list[str], today: date, retention_days: int
) -> list[str]:
    cutoff = today - timedelta(days=retention_days)
    out: list[str] = []
    for name in existing:
        day = _day_from_name(name)
        if day is not None and day < cutoff:
            out.append(name)
    return out


async def ensure_partitions(
    session: Any, today: date, ahead_days: int = 2
) -> None:
    for offset in range(0, ahead_days + 1):
        day = today + timedelta(days=offset)
        name = partition_name(day)
        lo, hi = partition_bounds(day)
        await session.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {name} "
                f"PARTITION OF celery_events "
                f"FOR VALUES FROM ('{lo}') TO ('{hi}');"
            )
        )
    await session.commit()


async def list_partitions(session: Any) -> list[str]:
    result = await session.execute(
        text(
            "SELECT inhrelid::regclass::text AS name "
            "FROM pg_inherits "
            "WHERE inhparent = 'celery_events'::regclass "
            "ORDER BY name;"
        )
    )
    return [row[0] for row in result.fetchall()]


async def drop_partition(session: Any, name: str) -> None:
    await session.execute(text(f"DROP TABLE IF EXISTS {name};"))
    await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/celery-gateway && pytest tests/unit/test_partitions.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/partitions.py services/celery-gateway/tests/unit/test_partitions.py
git commit -m "feat(events): partition management helpers"
```

---

### Task 3: Event → row mapping and `event_uid` (pure logic)

**Files:**
- Create: `services/celery-gateway/src/celery_gateway/services/event_mapper.py`
- Test: `services/celery-gateway/tests/unit/test_event_mapper.py`

**Interfaces:**
- Consumes: a parsed event dict (same shape produced by `kombu_parser.parse_kombu_message`, e.g. keys `uuid`, `type`, `timestamp`, `name`, `hostname`, `queue`, `runtime`, `result`, `exception`, `traceback`, `args`, `kwargs`).
- Produces:
  - `event_uid(event: dict) -> str` → deterministic sha1 hex of `task_id|event_type|timestamp`.
  - `event_to_row(event: dict) -> dict` → dict with keys matching `CeleryEvent` columns (`event_uid`, `event_time`, `event_type`, `task_id`, `task_name`, `hostname`, `queue`, `runtime`, `result`, `exception`, `traceback`, `payload`). `event_time` is a tz-aware `datetime`; `payload` is the original event dict.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_event_mapper.py`:

```python
from __future__ import annotations

from datetime import timezone

from celery_gateway.services.event_mapper import event_to_row, event_uid


def _sample() -> dict:
    return {
        "uuid": "abc-123",
        "type": "task-succeeded",
        "timestamp": 1_700_000_000.0,
        "name": "tasks.add",
        "hostname": "worker@host",
        "queue": "celery",
        "runtime": 0.42,
        "result": "7",
        "args": "[3, 4]",
        "kwargs": "{}",
    }


def test_event_uid_is_deterministic():
    e = _sample()
    assert event_uid(e) == event_uid(dict(e))


def test_event_uid_changes_with_type():
    e = _sample()
    other = dict(e, type="task-failed")
    assert event_uid(e) != event_uid(other)


def test_event_to_row_maps_typed_columns():
    row = event_to_row(_sample())
    assert row["task_id"] == "abc-123"
    assert row["event_type"] == "task-succeeded"
    assert row["task_name"] == "tasks.add"
    assert row["hostname"] == "worker@host"
    assert row["queue"] == "celery"
    assert row["runtime"] == 0.42
    assert row["result"] == "7"
    assert row["event_time"].tzinfo == timezone.utc
    assert row["payload"]["name"] == "tasks.add"


def test_event_to_row_handles_missing_timestamp():
    e = _sample()
    del e["timestamp"]
    row = event_to_row(e)
    assert row["event_time"].tzinfo == timezone.utc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/unit/test_event_mapper.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `services/event_mapper.py`**

```python
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def event_uid(event: dict[str, Any]) -> str:
    raw = "{}|{}|{}".format(
        event.get("uuid", ""),
        event.get("type", ""),
        event.get("timestamp", ""),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _event_time(event: dict[str, Any]) -> datetime:
    ts = event.get("timestamp")
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def event_to_row(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_uid": event_uid(event),
        "event_time": _event_time(event),
        "event_type": event.get("type", ""),
        "task_id": event.get("uuid"),
        "task_name": event.get("name"),
        "hostname": event.get("hostname"),
        "queue": event.get("queue"),
        "runtime": _as_float(event.get("runtime")),
        "result": _str_or_none(event.get("result")),
        "exception": _str_or_none(event.get("exception")),
        "traceback": _str_or_none(event.get("traceback")),
        "payload": event,
    }


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/celery-gateway && pytest tests/unit/test_event_mapper.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/event_mapper.py services/celery-gateway/tests/unit/test_event_mapper.py
git commit -m "feat(events): event-to-row mapping and deterministic event_uid"
```

---

### Task 4: Publish events to the Redis Stream from the collector

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/services/event_collector.py`
- Modify: `services/celery-gateway/src/celery_gateway/config.py`
- Test: `services/celery-gateway/tests/service/test_event_stream_publish.py`

**Interfaces:**
- Consumes: `get_redis()` (already imported in `event_collector`).
- Produces: `async def _publish_to_stream(event: dict) -> None` and a constant `EVENTS_STREAM_KEY = "celeryhub:events:stream"`. Called at the END of `_persist_event`. New setting `settings.celeryhub_events_stream_maxlen: int = 1_000_000`.

- [ ] **Step 1: Add the setting**

In `config.py` add next to the other `celeryhub_*` settings:

```python
    celeryhub_events_stream_maxlen: int = 1_000_000
    celeryhub_events_retention_days: int = 30
```

- [ ] **Step 2: Write the failing test**

Create `tests/service/test_event_stream_publish.py`:

```python
from __future__ import annotations

import pytest

from celery_gateway.services.event_collector import (
    EVENTS_STREAM_KEY,
    _publish_to_stream,
)


@pytest.mark.asyncio
async def test_publish_adds_to_stream(fake_redis):
    await _publish_to_stream(
        {"uuid": "x", "type": "task-succeeded", "timestamp": 1700000000.0}
    )
    length = await fake_redis.xlen(EVENTS_STREAM_KEY)
    assert length == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/service/test_event_stream_publish.py -v`
Expected: FAIL with `ImportError: cannot import name '_publish_to_stream'`.

- [ ] **Step 4: Implement the publisher in `event_collector.py`**

Add the constant near the other keys and the function below `_persist_event`. The stream stores a single field `data` holding the JSON-encoded event (the persister re-parses it).

```python
EVENTS_STREAM_KEY = "celeryhub:events:stream"


async def _publish_to_stream(event: dict[str, Any]) -> None:
    redis = get_redis()
    try:
        await redis.xadd(
            EVENTS_STREAM_KEY,
            {"data": json.dumps(event)},
            maxlen=settings.celeryhub_events_stream_maxlen,
            approximate=True,
        )
    except Exception:
        logger.warning("[CeleryHub EventCollector] Failed to enqueue event to stream")
```

At the very end of `_persist_event(event)`, after all Redis writes, add:

```python
    await _publish_to_stream(event)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd services/celery-gateway && pytest tests/service/test_event_stream_publish.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/event_collector.py services/celery-gateway/src/celery_gateway/config.py services/celery-gateway/tests/service/test_event_stream_publish.py
git commit -m "feat(events): publish parsed events to Redis Stream buffer"
```

---

### Task 5: `event_persister` — consume stream, bulk-insert with dedup

**Files:**
- Create: `services/celery-gateway/src/celery_gateway/services/event_persister.py`
- Test: `services/celery-gateway/tests/service/test_event_persister.py`

**Interfaces:**
- Consumes: `EVENTS_STREAM_KEY`, `event_to_row` (Task 3), `ensure_partitions` (Task 2), `get_redis`, `get_session`.
- Produces:
  - `EVENTS_GROUP = "celeryhub-persisters"`.
  - `async def _ensure_group(redis) -> None` → idempotent `XGROUP CREATE ... MKSTREAM`.
  - `async def _flush_batch(entries: list[tuple[str, dict]]) -> None` → maps to rows, `ensure_partitions`, bulk `INSERT ... ON CONFLICT (event_uid, event_time) DO NOTHING`, commit.
  - `async def _consume_once(redis) -> int` → one `XREADGROUP` (COUNT 500, BLOCK 1000), flush, `XACK`; returns entries processed.
  - `start_event_persister() -> asyncio.Task | None`, `async def stop_event_persister(task) -> None` (mirror collector lifecycle).

- [ ] **Step 1: Write the failing integration test**

Create `tests/service/test_event_persister.py`. Uses the real Postgres `db_session` fixture and `fake_redis`.

```python
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select, text

from celery_gateway.db.models import CeleryEvent
from celery_gateway.services.event_collector import EVENTS_STREAM_KEY
from celery_gateway.services.event_persister import (
    _consume_once,
    _ensure_group,
)


async def _seed(fake_redis, event: dict) -> None:
    await fake_redis.xadd(EVENTS_STREAM_KEY, {"data": json.dumps(event)})


@pytest.mark.asyncio
async def test_persister_inserts_event(fake_redis, db_session):
    await _ensure_group(fake_redis)
    await _seed(
        fake_redis,
        {"uuid": "t1", "type": "task-succeeded", "timestamp": 1700000000.0,
         "name": "tasks.add"},
    )
    processed = await _consume_once(fake_redis)
    assert processed == 1

    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 1


@pytest.mark.asyncio
async def test_persister_dedups_on_retry(fake_redis, db_session):
    await _ensure_group(fake_redis)
    evt = {"uuid": "t2", "type": "task-failed", "timestamp": 1700000000.0,
           "name": "tasks.boom"}
    await _seed(fake_redis, evt)
    await _seed(fake_redis, evt)  # same uid twice
    await _consume_once(fake_redis)

    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/service/test_event_persister.py -v`
Expected: FAIL with `ModuleNotFoundError: celery_gateway.services.event_persister`.

- [ ] **Step 3: Implement `services/event_persister.py`**

```python
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import get_session
from ..db.models import CeleryEvent
from .event_collector import EVENTS_STREAM_KEY
from .event_mapper import event_to_row
from .partitions import ensure_partitions
from .redis_client import get_redis

logger = logging.getLogger(__name__)

EVENTS_GROUP = "celeryhub-persisters"
_CONSUMER = "persister-1"
_BATCH = 500
_BLOCK_MS = 1000
_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 30.0

_started: bool = False


async def _ensure_group(redis: Any) -> None:
    try:
        await redis.xgroup_create(
            EVENTS_STREAM_KEY, EVENTS_GROUP, id="0", mkstream=True
        )
    except Exception as exc:  # BUSYGROUP if it already exists
        if "BUSYGROUP" not in str(exc):
            raise


def _decode_entries(raw: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for _stream, messages in raw:
        for msg_id, fields in messages:
            try:
                out.append((msg_id, json.loads(fields["data"])))
            except (KeyError, json.JSONDecodeError):
                out.append((msg_id, {}))
    return out


async def _flush_batch(entries: list[tuple[str, dict[str, Any]]]) -> None:
    events = [e for _id, e in entries if e]
    if not events:
        return
    rows = [event_to_row(e) for e in events]
    days = {r["event_time"].date() for r in rows}
    async with get_session() as session:
        today = datetime.now(timezone.utc).date()
        await ensure_partitions(session, today)
        for day in days:
            await ensure_partitions(session, day, ahead_days=0)
        stmt = pg_insert(CeleryEvent).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["event_uid", "event_time"])
        await session.execute(stmt)
        await session.commit()


async def _consume_once(redis: Any) -> int:
    raw = await redis.xreadgroup(
        EVENTS_GROUP,
        _CONSUMER,
        {EVENTS_STREAM_KEY: ">"},
        count=_BATCH,
        block=_BLOCK_MS,
    )
    if not raw:
        return 0
    entries = _decode_entries(raw)
    if not entries:
        return 0
    await _flush_batch(entries)
    await redis.xack(EVENTS_STREAM_KEY, EVENTS_GROUP, *[mid for mid, _ in entries])
    return len(entries)


async def _persister_loop() -> None:
    redis = get_redis()
    await _ensure_group(redis)
    logger.info("[CeleryHub EventPersister] Started")
    backoff = _BACKOFF_BASE
    try:
        while True:
            try:
                await _consume_once(redis)
                backoff = _BACKOFF_BASE
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "[CeleryHub EventPersister] Flush failed, retry in %.1fs (not acked)",
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)
    except asyncio.CancelledError:
        logger.info("[CeleryHub EventPersister] Stopped")


def start_event_persister() -> asyncio.Task[None] | None:
    global _started
    if _started:
        return None
    _started = True
    return asyncio.create_task(_persister_loop())


async def stop_event_persister(task: asyncio.Task[None]) -> None:
    global _started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    _started = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/celery-gateway && pytest tests/service/test_event_persister.py -v`
Expected: PASS (2 passed). (On failure of the flush, entries are NOT acked — verify by reading code path; covered conceptually by the retry design.)

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/event_persister.py services/celery-gateway/tests/service/test_event_persister.py
git commit -m "feat(events): event_persister consumes stream and bulk-inserts with dedup"
```

---

### Task 6: Retention job (drop old partitions)

**Files:**
- Create: `services/celery-gateway/src/celery_gateway/services/retention.py`
- Modify: `services/celery-gateway/src/celery_gateway/services/settings_store.py` (created in Task 7 — if implementing in order, this import is added in Task 7; for now read retention from `settings.celeryhub_events_retention_days`)
- Test: `services/celery-gateway/tests/service/test_retention.py`

**Interfaces:**
- Consumes: `list_partitions`, `partitions_to_drop`, `drop_partition` (Task 2).
- Produces:
  - `async def run_retention_once(retention_days: int) -> list[str]` → drops and returns dropped partition names.
  - `start_retention() -> asyncio.Task`, `async def stop_retention(task) -> None`. Loop ticks every 3600s.

- [ ] **Step 1: Write the failing test**

Create `tests/service/test_retention.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from celery_gateway.services.partitions import ensure_partitions, list_partitions
from celery_gateway.services.retention import run_retention_once


@pytest.mark.asyncio
async def test_retention_drops_old_partitions(db_session, monkeypatch):
    from celery_gateway.db import get_session

    # Create an old partition (60 days ago) directly.
    async with get_session() as s:
        await s.execute(
            text(
                "CREATE TABLE IF NOT EXISTS celery_events_20260101 "
                "PARTITION OF celery_events "
                "FOR VALUES FROM ('2026-01-01') TO ('2026-01-02');"
            )
        )
        await s.commit()
        await ensure_partitions(s, datetime.now(timezone.utc).date())

    dropped = await run_retention_once(retention_days=30)
    assert "celery_events_20260101" in dropped
```

Note: this test assumes "today" is well after 2026-02 so the 2026-01-01 partition is outside a 30-day window. If running earlier, adjust the hard-coded old date in the test to `today - 60 days`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/service/test_retention.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `services/retention.py`**

```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from ..db import get_session
from .partitions import drop_partition, list_partitions, partitions_to_drop

logger = logging.getLogger(__name__)

_TICK_SECONDS = 3600.0


async def run_retention_once(retention_days: int) -> list[str]:
    async with get_session() as session:
        existing = await list_partitions(session)
    today = datetime.now(timezone.utc).date()
    to_drop = partitions_to_drop(existing, today, retention_days)
    async with get_session() as session:
        for name in to_drop:
            await drop_partition(session, name)
    if to_drop:
        logger.info("[CeleryHub Retention] Dropped %d partition(s)", len(to_drop))
    return to_drop


async def _retention_loop() -> None:
    from .settings_store import get_retention_days

    logger.info("[CeleryHub Retention] Started")
    try:
        while True:
            try:
                days = await get_retention_days()
                await run_retention_once(days)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[CeleryHub Retention] Tick error")
            await asyncio.sleep(_TICK_SECONDS)
    except asyncio.CancelledError:
        logger.info("[CeleryHub Retention] Stopped")


def start_retention() -> asyncio.Task[None]:
    return asyncio.create_task(_retention_loop())


async def stop_retention(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/celery-gateway && pytest tests/service/test_retention.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/retention.py services/celery-gateway/tests/service/test_retention.py
git commit -m "feat(events): retention job drops partitions outside the window"
```

---

### Task 7: Settings store (UI-configurable retention)

**Files:**
- Create: `services/celery-gateway/src/celery_gateway/services/settings_store.py`
- Test: `services/celery-gateway/tests/service/test_settings_store.py`

**Interfaces:**
- Consumes: `Setting` model (Task 1), `settings.celeryhub_events_retention_days` as the default/env fallback.
- Produces:
  - `RETENTION_KEY = "events_retention_days"`.
  - `async def get_retention_days() -> int` → value from `settings` table if present, else `settings.celeryhub_events_retention_days`.
  - `async def set_retention_days(days: int) -> None` → upsert into `settings` (raises `ValueError` if `days < 1`).

- [ ] **Step 1: Write the failing test**

Create `tests/service/test_settings_store.py`:

```python
from __future__ import annotations

import pytest

from celery_gateway.services.settings_store import (
    get_retention_days,
    set_retention_days,
)


@pytest.mark.asyncio
async def test_retention_default_when_unset(db_session):
    # No row in settings -> env/default (30)
    assert await get_retention_days() == 30


@pytest.mark.asyncio
async def test_set_and_get_retention(db_session):
    await set_retention_days(90)
    assert await get_retention_days() == 90


@pytest.mark.asyncio
async def test_set_retention_rejects_non_positive(db_session):
    with pytest.raises(ValueError):
        await set_retention_days(0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/service/test_settings_store.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `services/settings_store.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import settings
from ..db import get_session
from ..db.models import Setting

RETENTION_KEY = "events_retention_days"


async def get_retention_days() -> int:
    async with get_session() as session:
        value = await session.scalar(
            select(Setting.value).where(Setting.key == RETENTION_KEY)
        )
    if value is None:
        return settings.celeryhub_events_retention_days
    try:
        return int(value)
    except ValueError:
        return settings.celeryhub_events_retention_days


async def set_retention_days(days: int) -> None:
    if days < 1:
        raise ValueError("retention_days must be >= 1")
    async with get_session() as session:
        stmt = pg_insert(Setting).values(key=RETENTION_KEY, value=str(days))
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"], set_={"value": str(days)}
        )
        await session.execute(stmt)
        await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/celery-gateway && pytest tests/service/test_settings_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/settings_store.py services/celery-gateway/tests/service/test_settings_store.py
git commit -m "feat(events): settings store for UI-configurable retention"
```

---

### Task 8: History query API + settings API

**Files:**
- Create: `services/celery-gateway/src/celery_gateway/routers/event_log.py`
- Create: `services/celery-gateway/src/celery_gateway/models/event_log.py`
- Modify: `services/celery-gateway/src/celery_gateway/main.py`
- Test: `services/celery-gateway/tests/api/test_event_log_router.py`

**Interfaces:**
- Consumes: `CeleryEvent`, `Setting`, `get_retention_days`/`set_retention_days`, `require_auth`, `CamelModel`.
- Produces:
  - `GET /api/event-log` with query params `task_id`, `task_name`, `event_type`, `since` (ISO), `until` (ISO), `limit` (default 100, max 500). Returns `{items: [...], nextCursor: <iso|null>}` keyset-paginated by `event_time` descending (cursor = `before` ISO timestamp).
  - `GET /api/settings/retention` → `{retentionDays: int}`.
  - `PUT /api/settings/retention` body `{retentionDays: int}` → `{retentionDays: int}` (400 on `< 1`).

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_event_log_router.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from celery_gateway.db import get_session
from celery_gateway.services.partitions import ensure_partitions


async def _insert_event(task_name: str, event_type: str) -> None:
    async with get_session() as s:
        await ensure_partitions(s, datetime.now(timezone.utc).date())
        await s.execute(
            text(
                "INSERT INTO celery_events "
                "(event_uid, event_time, event_type, task_id, task_name, payload, ingested_at) "
                "VALUES (:uid, now(), :etype, :tid, :tname, '{}'::jsonb, now())"
            ),
            {
                "uid": f"{task_name}-{event_type}",
                "etype": event_type,
                "tid": task_name,
                "tname": task_name,
            },
        )
        await s.commit()


@pytest.mark.asyncio
async def test_event_log_returns_inserted_events(client):
    await _insert_event("tasks.alpha", "task-succeeded")
    resp = await client.get("/api/event-log")
    assert resp.status_code == 200
    body = resp.json()
    assert any(i["taskName"] == "tasks.alpha" for i in body["items"])


@pytest.mark.asyncio
async def test_event_log_filters_by_type(client):
    await _insert_event("tasks.beta", "task-failed")
    resp = await client.get("/api/event-log", params={"eventType": "task-failed"})
    assert resp.status_code == 200
    assert all(i["eventType"] == "task-failed" for i in resp.json()["items"])


@pytest.mark.asyncio
async def test_get_and_put_retention(client):
    put = await client.put("/api/settings/retention", json={"retentionDays": 45})
    assert put.status_code == 200
    assert put.json()["retentionDays"] == 45

    get = await client.get("/api/settings/retention")
    assert get.json()["retentionDays"] == 45


@pytest.mark.asyncio
async def test_put_retention_rejects_zero(client):
    resp = await client.put("/api/settings/retention", json={"retentionDays": 0})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/celery-gateway && pytest tests/api/test_event_log_router.py -v`
Expected: FAIL (404s — routes not mounted).

- [ ] **Step 3: Create `models/event_log.py`**

```python
from __future__ import annotations

from datetime import datetime

from .base import CamelModel


class EventLogItem(CamelModel):
    event_time: datetime
    event_type: str
    task_id: str | None = None
    task_name: str | None = None
    hostname: str | None = None
    queue: str | None = None
    runtime: float | None = None


class EventLogPage(CamelModel):
    items: list[EventLogItem]
    next_cursor: datetime | None = None


class RetentionResponse(CamelModel):
    retention_days: int


class RetentionInput(CamelModel):
    retention_days: int
```

- [ ] **Step 4: Create `routers/event_log.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select

from ..db import get_session
from ..db.models import CeleryEvent
from ..middleware.auth import require_auth
from ..models.event_log import (
    EventLogItem,
    EventLogPage,
    RetentionInput,
    RetentionResponse,
)
from ..services.settings_store import get_retention_days, set_retention_days

router = APIRouter(tags=["event-log"], dependencies=[Depends(require_auth)])


@router.get("/event-log", response_model=EventLogPage)
async def event_log(
    task_id: str | None = Query(default=None, alias="taskId"),
    task_name: str | None = Query(default=None, alias="taskName"),
    event_type: str | None = Query(default=None, alias="eventType"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    before: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> EventLogPage:
    stmt = select(CeleryEvent)
    if task_id:
        stmt = stmt.where(CeleryEvent.task_id == task_id)
    if task_name:
        stmt = stmt.where(CeleryEvent.task_name == task_name)
    if event_type:
        stmt = stmt.where(CeleryEvent.event_type == event_type)
    if since:
        stmt = stmt.where(CeleryEvent.event_time >= since)
    if until:
        stmt = stmt.where(CeleryEvent.event_time <= until)
    if before:
        stmt = stmt.where(CeleryEvent.event_time < before)
    stmt = stmt.order_by(desc(CeleryEvent.event_time)).limit(limit + 1)

    async with get_session() as session:
        rows = list((await session.execute(stmt)).scalars().all())

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [EventLogItem.model_validate(r) for r in rows]
    next_cursor = rows[-1].event_time if has_more and rows else None
    return EventLogPage(items=items, next_cursor=next_cursor)


@router.get("/settings/retention", response_model=RetentionResponse)
async def get_retention() -> RetentionResponse:
    return RetentionResponse(retention_days=await get_retention_days())


@router.put("/settings/retention", response_model=RetentionResponse)
async def put_retention(body: RetentionInput) -> RetentionResponse:
    try:
        await set_retention_days(body.retention_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RetentionResponse(retention_days=await get_retention_days())
```

- [ ] **Step 5: Mount the router in `main.py`**

Add `event_log` to the routers import and include it:

```python
from .routers import control, event_log, events, queues, tasks, workflows, workers
```

```python
app.include_router(event_log.router, prefix="/api")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd services/celery-gateway && pytest tests/api/test_event_log_router.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/routers/event_log.py services/celery-gateway/src/celery_gateway/models/event_log.py services/celery-gateway/src/celery_gateway/main.py services/celery-gateway/tests/api/test_event_log_router.py
git commit -m "feat(events): event-log history API and retention settings API"
```

---

### Task 9: Wire persister + retention into the app lifespan

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/main.py`

**Interfaces:**
- Consumes: `start_event_persister`/`stop_event_persister` (Task 5), `start_retention`/`stop_retention` (Task 6).
- Produces: both background tasks started on app startup and stopped on shutdown, mirroring the collector/scheduler pattern.

- [ ] **Step 1: Add imports**

```python
from .services.event_persister import start_event_persister, stop_event_persister
from .services.retention import start_retention, stop_retention
```

- [ ] **Step 2: Start in lifespan (after `scheduler_task = start_scheduler()`)**

```python
    persister_task = start_event_persister()
    retention_task = start_retention()
```

- [ ] **Step 3: Stop in lifespan (in the shutdown section, before `celery_cache.stop()`)**

```python
    await stop_retention(retention_task)
    if persister_task is not None:
        await stop_event_persister(persister_task)
```

- [ ] **Step 4: Smoke test the full app boots**

Run (with Postgres + Redis up):
```bash
cd services/celery-gateway && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub \
  CELERY_BROKER_URL=redis://localhost:6379/0 \
  python -c "import asyncio; from celery_gateway.main import lifespan, app; \
  async def main():\n    async with lifespan(app):\n        print('boot-ok')\nasyncio.run(main())"
```
Expected: prints `boot-ok` with `EventPersister Started` and `Retention Started` in logs, then clean shutdown.

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/main.py
git commit -m "feat(events): start event_persister and retention in app lifespan"
```

---

### Task 10: End-to-end resilience test (Postgres-down buffering)

**Files:**
- Create: `services/celery-gateway/tests/service/test_event_persistence_e2e.py`

**Interfaces:**
- Consumes: collector publish (`_persist_event` → stream), persister consume, dedup.

- [ ] **Step 1: Write the test**

Verifies: events published while the persister is NOT consuming accumulate in the stream (pending), and are persisted once it consumes — proving no loss across a Postgres/persister outage.

```python
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from celery_gateway.db.models import CeleryEvent
from celery_gateway.services.event_collector import EVENTS_STREAM_KEY, _publish_to_stream
from celery_gateway.services.event_persister import _consume_once, _ensure_group


@pytest.mark.asyncio
async def test_events_buffered_then_persisted(fake_redis, db_session):
    await _ensure_group(fake_redis)

    # "Outage": events queued but not yet consumed.
    for i in range(5):
        await _publish_to_stream(
            {"uuid": f"e{i}", "type": "task-succeeded", "timestamp": 1700000000.0 + i,
             "name": "tasks.work"}
        )
    assert await fake_redis.xlen(EVENTS_STREAM_KEY) == 5

    # "Recovery": persister drains the backlog.
    processed = await _consume_once(fake_redis)
    assert processed == 5

    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 5
```

- [ ] **Step 2: Run the test**

Run: `cd services/celery-gateway && pytest tests/service/test_event_persistence_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run: `cd services/celery-gateway && pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add services/celery-gateway/tests/service/test_event_persistence_e2e.py
git commit -m "test(events): end-to-end buffering and persistence resilience"
```

---

## Verification (end of plan)

- [ ] `pytest -q` green (Postgres + fakeredis).
- [ ] `alembic upgrade head` reaches `0003`; `celery_events` is range-partitioned with the dedup unique index.
- [ ] With app + worker running, firing tasks produces rows in `celery_events`; `GET /api/event-log` returns them; live SSE on `/api/events` still works unchanged.
- [ ] `PUT /api/settings/retention {retentionDays:7}` then waiting one retention tick drops partitions older than 7 days.
- [ ] Killing Postgres mid-run leaves events pending in the stream; restarting Postgres drains them with no loss and no duplicates.

## Notes for the frontend (out of scope for this plan)

The UI work to add a "History" view consuming `GET /api/event-log` and a retention control consuming `GET/PUT /api/settings/retention` lives in `packages/web` and is a separate frontend task.
