from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CeleryEvent(BaseModel):
    type: str
    hostname: str = "unknown"
    timestamp: float = 0.0
    pid: int = 0
    clock: int = 0

    model_config = {"extra": "allow"}


class SSEConnectedEvent(BaseModel):
    type: str = "connected"


class SSEEventData(BaseModel):
    type: str
    hostname: str = "unknown"
    timestamp: float = 0.0
    pid: int = 0
    clock: int = 0
    extra: dict[str, Any] = {}
