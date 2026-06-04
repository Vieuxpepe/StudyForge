"""Tests for active recall integration with mistakes and weak points."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.active_recall import (  # noqa: E402
    get_active_recall_file,
    record_active_recall_attempt,
)
from studyforge.study.mistakes import load_mistakes_log, get_mistakes_log_path  # noqa: E402
from studyforge.study.weak_points import get_weak_points_path, load_weak_points  # noqa: E402

NUMBERED_TEXT = """# Active Recall

1. What is inflation?
2. How do you calculate CPI?
"""


class TestActiveRecallTracking(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        self.course.mkdir(parents=True)
        (self.course / "08_App_Data").mkdir(parents=True)
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
        recall_path = get_active_recall_file(self.course, "SRC-0001")
        recall_path.parent.mkdir(parents=True, exist_ok=True)
        recall_path.write_text(NUMBERED_TEXT, encoding="utf-8")
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Book",
                        "status": "study_pack_generated",
                        "active_recall_path": str(recall_path.resolve()),
                    }
                ]
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_wrong_create_mistake(self) -> None:
        result = record_active_recall_attempt(
            "ECA1010_Test",
            "SRC-0001",
            "AR-SRC-0001-Q001",
            "What is inflation?",
            "Rising prices",
            "wrong",
            create_mistake=True,
            root=self.root,
        )
        self.assertIn("mistake_id", result)
        mistakes = load_mistakes_log(get_mistakes_log_path(self.course))
        self.assertEqual(len(mistakes["mistakes"]), 1)

    def test_partial_create_weak_point(self) -> None:
        result = record_active_recall_attempt(
            "ECA1010_Test",
            "SRC-0001",
            "AR-SRC-0001-Q001",
            "What is inflation?",
            "Maybe CPI",
            "partial",
            create_weak_point=True,
            weak_point_concept="Inflation vs CPI",
            root=self.root,
        )
        self.assertIn("weak_point_id", result)
        data = load_weak_points(get_weak_points_path(self.course))
        self.assertEqual(len(data["weak_points"]), 1)
        self.assertEqual(data["weak_points"][0]["concept"], "Inflation vs CPI")

    def test_correct_does_not_create_mistake(self) -> None:
        result = record_active_recall_attempt(
            "ECA1010_Test",
            "SRC-0001",
            "AR-SRC-0001-Q001",
            "What is inflation?",
            "General price rise",
            "correct",
            create_mistake=True,
            create_weak_point=True,
            root=self.root,
        )
        self.assertNotIn("mistake_id", result)
        self.assertNotIn("weak_point_id", result)
        mistakes = load_mistakes_log(get_mistakes_log_path(self.course))
        self.assertEqual(len(mistakes["mistakes"]), 0)


if __name__ == "__main__":
    unittest.main()
