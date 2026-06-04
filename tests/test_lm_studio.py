"""Tests for LM Studio client (mocked HTTP)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.llm.lm_studio_client import (  # noqa: E402
    LMStudioAPIError,
    build_chat_completion_body,
    chat_completion,
    check_lm_studio_connection,
    choose_default_model,
)


class TestChooseDefaultModel(unittest.TestCase):
    def test_picks_first(self) -> None:
        resp = {"ok": True, "models": ["model-a", "model-b"]}
        self.assertEqual(choose_default_model(resp), "model-a")

    def test_none_when_empty(self) -> None:
        self.assertIsNone(choose_default_model({"models": []}))


class TestCheckConnection(unittest.TestCase):
    @mock.patch("studyforge.llm.lm_studio_client.requests.get")
    def test_connection_ok(self, mock_get: mock.Mock) -> None:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": [{"id": "local-model"}]
        }
        result = check_lm_studio_connection()
        self.assertTrue(result["ok"])
        self.assertEqual(result["models"], ["local-model"])

    @mock.patch("studyforge.llm.lm_studio_client.requests.get")
    def test_connection_failure(self, mock_get: mock.Mock) -> None:
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("refused")
        result = check_lm_studio_connection()
        self.assertFalse(result["ok"])
        self.assertIn("Connection failed", result["error"] or "")

    @mock.patch("studyforge.llm.lm_studio_client.requests.get")
    def test_connection_custom_base_url(self, mock_get: mock.Mock) -> None:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": [{"id": "remote-model"}]}
        custom = "http://192.168.2.152:1234/v1"
        result = check_lm_studio_connection(base_url=custom)
        mock_get.assert_called_once_with(f"{custom}/models", timeout=10)
        self.assertTrue(result["ok"])
        self.assertEqual(result["base_url"], custom)


class TestCheckLmStudioScript(unittest.TestCase):
    def test_cli_passes_base_url(self) -> None:
        import importlib.util

        script_path = Path(__file__).resolve().parent.parent / "scripts" / "check_lm_studio.py"
        spec = importlib.util.spec_from_file_location(
            "check_lm_studio_test_module", script_path
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        custom_url = "http://192.168.2.152:1234/v1"
        with mock.patch.object(
            module, "check_lm_studio_connection", return_value={
                "ok": True,
                "base_url": custom_url,
                "models": ["m1"],
                "error": None,
            }
        ) as mock_check:
            exit_code = module.main(["--base-url", custom_url])

        self.assertEqual(exit_code, 0)
        mock_check.assert_called_once_with(base_url=custom_url)


class TestBuildChatCompletionBody(unittest.TestCase):
    def test_disables_thinking_by_default(self) -> None:
        body = build_chat_completion_body(
            model="google/gemma-4-e4b",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            max_tokens=3000,
        )
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertFalse(body["chat_template_kwargs"]["enable_thinking"])
        self.assertFalse(
            body["extra_body"]["chat_template_kwargs"]["enable_thinking"]
        )

    def test_omits_thinking_flags_when_enabled(self) -> None:
        body = build_chat_completion_body(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            max_tokens=100,
            enable_thinking=True,
        )
        self.assertNotIn("reasoning_effort", body)
        self.assertNotIn("chat_template_kwargs", body)
        self.assertNotIn("extra_body", body)


class TestChatCompletion(unittest.TestCase):
    @mock.patch("studyforge.llm.lm_studio_client.requests.post")
    def test_sends_disable_thinking_fields(self, mock_post: mock.Mock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertFalse(body["chat_template_kwargs"]["enable_thinking"])

    @mock.patch("studyforge.llm.lm_studio_client.requests.post")
    def test_returns_content(self, mock_post: mock.Mock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "# Digest\n\nHello"}}]
        }
        text = chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
        )
        self.assertIn("Digest", text)

    @mock.patch("studyforge.llm.lm_studio_client.requests.post")
    def test_malformed_response(self, mock_post: mock.Mock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"choices": []}
        with self.assertRaises(LMStudioAPIError):
            chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model="test-model",
            )

    @mock.patch("studyforge.llm.lm_studio_client.requests.post")
    def test_non_200(self, mock_post: mock.Mock) -> None:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "server error"
        with self.assertRaises(LMStudioAPIError):
            chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model="test-model",
            )


if __name__ == "__main__":
    unittest.main()
