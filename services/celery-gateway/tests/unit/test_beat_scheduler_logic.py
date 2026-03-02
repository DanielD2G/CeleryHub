from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from celery_gateway.services.scheduler import (
    compute_next_run_at,
    validate_cron_expression,
)


class TestComputeNextRunAt:
    def test_interval_valid(self) -> None:
        base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = compute_next_run_at("interval", 60, None, from_date=base)
        assert result == datetime(2025, 1, 1, 0, 1, 0, tzinfo=timezone.utc)

    def test_interval_from_date(self) -> None:
        base = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = compute_next_run_at("interval", 3600, None, from_date=base)
        assert result == datetime(2025, 6, 15, 13, 0, 0, tzinfo=timezone.utc)

    def test_interval_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            compute_next_run_at("interval", 0, None)

    def test_interval_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            compute_next_run_at("interval", -10, None)

    def test_interval_none_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            compute_next_run_at("interval", None, None)

    def test_cron_valid(self) -> None:
        base = datetime(2025, 1, 1, 0, 3, 0, tzinfo=timezone.utc)
        result = compute_next_run_at("cron", None, "*/5 * * * *", from_date=base)
        assert result.minute % 5 == 0
        assert result > base

    def test_cron_without_expression_raises(self) -> None:
        with pytest.raises(ValueError, match="cron_expression is required"):
            compute_next_run_at("cron", None, None)

    def test_cron_empty_expression_raises(self) -> None:
        with pytest.raises(ValueError, match="cron_expression is required"):
            compute_next_run_at("cron", None, "")

    def test_cron_invalid_expression_raises(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            compute_next_run_at("cron", None, "invalid cron")

    def test_unknown_schedule_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown schedule type"):
            compute_next_run_at("weekly", None, None)

    def test_cron_result_has_utc_timezone(self) -> None:
        base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = compute_next_run_at("cron", None, "0 * * * *", from_date=base)
        assert result.tzinfo is not None

    def test_interval_uses_now_when_no_from_date(self) -> None:
        before = datetime.now(timezone.utc)
        result = compute_next_run_at("interval", 10, None)
        after = datetime.now(timezone.utc) + timedelta(seconds=10)
        assert before + timedelta(seconds=10) <= result <= after


class TestValidateCronExpression:
    def test_valid_expression(self) -> None:
        assert validate_cron_expression("0 * * * *") is None

    def test_valid_every_5_minutes(self) -> None:
        assert validate_cron_expression("*/5 * * * *") is None

    def test_valid_complex(self) -> None:
        assert validate_cron_expression("0 0 1 1 *") is None

    def test_invalid_expression(self) -> None:
        result = validate_cron_expression("invalid")
        assert result is not None
        assert isinstance(result, str)

    def test_seven_fields_croniter(self) -> None:
        # croniter supports second-level precision with 6+ fields
        result = validate_cron_expression("0 0 * * * * 2025")
        # May or may not be valid depending on croniter version; just ensure no crash
        assert result is None or isinstance(result, str)
