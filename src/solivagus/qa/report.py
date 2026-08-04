"""Render qa-report.md."""

from __future__ import annotations

from pathlib import Path

from solivagus.qa.models import QAReportSummary
from solivagus.util.text import atomic_write_text


def write_qa_report(artifact_dir: Path, report: QAReportSummary) -> Path:
    lines = [
        "# 翻译质量报告",
        "",
        "## 总体",
        "",
        f"- Unit：{report.unit_count}",
        f"- 直接通过：{report.passed}",
        f"- 自动修复：{report.repaired}",
        f"- 英文回退：{report.fallback}",
        f"- 警告：{report.warned}",
        f"- 未通过：{report.failed}",
        f"- HTML 表格原样保留：{report.html_tables_kept}",
        "",
    ]
    warned_units = [u for u in report.units if u.findings]
    if warned_units:
        lines.extend(["## 警告", ""])
        for unit in warned_units:
            lines.append(f"### {unit.unit_key}")
            lines.append("")
            for finding in unit.findings:
                flag = "已修复" if finding.repaired else unit.status
                lines.append(f"- {finding.message}")
                if finding.detail:
                    lines.append(f"- 详情：{finding.detail}")
                lines.append(f"- 结果：{flag}")
            lines.append("")
    else:
        lines.extend(["## 警告", "", "无。", ""])

    path = artifact_dir / "qa-report.md"
    atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
    return path
