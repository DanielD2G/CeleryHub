from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import settings
from ..db import get_session
from ..db.models import Setting

RETENTION_KEY = "events_retention_days"


async def get_retention_days() -> int:
    async with get_session() as session:
        value: str | None = await session.scalar(
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
