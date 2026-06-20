from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import get_session
from ..db.models import CeleryEvent
from .event_collector import EVENTS_STREAM_KEY
from .event_mapper import event_to_row
from .partitions import create_partition, partition_name
from .redis_client import get_redis

logger = logging.getLogger(__name__)

EVENTS_GROUP = "celeryhub-persisters"
# Single fixed consumer name; no XAUTOCLAIM — assumes single-instance deployment with clean shutdown.
_CONSUMER = "persister-1"
_BATCH = 500
_BLOCK_MS = 1000
_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 30.0

_started: bool = False
_ensured_partitions: set[str] = set()


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


async def _flush_batch(entries: list[tuple[str, dict[str, Any]]]) -> None:
    events = [e for _id, e in entries if e]
    if not events:
        return
    rows = [event_to_row(e) for e in events]
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
