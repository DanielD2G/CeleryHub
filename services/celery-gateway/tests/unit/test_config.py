from __future__ import annotations

from unittest.mock import patch

from celery_gateway.config import Settings


class TestSettings:
    def test_defaults(self) -> None:
        s = Settings()
        assert s.celery_broker_url == "redis://localhost:6379/0"
        assert s.port == 3000
        assert s.celeryhub_db_path == "./data/celeryhub.db"
        assert s.celery_result_backend is None
        assert s.inspect_timeout == 5.0
        assert s.inspect_cache_ttl == 3.0
        assert s.celeryhub_task_ttl == 0
        assert s.static_dir is None

    def test_result_backend_without_override(self) -> None:
        s = Settings()
        assert s.result_backend == s.celery_broker_url

    def test_result_backend_with_override(self) -> None:
        s = Settings(celery_result_backend="redis://other:6379/1")
        assert s.result_backend == "redis://other:6379/1"

    def test_cors_origins_default(self) -> None:
        s = Settings()
        assert s.cors_origins == ["*"]

    def test_custom_values(self) -> None:
        s = Settings(
            celery_broker_url="redis://custom:6380/2",
            port=8080,
            celeryhub_db_path="/tmp/test.db",
        )
        assert s.celery_broker_url == "redis://custom:6380/2"
        assert s.port == 8080
        assert s.celeryhub_db_path == "/tmp/test.db"
