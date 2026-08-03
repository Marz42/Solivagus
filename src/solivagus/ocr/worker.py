"""OCR worker process: OCR a page range and write batch checkpoint artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from solivagus.ocr.checkpoints import OcrConfig, PageRange, missing_page_stub, write_done
from solivagus.util.text import atomic_write_json, atomic_write_text, sha256_text


DEFAULT_IGNORE_LABELS = [
    "number",
    "footnote",
    "header",
    "header_image",
    "footer",
    "footer_image",
    "aside_text",
]


class WorkerError(RuntimeError):
    pass


def _eprint(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


def extract_markdown_result(result: Any) -> tuple[str, dict[str, Any]]:
    try:
        md = result.markdown
    except Exception as exc:  # pragma: no cover
        raise WorkerError(f"PaddleOCR result missing markdown: {exc}") from exc
    if not isinstance(md, dict):
        raise WorkerError("PaddleOCR result.markdown is not a dict")
    text = md.get("markdown_texts")
    images = md.get("markdown_images") or {}
    if not isinstance(text, str):
        raise WorkerError("markdown_texts is not a string")
    if not isinstance(images, dict):
        images = {}
    return text, images


def save_markdown_images(
    markdown_text: str,
    images: dict[str, Any],
    work_dir: Path,
    page_number: int,
) -> str:
    from solivagus.util.text import sanitize_stem

    updated = markdown_text
    page_assets = Path("assets") / f"page_{page_number:04d}"
    for index, (raw_name, image) in enumerate(images.items(), start=1):
        basename = Path(str(raw_name)).name or f"image_{index:04d}.png"
        basename = sanitize_stem(Path(basename).stem) + Path(basename).suffix
        rel_path = page_assets / f"{index:04d}_{basename}"
        target = work_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(target))
        new_name = rel_path.as_posix()
        for old_name in {str(raw_name), str(raw_name).replace("\\", "/")}:
            updated = updated.replace(old_name, new_name)
    return updated


def render_pages_to_images(pdf_path: Path, page_range: PageRange, out_dir: Path) -> list[Path]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise WorkerError("pypdfium2 is required to render PDF page batches") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf_path))
    paths: list[Path] = []
    try:
        for page_number in range(page_range.start, page_range.end + 1):
            page = doc[page_number - 1]
            bitmap = page.render(scale=2)
            image = bitmap.to_pil()
            target = out_dir / f"page_{page_number:04d}.png"
            image.save(target)
            paths.append(target)
            page.close()
    finally:
        doc.close()
    return paths


def run_batch_ocr(
    *,
    pdf_path: Path,
    artifact_dir: Path,
    batch_index: int,
    page_range: PageRange,
    config: OcrConfig,
    config_hash: str,
) -> dict[str, Any]:
    try:
        from paddleocr import PaddleOCRVL
    except ImportError as exc:
        raise WorkerError(
            "paddleocr not installed; install requirements-gpu.txt on the OCR machine"
        ) from exc

    batch_directory = artifact_dir / "ocr" / f"batch-{batch_index:04d}"
    batch_directory.mkdir(parents=True, exist_ok=True)
    parsed_dir = batch_directory / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="solivagus-ocr-") as tmp:
        image_paths = render_pages_to_images(pdf_path, page_range, Path(tmp) / "pages")
        kwargs: dict[str, Any] = {
            "pipeline_version": config.pipeline_version,
            "use_doc_orientation_classify": config.use_orientation,
            "use_doc_unwarping": config.use_unwarping,
            "use_chart_recognition": config.use_chart_recognition,
            "markdown_ignore_labels": list(config.ignore_labels) or DEFAULT_IGNORE_LABELS,
        }
        if config.device:
            kwargs["device"] = config.device

        _eprint(
            f"[OCR worker] batch-{batch_index:04d} pages "
            f"{page_range.start}-{page_range.end}"
        )
        pipeline = PaddleOCRVL(**kwargs)
        page_texts: list[str] = []
        failed_pages: list[int] = []

        for page_number, image_path in zip(
            range(page_range.start, page_range.end + 1), image_paths, strict=True
        ):
            try:
                page_results = list(pipeline.predict(input=str(image_path)))
                if not page_results:
                    raise WorkerError("empty OCR result")
                result = page_results[0]
                markdown_text, images = extract_markdown_result(result)
                markdown_text = save_markdown_images(
                    markdown_text, images, artifact_dir, page_number
                ).strip()
                page_marker = (
                    f"<!-- source-page: {page_number} -->\n"
                    f"<a id=\"source-page-{page_number}\"></a>"
                )
                page_texts.append(f"{page_marker}\n\n{markdown_text}\n")
            except Exception as exc:  # noqa: BLE001
                _eprint(f"[OCR worker] page {page_number} failed: {exc}")
                failed_pages.append(page_number)
                page_texts.append(missing_page_stub(page_number))

        if failed_pages and len(failed_pages) == page_range.page_count:
            raise WorkerError(
                f"all pages failed in batch-{batch_index:04d}: {failed_pages}"
            )

        source_text = "\n".join(page_texts).rstrip() + "\n"
        source_path = batch_directory / "source.md"
        atomic_write_text(source_path, source_text)
        result_payload = {
            "batch_index": batch_index,
            "page_start": page_range.start,
            "page_end": page_range.end,
            "failed_pages": failed_pages,
            "config_hash": config_hash,
        }
        atomic_write_json(batch_directory / "result.json", result_payload)
        write_done(
            batch_directory,
            batch_index=batch_index,
            page_range=page_range,
            config_hash=config_hash,
            source_hash=sha256_text(source_text),
            extra={"failed_pages": failed_pages},
        )
        return result_payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solivagus OCR batch worker")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--page-start", type=int, required=True)
    parser.add_argument("--page-end", type=int, required=True)
    parser.add_argument("--config-json", type=Path, required=True)
    parser.add_argument("--config-hash", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    raw = json.loads(args.config_json.read_text(encoding="utf-8"))
    config = OcrConfig(
        pipeline_version=str(raw.get("pipeline_version") or "v1.6"),
        device=raw.get("device"),
        use_orientation=bool(raw.get("use_orientation") or False),
        use_unwarping=bool(raw.get("use_unwarping") or False),
        use_chart_recognition=bool(raw.get("use_chart_recognition") or False),
        batch_pages=int(raw.get("batch_pages") or 8),
        ignore_labels=tuple(raw.get("ignore_labels") or DEFAULT_IGNORE_LABELS),
    )
    page_range = PageRange(args.page_start, args.page_end)
    try:
        run_batch_ocr(
            pdf_path=args.pdf.expanduser().resolve(),
            artifact_dir=args.artifact_dir.expanduser().resolve(),
            batch_index=args.batch_index,
            page_range=page_range,
            config=config,
            config_hash=args.config_hash,
        )
    except Exception as exc:  # noqa: BLE001
        _eprint(f"[OCR worker] FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
