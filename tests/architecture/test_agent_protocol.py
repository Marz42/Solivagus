from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AgentOperationProtocolTests(unittest.TestCase):
    def test_source_and_cursor_adapter_share_minimal_cli_operations(self) -> None:
        source = (ROOT / "AGENT_RULES.md").read_text(encoding="utf-8")
        adapter = (
            ROOT / ".cursor" / "rules" / "memory-bank-protocol.mdc"
        ).read_text(encoding="utf-8")
        operations = (
            ROOT / "tests" / "golden" / "agent-operation-protocol.txt"
        ).read_text(encoding="utf-8").splitlines()

        for operation in operations:
            with self.subTest(operation=operation):
                self.assertIn(operation, source)
                self.assertIn(operation, adapter)

        self.assertNotIn("# Role and Persona", source)
        self.assertNotIn("active-task checklist 打勾", source)
        self.assertNotIn("最近的 session log", adapter)
        self.assertIn("同步自 `AGENT_RULES.md`", adapter)

    def test_bootstrap_docs_initialize_runtime_through_cli(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        init_prompt = (ROOT / "INIT_PROMPT.md").read_text(encoding="utf-8")
        mode_f = init_prompt.split("## 模式 F", 1)[1].split("## 模式 A", 1)[0]

        self.assertIn("pd runtime init --write", readme)
        self.assertNotIn(
            "memory-bank-template/runtime/* memory-bank/runtime/", readme
        )
        self.assertIn("pd runtime init --write", mode_f)
        self.assertNotIn("从 memory-bank-template/runtime/ 复制", mode_f)

    def test_operational_prompts_use_context_manifest_instead_of_manual_hot_scan(self) -> None:
        text = (ROOT / "INIT_PROMPT.md").read_text(encoding="utf-8")
        operational = text.split("## 模式 A", 1)[1].split("## 模式 H", 1)[0]

        self.assertIn("pd context build", operational)
        self.assertIn("pd context verify", operational)
        self.assertNotIn("读取 memory-bank/runtime/active-task.md", operational)
        self.assertNotIn("读取 memory-bank/knowledge/index.md 和 HOT", operational)


if __name__ == "__main__":
    unittest.main()
