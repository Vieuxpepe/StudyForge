"""Tests for Google Generative Language API client (mocked HTTP)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.llm.google_genai_client import (  # noqa: E402
    GoogleGenAIAPIError,
    build_generate_content_body,
    generate_content,
)


class TestGoogleGenAI(unittest.TestCase):
    def test_body_omits_thinking_config_when_disabled(self) -> None:
        body = build_generate_content_body(
            user_text="hi",
            system_instruction="audit",
            disable_thinking=True,
        )
        self.assertNotIn("thinkingConfig", body["generationConfig"])

    @mock.patch("studyforge.llm.google_genai_client.requests.post")
    def test_generate_content(self, mock_post: mock.Mock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "## Audit\n\nAll good."}]}}
            ]
        }
        text = generate_content(
            api_key="test-key",
            model="gemma-4-26b-a4b-it",
            user_text="audit this",
            system_instruction="be strict",
        )
        self.assertIn("Audit", text)
        call_url = mock_post.call_args.args[0]
        self.assertIn("gemma-4-26b-a4b-it", call_url)
        self.assertIn("key=test-key", call_url)

    @mock.patch("studyforge.llm.google_genai_client.requests.post")
    def test_api_error(self, mock_post: mock.Mock) -> None:
        mock_post.return_value.status_code = 429
        mock_post.return_value.text = "rate limit"
        with self.assertRaises(GoogleGenAIAPIError):
            generate_content(
                api_key="k",
                model="gemma-4-26b-a4b-it",
                user_text="x",
            )


if __name__ == "__main__":
    unittest.main()
