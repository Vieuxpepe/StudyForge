"""Tests for local app settings persistence."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.app_settings import (  # noqa: E402
    get_app_settings_path,
    get_default_app_settings,
    load_app_settings,
    save_app_settings,
    update_app_settings,
    validate_app_settings,
)


class TestAppSettings(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps({"courses_dir": str(self.root / "courses")}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_settings_contain_expected_keys(self) -> None:
        defaults = get_default_app_settings()
        self.assertIn("lm_studio", defaults)
        self.assertIn("chunking", defaults)
        self.assertIn("digest", defaults)
        self.assertIn("gui", defaults)
        self.assertEqual(defaults["lm_studio"]["base_url"], "http://localhost:1234/v1")
        self.assertEqual(defaults["chunking"]["max_words"], 1200)
        self.assertEqual(defaults["gui"]["default_page"], "today")

    def test_load_returns_defaults_when_file_missing(self) -> None:
        settings = load_app_settings(self.root)
        self.assertEqual(settings, get_default_app_settings())

    def test_save_and_load_roundtrip(self) -> None:
        custom = get_default_app_settings()
        custom["lm_studio"]["base_url"] = "http://192.168.2.152:1234/v1"
        custom["lm_studio"]["default_model"] = "test-model"
        path = save_app_settings(custom, self.root)
        self.assertTrue(path.is_file())
        loaded = load_app_settings(self.root)
        self.assertEqual(
            loaded["lm_studio"]["base_url"],
            "http://192.168.2.152:1234/v1",
        )
        self.assertEqual(loaded["lm_studio"]["default_model"], "test-model")

    def test_merge_fills_missing_defaults(self) -> None:
        partial_path = get_app_settings_path(self.root)
        partial_path.write_text(
            json.dumps({"lm_studio": {"default_model": "partial-model"}}),
            encoding="utf-8",
        )
        loaded = load_app_settings(self.root)
        self.assertEqual(loaded["lm_studio"]["default_model"], "partial-model")
        self.assertEqual(loaded["lm_studio"]["base_url"], "http://localhost:1234/v1")
        self.assertEqual(loaded["chunking"]["max_words"], 1200)

    def test_malformed_json_falls_back_safely(self) -> None:
        path = get_app_settings_path(self.root)
        path.write_text("{not json", encoding="utf-8")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            loaded = load_app_settings(self.root)
        self.assertEqual(loaded, get_default_app_settings())
        self.assertTrue(any("Could not parse" in str(w.message) for w in caught))

    def test_validation_catches_overlap_ge_max_words(self) -> None:
        settings = get_default_app_settings()
        settings["chunking"]["max_words"] = 100
        settings["chunking"]["overlap_words"] = 100
        errors = validate_app_settings(settings)
        self.assertTrue(any("overlap" in e.lower() for e in errors))

    def test_validation_catches_bad_url(self) -> None:
        settings = get_default_app_settings()
        settings["lm_studio"]["base_url"] = "ftp://bad"
        errors = validate_app_settings(settings)
        self.assertTrue(any("http" in e.lower() for e in errors))

    def test_secret_keys_are_not_saved(self) -> None:
        settings = get_default_app_settings()
        settings["google_api_key"] = "secret-value"
        settings["lm_studio"]["api_key"] = "also-secret"
        save_app_settings(settings, self.root)
        raw = json.loads(get_app_settings_path(self.root).read_text(encoding="utf-8"))
        self.assertNotIn("google_api_key", raw)
        self.assertNotIn("api_key", raw["lm_studio"])

    def test_update_app_settings_merges(self) -> None:
        updated = update_app_settings(
            {"gui": {"show_advanced_options": False}},
            self.root,
        )
        self.assertFalse(updated["gui"]["show_advanced_options"])
        self.assertEqual(updated["gui"]["default_page"], "today")


class TestAppSettingsGitignore(unittest.TestCase):
    def test_gitignore_contains_local_app_settings(self) -> None:
        gitignore = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(
            encoding="utf-8"
        )
        self.assertIn("config/local_app_settings.json", gitignore)
        self.assertIn("config/local_secrets.json", gitignore)
        self.assertIn(".env", gitignore)


class TestAppSettingsCli(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps({"courses_dir": str(self.root / "courses")}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_show_and_reset(self) -> None:
        import importlib.util
        from unittest.mock import patch

        scripts_path = Path(__file__).resolve().parent.parent / "scripts" / "app_settings.py"
        spec = importlib.util.spec_from_file_location("app_settings_cli", scripts_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with patch("studyforge.core.app_settings.find_project_root", return_value=self.root):
            self.assertEqual(module.main(["--show"]), 0)
            save_app_settings(
                {"lm_studio": {"default_model": "cli-test"}},
                self.root,
            )
            self.assertEqual(module.main(["--reset"]), 0)
            loaded = load_app_settings(self.root)
            self.assertEqual(loaded["lm_studio"]["default_model"], "")


if __name__ == "__main__":
    unittest.main()
