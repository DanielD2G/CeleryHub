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


async def create_partition(session: Any, day: date) -> None:
    """Issue CREATE TABLE IF NOT EXISTS for one day's partition. Does not commit."""
    name = partition_name(day)
    lo, hi = partition_bounds(day)
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {name} "
            f"PARTITION OF celery_events "
            f"FOR VALUES FROM ('{lo}') TO ('{hi}');"
        )
    )


async def ensure_partitions(
    session: Any, today: date, ahead_days: int = 2
) -> None:
    for offset in range(0, ahead_days + 1):
        await create_partition(session, today + timedelta(days=offset))
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
