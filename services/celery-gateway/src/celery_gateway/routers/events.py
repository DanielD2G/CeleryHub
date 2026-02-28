from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["events"])

logger = logging.getLogger(__name__)


async def _event_stream(request: Request) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    from ..services.event_collector import on_celery_event

    def _on_event(event: dict[str, Any]) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    unsubscribe = on_celery_event(_on_event)

    try:
        yield json.dumps({"type": "connected"})

        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield json.dumps(event)
            except asyncio.TimeoutError:
                yield ""
    finally:
        unsubscribe()


@router.get("/events")
async def events(request: Request) -> EventSourceResponse:
    return EventSourceResponse(_event_stream(request))
