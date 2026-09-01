from __future__ import annotations

# Single source of truth for the partitioned celery_events table DDL.
# Imported by Alembic migration 0002 (prod) and the test fixture (tests),
# so the prod and test schemas never diverge. create_all cannot express
# PARTITION BY RANGE / composite PK / GENERATED IDENTITY, so celery_events
# is always built from these statements, never from Base.metadata.create_all.

_CREATE_TABLE = """
CREATE TABLE celery_events (
    id          bigint GENERATED ALWAYS AS IDENTITY,
    event_uid   text        NOT NULL,
    event_time  timestamptz NOT NULL,
    event_type  text        NOT NULL,
    task_id     text,
    task_name   text,
    hostname    text,
    queue       text,
    runtime     double precision,
    result      text,
    exception   text,
    traceback   text,
    payload     jsonb       NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, event_time),
    UNIQUE (event_uid, event_time)
) PARTITION BY RANGE (event_time);
"""

CELERY_EVENTS_STATEMENTS: list[str] = [
    _CREATE_TABLE,
    "CREATE INDEX idx_celery_events_task_id ON celery_events (task_id);",
    "CREATE INDEX idx_celery_events_name_time ON celery_events (task_name, event_time);",
    "CREATE INDEX idx_celery_events_type_time ON celery_events (event_type, event_time);",
]

DROP_CELERY_EVENTS: str = "DROP TABLE IF EXISTS celery_events CASCADE;"
