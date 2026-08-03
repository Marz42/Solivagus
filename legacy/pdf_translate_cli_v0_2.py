#!/usr/bin/env python3
"""
PDF technical-document translator: PaddleOCR-VL + OpenAI-compatible LLM API.

Design goals:
- One Python file, CLI only.
- Full PaddleOCR-VL page-level pipeline (layout + VLM recognition).
- Markdown output with local images.
- Chunked translation, placeholder protection, mechanical validation.
- Resume after interruption without a database.

Python: 3.9+

Install PaddleOCR separately according to your CPU/GPU environment, then install:
    python -m pip install -U "paddleocr[doc-parser]>=3.6.0,<3.7"

PaddlePaddle itself must match your hardware/CUDA version. See the official installer.

Translation API environment variables (OpenAI-compatible /chat/completions):
    LLM_API_BASE=https://api.openai.com/v1
    LLM_API_KEY=...
    LLM_MODEL=...

Example:
    python pdf_translate_cli.py paper.pdf --model YOUR_MODEL

OCR only:
    python pdf_translate_cli.py paper.pdf --ocr-only

Re-run the same command to resume. Completed OCR and translation chunks are reused.
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCRIPT_VERSION = "0.2.0-hotfix"
DEFAULT_API_BASE = "https://api.openai.com/v1"
DEFAULT_CHUNK_CHARS = 12000
DEFAULT_IGNORE_LABELS = [
    "number",
    "footnote",
    "header",
    "header_image",
    "footer",
    "footer_image",
    "aside_text",
]

SYSTEM_PROMPT = """你是严谨的技术文献翻译器。你的唯一任务是忠实翻译，不做摘要、评论、解释或内容补写。"""

USER_PROMPT_TEMPLATE = """请将下面的技术文献内容翻译为{target_language}。

硬性要求：
1. 完整翻译，不总结、不删减、不扩写，不添加原文没有的信息。
2. 保持 Markdown 标题、段落、列表、表格、引用和换行结构。
3. 所有形如 @@PRESERVE_00001@@ 的占位符必须原样保留，不能改写、删除、调序或加空格。
4. 保留章节号、图号、表号、参考文献编号、变量名、产品名、模型名和算法名。
5. 技术术语采用通行译法；重要术语首次出现可写作“中文译名（English term）”。
6. 严格保持原文证据强度，不把 may、might、suggest、associate、approximately 等不确定表达翻译成确定结论。
7. 只输出翻译后的 Markdown 正文，不要输出说明，不要使用包裹全文的代码围栏。

文档标题：{document_title}
当前翻译块：{block_id}

术语表（可能为空；如有则优先遵守）：
{glossary}

待翻译内容：
{protected_markdown}
"""


class AppError(RuntimeError):
    pass


class FatalAPIError(AppError):
    """Non-recoverable API/configuration error; do not silently fall back."""

    pass


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


def load_dotenv(path: Path) -> None:
    """Load a minimal KEY=VALUE .env file without another dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def sanitize_stem(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE).strip("._")
    return cleaned or "document"


def safe_relative_path(raw: str, fallback: Path) -> Path:
    normalized = raw.replace("\\", "/").lstrip("/")
    candidate = Path(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        return fallback
    return candidate


def save_pil_image(image: Any, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(target))


def save_markdown_images(
    markdown_text: str,
    images: Dict[str, Any],
    work_dir: Path,
    page_number: int,
) -> str:
    """Save PaddleOCR images under assets/page_XXXX and rewrite Markdown links."""
    updated = markdown_text
    page_assets = Path("assets") / f"page_{page_number:04d}"

    for index, (raw_name, image) in enumerate(images.items(), start=1):
        raw_path = safe_relative_path(
            str(raw_name), Path(f"image_{index:04d}.png")
        )
        basename = raw_path.name or f"image_{index:04d}.png"
        rel_path = page_assets / f"{index:04d}_{basename}"
        target = work_dir / rel_path

        save_pil_image(image, target)
        new_name = rel_path.as_posix()
        old_variants = {str(raw_name), str(raw_name).replace("\\", "/")}
        for old_name in old_variants:
            updated = updated.replace(old_name, new_name)
    return updated


def extract_markdown_result(result: Any) -> Tuple[str, Dict[str, Any]]:
    try:
        md = result.markdown
    except Exception as exc:  # pragma: no cover - runtime integration path
        raise AppError(f"PaddleOCR 结果不含 markdown 属性：{exc}") from exc

    if not isinstance(md, dict):
        raise AppError("PaddleOCR result.markdown 不是字典，请确认 paddleocr>=3.6.0。")

    text = md.get("markdown_texts")
    images = md.get("markdown_images") or {}
    if not isinstance(text, str):
        raise AppError("PaddleOCR result.markdown['markdown_texts'] 不是字符串。")
    if not isinstance(images, dict):
        images = {}
    return text, images


def run_ocr(
    pdf_path: Path,
    work_dir: Path,
    pipeline_version: str,
    device: Optional[str],
    use_orientation: bool,
    use_unwarping: bool,
    use_chart_recognition: bool,
) -> Path:
    try:
        from paddleocr import PaddleOCRVL
    except ImportError as exc:
        raise AppError(
            "未找到 paddleocr。请先安装与硬件匹配的 PaddlePaddle，再安装 "
            "'paddleocr[doc-parser]>=3.6.0,<3.7'。"
        ) from exc

    parsed_dir = work_dir / "parsed"
    pages_dir = parsed_dir / "pages"
    json_dir = parsed_dir / "json"
    pages_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    kwargs: Dict[str, Any] = {
        "pipeline_version": pipeline_version,
        "use_doc_orientation_classify": use_orientation,
        "use_doc_unwarping": use_unwarping,
        "use_chart_recognition": use_chart_recognition,
        "markdown_ignore_labels": DEFAULT_IGNORE_LABELS,
    }
    if device:
        kwargs["device"] = device

    eprint(f"[OCR] 初始化 PaddleOCR-VL {pipeline_version} ...")
    pipeline = PaddleOCRVL(**kwargs)

    eprint(f"[OCR] 解析 PDF：{pdf_path}")
    page_results = list(pipeline.predict(input=str(pdf_path)))
    if not page_results:
        raise AppError("PaddleOCR 没有返回任何页面结果。")

    eprint(f"[OCR] 重建 {len(page_results)} 页的跨页结构 ...")
    try:
        rebuilt_results = list(
            pipeline.restructure_pages(
                page_results,
                merge_tables=True,
                relevel_titles=True,
                concatenate_pages=False,
            )
        )
    except AttributeError as exc:
        raise AppError(
            "当前 PaddleOCR/PaddleX 组合缺少 restructure_pages。"
            "请升级并保持 paddleocr 与 paddlex 版本匹配，建议 paddleocr 3.6.x。"
        ) from exc

    combined_pages: List[str] = []
    for page_number, result in enumerate(rebuilt_results, start=1):
        markdown_text, images = extract_markdown_result(result)
        markdown_text = save_markdown_images(
            markdown_text=markdown_text,
            images=images,
            work_dir=work_dir,
            page_number=page_number,
        ).strip()

        page_marker = (
            f"<!-- source-page: {page_number} -->\n"
            f"<a id=\"source-page-{page_number}\"></a>"
        )
        page_text = f"{page_marker}\n\n{markdown_text}\n"
        atomic_write_text(pages_dir / f"page_{page_number:04d}.md", page_text)
        combined_pages.append(page_text)

        try:
            # Directory mode lets PaddleOCR choose a page-aware filename.
            result.save_to_json(save_path=json_dir)
        except Exception as exc:
            eprint(f"[警告] 第 {page_number} 页 JSON 保存失败，继续处理：{exc}")

    source_path = work_dir / "source.md"
    source_header = (
        f"<!-- generated-by: pdf_translate_cli.py {SCRIPT_VERSION} -->\n"
        f"<!-- source-file: {pdf_path.name} -->\n\n"
    )
    atomic_write_text(source_path, source_header + "\n".join(combined_pages).rstrip() + "\n")
    eprint(f"[OCR] Markdown 已生成：{source_path}")
    return source_path


def iter_markdown_blocks(markdown: str) -> Iterable[str]:
    """Split Markdown at blank lines, but not inside common multiline constructs."""
    lines = markdown.splitlines()
    current: List[str] = []
    fence: Optional[str] = None
    in_display_math = False
    html_end_tag: Optional[str] = None

    for line in lines:
        stripped = line.strip()

        if fence:
            current.append(line)
            if stripped.startswith(fence):
                fence = None
            continue

        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence_match:
            fence = fence_match.group(1)[:3]
            current.append(line)
            continue

        if html_end_tag:
            current.append(line)
            if html_end_tag in stripped.lower():
                html_end_tag = None
            continue

        lower = stripped.lower()
        for start_tag, end_tag in (
            ("<table", "</table>"),
            ("<details", "</details>"),
            ("<div", "</div>"),
        ):
            if lower.startswith(start_tag) and end_tag not in lower:
                html_end_tag = end_tag
                current.append(line)
                break
        else:
            if stripped.count("$$") % 2 == 1:
                in_display_math = not in_display_math
                current.append(line)
                continue
            if stripped == r"\[":
                in_display_math = True
                current.append(line)
                continue
            if stripped == r"\]":
                in_display_math = False
                current.append(line)
                continue

            if not stripped and not in_display_math:
                if current:
                    yield "\n".join(current).rstrip()
                    current = []
            else:
                current.append(line)

    if current:
        yield "\n".join(current).rstrip()


def split_markdown(markdown: str, chunk_chars: int) -> List[str]:
    if chunk_chars < 2000:
        raise AppError("--chunk-chars 不应低于 2000。")

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for block in iter_markdown_blocks(markdown):
        block_len = len(block) + 2
        if current and current_len + block_len > chunk_chars:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_len = 0

        if not current and block_len > chunk_chars:
            eprint(
                f"[警告] 单个 Markdown 块长度 {block_len} 超过 chunk-chars={chunk_chars}，"
                "为避免破坏表格/公式，将整块发送。"
            )

        current.append(block)
        current_len += block_len

    if current:
        chunks.append("\n\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


# Opaque structural blocks are never sent to the LLM. They are copied back locally.
# This is intentionally conservative: HTML tables remain in the source language in this
# hotfix, but they cannot stop an unattended translation run.
PASSTHROUGH_PATTERNS: Sequence[Tuple[str, re.Pattern[str]]] = [
    (
        "html_table_wrapper",
        re.compile(
            r"<div\b[^>]*>\s*<table\b[^>]*>.*?</table>\s*</div>",
            re.DOTALL | re.IGNORECASE,
        ),
    ),
    (
        "html_table",
        re.compile(r"<table\b[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE),
    ),
    (
        "html_comment",
        re.compile(r"<!--.*?-->", re.DOTALL),
    ),
    (
        "source_anchor",
        re.compile(
            r"<a\b[^>]*\bid=[\"']source-page-\d+[\"'][^>]*>\s*</a>",
            re.DOTALL | re.IGNORECASE,
        ),
    ),
]


# Inline or semantic content that must remain byte-for-byte intact inside a translated
# text segment. Large HTML tables/comments/page anchors have already been removed by
# split_passthrough_segments(), so the model no longer needs to reproduce dozens of
# structural placeholders.
PROTECT_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"(?ms)^```.*?^```\s*$|^~~~.*?^~~~\s*$"),
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
    re.compile(r"!\[[^\]]*\]\([^\n)]*\)"),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"(?<!\$)\$(?!\$)(?:\\.|[^$\n])+?\$(?!\$)"),
    re.compile(r"https?://[^\s<>\])]+"),
    re.compile(r"<[^>\n]+>"),
]


def split_passthrough_segments(text: str) -> List[Tuple[str, str]]:
    """Split text into translatable and locally preserved structural segments."""
    segments: List[Tuple[str, str]] = []
    cursor = 0

    while cursor < len(text):
        earliest_kind: Optional[str] = None
        earliest_match: Optional[re.Match[str]] = None
        for kind, pattern in PASSTHROUGH_PATTERNS:
            match = pattern.search(text, cursor)
            if match is None:
                continue
            if earliest_match is None or match.start() < earliest_match.start():
                earliest_kind = kind
                earliest_match = match
            elif (
                earliest_match is not None
                and match.start() == earliest_match.start()
                and match.end() > earliest_match.end()
            ):
                # Prefer the larger wrapper when two patterns start at the same place.
                earliest_kind = kind
                earliest_match = match

        if earliest_match is None or earliest_kind is None:
            if cursor < len(text):
                segments.append(("text", text[cursor:]))
            break

        if earliest_match.start() > cursor:
            segments.append(("text", text[cursor:earliest_match.start()]))
        segments.append((earliest_kind, earliest_match.group(0)))
        cursor = earliest_match.end()

    return [(kind, value) for kind, value in segments if value]


def protect_markdown(text: str) -> Tuple[str, Dict[str, str]]:
    placeholders: Dict[str, str] = {}
    counter = 1

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        token = f"@@PRESERVE_{counter:05d}@@"
        counter += 1
        placeholders[token] = match.group(0)
        return token

    protected = text
    for pattern in PROTECT_PATTERNS:
        protected = pattern.sub(replace, protected)
    return protected, placeholders


def restore_markdown(text: str, placeholders: Dict[str, str]) -> str:
    missing = [token for token in placeholders if text.count(token) != 1]
    if missing:
        preview = ", ".join(missing[:8])
        raise AppError(
            f"译文占位符缺失、重复或被改写：{preview}"
            + (" ..." if len(missing) > 8 else "")
        )

    restored = text
    for token, original in placeholders.items():
        restored = restored.replace(token, original)
    return restored


def strip_wrapping_code_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*)\n```", stripped, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped


def build_chat_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def parse_chat_response(response: Dict[str, Any]) -> Tuple[str, Optional[str], Dict[str, Any]]:
    try:
        choice = response["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError(
            "LLM API 返回格式不是 OpenAI-compatible chat/completions："
            + json.dumps(response, ensure_ascii=False)[:800]
        ) from exc

    text: Optional[str] = None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            text = "".join(parts)

    if text is None:
        raise AppError("LLM API 返回的 message.content 不是可识别文本。")

    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    return text, finish_reason, usage


def call_chat_api(
    api_base: str,
    api_key: Optional[str],
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    temperature: Optional[float],
) -> Tuple[str, Optional[str], Dict[str, Any]]:
    endpoint = build_chat_endpoint(api_base)
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = f"LLM API HTTP {exc.code}: {body[:1200]}"
        if exc.code in {400, 401, 403, 404, 405, 413, 422}:
            raise FatalAPIError(message) from exc
        raise AppError(message) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"LLM API 网络错误：{exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(f"LLM API 返回非 JSON：{raw[:800]}") from exc
    return parse_chat_response(data)


def enable_prevent_sleep(enabled: bool) -> None:
    """Prevent Windows idle sleep while the process is running."""
    if not enabled:
        return
    if os.name != "nt":
        eprint("[提示] --prevent-sleep 目前仅在 Windows 上生效。")
        return

    es_continuous = 0x80000000
    es_system_required = 0x00000001
    result = ctypes.windll.kernel32.SetThreadExecutionState(
        es_continuous | es_system_required
    )
    if result == 0:
        eprint("[警告] 无法启用 Windows 防睡眠。")
        return

    def reset() -> None:
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)
        except Exception:
            pass

    atexit.register(reset)
    eprint("[无人值守] 已阻止 Windows 因空闲自动睡眠；显示器仍可关闭。")


def infer_document_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return fallback


def read_glossary(path: Optional[Path]) -> str:
    if path is None:
        return "（无）"
    if not path.exists():
        raise AppError(f"术语表文件不存在：{path}")
    text = path.read_text(encoding="utf-8-sig").strip()
    return text or "（无）"


def _attempt_artifact_path(
    failure_path: Path,
    block_id: str,
    segment_index: int,
    attempt: int,
    suffix: str,
) -> Path:
    return failure_path.with_name(
        f"{block_id}.segment-{segment_index:03d}.attempt-{attempt}.{suffix}"
    )


def translate_text_segment(
    source_text: str,
    block_id: str,
    segment_index: int,
    document_title: str,
    glossary: str,
    target_language: str,
    api_base: str,
    api_key: Optional[str],
    model: str,
    timeout: int,
    temperature: Optional[float],
    retries: int,
    failure_path: Path,
) -> str:
    if not source_text.strip():
        return source_text

    protected, placeholders = protect_markdown(source_text)
    prompt = USER_PROMPT_TEMPLATE.format(
        target_language=target_language,
        document_title=document_title,
        block_id=f"{block_id}/segment-{segment_index:03d}",
        glossary=glossary,
        protected_markdown=protected,
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        raw: Optional[str] = None
        finish_reason: Optional[str] = None
        usage: Dict[str, Any] = {}
        try:
            raw, finish_reason, usage = call_chat_api(
                api_base=api_base,
                api_key=api_key,
                model=model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                timeout=timeout,
                temperature=temperature,
            )
            if finish_reason in {"length", "max_tokens", "content_filter"}:
                raise AppError(f"LLM 输出未正常完成，finish_reason={finish_reason}")

            cleaned = strip_wrapping_code_fence(raw)
            restored = restore_markdown(cleaned, placeholders)
            return restored.strip()
        except Exception as exc:
            last_error = exc
            if raw is not None:
                atomic_write_text(
                    _attempt_artifact_path(
                        failure_path, block_id, segment_index, attempt, "raw.md"
                    ),
                    raw,
                )
                atomic_write_json(
                    _attempt_artifact_path(
                        failure_path, block_id, segment_index, attempt, "meta.json"
                    ),
                    {"finish_reason": finish_reason, "usage": usage},
                )
            detail = (
                f"block={block_id}\nsegment={segment_index}\nattempt={attempt}\n"
                f"finish_reason={finish_reason}\nerror={exc}\n"
            )
            atomic_write_text(failure_path, detail)
            if isinstance(exc, FatalAPIError):
                raise
            if attempt < retries:
                delay = min(2 ** (attempt - 1), 8)
                eprint(
                    f"[重试] {block_id}/segment-{segment_index:03d} "
                    f"第 {attempt} 次失败：{exc}；{delay}s 后重试"
                )
                time.sleep(delay)

    raise AppError(
        f"翻译块 {block_id} 的第 {segment_index} 个文本段在 {retries} 次尝试后仍失败："
        f"{last_error}"
    )


def translate_one_chunk(
    source_chunk: str,
    block_id: str,
    document_title: str,
    glossary: str,
    target_language: str,
    api_base: str,
    api_key: Optional[str],
    model: str,
    timeout: int,
    temperature: Optional[float],
    retries: int,
    failure_path: Path,
) -> str:
    segments = split_passthrough_segments(source_chunk.strip())
    table_count = sum(1 for kind, _ in segments if kind in {"html_table", "html_table_wrapper"})
    if table_count:
        eprint(
            f"[结构] {block_id} 检测到 {table_count} 个 HTML 表格；"
            "本热修版将其原样保留，不发送给 LLM。"
        )

    output_parts: List[str] = [f"<!-- translation-block: {block_id} -->"]
    text_segment_index = 0
    for kind, value in segments:
        if kind != "text":
            output_parts.append(value)
            continue

        if not value.strip():
            output_parts.append(value)
            continue

        text_segment_index += 1
        translated = translate_text_segment(
            source_text=value,
            block_id=block_id,
            segment_index=text_segment_index,
            document_title=document_title,
            glossary=glossary,
            target_language=target_language,
            api_base=api_base,
            api_key=api_key,
            model=model,
            timeout=timeout,
            temperature=temperature,
            retries=retries,
            failure_path=failure_path,
        )
        output_parts.append(translated)

    return "\n\n".join(part.strip() for part in output_parts if part.strip()) + "\n"


def make_untranslated_fallback(block_id: str, source_chunk: str, error: Exception) -> str:
    safe_error = str(error).replace("\n", " ").strip()
    return (
        f"<!-- translation-block: {block_id} -->\n\n"
        f"> [翻译警告] 本块自动翻译失败，已保留英文原文以便无人值守任务继续。  \n"
        f"> 错误：`{safe_error[:500]}`\n\n"
        f"{source_chunk.strip()}\n"
    )


def assemble_outputs(
    work_dir: Path,
    chunks: Sequence[Dict[str, Any]],
    document_title: str,
    pdf_name: str,
    model: str,
    pipeline_version: str,
    make_bilingual: bool,
) -> None:
    zh_header = (
        f"# {document_title}（中文译文）\n\n"
        f"> 原文件：`{pdf_name}`  \n"
        f"> 文档解析：PaddleOCR-VL {pipeline_version}  \n"
        f"> 翻译模型：`{model}`  \n"
        f"> 机器翻译仅供阅读，关键结论请核对英文原文。\n\n"
    )
    zh_parts: List[str] = [zh_header]
    bilingual_parts: List[str] = [
        f"# {document_title}（英中对照）\n\n"
        f"> 原文件：`{pdf_name}`  \n"
        f"> 文档解析：PaddleOCR-VL {pipeline_version}  \n"
        f"> 翻译模型：`{model}`\n\n"
    ]

    for item in chunks:
        source_path = work_dir / item["source_file"]
        translated_path = work_dir / item["translated_file"]
        source = source_path.read_text(encoding="utf-8").strip()
        translated = translated_path.read_text(encoding="utf-8").strip()
        zh_parts.append(translated + "\n")

        if make_bilingual:
            block_id = item["id"]
            bilingual_parts.append(
                f"\n---\n\n<!-- bilingual-block: {block_id} -->\n\n"
                f"<details>\n<summary>英文原文 · {block_id}</summary>\n\n"
                f"{source}\n\n</details>\n\n"
                f"{translated}\n"
            )

    atomic_write_text(work_dir / "translated.zh.md", "\n".join(zh_parts).rstrip() + "\n")
    if make_bilingual:
        atomic_write_text(
            work_dir / "translated.bilingual.md",
            "\n".join(bilingual_parts).rstrip() + "\n",
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用 PaddleOCR-VL 和 OpenAI-compatible LLM API 翻译 PDF 为 Markdown。"
    )
    parser.add_argument("pdf", type=Path, help="输入 PDF 文件")
    parser.add_argument("--work-dir", type=Path, help="工作目录；默认在 PDF 同目录创建 <文件名>.translation")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="环境变量文件，默认 ./.env")

    parser.add_argument("--pipeline-version", default="v1.6", choices=["v1", "v1.5", "v1.6"])
    parser.add_argument("--device", help="PaddleOCR 设备，例如 gpu:0 或 cpu；默认自动选择")
    parser.add_argument("--use-orientation", action="store_true", help="启用文档方向分类")
    parser.add_argument("--use-unwarping", action="store_true", help="启用文档畸变矫正")
    parser.add_argument("--use-chart-recognition", action="store_true", help="启用图表解析；默认只保留图像")
    parser.add_argument("--force-ocr", action="store_true", help="忽略缓存，重新 OCR")
    parser.add_argument("--ocr-only", action="store_true", help="只解析 PDF，不调用翻译 API")

    parser.add_argument("--api-base", help="OpenAI-compatible API base，或设置 LLM_API_BASE")
    parser.add_argument("--api-key", help="API key，或设置 LLM_API_KEY / OPENAI_API_KEY")
    parser.add_argument("--model", help="翻译模型名，或设置 LLM_MODEL")
    parser.add_argument("--target-language", default="简体中文")
    parser.add_argument("--glossary", type=Path, help="可选术语表；脚本会把文件原文放进提示词")
    parser.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS, help="每个翻译块的近似字符上限")
    parser.add_argument("--temperature", type=float, default=0.1, help="翻译温度；不兼容时使用 --no-temperature")
    parser.add_argument("--no-temperature", action="store_true", help="API 请求不发送 temperature 参数")
    parser.add_argument("--timeout", type=int, default=300, help="单次 API 请求超时秒数")
    parser.add_argument("--retries", type=int, default=3, help="单块翻译最大尝试次数")
    parser.add_argument("--force-translate", action="store_true", help="重新翻译所有块")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="任一翻译块失败时立即退出；默认保留英文原文并继续",
    )
    parser.add_argument(
        "--prevent-sleep",
        action="store_true",
        help="Windows：运行期间阻止系统因空闲自动睡眠",
    )
    parser.add_argument("--zh-only", action="store_true", help="只生成中文版本，不生成英中对照版本")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    enable_prevent_sleep(args.prevent_sleep)

    load_dotenv(args.env_file)

    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.exists() or not pdf_path.is_file():
        raise AppError(f"PDF 文件不存在：{pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise AppError("当前第一版只接受 PDF 文件。")

    work_dir = (
        args.work_dir.expanduser().resolve()
        if args.work_dir
        else pdf_path.parent / f"{sanitize_stem(pdf_path.stem)}.translation"
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = work_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    state_path = work_dir / "state.json"
    state = read_json(state_path)
    current_pdf_hash = sha256_file(pdf_path)

    cached_hash = state.get("source_pdf_sha256")
    if cached_hash and cached_hash != current_pdf_hash and not args.force_ocr:
        raise AppError(
            "工作目录中的缓存来自另一个版本的 PDF。请指定新的 --work-dir，"
            "或使用 --force-ocr 覆盖现有解析结果。"
        )

    source_path = work_dir / "source.md"
    need_ocr = args.force_ocr or not source_path.exists() or cached_hash != current_pdf_hash
    if need_ocr:
        if args.force_ocr:
            for path in [work_dir / "parsed", work_dir / "assets", work_dir / "imgs"]:
                if path.exists():
                    shutil.rmtree(path)
        source_path = run_ocr(
            pdf_path=pdf_path,
            work_dir=work_dir,
            pipeline_version=args.pipeline_version,
            device=args.device,
            use_orientation=args.use_orientation,
            use_unwarping=args.use_unwarping,
            use_chart_recognition=args.use_chart_recognition,
        )
        state = {
            "script_version": SCRIPT_VERSION,
            "source_pdf": str(pdf_path),
            "source_pdf_sha256": current_pdf_hash,
            "pipeline_version": args.pipeline_version,
            "ocr_options": {
                "device": args.device,
                "use_orientation": args.use_orientation,
                "use_unwarping": args.use_unwarping,
                "use_chart_recognition": args.use_chart_recognition,
            },
            "chunks": [],
        }
        atomic_write_json(state_path, state)
    else:
        eprint(f"[缓存] 跳过 OCR，使用：{source_path}")

    if args.ocr_only:
        eprint("[完成] OCR-only 模式。")
        print(source_path)
        return 0

    api_base = args.api_base or os.getenv("LLM_API_BASE") or DEFAULT_API_BASE
    api_key = args.api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = args.model or os.getenv("LLM_MODEL")
    if not model:
        raise AppError("缺少翻译模型名：请传入 --model 或设置 LLM_MODEL。")

    source_markdown = source_path.read_text(encoding="utf-8")
    document_title = infer_document_title(source_markdown, pdf_path.stem)
    glossary = read_glossary(args.glossary)
    glossary_hash = sha256_text(glossary)

    source_chunks = split_markdown(source_markdown, args.chunk_chars)
    eprint(f"[分块] 共 {len(source_chunks)} 个翻译块。")

    old_chunks_by_id = {
        item.get("id"): item
        for item in state.get("chunks", [])
        if isinstance(item, dict) and item.get("id")
    }
    new_manifest: List[Dict[str, Any]] = []

    temperature: Optional[float] = None if args.no_temperature else args.temperature
    warning_count = 0
    state["completed"] = False
    state["stage"] = "translation_running"
    atomic_write_json(state_path, state)

    for index, chunk_text in enumerate(source_chunks, start=1):
        block_id = f"b{index:05d}"
        source_rel = Path("chunks") / f"{block_id}.source.md"
        translated_rel = Path("chunks") / f"{block_id}.zh.md"
        failure_rel = Path("chunks") / f"{block_id}.failed.txt"
        source_chunk_path = work_dir / source_rel
        translated_chunk_path = work_dir / translated_rel
        failure_path = work_dir / failure_rel

        atomic_write_text(source_chunk_path, chunk_text.strip() + "\n")
        source_hash = sha256_text(chunk_text)
        translation_signature = sha256_text(
            "\n".join(
                [
                    source_hash,
                    model,
                    api_base,
                    args.target_language,
                    glossary_hash,
                    SYSTEM_PROMPT,
                    USER_PROMPT_TEMPLATE,
                ]
            )
        )

        previous = old_chunks_by_id.get(block_id, {})
        can_reuse = (
            not args.force_translate
            and translated_chunk_path.exists()
            and previous.get("translation_signature") == translation_signature
            and previous.get("status") == "done"
        )

        item: Dict[str, Any] = {
            "id": block_id,
            "source_file": source_rel.as_posix(),
            "translated_file": translated_rel.as_posix(),
            "source_sha256": source_hash,
            "translation_signature": translation_signature,
            "status": "done" if can_reuse else "pending",
        }
        new_manifest.append(item)
        state["chunks"] = new_manifest
        state["translation"] = {
            "api_base": api_base,
            "model": model,
            "target_language": args.target_language,
            "chunk_chars": args.chunk_chars,
            "glossary_sha256": glossary_hash,
        }
        atomic_write_json(state_path, state)

        if can_reuse:
            eprint(f"[缓存] {block_id} 已完成，跳过。")
            continue

        eprint(f"[翻译] {block_id} ({index}/{len(source_chunks)}, {len(chunk_text)} chars)")
        try:
            translated = translate_one_chunk(
                source_chunk=chunk_text,
                block_id=block_id,
                document_title=document_title,
                glossary=glossary,
                target_language=args.target_language,
                api_base=api_base,
                api_key=api_key,
                model=model,
                timeout=args.timeout,
                temperature=temperature,
                retries=max(1, args.retries),
                failure_path=failure_path,
            )
            atomic_write_text(translated_chunk_path, translated)
            if failure_path.exists():
                failure_path.unlink()
            item["status"] = "done"
        except Exception as exc:
            if args.strict or isinstance(exc, FatalAPIError):
                item["status"] = "failed"
                item["error"] = str(exc)
                atomic_write_json(state_path, state)
                raise

            warning_count += 1
            eprint(
                f"[警告] {block_id} 翻译失败，保留英文原文并继续：{exc}"
            )
            atomic_write_text(
                translated_chunk_path,
                make_untranslated_fallback(block_id, chunk_text, exc),
            )
            item["status"] = "fallback_source"
            item["error"] = str(exc)
        atomic_write_json(state_path, state)

    assemble_outputs(
        work_dir=work_dir,
        chunks=new_manifest,
        document_title=document_title,
        pdf_name=pdf_path.name,
        model=model,
        pipeline_version=args.pipeline_version,
        make_bilingual=not args.zh_only,
    )

    state["completed"] = True
    state["stage"] = "translation_complete_with_warnings" if warning_count else "translation_complete"
    state["warning_count"] = warning_count
    state["outputs"] = {
        "source": "source.md",
        "translated_zh": "translated.zh.md",
        "translated_bilingual": None if args.zh_only else "translated.bilingual.md",
    }
    atomic_write_json(state_path, state)

    if warning_count:
        eprint(f"[完成但有警告] {warning_count} 个块保留了英文原文；可查看 chunks/*.failed.txt。")
    eprint(f"[完成] 中文版：{work_dir / 'translated.zh.md'}")
    if not args.zh_only:
        eprint(f"[完成] 对照版：{work_dir / 'translated.bilingual.md'}")
    print(work_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        eprint("\n已中断。重新运行相同命令即可从缓存继续。")
        raise SystemExit(130)
    except AppError as exc:
        eprint(f"错误：{exc}")
        raise SystemExit(2)
