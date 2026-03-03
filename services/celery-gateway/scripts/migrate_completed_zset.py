"""Migrate existing completed tasks into the celeryhub:completed ZSET.

Scans celery-task-meta-* keys for terminal tasks and indexes them in the
ZSET used by get_historical_tasks().  Also back-fills completed_at, result
and traceback into celeryhub:tasks:{id} hashes when missing.

Usage:
    CELERY_BROKER_URL=redis://localhost:6379/0 python scripts/migrate_completed_zset.py

Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from redis.asyncio import Redis

_COMPLETED_ZSET_KEY = "celeryhub:completed"
_TASK_META_KEY = "celeryhub:tasks"
_TERMINAL_STATES = frozenset({"SUCCESS", "FAILURE", "REVOKED"})
_SCAN_BATCH = 200


def _parse_completed_at(date_done: str) -> float | None:
    if not date_done:
        return None
    try:
        dt = datetime.fromisoformat(date_done.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


async def _migrate(redis_url: str) -> None:
    redis = Redis.from_url(redis_url, decode_responses=True)
    migrated = 0
    enriched = 0
    scanned = 0
    cursor: int | bytes = 0

    print(f"Connecting to {_redact_url(redis_url)} ...")

    try:
        await redis.ping()
    except Exception as exc:
        print(f"Error: cannot connect to Redis — {exc}")
        return

    print("Scanning celery-task-meta-* keys ...")

    while True:
        cursor, keys = await redis.scan(
            cursor=cursor, match="celery-task-meta-*", count=_SCAN_BATCH,
        )
        scanned += len(keys)

        if keys:
            pipe = redis.pipeline()
            for key in keys:
                pipe.get(key)
            values = await pipe.execute()

            zadd_mapping: dict[str, float] = {}
            enrich_cmds: list[tuple[str, dict[str, str]]] = []

            for key, raw in zip(keys, values):
                if not raw:
                    continue
                try:
                    data: dict[str, object] = json.loads(raw)
                except Exception:
                    continue

                status = data.get("status", "")
                if status not in _TERMINAL_STATES:
                    continue

                task_id = str(data.get("task_id", ""))
                if not task_id:
                    continue

                completed_at = _parse_completed_at(
                    str(data.get("date_done", ""))
                )
                if completed_at is None:
                    continue

                zadd_mapping[task_id] = completed_at

                # Back-fill hash fields that the old collector didn't store
                hash_fields: dict[str, str] = {
                    "completed_at": str(completed_at),
                }
                if data.get("result") is not None:
                    hash_fields["result"] = str(data["result"])
                if data.get("traceback"):
                    hash_fields["traceback"] = str(data["traceback"])
                if data.get("name"):
                    hash_fields["name"] = str(data["name"])
                if data.get("worker"):
                    hash_fields["worker"] = str(data["worker"])
                if data.get("runtime") is not None:
                    hash_fields["runtime"] = str(data["runtime"])
                if status:
                    hash_fields["status"] = str(status)
                enrich_cmds.append((task_id, hash_fields))

            if zadd_mapping:
                await redis.zadd(_COMPLETED_ZSET_KEY, zadd_mapping)  # type: ignore[arg-type]
                migrated += len(zadd_mapping)

            if enrich_cmds:
                pipe = redis.pipeline()
                for task_id, fields in enrich_cmds:
                    pipe.hset(f"{_TASK_META_KEY}:{task_id}", mapping=fields)
                await pipe.execute()
                enriched += len(enrich_cmds)

        if cursor == 0:
            break

    print(
        f"Done. Scanned {scanned} keys, "
        f"indexed {migrated} tasks in ZSET, "
        f"enriched {enriched} hashes."
    )

    zset_size = await redis.zcard(_COMPLETED_ZSET_KEY)
    print(f"ZSET '{_COMPLETED_ZSET_KEY}' now has {zset_size} entries.")

    await redis.aclose()


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.password:
        return url.replace(f":{parsed.password}@", ":***@")
    return url


def main() -> None:
    redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    asyncio.run(_migrate(redis_url))


if __name__ == "__main__":
    main()
