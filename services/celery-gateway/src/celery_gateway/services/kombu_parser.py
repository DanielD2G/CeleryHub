from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def parse_kombu_message(
    raw: str, channel_event_type: str | None = None
) -> dict[str, Any] | None:
    try:
        msg: dict[str, Any] = json.loads(raw)

        # Format 1: Kombu envelope with body field
        if "body" in msg:
            body: dict[str, Any]

            if isinstance(msg["body"], str):
                encoding = (
                    (msg.get("properties") or {}).get("body_encoding")
                    or (msg.get("headers") or {}).get("body_encoding")
                    or msg.get("body-encoding")
                )

                if encoding == "base64":
                    decoded = base64.b64decode(msg["body"]).decode("utf-8")
                    body = json.loads(decoded)
                else:
                    body = json.loads(msg["body"])
            else:
                body = msg["body"]

            # Kombu wraps event data in an array: [{...event...}]
            if isinstance(body, list):
                body = body[0] if body else {}

            event: dict[str, Any] = body or {}

            # Normalize the type field
            if "type" not in event and channel_event_type:
                event["type"] = channel_event_type

            # Merge headers into event if present (don't overwrite body fields)
            headers = msg.get("headers")
            if isinstance(headers, dict):
                for key, value in headers.items():
                    if key not in event:
                        event[key] = value

            return _normalize_event(event)

        # Format 2: Raw event with type field directly
        if "type" in msg:
            return _normalize_event(msg)

        # Format 3: No type field, use channel info
        if channel_event_type:
            msg["type"] = channel_event_type
            return _normalize_event(msg)

        return None
    except Exception:
        return None


def _normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    event_type = raw.get("type", "unknown")
    if isinstance(event_type, str):
        event_type = event_type.replace(".", "-")
    else:
        event_type = "unknown"

    return {
        **raw,
        "type": event_type,
        "hostname": raw.get("hostname", "unknown") or "unknown",
        "timestamp": raw.get("timestamp") or time.time(),
        "pid": raw.get("pid", 0) or 0,
        "clock": raw.get("clock", 0) or 0,
    }
