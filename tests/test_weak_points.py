"""Tests for weak points tracker v1."""

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
from studyforge.study.weak_points import (  # noqa: E402
    InvalidConfidenceError,
    InvalidWeakPointStatusError,
    add_weak_point,
    export_weak_points_markdown,
    get_weak_points_path,
    load_weak_points,
    update_weak_point,
)


class TestWeakPoints(unittest.TestCase):
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

    def test_add_weak_point_creates_json(self) -> None:
        result = add_weak_point(
            "ECA1010_Test",
            "SRC-0001",
            "Average annual inflation",
            confidence_level=2,
            why_hard="Total vs average",
            root=self.root,
        )
        self.assertEqual(result["weak_point_id"], "WEAK-0001")
        path = get_weak_points_path(self.course)
        self.assertTrue(path.is_file())
        data = load_weak_points(path)
        self.assertEqual(len(data["weak_points"]), 1)

    def test_update_weak_point(self) -> None:
        add_weak_point(
            "ECA1010_Test",
            "SRC-0001",
            "Concept A",
            root=self.root,
        )
        result = update_weak_point(
            "ECA1010_Test",
            "WEAK-0001",
            confidence_level=4,
            status="improving",
            root=self.root,
        )
        self.assertEqual(result["confidence_level"], 4)
        self.assertEqual(result["status"], "improving")

    def test_invalid_confidence_rejected(self) -> None:
        with self.assertRaises(InvalidConfidenceError):
            add_weak_point(
                "ECA1010_Test",
                "SRC-0001",
                "Bad",
                confidence_level=9,
                root=self.root,
            )

    def test_export_weak_points_markdown(self) -> None:
        add_weak_point(
            "ECA1010_Test",
            "SRC-0001",
            "Elasticity",
            root=self.root,
        )
        path = export_weak_points_markdown("ECA1010_Test", root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("# Weak Points", text)
        self.assertIn("WEAK-0001", text)
        self.assertIn("Confidence level:", text)

    def test_invalid_status_rejected(self) -> None:
        with self.assertRaises(InvalidWeakPointStatusError):
            add_weak_point(
                "ECA1010_Test",
                "SRC-0001",
                "X",
                status="unknown",
                root=self.root,
            )

    def test_pipeline_warning_open_weak_points(self) -> None:
        add_weak_point(
            "ECA1010_Test",
            "SRC-0001",
            "Hard topic",
            status="still_weak",
            root=self.root,
        )
        from studyforge.core.sources import save_source_registry

        save_source_registry(
            self.course,
            {"sources": [{"id": "SRC-0001", "title": "Book", "status": "added"}]},
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(
            any("Weak points remain" in w for w in status["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
