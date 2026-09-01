from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select, text

from ..db import get_session
from ..db.models import AlertChannel, AlertEvent, Workflow

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_S = 30.0
_COOLDOWN_S = 1800  # don't re-fire the same (rule, subject) within 30 min
_HTTP_TIMEOUT = 10.0

# Rule names — each channel opts into a subset via its `rules` JSON:
#   {"workflow_failed": {"enabled": true}, "persister_lag": {"enabled": true, "threshold": 1000}, ...}
RULE_WORKFLOW_FAILED = "workflow_failed"
RULE_DEAD_MANS_SWITCH = "dead_mans_switch"
RULE_WORKER_OFFLINE = "worker_offline"
RULE_PERSISTER_LAG = "persister_lag"
RULE_ANOMALY = "anomaly"

KNOWN_RULES = (
    RULE_WORKFLOW_FAILED,
    RULE_DEAD_MANS_SWITCH,
    RULE_WORKER_OFFLINE,
    RULE_PERSISTER_LAG,
    RULE_ANOMALY,
)

_started: bool = False
# Last worker count seen by the loop, to detect workers disappearing.
_last_worker_count: int | None = None


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _format_payload(kind: str, config: dict[str, Any], rule: str, subject: str, message: str) -> tuple[str, dict[str, Any]]:
    """Return (url, json_body) for the channel kind."""
    if kind == "discord":
        return config["url"], {"content": f"**[CeleryHub · {rule}]** {message}"}
    if kind == "telegram":
        token, chat_id = config["botToken"], config["chatId"]
        return (
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": chat_id, "text": f"[CeleryHub · {rule}] {message}"},
        )
    # generic webhook
    return config["url"], {
        "source": "celeryhub",
        "rule": rule,
        "subject": subject,
        "message": message,
        "firedAt": datetime.now(timezone.utc).isoformat(),
    }


async def _deliver(channel: AlertChannel, rule: str, subject: str, message: str) -> tuple[bool, str | None]:
    try:
        config = json.loads(channel.config or "{}")
        url, body = _format_payload(channel.kind, config, rule, subject, message)
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        return True, None
    except Exception as exc:
        return False, str(exc)[:300]


def _rule_config(channel: AlertChannel, rule: str) -> dict[str, Any] | None:
    """The rule's config on this channel, or None if not enabled there."""
    try:
        rules = json.loads(channel.rules or "{}")
    except json.JSONDecodeError:
        return None
    cfg = rules.get(rule)
    if not cfg or not cfg.get("enabled"):
        return None
    return cfg


async def _in_cooldown(session: Any, rule: str, subject: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_COOLDOWN_S)
    row = await session.scalar(
        select(AlertEvent.id)
        .where(
            AlertEvent.rule == rule,
            AlertEvent.subject == subject,
            AlertEvent.fired_at >= cutoff,
        )
        .limit(1)
    )
    return row is not None


async def fire(rule: str, subject: str, message: str) -> int:
    """Fire an alert through every enabled channel that opted into the rule.

    Cooldown is per (rule, subject) across channels. Returns the number of
    channels the alert was sent to (0 when suppressed or nobody listens).
    """
    async with get_session() as session:
        if await _in_cooldown(session, rule, subject):
            return 0
        channels = list(
            (
                await session.execute(
                    select(AlertChannel).where(AlertChannel.enabled == True)  # noqa: E712
                )
            ).scalars()
        )
        targets = [c for c in channels if _rule_config(c, rule) is not None]
        if not targets:
            return 0

        sent = 0
        now = datetime.now(timezone.utc)
        for channel in targets:
            ok, err = await _deliver(channel, rule, subject, message)
            session.add(
                AlertEvent(
                    id=str(_uuid.uuid4()),
                    rule=rule,
                    subject=subject,
                    message=message,
                    channel_id=channel.id,
                    delivered=ok,
                    error=err,
                    fired_at=now,
                )
            )
            if ok:
                sent += 1
            else:
                logger.warning(
                    "[CeleryHub Alerts] Delivery to channel '%s' failed: %s",
                    channel.name,
                    err,
                )
        await session.commit()
        return sent


def fire_and_forget(rule: str, subject: str, message: str) -> None:
    """Schedule an alert without blocking the caller (used from the engine)."""
    try:
        asyncio.get_running_loop().create_task(fire(rule, subject, message))
    except RuntimeError:
        pass  # no loop (tests calling sync paths)


# ---------------------------------------------------------------------------
# Periodic checks (dead man's switch, worker offline, persister lag)
# ---------------------------------------------------------------------------


async def _check_dead_mans_switches() -> None:
    """Workflows with expect_success_within_seconds and no recent success."""
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT w.id, w.name, w.expect_success_within_seconds,
                           max(r.finished_at) FILTER (WHERE r.status = 'succeeded') AS last_ok
                    FROM workflows w
                    LEFT JOIN workflow_runs r ON r.workflow_id = w.id
                    WHERE w.enabled = true
                      AND w.expect_success_within_seconds IS NOT NULL
                    GROUP BY w.id, w.name, w.expect_success_within_seconds
                    """
                )
            )
        ).all()

    now = datetime.now(timezone.utc)
    for wf_id, name, window_s, last_ok in rows:
        breached = (
            last_ok is None or (now - last_ok).total_seconds() > window_s
        )
        if breached:
            since = last_ok.isoformat() if last_ok else "never"
            await fire(
                RULE_DEAD_MANS_SWITCH,
                wf_id,
                f"Workflow '{name}' has no successful run within its "
                f"{window_s}s window (last success: {since}).",
            )


async def _check_workers(app_state: Any) -> None:
    """Alert when reachable worker count drops."""
    global _last_worker_count
    try:
        cache = app_state.celery_cache
        workers = await cache.get_workers()
        count = len(workers) if workers else 0
    except Exception:
        return
    if _last_worker_count is not None and count < _last_worker_count:
        await fire(
            RULE_WORKER_OFFLINE,
            "workers",
            f"Reachable workers dropped from {_last_worker_count} to {count}.",
        )
    _last_worker_count = count


async def _check_persister_lag() -> None:
    from .event_collector import EVENTS_STREAM_KEY
    from .event_persister import EVENTS_GROUP
    from .redis_client import get_redis

    try:
        groups = await get_redis().xinfo_groups(EVENTS_STREAM_KEY)
    except Exception:
        return
    for g in groups:
        name = g.get("name")
        if isinstance(name, bytes):
            name = name.decode()
        if name != EVENTS_GROUP:
            continue
        lag = g.get("lag") or 0
        pending = g.get("pending") or 0
        # Default threshold; channels can raise it per-rule but the loop uses
        # a floor to avoid evaluating channel configs here.
        if int(lag) + int(pending) > 1000:
            await fire(
                RULE_PERSISTER_LAG,
                "persister",
                f"Event persister behind: lag={lag} pending={pending}.",
            )


async def _alerts_loop(app: Any) -> None:
    logger.info("[CeleryHub Alerts] Started")
    cycle = 0
    try:
        while True:
            try:
                await _check_dead_mans_switches()
                await _check_workers(app.state)
                await _check_persister_lag()
                if cycle % 10 == 0:
                    from .anomalies import check_and_alert

                    await check_and_alert()
                cycle += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[CeleryHub Alerts] Check cycle failed")
            await asyncio.sleep(_CHECK_INTERVAL_S)
    except asyncio.CancelledError:
        logger.info("[CeleryHub Alerts] Stopped")


def start_alerts(app: Any) -> asyncio.Task[None] | None:
    global _started
    if _started:
        return None
    _started = True
    return asyncio.create_task(_alerts_loop(app))


async def stop_alerts(task: asyncio.Task[None]) -> None:
    global _started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    _started = False
