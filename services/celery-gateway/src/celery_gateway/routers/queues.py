from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["queues"])


@router.get("/queues")
async def get_queues(request: Request) -> dict[str, Any]:
    cache = request.app.state.celery_cache
    details = await cache.get("queue-details")
    return details
