from __future__ import annotations

from datetime import timezone

from celery_gateway.services.event_mapper import event_to_row, event_uid


def _sample() -> dict:
    return {
        "uuid": "abc-123",
        "type": "task-succeeded",
        "timestamp": 1_700_000_000.0,
        "name": "tasks.add",
        "hostname": "worker@host",
        "queue": "celery",
        "runtime": 0.42,
        "result": "7",
        "args": "[3, 4]",
        "kwargs": "{}",
    }


def test_event_uid_is_deterministic():
    e = _sample()
    assert event_uid(e) == event_uid(dict(e))


def test_event_uid_changes_with_type():
    e = _sample()
    other = dict(e, type="task-failed")
    assert event_uid(e) != event_uid(other)


def test_event_to_row_maps_typed_columns():
    row = event_to_row(_sample())
    assert row["task_id"] == "abc-123"
    assert row["event_type"] == "task-succeeded"
    assert row["task_name"] == "tasks.add"
    assert row["hostname"] == "worker@host"
    assert row["queue"] == "celery"
    assert row["runtime"] == 0.42
    assert row["result"] == "7"
    assert row["event_time"].tzinfo == timezone.utc
    assert row["payload"]["name"] == "tasks.add"


def test_event_to_row_handles_missing_timestamp():
    e = _sample()
    del e["timestamp"]
    row = event_to_row(e)
    assert row["event_time"].tzinfo == timezone.utc
