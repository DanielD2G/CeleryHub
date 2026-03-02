from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from celery_gateway.services.inspect_cache import InspectCache


def _make_inspect_cache(
    active_return: dict[str, Any] | None = None,
    ttl: float = 1.0,
) -> tuple[InspectCache, MagicMock]:
    app = MagicMock()
    inspector = MagicMock()
    inspector.active.return_value = active_return or {"w1": []}
    inspector.registered.return_value = {"w1": ["tasks.add"]}
    inspector.stats.return_value = {"w1": {"total": {}}}
    inspector.active_queues.return_value = {"w1": [{"name": "celery"}]}
    app.control.inspect.return_value = inspector
    return InspectCache(app, timeout=2.0, ttl=ttl), inspector


class TestInspectCache:
    async def test_get_first_call(self) -> None:
        cache, inspector = _make_inspect_cache()
        result = await cache.get("active")
        assert result == {"w1": []}
        inspector.active.assert_called_once()

    async def test_get_within_ttl_returns_cached(self) -> None:
        cache, inspector = _make_inspect_cache(ttl=10.0)
        await cache.get("active")
        await cache.get("active")
        # Should only be called once due to cache
        inspector.active.assert_called_once()

    async def test_get_after_ttl_re_invokes(self) -> None:
        cache, inspector = _make_inspect_cache(ttl=0.0)
        await cache.get("active")
        await cache.get("active")
        # TTL=0 means always expired, so should be called twice
        assert inspector.active.call_count == 2

    async def test_inspector_error_returns_stale(self) -> None:
        cache, inspector = _make_inspect_cache(ttl=0.0)
        # First call succeeds
        result1 = await cache.get("active")
        assert result1 == {"w1": []}

        # Make control.inspect() itself fail so _run_inspect raises
        cache._app.control.inspect.side_effect = RuntimeError("connection refused")
        result2 = await cache.get("active")
        # Should return stale data
        assert result2 == {"w1": []}

    async def test_inspector_error_no_stale_returns_empty(self) -> None:
        cache, inspector = _make_inspect_cache(ttl=0.0)
        inspector.active.side_effect = RuntimeError("fail")
        result = await cache.get("active")
        # No stale data available, should return empty dict
        assert result == {}

    async def test_force_refresh(self) -> None:
        cache, inspector = _make_inspect_cache(ttl=0.0)
        await cache.get("active")
        await cache.get("active", force_refresh=True)
        assert inspector.active.call_count == 2

    async def test_destination_filter(self) -> None:
        cache, inspector = _make_inspect_cache(ttl=10.0)
        await cache.get("active", destination=["worker1@host"])
        await cache.get("active", destination=["worker2@host"])
        # Different destinations = different cache keys
        assert inspector.active.call_count == 2

    async def test_multiple_methods(self) -> None:
        cache, inspector = _make_inspect_cache()
        active = await cache.get("active")
        registered = await cache.get("registered")

        assert active == {"w1": []}
        assert registered == {"w1": ["tasks.add"]}
