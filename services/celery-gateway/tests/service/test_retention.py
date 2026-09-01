from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from celery_gateway.services.partitions import ensure_partitions, list_partitions
from celery_gateway.services.retention import run_retention_once


@pytest.mark.asyncio
async def test_retention_drops_old_partitions(db_session, monkeypatch):
    from celery_gateway.db import get_session

    # Create an old partition (2026-01-01 — ~169 days before 2026-06-19) directly.
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
