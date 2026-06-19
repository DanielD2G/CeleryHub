from __future__ import annotations

import importlib
from unittest.mock import patch

from celery_gateway.config import Settings


class TestSettings:
    def test_defaults(self) -> None:
        s = Settings()
        assert s.celery_broker_url == "redis://localhost:6379/0"
        assert s.port == 3000
        assert s.database_url == "postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub"
        assert s.celery_result_backend is None
        assert s.inspect_timeout == 5.0
        assert s.inspect_cache_ttl == 3.0
        assert s.celeryhub_task_ttl == 604800
        assert s.static_dir is None

    def test_result_backend_without_override(self) -> None:
        s = Settings()
        assert s.result_backend == s.celery_broker_url

    def test_result_backend_with_override(self) -> None:
        s = Settings(celery_result_backend="redis://other:6379/1")
        assert s.result_backend == "redis://other:6379/1"

    def test_cors_origins_default(self) -> None:
        s = Settings()
        assert s.cors_origins == []

    def test_custom_values(self) -> None:
        s = Settings(
            celery_broker_url="redis://custom:6380/2",
            port=8080,
            database_url="postgresql+asyncpg://u:p@db:5432/x",
        )
        assert s.celery_broker_url == "redis://custom:6380/2"
        assert s.port == 8080
        assert s.database_url == "postgresql+asyncpg://u:p@db:5432/x"


def test_database_url_defaults_to_asyncpg(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import celery_gateway.config as config

    config = importlib.reload(config)
    assert config.settings.database_url.startswith("postgresql+asyncpg://")


def test_database_url_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    import celery_gateway.config as config

    config = importlib.reload(config)
    assert config.settings.database_url == "postgresql+asyncpg://u:p@db:5432/x"
