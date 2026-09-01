from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import desc, select

from ..db import get_session
from ..db.models import AlertChannel, AlertEvent
from ..middleware.auth import require_auth
from ..models.base import CamelModel
from ..services.alerts import KNOWN_RULES, _deliver

router = APIRouter(
    prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_auth)]
)


class ChannelInput(CamelModel):
    name: str = Field(min_length=1)
    kind: str  # webhook|discord|telegram
    config: dict = Field(default_factory=dict)
    enabled: bool = True
    rules: dict = Field(default_factory=dict)


class ChannelResponse(CamelModel):
    id: str
    name: str
    kind: str
    config: dict
    enabled: bool
    rules: dict
    created_at: datetime


class AlertEventResponse(CamelModel):
    id: str
    rule: str
    subject: str
    message: str
    channel_id: str | None
    delivered: bool
    error: str | None
    fired_at: datetime


_KINDS = ("webhook", "discord", "telegram")


def _validate(body: ChannelInput) -> None:
    if body.kind not in _KINDS:
        raise HTTPException(400, f"kind must be one of {_KINDS}")
    if body.kind in ("webhook", "discord") and not body.config.get("url"):
        raise HTTPException(400, "config.url is required for this kind")
    if body.kind == "telegram" and not (
        body.config.get("botToken") and body.config.get("chatId")
    ):
        raise HTTPException(400, "config.botToken and config.chatId are required")
    unknown = set(body.rules) - set(KNOWN_RULES)
    if unknown:
        raise HTTPException(400, f"unknown rules: {sorted(unknown)}")


def _to_response(c: AlertChannel) -> ChannelResponse:
    return ChannelResponse(
        id=c.id,
        name=c.name,
        kind=c.kind,
        config=json.loads(c.config or "{}"),
        enabled=c.enabled,
        rules=json.loads(c.rules or "{}"),
        created_at=c.created_at,
    )


@router.get("/rules")
async def list_rules() -> list[str]:
    return list(KNOWN_RULES)


@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels() -> list[ChannelResponse]:
    async with get_session() as session:
        rows = (await session.execute(select(AlertChannel))).scalars().all()
    return [_to_response(c) for c in rows]


@router.post("/channels", response_model=ChannelResponse, status_code=201)
async def create_channel(body: ChannelInput) -> ChannelResponse:
    _validate(body)
    channel = AlertChannel(
        id=str(_uuid.uuid4()),
        name=body.name,
        kind=body.kind,
        config=json.dumps(body.config),
        enabled=body.enabled,
        rules=json.dumps(body.rules),
        created_at=datetime.now(timezone.utc),
    )
    async with get_session() as session:
        session.add(channel)
        await session.commit()
    return _to_response(channel)


@router.put("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(channel_id: str, body: ChannelInput) -> ChannelResponse:
    _validate(body)
    async with get_session() as session:
        channel = await session.get(AlertChannel, channel_id)
        if channel is None:
            raise HTTPException(404, "Channel not found")
        channel.name = body.name
        channel.kind = body.kind
        channel.config = json.dumps(body.config)
        channel.enabled = body.enabled
        channel.rules = json.dumps(body.rules)
        await session.commit()
        return _to_response(channel)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: str) -> None:
    async with get_session() as session:
        channel = await session.get(AlertChannel, channel_id)
        if channel is None:
            raise HTTPException(404, "Channel not found")
        await session.delete(channel)
        await session.commit()


@router.post("/channels/{channel_id}/test")
async def test_channel(channel_id: str) -> dict:
    async with get_session() as session:
        channel = await session.get(AlertChannel, channel_id)
        if channel is None:
            raise HTTPException(404, "Channel not found")
    ok, err = await _deliver(
        channel, "test", "test", "Test alert from CeleryHub — channel works."
    )
    return {"delivered": ok, "error": err}


@router.get("/events", response_model=list[AlertEventResponse])
async def list_events(limit: int = 50) -> list[AlertEventResponse]:
    async with get_session() as session:
        rows = (
            await session.execute(
                select(AlertEvent)
                .order_by(desc(AlertEvent.fired_at))
                .limit(min(max(limit, 1), 200))
            )
        ).scalars().all()
    return [AlertEventResponse.model_validate(e) for e in rows]
