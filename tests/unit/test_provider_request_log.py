"""Provider request log covers warm-up-class calls outside translation_attempts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from solivagus.providers import request_log as rl
from solivagus.providers.openai_compatible import call_chat_api


class ProviderRequestLogTests(unittest.TestCase):
    def setUp(self) -> None:
        rl.reset_provider_request_count_for_tests()

    def test_call_chat_api_appends_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "provider-requests.jsonl"
            with rl.provider_log_scope(log_path):
                with mock.patch(
                    "solivagus.providers.openai_compatible.request.urlopen"
                ) as urlopen:
                    resp = mock.MagicMock()
                    resp.status = 200
                    resp.read.return_value = (
                        b'{"choices":[{"message":{"content":"ok"},'
                        b'"finish_reason":"stop"}],"usage":{}}'
                    )
                    resp.__enter__.return_value = resp
                    resp.__exit__.return_value = False
                    urlopen.return_value = resp
                    text, _fr, _usage = call_chat_api(
                        api_base="https://example.test/v1",
                        api_key="k",
                        model="m",
                        system_prompt="s",
                        user_prompt="u",
                    )
                    self.assertEqual(text, "ok")
            self.assertEqual(rl.count_provider_log_lines(log_path), 1)
            self.assertEqual(rl.provider_request_count(), 1)


if __name__ == "__main__":
    unittest.main()
