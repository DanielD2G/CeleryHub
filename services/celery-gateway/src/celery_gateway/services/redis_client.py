from __future__ import annotations

from urllib.parse import urlparse

from redis.asyncio import Redis

from ..config import settings

_cached: Redis | None = None


def _get_broker_url() -> str:
    return settings.celery_broker_url


def extract_db_number(url: str) -> int:
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").lstrip("/")
        return int(path)
    except (ValueError, TypeError):
        return 0


def get_redis() -> Redis:
    global _cached
    if _cached is not None:
        return _cached
    _cached = Redis.from_url(
        _get_broker_url(),
        max_connections=3,
        decode_responses=True,
    )
    return _cached


def create_subscriber() -> Redis:
    return Redis.from_url(
        _get_broker_url(),
        decode_responses=True,
    )


def get_db_number() -> int:
    return extract_db_number(_get_broker_url())


async def close_redis() -> None:
    global _cached
    if _cached is not None:
        await _cached.aclose()
        _cached = None
