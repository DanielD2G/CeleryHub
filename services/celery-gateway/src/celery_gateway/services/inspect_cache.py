from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from celery import Celery

logger = logging.getLogger(__name__)


class InspectCache:
    def __init__(self, celery_app: Celery, timeout: float, ttl: float) -> None:
        self._app = celery_app
        self._timeout = timeout
        self._ttl = ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get(
        self,
        method: str,
        *,
        force_refresh: bool = False,
        destination: list[str] | None = None,
    ) -> Any:
        cache_key = f"{method}:{','.join(destination) if destination else '*'}"
        now = time.monotonic()

        if not force_refresh and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self._ttl:
                return data

        if force_refresh:
            lock = self._get_lock(cache_key)
            async with lock:
                # Double-check: another caller may have refreshed while we waited
                now = time.monotonic()
                if cache_key in self._cache:
                    ts, data = self._cache[cache_key]
                    if now - ts < self._ttl:
                        return data
                return await self._fetch(method, destination, cache_key)

        return await self._fetch(method, destination, cache_key)

    async def _fetch(
        self,
        method: str,
        destination: list[str] | None,
        cache_key: str,
    ) -> Any:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, self._run_inspect, method, destination
            )
        except Exception:
            logger.exception("Inspect %s failed", method)
            # Return stale data if available
            if cache_key in self._cache:
                return self._cache[cache_key][1]
            return {}

        self._cache[cache_key] = (time.monotonic(), result)
        return result

    def _run_inspect(
        self, method: str, destination: list[str] | None
    ) -> dict[str, Any]:
        inspector = self._app.control.inspect(
            timeout=self._timeout, destination=destination
        )
        fn = getattr(inspector, method)
        try:
            return fn() or {}
        except Exception:
            logger.exception("Inspect %s raised", method)
            return {}
