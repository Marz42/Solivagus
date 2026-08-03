"""Stable identifiers for memory records."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import secrets


MEMORY_ID_PREFIX = "MEM-"
MEMORY_ID_PATTERN = re.compile(r"^MEM-[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_MAX_TIMESTAMP_MS = (1 << 48) - 1


def generate_memory_id(
    timestamp: datetime | None = None,
    *,
    randomness: bytes | None = None,
) -> str:
    """Return a time-sortable, ULID-compatible memory identifier.

    ``timestamp`` and ``randomness`` are injectable so codecs and tests can
    reproduce an identifier without replacing the production entropy source.
    """

    instant = datetime.now(timezone.utc) if timestamp is None else timestamp
    _require_aware_datetime(instant)
    timestamp_seconds = instant.timestamp()
    if timestamp_seconds < 0:
        raise ValueError("timestamp is outside the 48-bit memory ID range")
    timestamp_ms = int(timestamp_seconds * 1000)
    if not 0 <= timestamp_ms <= _MAX_TIMESTAMP_MS:
        raise ValueError("timestamp is outside the 48-bit memory ID range")

    entropy = secrets.token_bytes(10) if randomness is None else randomness
    if not isinstance(entropy, bytes) or len(entropy) != 10:
        raise ValueError("randomness must be exactly 10 bytes")

    value = (timestamp_ms << 80) | int.from_bytes(entropy, "big")
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = _CROCKFORD_BASE32[value & 31]
        value >>= 5
    return MEMORY_ID_PREFIX + "".join(encoded)


def is_memory_id(value: object) -> bool:
    """Return whether *value* is a canonical memory identifier."""

    return isinstance(value, str) and MEMORY_ID_PATTERN.fullmatch(value) is not None


def require_memory_id(value: object, *, field: str = "memory_id") -> str:
    if not is_memory_id(value):
        raise ValueError(
            f"{field} must match MEM-[0-7][0-9A-HJKMNP-TV-Z]{{25}}"
        )
    return value


def _require_aware_datetime(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError("timestamp must be a timezone-aware datetime")
