from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import get_session
from ..db.models import CeleryEvent
from .event_collector import EVENTS_STREAM_KEY, _TASK_META_KEY
from .event_mapper import event_to_row
from .partitions import create_partition, partition_name
from .redis_client import get_redis

logger = logging.getLogger(__name__)

EVENTS_GROUP = "celeryhub-persisters"
# Single fixed consumer name. Entries left pending by a hard kill are
# reclaimed on startup and periodically via XAUTOCLAIM (see _claim_stale).
_CONSUMER = "persister-1"
_BATCH = 500
_BLOCK_MS = 1000
_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 30.0
_CLAIM_MIN_IDLE_MS = 60_000
_CLAIM_INTERVAL_S = 300.0
_NAME_CACHE_MAX = 10_000

_started: bool = False
_ensured_partitions: set[str] = set()
# task_id -> task_name, fed by events that carry "name" (task-sent/received).
# Celery omits the name on started/succeeded/failed events; without this
# backfill those rows persist with task_name NULL and per-task runtime
# queries cannot use them.
_task_names: dict[str, str] = {}


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
            except (KeyError, json.JSONDecodeError) as exc:
                logger.warning(
                    "[CeleryHub EventPersister] Skipping malformed stream entry %s: %s",
                    msg_id,
                    exc,
                )
                out.append((msg_id, {}))
    return out


def _remember_task_name(task_id: str, name: str) -> None:
    if len(_task_names) >= _NAME_CACHE_MAX:
        # Drop ~10% oldest insertions; dict preserves insertion order.
        for key in list(_task_names)[: _NAME_CACHE_MAX // 10]:
            _task_names.pop(key, None)
    _task_names[task_id] = name


async def _backfill_task_names(redis: Any, rows: list[dict[str, Any]]) -> None:
    """Fill task_name on rows whose event type does not carry it.

    Sources, in order: names seen in this same batch, the process-local
    cache, and finally the Redis hot-layer task metadata hash.
    """
    for row in rows:
        if row["task_name"] and row["task_id"]:
            _remember_task_name(row["task_id"], row["task_name"])

    missing = [
        r for r in rows
        if not r["task_name"] and r["task_id"]
    ]
    still_missing: list[dict[str, Any]] = []
    for row in missing:
        cached = _task_names.get(row["task_id"])
        if cached:
            row["task_name"] = cached
        else:
            still_missing.append(row)

    if not still_missing:
        return
    try:
        pipe = redis.pipeline()
        for row in still_missing:
            pipe.hget(f"{_TASK_META_KEY}:{row['task_id']}", "name")
        results = await pipe.execute()
    except Exception:
        logger.warning(
            "[CeleryHub EventPersister] task_name backfill lookup failed; "
            "%d row(s) keep NULL task_name",
            len(still_missing),
        )
        return
    unresolved: list[dict[str, Any]] = []
    for row, name in zip(still_missing, results):
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name:
            row["task_name"] = name
            _remember_task_name(row["task_id"], name)
        else:
            unresolved.append(row)

    if not unresolved:
        return
    # Last resort: the workflow engine's task_runs table. Covers tasks that
    # never produced a task-received (e.g. NotRegistered failures).
    try:
        from sqlalchemy import select

        from ..db.models import TaskRun

        ids = [r["task_id"] for r in unresolved]
        async with get_session() as session:
            rows_db = (
                await session.execute(
                    select(TaskRun.task_id, TaskRun.task_name).where(
                        TaskRun.task_id.in_(ids)
                    )
                )
            ).all()
        by_id = {tid: name for tid, name in rows_db if name}
        for row in unresolved:
            name = by_id.get(row["task_id"])
            if name:
                row["task_name"] = name
                _remember_task_name(row["task_id"], name)
    except Exception:
        logger.warning(
            "[CeleryHub EventPersister] task_runs backfill lookup failed",
            exc_info=True,
        )


async def _flush_batch(
    entries: list[tuple[str, dict[str, Any]]], redis: Any
) -> None:
    events = [e for _id, e in entries if e]
    if not events:
        return
    rows = [event_to_row(e) for e in events]
    await _backfill_task_names(redis, rows)
    today = datetime.now(timezone.utc).date()
    needed_days = {r["event_time"].date() for r in rows}
    needed_days |= {today + timedelta(days=offset) for offset in range(3)}
    missing = sorted(d for d in needed_days if partition_name(d) not in _ensured_partitions)
    try:
        async with get_session() as session:
            for day in missing:
                await create_partition(session, day)
            stmt = pg_insert(CeleryEvent).values(rows)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["event_uid", "event_time"]
            )
            await session.execute(stmt)
            await session.commit()
        _ensured_partitions.update(partition_name(d) for d in missing)
    except Exception:
        _ensured_partitions.clear()
        raise


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
    await _flush_batch(entries, redis)
    await redis.xack(EVENTS_STREAM_KEY, EVENTS_GROUP, *[mid for mid, _ in entries])
    return len(entries)


async def _claim_stale(redis: Any) -> int:
    """Reclaim entries stuck in the PEL after a hard kill.

    A crash between XREADGROUP and XACK leaves entries pending forever for
    this consumer group. XAUTOCLAIM re-delivers any entry idle longer than
    _CLAIM_MIN_IDLE_MS so it gets flushed and acked.
    """
    claimed_total = 0
    cursor = "0-0"
    while True:
        try:
            reply = await redis.xautoclaim(
                EVENTS_STREAM_KEY,
                EVENTS_GROUP,
                _CONSUMER,
                min_idle_time=_CLAIM_MIN_IDLE_MS,
                start_id=cursor,
                count=_BATCH,
            )
        except Exception as exc:
            if "NOGROUP" in str(exc):
                return claimed_total
            raise
        # redis-py returns (next_cursor, messages[, deleted_ids])
        cursor, messages = reply[0], reply[1]
        if messages:
            entries = _decode_entries([(EVENTS_STREAM_KEY, messages)])
            await _flush_batch(entries, redis)
            await redis.xack(
                EVENTS_STREAM_KEY, EVENTS_GROUP, *[mid for mid, _ in entries]
            )
            claimed_total += len(entries)
        if isinstance(cursor, bytes):
            cursor = cursor.decode()
        if cursor == "0-0" or not messages:
            break
    if claimed_total:
        logger.info(
            "[CeleryHub EventPersister] Reclaimed %d stale pending entrie(s)",
            claimed_total,
        )
    return claimed_total


async def _persister_loop() -> None:
    redis = get_redis()
    await _ensure_group(redis)
    logger.info("[CeleryHub EventPersister] Started")
    backoff = _BACKOFF_BASE
    last_claim = 0.0
    try:
        while True:
            try:
                now = asyncio.get_running_loop().time()
                if now - last_claim >= _CLAIM_INTERVAL_S:
                    await _claim_stale(redis)
                    last_claim = now
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
