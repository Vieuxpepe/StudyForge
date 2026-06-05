"""Tests for Today Dashboard v1."""

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
from studyforge.study.flashcard_review import (  # noqa: E402
    get_flashcard_review_log_path,
    save_flashcard_review_log,
)
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.review_planner import generate_review_plan  # noqa: E402
from studyforge.study.study_session import start_study_session  # noqa: E402
from studyforge.study.today_dashboard import (  # noqa: E402
    build_today_dashboard_markdown,
    export_today_dashboard,
    get_today_dashboard,
    get_today_dashboard_json_path,
)
from studyforge.study.weak_points import add_weak_point  # noqa: E402


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {"sources": [{"id": "SRC-0001", "title": "Book", "status": "added"}]},
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


class TestTodayDashboard(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_course_nothing_due(self) -> None:
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["recommended_actions"][0]["key"], "nothing_due")
        self.assertEqual(dashboard["summary"]["due_flashcards"], 0)
        self.assertEqual(dashboard["summary"]["latest_session_status"], "none")

    def test_due_flashcards_count(self) -> None:
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        save_flashcard_review_log(
            log_path,
            {
                "source_id": "SRC-0001",
                "reviews": [
                    {
                        "review_id": "FC-REVIEW-0001",
                        "source_id": "SRC-0001",
                        "card_id": "FC-SRC-0001-0001",
                        "front": "Q",
                        "back": "A",
                        "grade": "hard",
                        "notes": "",
                        "date_reviewed": "2026-06-04T10:00:00",
                    }
                ],
            },
        )
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["summary"]["due_flashcards"], 1)
        self.assertNotEqual(dashboard["recommended_actions"][0]["key"], "nothing_due")

    def test_open_mistakes_count(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["summary"]["open_mistakes"], 1)

    def test_open_weak_points_count(self) -> None:
        add_weak_point("ECA1010_Test", "SRC-0001", "Concept", root=self.root)
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["summary"]["open_weak_points"], 1)

    def test_active_recall_needs_review_count(self) -> None:
        from studyforge.study.active_recall import get_active_recall_log_path, save_active_recall_log

        log_path = get_active_recall_log_path(self.course, "SRC-0001")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        save_active_recall_log(
            log_path,
            {
                "source_id": "SRC-0001",
                "attempts": [
                    {
                        "attempt_id": "AR-ATTEMPT-0001",
                        "source_id": "SRC-0001",
                        "question_id": "AR-SRC-0001-Q001",
                        "question": "Q",
                        "user_answer": "bad",
                        "grade": "wrong",
                        "notes": "",
                        "date_answered": "2026-06-04T10:00:00",
                    }
                ],
            },
        )
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["summary"]["active_recall_needs_review"], 1)

    def test_review_plan_changes_recommended_action(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            before = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(before["recommended_actions"][0]["key"], "generate_review_plan")

        generate_review_plan("ECA1010_Test", date_str="2026-06-04", root=self.root)
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            after = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertTrue(after["summary"]["has_review_plan_today"])
        self.assertEqual(after["recommended_actions"][0]["key"], "start_study_session")

    def test_in_progress_session_continue(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        generate_review_plan("ECA1010_Test", date_str="2026-06-04", root=self.root)
        start_study_session("ECA1010_Test", limit=5, root=self.root)
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["summary"]["latest_session_status"], "in_progress")
        self.assertEqual(
            dashboard["recommended_actions"][0]["key"], "continue_study_session"
        )

    def test_complete_session_recommended_action(self) -> None:
        from studyforge.study.study_session import complete_study_session

        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        generate_review_plan("ECA1010_Test", date_str="2026-06-04", root=self.root)
        started = start_study_session("ECA1010_Test", limit=5, root=self.root)
        complete_study_session(
            "ECA1010_Test", started["session_id"], root=self.root
        )
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["summary"]["latest_session_status"], "complete")
        self.assertEqual(
            dashboard["recommended_actions"][0]["key"],
            "review_complete_or_start_new",
        )

    def test_build_markdown(self) -> None:
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        text = build_today_dashboard_markdown(dashboard)
        self.assertIn("# Today Dashboard — 2026-06-04", text)
        self.assertIn("## Summary", text)
        self.assertIn("## Recommended Actions", text)

    def test_export_writes_files(self) -> None:
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            md_path = export_today_dashboard("ECA1010_Test", root=self.root)
        json_path = get_today_dashboard_json_path(self.course, "2026-06-04")
        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["date"], "2026-06-04")

    @patch("scripts.today.get_today_dashboard")
    def test_cli_output(self, mock_dashboard) -> None:
        from scripts import today as cli_module

        mock_dashboard.return_value = {
            "course": "ECA1010_Test",
            "date": "2026-06-04",
            "summary": {
                "due_flashcards": 2,
                "active_recall_needs_review": 1,
                "open_mistakes": 3,
                "open_weak_points": 0,
                "has_review_plan_today": False,
                "latest_session_status": "none",
            },
            "recommended_actions": [
                {"key": "generate_review_plan", "label": "Generate today's review plan"}
            ],
            "warnings": [],
        }
        code = cli_module.main(["--course", "ECA1010_Test"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
