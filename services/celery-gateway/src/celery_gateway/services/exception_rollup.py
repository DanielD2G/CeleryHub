from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from ..db import get_session

logger = logging.getLogger(__name__)

_ROLLUP_INTERVAL_S = 3600.0  # hourly
# Re-aggregate a 2-day sliding window so late-arriving events are captured
# before their partition ages out.
_WINDOW_DAYS = 2

_UPSERT = text(
    """
    INSERT INTO exception_rollup (day, task_name, signature, count, sample_task_id, last_seen)
    SELECT
        (event_time AT TIME ZONE 'UTC')::date AS day,
        coalesce(task_name, '(unknown)') AS task_name,
        split_part(exception, E'\n', 1) AS signature,
        count(*) AS count,
        (array_agg(task_id ORDER BY event_time DESC))[1] AS sample_task_id,
        max(event_time) AS last_seen
    FROM celery_events
    WHERE event_type = 'task-failed'
      AND exception IS NOT NULL
      AND event_time >= :since
    GROUP BY 1, 2, 3
    ON CONFLICT (day, task_name, signature) DO UPDATE SET
        count = EXCLUDED.count,
        sample_task_id = EXCLUDED.sample_task_id,
        last_seen = EXCLUDED.last_seen
    """
)


async def rollup_once() -> None:
    since = datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)
    async with get_session() as session:
        await session.execute(_UPSERT, {"since": since})
        await session.commit()


async def _rollup_loop() -> None:
    logger.info("[CeleryHub ExceptionRollup] Started")
    try:
        while True:
            try:
                await rollup_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[CeleryHub ExceptionRollup] Rollup failed")
            await asyncio.sleep(_ROLLUP_INTERVAL_S)
    except asyncio.CancelledError:
        logger.info("[CeleryHub ExceptionRollup] Stopped")


def start_exception_rollup() -> asyncio.Task[None]:
    return asyncio.create_task(_rollup_loop())


async def stop_exception_rollup(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
