from __future__ import annotations

from celery_gateway.services.redis_client import extract_db_number


class TestExtractDbNumber:
    def test_with_db_number(self) -> None:
        assert extract_db_number("redis://host:6379/3") == 3

    def test_db_zero(self) -> None:
        assert extract_db_number("redis://host:6379/0") == 0

    def test_without_path(self) -> None:
        assert extract_db_number("redis://host:6379") == 0

    def test_non_numeric_path(self) -> None:
        assert extract_db_number("redis://host:6379/abc") == 0

    def test_empty_string(self) -> None:
        assert extract_db_number("") == 0

    def test_with_auth(self) -> None:
        assert extract_db_number("redis://:pass@host:6379/2") == 2

    def test_with_username_and_password(self) -> None:
        assert extract_db_number("redis://user:pass@host:6379/5") == 5

    def test_high_db_number(self) -> None:
        assert extract_db_number("redis://host:6379/15") == 15
