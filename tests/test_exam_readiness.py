"""Tests for Exam Readiness Score v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.exam_prep import collect_exam_prep_state  # noqa: E402
from studyforge.study.exam_readiness import (  # noqa: E402
    ExamReadinessReportExistsError,
    build_exam_readiness_markdown,
    calculate_exam_readiness_score,
    export_exam_readiness_report,
    get_exam_readiness_report,
    get_exam_readiness_report_paths,
)
from studyforge.study.exam_targets import create_exam_target  # noqa: E402
from studyforge.study.mock_tests import record_mock_test_attempt  # noqa: E402
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.study_units import create_study_unit  # noqa: E402
from studyforge.study.today_dashboard import get_today_dashboard  # noqa: E402
from studyforge.study.weak_points import add_weak_point  # noqa: E402


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "00_Master").mkdir(parents=True)
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {
            "sources": [
                {"id": "SRC-0001", "title": "Textbook", "status": "study_pack_generated"},
                {"id": "SRC-0002", "title": "Slides", "status": "added"},
                {"id": "SRC-0005", "title": "Homework", "status": "added"},
            ]
        },
    )
    manifest = course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"quality": {"quality_status": "ok"}}),
        encoding="utf-8",
    )
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "studyforge_config.json").write_text(
        json.dumps(
            {
                "project_root": str(root),
                "courses_dir": str(courses),
                "default_course_template": "_Course_Template",
            }
        ),
        encoding="utf-8",
    )
    return course


def _base_state() -> dict:
    return {
        "exam": {"target_score": 80, "title": "Quiz 2"},
        "days_until_exam": 10,
        "readiness": {
            "incomplete_sources": [],
            "units_without_synthesis": [],
            "units_without_unit_pack": [],
        },
        "review": {
            "due_flashcards": [],
            "due_unit_flashcards": [],
            "active_recall_needs_review": [],
            "unit_recall_needs_review": [],
            "open_mistakes": [],
            "open_weak_points": [],
        },
        "mock_tests": {
            "attempt_count": 1,
            "latest_score": 85.0,
        },
        "warnings": [],
    }


class TestExamReadinessScoring(unittest.TestCase):
    def test_perfect_readiness_score(self) -> None:
        result = calculate_exam_readiness_score(_base_state())
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["breakdown"]["readiness"], 30)
        self.assertEqual(result["breakdown"]["review_load"], 25)
        self.assertEqual(result["breakdown"]["mock_tests"], 30)
        self.assertEqual(result["breakdown"]["time"], 15)

    def test_incomplete_sources_reduce_score(self) -> None:
        state = _base_state()
        state["readiness"]["incomplete_sources"] = [{"source_id": "SRC-0002"}]
        result = calculate_exam_readiness_score(state)
        self.assertEqual(result["breakdown"]["readiness"], 20)
        self.assertTrue(
            any("lack study packs" in blocker for blocker in result["blockers"])
        )

    def test_review_load_reduces_score(self) -> None:
        state = _base_state()
        state["review"]["due_flashcards"] = [{"card_id": f"FC-{i}"} for i in range(8)]
        state["review"]["open_weak_points"] = [
            {"concept": f"C{i}"} for i in range(3)
        ]
        result = calculate_exam_readiness_score(state)
        self.assertEqual(result["breakdown"]["review_load"], 11)
        self.assertTrue(any("due flashcard" in b for b in result["blockers"]))
        self.assertTrue(any("weak point" in b for b in result["blockers"]))

    def test_no_mock_attempt_partial_points_and_blocker(self) -> None:
        state = _base_state()
        state["mock_tests"] = {"attempt_count": 0, "latest_score": None}
        result = calculate_exam_readiness_score(state)
        self.assertEqual(result["breakdown"]["mock_tests"], 10)
        self.assertIn("No mock test attempt yet.", result["blockers"])
        self.assertIn("Take a mock test.", result["recommendations"])

    def test_latest_mock_below_target_blocker(self) -> None:
        state = _base_state()
        state["mock_tests"]["latest_score"] = 65.0
        result = calculate_exam_readiness_score(state)
        self.assertEqual(result["breakdown"]["mock_tests"], 15)
        self.assertTrue(
            any("below target" in blocker for blocker in result["blockers"])
        )

    def test_time_pressure_scoring(self) -> None:
        cases = [
            (-1, 0),
            (0, 4),
            (1, 7),
            (2, 7),
            (6, 11),
            (7, 15),
            (30, 15),
        ]
        for days, expected in cases:
            state = _base_state()
            state["days_until_exam"] = days
            result = calculate_exam_readiness_score(state)
            self.assertEqual(
                result["breakdown"]["time"],
                expected,
                msg=f"days={days}",
            )

    def test_status_thresholds(self) -> None:
        ready = calculate_exam_readiness_score(_base_state())
        self.assertEqual(ready["status"], "ready")

        needs_review_state = _base_state()
        needs_review_state["readiness"]["incomplete_sources"] = [{"source_id": "X"}]
        needs_review_state["mock_tests"] = {"attempt_count": 0, "latest_score": None}
        needs_review = calculate_exam_readiness_score(needs_review_state)
        self.assertEqual(needs_review["status"], "needs_review")

        at_risk_state = _base_state()
        at_risk_state["readiness"]["incomplete_sources"] = [{"source_id": "X"}]
        at_risk_state["readiness"]["units_without_synthesis"] = [{"unit_id": "U"}]
        at_risk_state["readiness"]["units_without_unit_pack"] = [{"unit_id": "U"}]
        at_risk_state["mock_tests"] = {"attempt_count": 0, "latest_score": None}
        at_risk_state["days_until_exam"] = 1
        at_risk = calculate_exam_readiness_score(at_risk_state)
        self.assertEqual(at_risk["status"], "at_risk")

        not_ready_state = _base_state()
        not_ready_state["readiness"]["incomplete_sources"] = [{"source_id": "X"}]
        not_ready_state["readiness"]["units_without_synthesis"] = [{"unit_id": "U"}]
        not_ready_state["readiness"]["units_without_unit_pack"] = [{"unit_id": "U"}]
        not_ready_state["review"]["open_mistakes"] = [{"id": str(i)} for i in range(4)]
        not_ready_state["review"]["open_weak_points"] = [{"id": str(i)} for i in range(5)]
        not_ready_state["mock_tests"] = {"attempt_count": 1, "latest_score": 50.0}
        not_ready_state["days_until_exam"] = 0
        not_ready = calculate_exam_readiness_score(not_ready_state)
        self.assertEqual(not_ready["status"], "not_ready")


class TestExamReadinessIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.unit1 = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        self.exam = create_exam_target(
            "ECA1010_Test",
            "Quiz 2",
            "2026-06-20",
            target_score=80,
            unit_ids=[self.unit1["unit_id"]],
            source_ids=["SRC-0005"],
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_get_exam_readiness_report(self) -> None:
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            report = get_exam_readiness_report(
                "ECA1010_Test", self.exam["exam_id"], root=self.root
            )
        self.assertEqual(report["exam_id"], "EXAM-0001")
        self.assertEqual(report["title"], "Quiz 2")
        self.assertEqual(report["days_until_exam"], 10)
        self.assertEqual(report["target_score"], 80)
        self.assertIn("score", report["readiness"])
        self.assertIn("state_summary", report)

    def test_markdown_includes_score_and_blockers(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            report = get_exam_readiness_report(
                "ECA1010_Test", self.exam["exam_id"], root=self.root
            )
        md = build_exam_readiness_markdown(report)
        self.assertIn("# Exam Readiness Report — EXAM-0001", md)
        self.assertIn("Readiness score:", md)
        self.assertIn("## Main Blockers", md)
        self.assertIn("## Recommendations", md)
        self.assertIn("## Next Study Action", md)
        self.assertIn("not a guarantee", md)

    def test_export_writes_md_json(self) -> None:
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            result = export_exam_readiness_report(
                "ECA1010_Test",
                self.exam["exam_id"],
                root=self.root,
            )
        md_path = Path(result["markdown_path"])
        json_path = Path(result["json_path"])
        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())
        self.assertIn("Exam Readiness Report", md_path.read_text(encoding="utf-8"))
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["exam_id"], "EXAM-0001")

        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            with self.assertRaises(ExamReadinessReportExistsError):
                export_exam_readiness_report(
                    "ECA1010_Test",
                    self.exam["exam_id"],
                    root=self.root,
                )

    def test_today_nearest_exam_readiness(self) -> None:
        add_weak_point(
            "ECA1010_Test",
            "SRC-0001",
            "Inflation",
            confidence_level=2,
            root=self.root,
        )
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ), patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-10",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        nearest = dashboard["summary"].get("nearest_exam")
        self.assertIsNotNone(nearest)
        self.assertIsNotNone(nearest.get("readiness_score"))
        self.assertIn(nearest.get("readiness_status"), {
            "ready",
            "needs_review",
            "at_risk",
            "not_ready",
        })

    @patch("scripts.exam_readiness.get_exam_readiness_report")
    def test_cli_smoke(self, mock_report) -> None:
        from scripts import exam_readiness as cli_module

        mock_report.return_value = {
            "title": "Quiz 2",
            "readiness": {
                "score": 72,
                "status": "needs_review",
                "blockers": ["No mock test attempt yet."],
                "recommendations": ["Take a mock test."],
            },
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--exam-id", "EXAM-0001"]
        )
        self.assertEqual(code, 0)
        mock_report.assert_called_once_with("ECA1010_Test", "EXAM-0001")

    def test_mock_score_improves_readiness(self) -> None:
        record_mock_test_attempt(
            "ECA1010_Test",
            "MT-SRC-0001-TEST",
            "source",
            "SRC-0001",
            None,
            18,
            20,
            root=self.root,
        )
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            report = get_exam_readiness_report(
                "ECA1010_Test", self.exam["exam_id"], root=self.root
            )
        self.assertEqual(report["readiness"]["breakdown"]["mock_tests"], 30)
        self.assertNotIn("No mock test attempt yet.", report["readiness"]["blockers"])


if __name__ == "__main__":
    unittest.main()
