"""Small validation helpers shared by immutable kernel values."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
from typing import TypeVar


EnumT = TypeVar("EnumT", bound=Enum)
_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field} must not have surrounding whitespace")
    return value


def optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return require_text(value, field)


def require_token(value: object, field: str) -> str:
    checked = require_text(value, field)
    if not _TOKEN_PATTERN.fullmatch(checked):
        raise ValueError(f"{field} must be a lowercase snake_case token")
    return checked


def require_aware_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def optional_aware_datetime(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    return require_aware_datetime(value, field)


def require_tuple(value: object, field: str) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be a tuple")
    return value


def require_unique_text_tuple(value: object, field: str) -> tuple[str, ...]:
    items = require_tuple(value, field)
    normalized = tuple(require_text(item, f"{field} item") for item in items)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def coerce_enum(value: object, enum_type: type[EnumT], field: str) -> EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        allowed = ", ".join(str(item.value) for item in enum_type)
        raise ValueError(f"{field} must be one of: {allowed}") from error
