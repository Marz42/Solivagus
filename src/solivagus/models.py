from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PREFLIGHT = "preflight"
    OCR_RUNNING = "ocr_running"
    OCR_COMPLETE = "ocr_complete"
    OCR_COMPLETE_WITH_WARNINGS = "ocr_complete_with_warnings"
    PLANNING = "planning"
    TRANSLATION_RUNNING = "translation_running"
    TRANSLATION_COMPLETE = "translation_complete"
    TRANSLATION_COMPLETE_WITH_WARNINGS = "translation_complete_with_warnings"
    QA_COMPLETE = "qa_complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UnitStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    FALLBACK = "fallback"


class Stage(StrEnum):
    ALL = "all"
    OCR = "ocr"
    PLAN = "plan"
    TRANSLATE = "translate"
    QA = "qa"
