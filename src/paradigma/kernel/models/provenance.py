"""Provenance values for memory records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re

from ._validation import (
    coerce_enum,
    optional_aware_datetime,
    optional_text,
)


class ProvenanceType(str, Enum):
    USER_STATEMENT = "user_statement"
    REPOSITORY_FILE = "repository_file"
    GIT_COMMIT = "git_commit"
    TOOL_RESULT = "tool_result"
    RESEARCH_SOURCE = "research_source"
    WEB_SOURCE = "web_source"
    AGENT_INFERENCE = "agent_inference"
    MANUAL_ENTRY = "manual_entry"


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProvenanceRef:
    source_type: ProvenanceType
    source_uri: str | None = None
    source_id: str | None = None
    observed_at: datetime | None = None
    excerpt_hash: str | None = None
    actor: str | None = None

    def __post_init__(self) -> None:
        source_type = coerce_enum(self.source_type, ProvenanceType, "source_type")
        object.__setattr__(self, "source_type", source_type)
        optional_text(self.source_uri, "source_uri")
        optional_text(self.source_id, "source_id")
        optional_aware_datetime(self.observed_at, "observed_at")
        optional_text(self.actor, "actor")
        if self.excerpt_hash is not None and not _SHA256_PATTERN.fullmatch(
            self.excerpt_hash
        ):
            raise ValueError("excerpt_hash must be 64 lowercase SHA-256 hex digits")
        if self.source_uri is None and self.source_id is None and self.actor is None:
            raise ValueError(
                "provenance must identify at least one source_uri, source_id, or actor"
            )
