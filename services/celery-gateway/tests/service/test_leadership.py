from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from celery_gateway.services import leadership


@pytest.fixture(autouse=True)
async def _reset_leadership():
    yield
    await leadership.release()


@pytest.mark.asyncio
async def test_single_instance_acquires_immediately(db_engine: AsyncEngine):
    assert await leadership._try_acquire(db_engine) is True
    assert leadership.is_leader() is True


@pytest.mark.asyncio
async def test_second_connection_does_not_acquire(db_engine: AsyncEngine):
    assert await leadership._try_acquire(db_engine) is True

    # A second "instance": same lock key over a different connection.
    from sqlalchemy import text

    conn = await db_engine.connect()
    try:
        got = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": leadership.LEADER_LOCK_KEY},
        )
        assert got is False
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_release_frees_the_lock(db_engine: AsyncEngine):
    assert await leadership._try_acquire(db_engine) is True
    await leadership.release()
    assert leadership.is_leader() is False
    # Now it can be taken again.
    assert await leadership._try_acquire(db_engine) is True


@pytest.mark.asyncio
async def test_run_when_leader_starts_services(db_engine: AsyncEngine):
    started = asyncio.Event()

    async def _on_acquired() -> None:
        started.set()

    task = await leadership.run_when_leader(db_engine, _on_acquired)
    await asyncio.wait_for(started.wait(), timeout=5)
    await task  # loop returns after starting services
    assert leadership.is_leader() is True
