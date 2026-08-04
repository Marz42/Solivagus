"""Pure mechanical QA checks (no network)."""

from __future__ import annotations

import re
from typing import Iterable

from solivagus.qa.models import QAFinding, Severity, UnitQAResult
from solivagus.util.markdown import PASSTHROUGH_PATTERNS, protect_markdown

_NUMBER_RE = re.compile(r"(?<![\w./-])(\d+(?:\.\d+)?)(%|°C|°F|ms|s|kg|m|cm|mm|Hz|GHz|MB|GB)?\b")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_CITATION_RE = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
_FIG_RE = re.compile(r"\b(?:Fig(?:ure)?|图)\s*\.?\s*(\d+[a-zA-Z]?)\b", re.IGNORECASE)
_TABLE_RE = re.compile(r"\b(?:Table|表)\s*\.?\s*(\d+[a-zA-Z]?)\b", re.IGNORECASE)
_EQ_RE = re.compile(r"\b(?:Eq(?:uation)?|公式)\s*\.?\s*\(?(\d+)\)?\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s<>\])]+")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_FENCE_RE = re.compile(r"(?m)^(?:```|~~~)")
_FORMULA_RE = re.compile(r"\$\$|\\\(|\\\[")
_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+")
_PAGE_MARKER_RE = re.compile(r"<!--\s*source-page:\s*\d+\s*-->", re.IGNORECASE)
_MD_TABLE_SEP_RE = re.compile(r"(?m)^\s*\|?[\s:-]+\|[\s|:-]*$")


def _extract_html_tables(text: str) -> list[str]:
    tables: list[str] = []
    for kind, pattern in PASSTHROUGH_PATTERNS:
        if kind not in {"html_table", "html_table_wrapper"}:
            continue
        tables.extend(m.group(0) for m in pattern.finditer(text))
    return tables


def _md_table_shapes(text: str) -> list[tuple[int, int]]:
    """Return list of (header_cols, row_count) for markdown tables."""
    shapes: list[tuple[int, int]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "|" not in lines[i]:
            i += 1
            continue
        block = [lines[i]]
        j = i + 1
        while j < len(lines) and "|" in lines[j]:
            block.append(lines[j])
            j += 1
        if len(block) >= 2 and _MD_TABLE_SEP_RE.match(block[1]):
            cols = [c for c in block[0].strip().strip("|").split("|")]
            shapes.append((len(cols), len(block)))
        i = j
    return shapes


def _numbers(text: str) -> set[str]:
    return {m.group(1) for m in _NUMBER_RE.finditer(text)}


def _set_missing(source_items: Iterable[str], translation: str) -> list[str]:
    missing = []
    for item in source_items:
        if item and item not in translation:
            missing.append(item)
    return missing


def check_unit(
    *,
    unit_key: str,
    source_text: str,
    translation_text: str,
    unit_status: str = "done",
    warning_flags: str | None = None,
    terminology: dict[str, str] | None = None,
    numerical_check: bool = True,
    structure_check: bool = True,
    citation_check: bool = True,
    terminology_check: bool = True,
) -> UnitQAResult:
    findings: list[QAFinding] = []
    source = source_text or ""
    translation = translation_text or ""

    if unit_status == "fallback" or (warning_flags and "fallback" in warning_flags):
        findings.append(
            QAFinding(
                code="fallback",
                message="API 失败或校验失败，已保留英文原文",
                severity=Severity.HIGH,
            )
        )
        return UnitQAResult(
            unit_key=unit_key,
            status="fallback",
            findings=findings,
            source_text=source,
            translation_text=translation,
            html_tables_kept=len(_extract_html_tables(source)),
        )

    if structure_check:
        # Preserve placeholders if present in source after protect simulation.
        protected, placeholders = protect_markdown(source)
        _ = protected
        for token in placeholders:
            if token not in translation and placeholders[token] not in translation:
                # Source keepers should appear literally in translation when they are
                # structural (code/formula/image). Soft-check: if original fragment missing.
                original = placeholders[token]
                if original and original not in translation:
                    findings.append(
                        QAFinding(
                            code="structure_preserve",
                            message="受保护结构片段在译文中缺失",
                            severity=Severity.HIGH,
                            detail=original[:120],
                        )
                    )

        src_tables = _extract_html_tables(source)
        zh_tables = _extract_html_tables(translation)
        if len(src_tables) != len(zh_tables):
            findings.append(
                QAFinding(
                    code="html_table_count",
                    message="HTML 表格数量不一致",
                    severity=Severity.HIGH,
                    detail=f"source={len(src_tables)} translation={len(zh_tables)}",
                )
            )
        else:
            for idx, (a, b) in enumerate(zip(src_tables, zh_tables)):
                if a != b:
                    findings.append(
                        QAFinding(
                            code="html_table_mutated",
                            message=f"HTML 表格 #{idx + 1} 结构被改写",
                            severity=Severity.HIGH,
                        )
                    )

        src_shapes = _md_table_shapes(source)
        zh_shapes = _md_table_shapes(translation)
        if src_shapes and src_shapes != zh_shapes:
            findings.append(
                QAFinding(
                    code="md_table_shape",
                    message="Markdown 表格行列结构不一致",
                    severity=Severity.HIGH,
                    detail=f"source={src_shapes} translation={zh_shapes}",
                )
            )

        for label, pattern in (
            ("heading", _HEADING_RE),
            ("page_marker", _PAGE_MARKER_RE),
            ("image", _IMAGE_RE),
            ("fence", _FENCE_RE),
            ("formula", _FORMULA_RE),
        ):
            sc = len(pattern.findall(source))
            tc = len(pattern.findall(translation))
            if sc and tc < sc:
                findings.append(
                    QAFinding(
                        code=f"structure_{label}",
                        message=f"{label} 数量减少",
                        severity=Severity.HIGH,
                        detail=f"source={sc} translation={tc}",
                    )
                )

    if numerical_check:
        missing_nums = sorted(_numbers(source) - _numbers(translation))
        # Ignore trivial single digits that often localize differently when too many.
        missing_nums = [n for n in missing_nums if len(n) >= 2 or "." in n]
        if missing_nums:
            findings.append(
                QAFinding(
                    code="number_mismatch",
                    message="数字不一致",
                    severity=Severity.MEDIUM,
                    detail=f"原文特有：{', '.join(missing_nums[:12])}",
                )
            )
        missing_years = _set_missing(_YEAR_RE.findall(source), translation)
        if missing_years:
            findings.append(
                QAFinding(
                    code="year_mismatch",
                    message="年份缺失",
                    severity=Severity.MEDIUM,
                    detail=", ".join(missing_years[:8]),
                )
            )

    if citation_check:
        for label, pattern in (
            ("citation", _CITATION_RE),
            ("figure", _FIG_RE),
            ("table_ref", _TABLE_RE),
            ("equation", _EQ_RE),
            ("url", _URL_RE),
            ("doi", _DOI_RE),
        ):
            src_vals = pattern.findall(source)
            # findall may return tuples for groups
            normalized = []
            for val in src_vals:
                if isinstance(val, tuple):
                    normalized.append("".join(val))
                else:
                    normalized.append(str(val))
            missing = _set_missing(normalized, translation)
            # For citations like [1], check bracket form still present.
            if label == "citation":
                missing = [m for m in normalized if f"[{m}]" not in translation]
            if missing:
                findings.append(
                    QAFinding(
                        code=f"{label}_mismatch",
                        message=f"{label} 引用缺失或不一致",
                        severity=Severity.MEDIUM,
                        detail=", ".join(missing[:10]),
                    )
                )

    if source.strip() and translation.strip():
        ratio = len(translation) / max(len(source), 1)
        if ratio < 0.3 or ratio > 3.0:
            findings.append(
                QAFinding(
                    code="length_ratio",
                    message="译文长度异常",
                    severity=Severity.MEDIUM,
                    detail=f"ratio={ratio:.2f}",
                )
            )

    if terminology_check and terminology:
        for en, zh in terminology.items():
            if en in source and zh and zh not in translation and en in translation:
                findings.append(
                    QAFinding(
                        code="terminology",
                        message=f"术语未采用约定译法：{en} → {zh}",
                        severity=Severity.LOW,
                    )
                )

    html_kept = len(_extract_html_tables(source))
    high = any(f.severity == Severity.HIGH for f in findings)
    medium = any(f.severity == Severity.MEDIUM for f in findings)
    if high:
        status = "fail"
    elif medium or findings:
        status = "warn"
    else:
        status = "pass"

    return UnitQAResult(
        unit_key=unit_key,
        status=status,
        findings=findings,
        source_text=source,
        translation_text=translation,
        html_tables_kept=html_kept,
    )
