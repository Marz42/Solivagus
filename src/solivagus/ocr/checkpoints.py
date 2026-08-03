from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class PageRange:
    start: int
    end: int

    @property
    def page_count(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class OcrConfig:
    pipeline_version: str = "v1.6"
    device: str | None = None
    use_orientation: bool = False
    use_unwarping: bool = False
    use_chart_recognition: bool = False
    batch_pages: int = 8
    ignore_labels: tuple[str, ...] = (
        "number",
        "footnote",
        "header",
        "header_image",
        "footer",
        "footer_image",
        "aside_text",
    )

    def config_hash(self, *, source_sha256: str, paddleocr_version: str = "unknown") -> str:
        payload = {
            "source_sha256": source_sha256,
            "paddleocr_version": paddleocr_version,
            "pipeline_version": self.pipeline_version,
            "device": self.device,
            "use_orientation": self.use_orientation,
            "use_unwarping": self.use_unwarping,
            "use_chart_recognition": self.use_chart_recognition,
            "batch_pages": self.batch_pages,
            "ignore_labels": list(self.ignore_labels),
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def plan_batches(page_count: int, batch_pages: int = 8) -> list[PageRange]:
    if page_count <= 0:
        return []
    if batch_pages <= 0:
        raise ValueError("batch_pages must be positive")
    ranges: list[PageRange] = []
    start = 1
    while start <= page_count:
        end = min(page_count, start + batch_pages - 1)
        ranges.append(PageRange(start, end))
        start = end + 1
    return ranges


def split_range(page_range: PageRange) -> list[PageRange]:
    if page_range.start == page_range.end:
        return []
    mid = (page_range.start + page_range.end) // 2
    return [PageRange(page_range.start, mid), PageRange(mid + 1, page_range.end)]


def batch_dir(artifact_dir: Path, batch_index: int) -> Path:
    return artifact_dir / "ocr" / f"batch-{batch_index:04d}"


def done_path(batch_directory: Path) -> Path:
    return batch_directory / "done.json"


def is_batch_done(batch_directory: Path, *, config_hash: str) -> bool:
    marker = done_path(batch_directory)
    if not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(payload.get("config_hash") or "") == config_hash and (
        batch_directory / "source.md"
    ).is_file()


def write_done(
    batch_directory: Path,
    *,
    batch_index: int,
    page_range: PageRange,
    config_hash: str,
    source_hash: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    payload = {
        "batch_id": f"{batch_index:04d}",
        "page_start": page_range.start,
        "page_end": page_range.end,
        "config_hash": config_hash,
        "source_hash": source_hash,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if extra:
        payload.update(extra)
    marker = done_path(batch_directory)
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return marker


def ordered_batch_indices(artifact_dir: Path, batch_indices: Sequence[int]) -> list[int]:
    decorated: list[tuple[int, int]] = []
    for index in batch_indices:
        marker = done_path(batch_dir(artifact_dir, index))
        page_start = index
        if marker.is_file():
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
                page_start = int(payload.get("page_start") or index)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                page_start = index
        decorated.append((page_start, index))
    decorated.sort()
    return [index for _, index in decorated]


def assemble_source_markdown(
    artifact_dir: Path,
    batch_indices: Sequence[int],
    *,
    pdf_name: str,
    script_version: str,
) -> Path:
    parts: list[str] = [
        f"<!-- generated-by: solivagus {script_version} -->\n",
        f"<!-- source-file: {pdf_name} -->\n\n",
    ]
    for index in ordered_batch_indices(artifact_dir, batch_indices):
        source = batch_dir(artifact_dir, index) / "source.md"
        if not source.is_file():
            parts.append(
                f"\n<!-- OCR FAILED OR MISSING: batch-{index:04d} -->\n\n"
                f"> [OCR 警告] 批次 batch-{index:04d} 缺少 source.md。\n"
            )
            continue
        parts.append(source.read_text(encoding="utf-8").rstrip() + "\n\n")
    out = artifact_dir / "source.md"
    out.write_text("".join(parts).rstrip() + "\n", encoding="utf-8")
    return out


def missing_page_stub(page_number: int) -> str:
    return (
        f"<!-- source-page: {page_number} -->\n"
        f"<a id=\"source-page-{page_number}\"></a>\n\n"
        f"<!-- OCR FAILED: source-page {page_number} -->\n\n"
        f"> [OCR 警告] 原 PDF 第 {page_number} 页处理失败。\n"
    )


def covered_pages(artifact_dir: Path, *, config_hash: str) -> set[int]:
    ocr_root = artifact_dir / "ocr"
    covered: set[int] = set()
    if not ocr_root.is_dir():
        return covered
    for path in ocr_root.glob("batch-*"):
        marker = done_path(path)
        if not marker.is_file() or not (path / "source.md").is_file():
            continue
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("config_hash") or "") != config_hash:
            continue
        start = int(payload.get("page_start") or 0)
        end = int(payload.get("page_end") or -1)
        if start <= 0 or end < start:
            continue
        covered.update(range(start, end + 1))
    return covered


def find_done_batch(
    artifact_dir: Path,
    page_range: PageRange,
    *,
    config_hash: str,
) -> int | None:
    ocr_root = artifact_dir / "ocr"
    if not ocr_root.is_dir():
        return None
    for path in sorted(ocr_root.glob("batch-*")):
        marker = done_path(path)
        if not marker.is_file():
            continue
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("config_hash") or "") != config_hash:
            continue
        if int(payload.get("page_start") or -1) != page_range.start:
            continue
        if int(payload.get("page_end") or -1) != page_range.end:
            continue
        if not (path / "source.md").is_file():
            continue
        try:
            return int(path.name.split("-", 1)[1])
        except (IndexError, ValueError):
            continue
    return None


def next_batch_index(artifact_dir: Path) -> int:
    ocr_root = artifact_dir / "ocr"
    if not ocr_root.is_dir():
        return 1
    indices: list[int] = []
    for path in ocr_root.glob("batch-*"):
        try:
            indices.append(int(path.name.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return (max(indices) + 1) if indices else 1
