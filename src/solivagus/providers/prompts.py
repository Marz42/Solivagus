"""Stable partition prompts and dynamic unit request builders."""

from __future__ import annotations

from typing import Literal

from solivagus.util.text import sha256_text

PROMPT_VERSION = "translate-v1"

STABLE_SYSTEM_PROMPT = """你是严谨的技术文献翻译器。你的唯一任务是忠实翻译，不做摘要、评论、解释或内容补写。

硬性规则：
1. 完整翻译，不总结、不删减、不扩写，不添加原文没有的信息。
2. 保持 Markdown 标题、段落、列表、表格、引用和换行结构。
3. 所有形如 @@PRESERVE_00001@@ 的占位符必须原样保留。
4. 保留章节号、图号、表号、参考文献编号、变量名、产品名、模型名和算法名。
5. 技术术语采用通行译法；重要术语首次出现可写作“中文译名（English term）”。
6. 严格保持原文证据强度，不把 may/might/suggest 等不确定表达译成确定结论。
7. 只输出指定 Unit 的译文 Markdown，并使用要求的开始/结束标记。
"""


def document_user_id(source_sha256: str) -> str:
    return "pdf_" + source_sha256[:20]


def build_stable_prefix(
    *,
    document_title: str,
    target_language: str,
    units: list[dict],
    glossary: str = "",
    style_capsule: str = "",
    prompt_version: str = PROMPT_VERSION,
) -> tuple[str, str, str]:
    """Return (system, user, prefix_hash)."""
    system = STABLE_SYSTEM_PROMPT + f"\n提示词版本：{prompt_version}\n目标语言：{target_language}\n"
    unit_blocks: list[str] = []
    for unit in units:
        key = str(unit["unit_key"])
        text = str(unit["source_text"]).rstrip()
        unit_blocks.append(f'[UNIT id="{key}"]\n{text}\n')
    partition_source = "\n".join(unit_blocks).rstrip()
    user = (
        "<document-context>\n"
        f"文档标题：{document_title}\n"
        f"术语表：{glossary or '(空)'}\n"
        f"风格胶囊：{style_capsule or '(空)'}\n"
        "</document-context>\n\n"
        "<partition-source>\n"
        f"{partition_source}\n"
        "</partition-source>\n\n"
        "请读取以上分区并回复固定字符串：\n"
        "PARTITION_READY\n"
    )
    prefix_hash = sha256_text(system + "\n" + user)[:32]
    return system, user, prefix_hash


def build_unit_user_tail(
    *,
    unit_key: str,
    source_text: str,
    target_mode: Literal["repeat", "id_only"] = "repeat",
) -> str:
    lines = [
        "翻译任务：",
        f"只翻译 UNIT {unit_key}。",
        "保持 Markdown 结构。",
        "不要输出其他 Unit。",
        "必须输出开始和结束标记：",
        f"<<<UNIT:{unit_key}:BEGIN>>>",
        "译文……",
        f"<<<UNIT:{unit_key}:END>>>",
    ]
    if target_mode == "repeat":
        lines.extend(
            [
                "",
                "以下是目标文本的副本：",
                "",
                f'<translation-unit id="{unit_key}">',
                source_text.rstrip(),
                "</translation-unit>",
                "",
            ]
        )
    else:
        lines.extend(["", f"目标 Unit ID：{unit_key}", ""])
    return "\n".join(lines)


def build_unit_messages(
    *,
    stable_system: str,
    stable_user: str,
    warmup_assistant: str,
    unit_key: str,
    source_text: str,
    target_mode: Literal["repeat", "id_only"] = "repeat",
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": stable_system},
        {"role": "user", "content": stable_user},
        {"role": "assistant", "content": warmup_assistant},
        {
            "role": "user",
            "content": build_unit_user_tail(
                unit_key=unit_key,
                source_text=source_text,
                target_mode=target_mode,
            ),
        },
    ]


def extract_unit_translation(raw: str, unit_key: str) -> str:
    begin = f"<<<UNIT:{unit_key}:BEGIN>>>"
    end = f"<<<UNIT:{unit_key}:END>>>"
    if begin in raw and end in raw:
        start = raw.index(begin) + len(begin)
        finish = raw.index(end, start)
        return raw[start:finish].strip() + "\n"
    return raw.strip() + "\n"
