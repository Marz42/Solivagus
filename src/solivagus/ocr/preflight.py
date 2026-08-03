from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from solivagus.util.text import sha256_file


@dataclass
class PreflightResult:
    path: str
    page_count: int
    encrypted: bool
    source_sha256: str
    suspected_scan_pages: int = 0
    suspected_blank_pages: int = 0
    native_text_pages: int = 0
    estimated_chars: int = 0
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings or [])
        return payload


class PreflightError(RuntimeError):
    pass


def preflight_pdf(path) -> PreflightResult:
    """Inspect a PDF before OCR. Uses pypdfium2 when available."""
    from pathlib import Path

    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file():
        raise PreflightError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PreflightError("only PDF input is supported")

    source_sha = sha256_file(pdf_path)
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise PreflightError(
            "pypdfium2 is required for preflight; install requirements-gpu.txt"
        ) from exc

    warnings: list[str] = []
    try:
        doc = pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:  # noqa: BLE001
        raise PreflightError(f"failed to open PDF: {exc}") from exc

    try:
        page_count = len(doc)
        if page_count <= 0:
            raise PreflightError("PDF has zero pages")
        native_text_pages = 0
        blank_pages = 0
        estimated_chars = 0
        for index in range(page_count):
            page = doc[index]
            try:
                textpage = page.get_textpage()
                text = textpage.get_text_bounded() or ""
                textpage.close()
            except Exception:  # noqa: BLE001
                text = ""
                warnings.append(f"page {index + 1}: text extraction failed")
            stripped = text.strip()
            if not stripped:
                blank_pages += 1
            else:
                native_text_pages += 1
                estimated_chars += len(stripped)
            page.close()
        suspected_scan = max(0, page_count - native_text_pages)
        return PreflightResult(
            path=str(pdf_path),
            page_count=page_count,
            encrypted=False,
            source_sha256=source_sha,
            suspected_scan_pages=suspected_scan,
            suspected_blank_pages=blank_pages,
            native_text_pages=native_text_pages,
            estimated_chars=estimated_chars,
            warnings=warnings,
        )
    finally:
        doc.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
