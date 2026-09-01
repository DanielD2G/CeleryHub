from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

# Arbitrary but stable application-wide lock key ("CELH" in ASCII).
LEADER_LOCK_KEY = 0x43454C48

_RETRY_INTERVAL_S = 10.0

_conn: AsyncConnection | None = None
_is_leader: bool = False


def is_leader() -> bool:
    return _is_leader


async def _try_acquire(engine: Any) -> bool:
    """Try to take the leader lock on a dedicated connection.

    The connection is held open for the process lifetime; Postgres releases
    session-level advisory locks automatically when it drops, so a crashed
    leader frees the lock without cleanup.
    """
    global _conn, _is_leader
    conn = await engine.connect()
    try:
        got = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": LEADER_LOCK_KEY}
        )
    except Exception:
        await conn.close()
        raise
    if got:
        _conn = conn
        _is_leader = True
        return True
    await conn.close()
    return False


async def run_when_leader(
    engine: Any, on_acquired: Callable[[], Awaitable[None]]
) -> asyncio.Task[None]:
    """Start singleton services once this instance wins the leader lock.

    With a single replica the lock is acquired immediately. With N replicas
    exactly one runs beat/persister/retention while the rest serve the API
    and retry every _RETRY_INTERVAL_S in case the leader dies.
    """

    async def _loop() -> None:
        global _is_leader
        try:
            while True:
                try:
                    if await _try_acquire(engine):
                        logger.info(
                            "[CeleryHub Leadership] Acquired leader lock; "
                            "starting singleton services"
                        )
                        await on_acquired()
                        return
                    logger.info(
                        "[CeleryHub Leadership] Another instance holds the "
                        "leader lock; retrying in %.0fs",
                        _RETRY_INTERVAL_S,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "[CeleryHub Leadership] Lock attempt failed; retrying"
                    )
                await asyncio.sleep(_RETRY_INTERVAL_S)
        except asyncio.CancelledError:
            pass

    return asyncio.create_task(_loop())


async def release() -> None:
    global _conn, _is_leader
    _is_leader = False
    if _conn is not None:
        try:
            await _conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": LEADER_LOCK_KEY}
            )
        except Exception:
            pass
        try:
            await _conn.close()
        except Exception:
            pass
        _conn = None
