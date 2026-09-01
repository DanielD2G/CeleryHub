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
