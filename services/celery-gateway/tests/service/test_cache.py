from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from celery_gateway.services.cache import CeleryCache


def _make_cache(
    inspect_cache: Any = None,
) -> tuple[CeleryCache, AsyncMock]:
    """Create a CeleryCache with a simple test key and return (cache, refresh_fn)."""
    ic = inspect_cache or AsyncMock()
    cache = CeleryCache(ic)

    refresh_fn = AsyncMock(return_value=["data1"])
    cache._register("test-key", 100.0, refresh_fn)
    return cache, refresh_fn


class TestCeleryCache:
    async def test_get_first_call_invokes_refresh(self) -> None:
        cache, refresh_fn = _make_cache()
        try:
            result = await cache.get("test-key")
            assert result == ["data1"]
            refresh_fn.assert_awaited_once()
        finally:
            cache.stop()

    async def test_get_cached_no_re_invoke(self) -> None:
        cache, refresh_fn = _make_cache()
        try:
            await cache.get("test-key")
            await cache.get("test-key")
            # Only one invocation because TTL hasn't expired
            refresh_fn.assert_awaited_once()
        finally:
            cache.stop()

    async def test_get_unknown_key_raises(self) -> None:
        ic = AsyncMock()
        cache = CeleryCache(ic)
        # Remove default keys to test unknown
        cache._entries.clear()
        try:
            with pytest.raises(KeyError, match="Unknown cache key"):
                await cache.get("nonexistent")
        finally:
            cache.stop()

    async def test_stop_cancels_timers(self) -> None:
        cache, _ = _make_cache()
        await cache.get("test-key")

        entry = cache._entries["test-key"]
        assert entry.task is not None
        assert not entry.task.cancelled()

        cache.stop()
        assert entry.task is None

    async def test_refresh_failure_keeps_stale_data(self) -> None:
        cache, refresh_fn = _make_cache()
        try:
            # First call succeeds
            await cache.get("test-key")
            assert cache._entries["test-key"].data == ["data1"]

            # Simulate failure
            refresh_fn.side_effect = RuntimeError("connection lost")
            await cache._refresh("test-key")

            # Data should still be the stale value
            assert cache._entries["test-key"].data == ["data1"]
        finally:
            cache.stop()

    async def test_inflight_dedup(self) -> None:
        slow_fn = AsyncMock(side_effect=lambda: asyncio.sleep(0.05) or "result")
        ic = AsyncMock()
        cache = CeleryCache(ic)
        cache._register("slow-key", 100.0, slow_fn)

        try:
            # Trigger first refresh to initialize
            await cache.get("slow-key")

            # Now both should use the same inflight task
            call_count_before = slow_fn.await_count
            t1 = asyncio.create_task(cache._refresh("slow-key"))
            t2 = asyncio.create_task(cache._refresh("slow-key"))
            await asyncio.gather(t1, t2)

            # Should have only one additional call (not two)
            assert slow_fn.await_count <= call_count_before + 1
        finally:
            cache.stop()

    async def test_data_initially_none(self) -> None:
        ic = AsyncMock()
        cache = CeleryCache(ic)
        entry = cache._entries.get("active-tasks")
        assert entry is not None
        assert entry.data is None
        cache.stop()

    async def test_registered_keys_exist(self) -> None:
        ic = AsyncMock()
        cache = CeleryCache(ic)
        expected_keys = {
            "active-tasks",
            "queue-depths",
            "task-history",
            "worker-inspect",
            "registered-tasks",
            "queue-details",
        }
        assert set(cache._entries.keys()) >= expected_keys
        cache.stop()


@pytest.mark.asyncio
async def test_registered_refresh_seeds_known_tasks(fake_redis):
    """Tasks a worker registers appear in the known-tasks set without
    waiting for their first event — this is what makes newly deployed
    tasks show up in the UI within one refresh cycle."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from celery_gateway.services.cache import CeleryCache

    inspect_cache = MagicMock()
    inspect_cache.get = AsyncMock(
        return_value={"celery@w1": ["scrape_new_store", "celery.chord_unlock"]}
    )
    cache = CeleryCache(inspect_cache)

    with (
        patch(
            "celery_gateway.services.celery_redis.get_known_task_names",
            new=AsyncMock(return_value=["scrape_old"]),
        ),
        patch(
            "celery_gateway.services.redis_client.get_redis",
            return_value=fake_redis,
        ),
    ):
        data = await cache._refresh_registered_tasks()

    # celery.* internals are excluded; the new task is seeded
    members = await fake_redis.smembers("celeryhub:known-tasks")
    decoded = {m.decode() if isinstance(m, bytes) else m for m in members}
    assert decoded == {"scrape_new_store"}
    assert "scrape_new_store" in data["tasks"]
    cache.stop()
