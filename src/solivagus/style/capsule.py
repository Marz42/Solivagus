"""Style capsule: frozen shared context at partition boundaries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from solivagus.util.text import sha256_text

DEFAULT_STYLE_RULES: list[str] = [
    "使用正式、简洁的技术书面语",
    "不解释原文",
    "保留原文证据强度",
    "保留标题编号",
    "产品名和模型名保留英文",
]

_TABLE_RE = re.compile(r"<table\b|\|[-: ]+\|", re.IGNORECASE)
_REF_RE = re.compile(r"(?im)^(references|bibliography|参考文献|参考资料)\b")
_PAREN_TERM_RE = re.compile(
    r"([\u4e00-\u9fff]{2,40})[（(]\s*([A-Za-z][A-Za-z0-9 +/\-]{2,60})\s*[）)]"
)


@dataclass
class StyleCapsule:
    version: int = 0
    style_rules: list[str] = field(default_factory=lambda: list(DEFAULT_STYLE_RULES))
    terminology: dict[str, str] = field(default_factory=dict)
    examples: list[dict[str, str]] = field(default_factory=list)
    boundary_context: dict[str, str] = field(default_factory=dict)
    provisional: bool = False

    def to_prompt_text(self) -> str:
        lines = [f"version: {self.version}"]
        if self.provisional:
            lines.append("provisional: true")
        lines.append("style_rules:")
        for rule in self.style_rules:
            lines.append(f"  - {rule}")
        lines.append("terminology:")
        if self.terminology:
            for en, zh in sorted(self.terminology.items()):
                lines.append(f"  {en}: {zh}")
        else:
            lines.append("  (empty)")
        lines.append("representative_examples:")
        if self.examples:
            for idx, example in enumerate(self.examples, start=1):
                src = (example.get("source") or "").strip().replace("\n", " ")[:240]
                zh = (example.get("translation") or "").strip().replace("\n", " ")[:240]
                lines.append(f"  - id: {idx}")
                lines.append(f"    source: {src}")
                lines.append(f"    translation: {zh}")
        else:
            lines.append("  (empty)")
        boundary = self.boundary_context or {}
        lines.append("boundary_context:")
        lines.append(f"  source_tail: {(boundary.get('source_tail') or '(empty)').strip()[:500]}")
        lines.append(
            f"  translation_tail: {(boundary.get('translation_tail') or '(empty)').strip()[:500]}"
        )
        return "\n".join(lines)

    def content_hash(self) -> str:
        payload = {
            "version": self.version,
            "provisional": self.provisional,
            "style_rules": self.style_rules,
            "terminology": self.terminology,
            "examples": self.examples,
            "boundary_context": self.boundary_context,
        }
        return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def version_label(self) -> str:
        if self.provisional:
            return f"{self.version}-provisional"
        return str(self.version)

    def to_db_fields(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "rules_json": json.dumps(self.style_rules, ensure_ascii=False),
            "terminology_json": json.dumps(self.terminology, ensure_ascii=False),
            "examples_json": json.dumps(self.examples, ensure_ascii=False),
            "boundary_context_json": json.dumps(self.boundary_context, ensure_ascii=False),
            "content_hash": self.content_hash(),
        }

    @classmethod
    def from_db_row(cls, row: Any) -> StyleCapsule:
        return cls(
            version=int(row["version"]),
            style_rules=json.loads(row["rules_json"] or "[]"),
            terminology=json.loads(row["terminology_json"] or "{}"),
            examples=json.loads(row["examples_json"] or "[]"),
            boundary_context=json.loads(row["boundary_context_json"] or "{}"),
            provisional=False,
        )


def empty_capsule() -> StyleCapsule:
    return StyleCapsule(version=0, provisional=False)


def _unit_token_estimate(text: str) -> int:
    return max(1, int(len(text) * 0.3 + 0.999))


def select_seed_unit(units: list[Any]) -> Any | None:
    """Pick a prose-heavy unit (~2K–6K tokens) without large tables/refs."""

    def _get(unit: Any, key: str, default: Any = None) -> Any:
        try:
            value = unit[key]
        except Exception:  # noqa: BLE001
            return default
        return default if value is None else value

    scored: list[tuple[float, int, Any]] = []
    for unit in units:
        text = str(_get(unit, "source_text", "") or "")
        if not text.strip():
            continue
        if _TABLE_RE.search(text) or _REF_RE.search(text):
            continue
        tokens = int(_get(unit, "source_tokens") or _unit_token_estimate(text))
        if tokens < 200 or tokens > 12000:
            continue
        ideal = 4000
        # Prefer closer-to-ideal token length; break ties by earlier sequence_index.
        score = -abs(tokens - ideal)
        seq = int(_get(unit, "sequence_index") or 0)
        scored.append((score, -seq, unit))
    if not scored:
        return units[0] if units else None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2]


def select_examples(assembled: list[dict[str, str]], *, max_n: int = 4) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for item in assembled:
        source = (item.get("source_text") or "").strip()
        translation = (item.get("translation_text") or "").strip()
        if not source or not translation:
            continue
        if translation.startswith(">"):  # fallback warning blocks
            continue
        if _TABLE_RE.search(source):
            continue
        examples.append(
            {
                "source": source[:1200],
                "translation": translation[:1200],
            }
        )
        if len(examples) >= max_n:
            break
    return examples


def extract_boundary_context(
    assembled: list[dict[str, str]],
    *,
    tail_chars: int = 2000,
) -> dict[str, str]:
    if not assembled:
        return {"source_tail": "", "translation_tail": ""}
    # Prefer last 1–2 units.
    tail_items = assembled[-2:] if len(assembled) >= 2 else assembled[-1:]
    source = "\n\n".join(item.get("source_text", "").rstrip() for item in tail_items)
    translation = "\n\n".join(item.get("translation_text", "").rstrip() for item in tail_items)
    return {
        "source_tail": source[-tail_chars:],
        "translation_tail": translation[-tail_chars:],
    }


def extract_terminology_candidates(assembled: list[dict[str, str]]) -> dict[str, str]:
    """Pull bilingual parenthetical pairs from Chinese translations: 中文（English）."""
    found: dict[str, str] = {}
    for item in assembled:
        text = item.get("translation_text") or ""
        for match in _PAREN_TERM_RE.finditer(text):
            zh, en = match.group(1).strip(), match.group(2).strip()
            if en and zh and en not in found:
                found[en] = zh
    return found


def merge_terminology(prev: dict[str, str], candidates: dict[str, str]) -> dict[str, str]:
    merged = dict(prev)
    for en, zh in candidates.items():
        merged.setdefault(en, zh)
    return merged


def provisional_from_seed(
    base: StyleCapsule,
    *,
    source_text: str,
    translation_text: str,
) -> StyleCapsule:
    examples = list(base.examples)
    examples.insert(
        0,
        {
            "source": source_text.strip()[:1200],
            "translation": translation_text.strip()[:1200],
        },
    )
    examples = examples[:4]
    terms = merge_terminology(
        base.terminology,
        extract_terminology_candidates(
            [{"source_text": source_text, "translation_text": translation_text}]
        ),
    )
    return StyleCapsule(
        version=base.version,
        style_rules=list(base.style_rules),
        terminology=terms,
        examples=examples,
        boundary_context=dict(base.boundary_context),
        provisional=True,
    )


def build_next_capsule(
    prev: StyleCapsule,
    assembled: list[dict[str, str]],
) -> StyleCapsule:
    examples = select_examples(assembled, max_n=4)
    if not examples and prev.examples:
        examples = list(prev.examples)[:4]
    terms = merge_terminology(prev.terminology, extract_terminology_candidates(assembled))
    boundary = extract_boundary_context(assembled)
    return StyleCapsule(
        version=int(prev.version) + 1,
        style_rules=list(prev.style_rules or DEFAULT_STYLE_RULES),
        terminology=terms,
        examples=examples,
        boundary_context=boundary,
        provisional=False,
    )
