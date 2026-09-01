from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def event_uid(event: dict[str, Any]) -> str:
    raw = "{}|{}|{}".format(
        event.get("uuid", ""),
        event.get("type", ""),
        event.get("timestamp", ""),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _event_time(event: dict[str, Any]) -> datetime:
    ts = event.get("timestamp")
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def event_to_row(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_uid": event_uid(event),
        "event_time": _event_time(event),
        "event_type": event.get("type", ""),
        "task_id": event.get("uuid"),
        "task_name": event.get("name"),
        "hostname": event.get("hostname"),
        "queue": event.get("queue"),
        "runtime": _as_float(event.get("runtime")),
        "result": _str_or_none(event.get("result")),
        "exception": _str_or_none(event.get("exception")),
        "traceback": _str_or_none(event.get("traceback")),
        "payload": event,
    }


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
