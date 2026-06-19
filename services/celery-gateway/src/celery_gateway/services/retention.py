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
