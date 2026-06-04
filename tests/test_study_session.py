"""Tests for Study Session Mode v1."""

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
from studyforge.study.active_recall import (  # noqa: E402
    get_active_recall_log_path,
    save_active_recall_log,
)
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.study_session import (  # noqa: E402
    InvalidSessionResultError,
    StudySessionItemNotFoundError,
    build_study_session_items,
    complete_study_session,
    export_study_session_summary,
    get_study_session_log_path,
    record_session_item_result,
    start_study_session,
)
from studyforge.study.weak_points import add_weak_point  # noqa: E402


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {"sources": [{"id": "SRC-0001", "title": "Book", "status": "study_pack_generated"}]},
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


class TestStudySession(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_build_items_includes_all_types(self) -> None:
        add_mistake(
            "ECA1010_Test", "SRC-0001", "What is CPI?", "Wrong", root=self.root
        )
        add_weak_point(
            "ECA1010_Test", "SRC-0001", "Inflation rate", confidence_level=2, root=self.root
        )
        log_path = get_active_recall_log_path(self.course, "SRC-0001")
        save_active_recall_log(
            log_path,
            {
                "source_id": "SRC-0001",
                "attempts": [
                    {
                        "attempt_id": "AR-ATTEMPT-0001",
                        "source_id": "SRC-0001",
                        "question_id": "AR-SRC-0001-Q001",
                        "question": "Define CPI",
                        "user_answer": "idk",
                        "grade": "wrong",
                        "notes": "",
                        "date_answered": "2026-06-04T12:00:00",
                    }
                ],
            },
        )

        items = build_study_session_items("ECA1010_Test", root=self.root, limit=10)
        types = {item["type"] for item in items}
        self.assertIn("mistake", types)
        self.assertIn("weak_point", types)
        self.assertIn("active_recall", types)
        self.assertTrue(all(item["session_item_id"].startswith("SESSION-ITEM-") for item in items))

    def test_empty_data_returns_zero_items(self) -> None:
        items = build_study_session_items("ECA1010_Test", root=self.root, limit=5)
        self.assertEqual(items, [])

    def test_start_creates_json_log(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        summary = start_study_session("ECA1010_Test", limit=5, root=self.root)
        path = get_study_session_log_path(self.course, summary["session_id"])
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "in_progress")
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_record_and_complete_session(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        started = start_study_session("ECA1010_Test", limit=5, root=self.root)
        item_id = json.loads(
            get_study_session_log_path(self.course, started["session_id"]).read_text(
                encoding="utf-8"
            )
        )["items"][0]["session_item_id"]

        recorded = record_session_item_result(
            "ECA1010_Test",
            started["session_id"],
            item_id,
            "reviewed_once",
            notes="Looked again",
            root=self.root,
        )
        self.assertEqual(recorded["result"], "reviewed_once")
        self.assertEqual(recorded["completed_count"], 1)

        finished = complete_study_session(
            "ECA1010_Test", started["session_id"], root=self.root
        )
        self.assertEqual(finished["status"], "complete")
        data = json.loads(
            get_study_session_log_path(self.course, started["session_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(data["status"], "complete")
        self.assertIsNotNone(data["date_completed"])

    def test_export_summary_markdown(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        started = start_study_session("ECA1010_Test", root=self.root)
        path = export_study_session_summary(
            "ECA1010_Test", started["session_id"], root=self.root
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("# Study Session Summary", text)
        self.assertIn(started["session_id"], text)
        self.assertIn("Next suggested actions", text)

    def test_invalid_result_rejected(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        started = start_study_session("ECA1010_Test", root=self.root)
        item_id = json.loads(
            get_study_session_log_path(self.course, started["session_id"]).read_text(
                encoding="utf-8"
            )
        )["items"][0]["session_item_id"]
        with self.assertRaises(InvalidSessionResultError):
            record_session_item_result(
                "ECA1010_Test",
                started["session_id"],
                item_id,
                "bogus",
                root=self.root,
            )

    def test_unknown_item_rejected(self) -> None:
        started = start_study_session("ECA1010_Test", root=self.root)
        with self.assertRaises(StudySessionItemNotFoundError):
            record_session_item_result(
                "ECA1010_Test",
                started["session_id"],
                "SESSION-ITEM-9999",
                "completed",
                root=self.root,
            )

    @patch("scripts.study_session.start_study_session")
    def test_cli_start(self, mock_start) -> None:
        from scripts import study_session as cli_module

        mock_start.return_value = {
            "session_id": "SESSION-20260604-120000",
            "item_count": 3,
            "log_path": "/tmp/s.json",
        }
        code = cli_module.main(["--course", "ECA1010_Test", "--start", "--limit", "5"])
        self.assertEqual(code, 0)
        mock_start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
