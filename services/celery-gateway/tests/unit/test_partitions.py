from __future__ import annotations

from datetime import date

from celery_gateway.services.partitions import (
    partition_bounds,
    partition_name,
    partitions_to_drop,
)


def test_partition_name():
    assert partition_name(date(2026, 6, 19)) == "celery_events_20260619"


def test_partition_bounds_is_one_day_range():
    lo, hi = partition_bounds(date(2026, 6, 19))
    assert lo == "2026-06-19"
    assert hi == "2026-06-20"


def test_partitions_to_drop_keeps_window():
    existing = [
        "celery_events_20260601",  # 18 days old -> drop (retention 30? keep) ...
        "celery_events_20260510",  # 40 days old -> drop
        "celery_events_20260619",  # today -> keep
    ]
    today = date(2026, 6, 19)
    dropped = partitions_to_drop(existing, today, retention_days=30)
    assert dropped == ["celery_events_20260510"]


def test_partitions_to_drop_ignores_unparseable_names():
    dropped = partitions_to_drop(["not_a_partition"], date(2026, 6, 19), 30)
    assert dropped == []
