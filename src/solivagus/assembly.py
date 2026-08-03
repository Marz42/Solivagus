from __future__ import annotations

from pathlib import Path
from typing import Sequence

from solivagus.util.text import atomic_write_text


def assemble_outputs(
    work_dir: Path,
    chunks: Sequence[dict[str, str]],
    *,
    document_title: str,
    pdf_name: str,
    model: str,
    pipeline_version: str = "v1.6",
    make_bilingual: bool = True,
) -> None:
    zh_header = (
        f"# {document_title}（中文译文）\n\n"
        f"> 原文件：`{pdf_name}`  \n"
        f"> 文档解析：PaddleOCR-VL {pipeline_version}  \n"
        f"> 翻译模型：`{model}`  \n"
        f"> 机器翻译仅供阅读，关键结论请核对英文原文。\n\n"
    )
    zh_parts: list[str] = [zh_header]
    bilingual_parts: list[str] = [
        f"# {document_title}（英中对照）\n\n"
        f"> 原文件：`{pdf_name}`  \n"
        f"> 文档解析：PaddleOCR-VL {pipeline_version}  \n"
        f"> 翻译模型：`{model}`\n\n"
    ]

    for item in chunks:
        source = item["source_text"].strip()
        translated = (item.get("translation_text") or source).strip()
        zh_parts.append(translated + "\n")
        if make_bilingual:
            block_id = item["unit_key"]
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
