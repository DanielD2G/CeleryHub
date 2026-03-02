from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel


def validate_json_string(v: str | None, field_name: str) -> str | None:
    """Validate that *v* is a valid JSON string, or ``None``."""
    if v is None:
        return v
    try:
        json.loads(v)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid JSON for {field_name}") from exc
    return v


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    @model_validator(mode="after")
    def _ensure_utc_datetimes(self) -> CamelModel:
        """Attach UTC tzinfo to naive datetimes (e.g. read from SQLite)."""
        for name, field_info in self.model_fields.items():
            value = getattr(self, name)
            if isinstance(value, datetime) and value.tzinfo is None:
                object.__setattr__(self, name, value.replace(tzinfo=timezone.utc))
        return self
