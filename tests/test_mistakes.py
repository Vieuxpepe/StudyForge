"""Tests for mistakes log v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.pipeline_status import get_pipeline_status  # noqa: E402
from studyforge.study.mistakes import (  # noqa: E402
    InvalidMistakeStatusError,
    add_mistake,
    export_mistakes_markdown,
    get_mistakes_log_path,
    load_mistakes_log,
    update_mistake_status,
)


class TestMistakes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        self.course.mkdir(parents=True)
        (self.root / "config").mkdir()
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps(
                {
                    "project_root": str(self.root),
                    "courses_dir": str(courses),
                    "default_course_template": "_Course_Template",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_add_mistake_creates_json(self) -> None:
        result = add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "What is inflation?",
            "Prices go up",
            why_wrong="Vague",
            root=self.root,
        )
        self.assertEqual(result["mistake_id"], "MISTAKE-0001")
        log_path = get_mistakes_log_path(self.course)
        self.assertTrue(log_path.is_file())
        data = load_mistakes_log(log_path)
        self.assertEqual(len(data["mistakes"]), 1)

    def test_update_mistake_status(self) -> None:
        add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "Q",
            "A",
            root=self.root,
        )
        result = update_mistake_status(
            "ECA1010_Test", "MISTAKE-0001", "mastered", root=self.root
        )
        self.assertEqual(result["status"], "mastered")

    def test_export_mistakes_markdown(self) -> None:
        add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "What is CPI?",
            "Consumer price index",
            why_wrong="Confused terms",
            root=self.root,
        )
        path = export_mistakes_markdown("ECA1010_Test", root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("# Mistakes Log", text)
        self.assertIn("MISTAKE-0001", text)
        self.assertIn("Why I got it wrong:", text)

    def test_invalid_mistake_status_rejected(self) -> None:
        with self.assertRaises(InvalidMistakeStatusError):
            add_mistake(
                "ECA1010_Test",
                "SRC-0001",
                "Q",
                "A",
                status="done",
                root=self.root,
            )

    def test_pipeline_warning_open_mistakes(self) -> None:
        add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "Q",
            "A",
            status="new",
            root=self.root,
        )
        from studyforge.core.sources import save_source_registry

        save_source_registry(
            self.course,
            {"sources": [{"id": "SRC-0001", "title": "Book", "status": "added"}]},
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(
            any("Open mistakes remain" in w for w in status["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
