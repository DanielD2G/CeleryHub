from __future__ import annotations

import base64
import json
import time

from celery_gateway.services.kombu_parser import _normalize_event, parse_kombu_message


class TestParseKombuMessage:
    def test_body_string_plain(self) -> None:
        raw = json.dumps({
            "body": json.dumps({"type": "task-sent", "uuid": "abc"}),
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "task-sent"
        assert result["uuid"] == "abc"

    def test_body_base64(self) -> None:
        event_data = {"type": "task-received", "uuid": "xyz"}
        encoded = base64.b64encode(json.dumps(event_data).encode()).decode()
        raw = json.dumps({
            "body": encoded,
            "properties": {"body_encoding": "base64"},
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "task-received"
        assert result["uuid"] == "xyz"

    def test_body_base64_via_headers(self) -> None:
        event_data = {"type": "task-started"}
        encoded = base64.b64encode(json.dumps(event_data).encode()).decode()
        raw = json.dumps({
            "body": encoded,
            "headers": {"body_encoding": "base64"},
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "task-started"

    def test_body_base64_via_body_encoding_key(self) -> None:
        event_data = {"type": "task-failed"}
        encoded = base64.b64encode(json.dumps(event_data).encode()).decode()
        raw = json.dumps({
            "body": encoded,
            "body-encoding": "base64",
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "task-failed"

    def test_body_dict_direct(self) -> None:
        raw = json.dumps({
            "body": {"type": "task-sent", "name": "add"},
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "task-sent"
        assert result["name"] == "add"

    def test_body_array_wrap(self) -> None:
        raw = json.dumps({
            "body": [{"type": "task-sent", "uuid": "wrapped"}],
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "task-sent"
        assert result["uuid"] == "wrapped"

    def test_body_empty_array(self) -> None:
        raw = json.dumps({"body": []})
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "unknown"

    def test_raw_with_type(self) -> None:
        raw = json.dumps({"type": "worker.online", "hostname": "w1"})
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "worker-online"
        assert result["hostname"] == "w1"

    def test_no_type_with_channel(self) -> None:
        raw = json.dumps({"hostname": "w1"})
        result = parse_kombu_message(raw, channel_event_type="task.sent")
        assert result is not None
        assert result["type"] == "task-sent"
        assert result["hostname"] == "w1"

    def test_no_type_no_channel(self) -> None:
        raw = json.dumps({"hostname": "w1"})
        result = parse_kombu_message(raw)
        assert result is None

    def test_invalid_json(self) -> None:
        result = parse_kombu_message("not json")
        assert result is None

    def test_headers_merge(self) -> None:
        raw = json.dumps({
            "body": json.dumps({"type": "task-sent", "name": "add"}),
            "headers": {"task": "tasks.add", "id": "header-id", "name": "should-not-overwrite"},
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["name"] == "add"  # body value preserved
        assert result["task"] == "tasks.add"  # header value merged
        assert result["id"] == "header-id"

    def test_body_envelope_with_channel_type_fallback(self) -> None:
        raw = json.dumps({"body": json.dumps({"hostname": "w1"})})
        result = parse_kombu_message(raw, channel_event_type="worker.online")
        assert result is not None
        assert result["type"] == "worker-online"

    def test_deeply_nested_properties_encoding(self) -> None:
        event_data = {"type": "task-sent"}
        encoded = base64.b64encode(json.dumps(event_data).encode()).decode()
        raw = json.dumps({
            "body": encoded,
            "properties": {"body_encoding": "base64"},
            "headers": {},
        })
        result = parse_kombu_message(raw)
        assert result is not None
        assert result["type"] == "task-sent"


class TestNormalizeEvent:
    def test_dots_to_dashes(self) -> None:
        result = _normalize_event({"type": "worker.online"})
        assert result["type"] == "worker-online"

    def test_hostname_default(self) -> None:
        result = _normalize_event({"type": "test"})
        assert result["hostname"] == "unknown"

    def test_hostname_none_becomes_unknown(self) -> None:
        result = _normalize_event({"type": "test", "hostname": None})
        assert result["hostname"] == "unknown"

    def test_hostname_preserved(self) -> None:
        result = _normalize_event({"type": "test", "hostname": "worker1"})
        assert result["hostname"] == "worker1"

    def test_timestamp_default(self) -> None:
        before = time.time()
        result = _normalize_event({"type": "test"})
        after = time.time()
        assert before <= result["timestamp"] <= after

    def test_timestamp_preserved(self) -> None:
        result = _normalize_event({"type": "test", "timestamp": 12345.0})
        assert result["timestamp"] == 12345.0

    def test_pid_default(self) -> None:
        result = _normalize_event({"type": "test"})
        assert result["pid"] == 0

    def test_clock_default(self) -> None:
        result = _normalize_event({"type": "test"})
        assert result["clock"] == 0

    def test_non_string_type(self) -> None:
        result = _normalize_event({"type": 123})
        assert result["type"] == "unknown"

    def test_extra_fields_preserved(self) -> None:
        result = _normalize_event({"type": "test", "custom": "value"})
        assert result["custom"] == "value"
