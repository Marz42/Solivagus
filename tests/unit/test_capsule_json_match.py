"""Capsule JSON match must validate payload content, not declared hash alone."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from solivagus.pipeline.translate import (
    _capsule_json_matches,
    _capsule_json_payload,
)
from solivagus.style.capsule import StyleCapsule
from solivagus.util.text import atomic_write_json


class CapsuleJsonMatchTests(unittest.TestCase):
    def test_stale_hash_with_mutated_terminology_fails(self) -> None:
        capsule = StyleCapsule(
            version=1,
            style_rules=["a"],
            terminology={"foo": "条"},
            examples=[],
            boundary_context={},
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v1.json"
            payload = _capsule_json_payload(capsule, part_id=7)
            # Mutate terminology but keep the original content_hash declaration.
            payload["terminology"] = {"foo": "被篡改"}
            atomic_write_json(path, payload)
            self.assertFalse(
                _capsule_json_matches(path, capsule=capsule, part_id=7)
            )

    def test_broken_version_type_fails_without_raise(self) -> None:
        capsule = StyleCapsule(version=1, terminology={"a": "b"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v1.json"
            payload = _capsule_json_payload(capsule, part_id=3)
            payload["version"] = "broken"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertFalse(
                _capsule_json_matches(path, capsule=capsule, part_id=3)
            )

    def test_canonical_payload_matches(self) -> None:
        capsule = StyleCapsule(
            version=2,
            style_rules=["r"],
            terminology={"t": "词"},
            examples=[{"source": "a", "translation": "甲"}],
            boundary_context={"source_tail": "x"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v2.json"
            atomic_write_json(path, _capsule_json_payload(capsule, part_id=9))
            self.assertTrue(_capsule_json_matches(path, capsule=capsule, part_id=9))


if __name__ == "__main__":
    unittest.main()
