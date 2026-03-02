from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..models.tasks import FrontendQueueDetailsResult

router = APIRouter(tags=["queues"])


@router.get("/queues", response_model=FrontendQueueDetailsResult)
async def get_queues(request: Request) -> Any:
    cache = request.app.state.celery_cache
    return await cache.get("queue-details")
