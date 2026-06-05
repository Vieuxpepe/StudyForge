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
    get_active_recall_file,
    get_active_recall_log_path,
    load_active_recall_log,
    save_active_recall_log,
)
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.exam_targets import (  # noqa: E402
    ExamTargetNotFoundError,
    create_exam_target,
)
from studyforge.study.study_session import (  # noqa: E402
    ConflictingSessionScopeError,
    InvalidSessionResultError,
    StudySessionItemNotFoundError,
    build_study_session_items,
    collect_unanswered_active_recall_questions,
    complete_study_session,
    export_study_session_summary,
    filter_items_by_exam_scope,
    filter_items_by_source_ids,
    get_exam_scope_info,
    get_study_session_log_path,
    get_unit_scope_info,
    record_session_item_result,
    start_study_session,
)
from studyforge.study.study_units import StudyUnitNotFoundError, create_study_unit  # noqa: E402
from studyforge.study.weak_points import add_weak_point  # noqa: E402

ACTIVE_RECALL_TEXT = """# Active Recall

Instructions:
Ask one at a time.

1. What is inflation?
2. Define CPI.
3. What is GDP?
"""


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


def _write_active_recall_file(course: Path, source_id: str = "SRC-0001") -> Path:
    recall_path = get_active_recall_file(course, source_id)
    recall_path.parent.mkdir(parents=True, exist_ok=True)
    recall_path.write_text(ACTIVE_RECALL_TEXT, encoding="utf-8")
    return recall_path


class TestStudySession(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_build_items_includes_all_types(self) -> None:
        _write_active_recall_file(self.course)
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

    def test_fresh_study_pack_includes_unanswered_recall(self) -> None:
        _write_active_recall_file(self.course)
        items = build_study_session_items("ECA1010_Test", root=self.root, limit=5)
        unanswered = [item for item in items if item["type"] == "active_recall_unanswered"]
        self.assertEqual(len(unanswered), 3)
        self.assertEqual(unanswered[0]["payload"]["question_id"], "AR-SRC-0001-Q001")
        self.assertEqual(unanswered[0]["title"], "Unanswered active recall question")

    def test_collect_unanswered_excludes_latest_correct(self) -> None:
        _write_active_recall_file(self.course)
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
                        "question": "What is inflation?",
                        "user_answer": "Rising prices",
                        "grade": "correct",
                        "notes": "",
                        "date_answered": "2026-06-04T12:00:00",
                    }
                ],
            },
        )

        unanswered = collect_unanswered_active_recall_questions(
            "ECA1010_Test", root=self.root
        )
        question_ids = {item["question_id"] for item in unanswered}
        self.assertNotIn("AR-SRC-0001-Q001", question_ids)
        self.assertIn("AR-SRC-0001-Q002", question_ids)
        self.assertIn("AR-SRC-0001-Q003", question_ids)

    def test_needs_review_not_duplicated_as_unanswered(self) -> None:
        _write_active_recall_file(self.course)
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
                        "question": "What is inflation?",
                        "user_answer": "idk",
                        "grade": "wrong",
                        "notes": "",
                        "date_answered": "2026-06-04T12:00:00",
                    }
                ],
            },
        )

        items = build_study_session_items("ECA1010_Test", root=self.root, limit=10)
        recall_ids = [
            item["payload"]["question_id"]
            for item in items
            if item["type"] in {"active_recall", "active_recall_unanswered"}
        ]
        self.assertEqual(recall_ids.count("AR-SRC-0001-Q001"), 1)
        self.assertEqual(
            next(
                item["type"]
                for item in items
                if item["payload"].get("question_id") == "AR-SRC-0001-Q001"
            ),
            "active_recall",
        )

    def test_session_limit_respects_priority_then_unanswered(self) -> None:
        _write_active_recall_file(self.course)
        add_mistake("ECA1010_Test", "SRC-0001", "Q1", "A1", root=self.root)
        add_mistake("ECA1010_Test", "SRC-0001", "Q2", "A2", root=self.root)
        add_weak_point(
            "ECA1010_Test", "SRC-0001", "Concept", confidence_level=1, root=self.root
        )

        items = build_study_session_items("ECA1010_Test", root=self.root, limit=5)
        self.assertEqual(len(items), 5)
        priority_types = {"mistake", "weak_point"}
        self.assertEqual(sum(1 for item in items if item["type"] in priority_types), 3)
        unanswered = [item for item in items if item["type"] == "active_recall_unanswered"]
        self.assertEqual(len(unanswered), 2)

    def test_record_unanswered_recall_creates_log_entry(self) -> None:
        _write_active_recall_file(self.course)
        started = start_study_session("ECA1010_Test", limit=3, root=self.root)
        session = json.loads(
            get_study_session_log_path(self.course, started["session_id"]).read_text(
                encoding="utf-8"
            )
        )
        item = session["items"][0]
        self.assertEqual(item["type"], "active_recall_unanswered")

        recorded = record_session_item_result(
            "ECA1010_Test",
            started["session_id"],
            item["session_item_id"],
            "partial",
            user_answer="Maybe rising prices",
            notes="Unsure",
            root=self.root,
        )
        self.assertEqual(recorded["result"], "partial")
        self.assertIn("active_recall", recorded["applied"])

        log = load_active_recall_log(get_active_recall_log_path(self.course, "SRC-0001"))
        self.assertEqual(len(log["attempts"]), 1)
        self.assertEqual(log["attempts"][0]["question_id"], item["payload"]["question_id"])
        self.assertEqual(log["attempts"][0]["grade"], "partial")

    def test_start_creates_json_log(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        summary = start_study_session("ECA1010_Test", limit=5, root=self.root)
        path = get_study_session_log_path(self.course, summary["session_id"])
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "in_progress")
        self.assertEqual(data.get("scope"), "course")
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
        _write_active_recall_file(self.course)
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
            "scope": "course",
        }
        code = cli_module.main(["--course", "ECA1010_Test", "--start", "--limit", "5"])
        self.assertEqual(code, 0)
        mock_start.assert_called_once_with(
            "ECA1010_Test", limit=5, unit_id=None, exam_id=None
        )

    @patch("scripts.study_session.start_study_session")
    def test_cli_start_unit(self, mock_start) -> None:
        from scripts import study_session as cli_module

        mock_start.return_value = {
            "session_id": "SESSION-20260604-120001",
            "item_count": 2,
            "log_path": "/tmp/u.json",
            "scope": "unit",
            "unit_id": "UNIT-0001",
            "unit_title": "Inflation",
        }
        code = cli_module.main(
            [
                "--course",
                "ECA1010_Test",
                "--start",
                "--unit-id",
                "UNIT-0001",
                "--limit",
                "10",
            ]
        )
        self.assertEqual(code, 0)
        mock_start.assert_called_once_with(
            "ECA1010_Test", limit=10, unit_id="UNIT-0001", exam_id=None
        )

    @patch("scripts.study_session.start_study_session")
    def test_cli_start_exam(self, mock_start) -> None:
        from scripts import study_session as cli_module

        mock_start.return_value = {
            "session_id": "SESSION-20260604-120002",
            "item_count": 20,
            "log_path": "/tmp/e.json",
            "scope": "exam",
            "exam_id": "EXAM-0001",
            "exam_title": "Quiz 2",
            "exam_date": "2026-06-20",
            "target_score": 80,
        }
        code = cli_module.main(
            [
                "--course",
                "ECA1010_Test",
                "--start",
                "--exam-id",
                "EXAM-0001",
                "--limit",
                "20",
            ]
        )
        self.assertEqual(code, 0)
        mock_start.assert_called_once_with(
            "ECA1010_Test", limit=20, unit_id=None, exam_id="EXAM-0001"
        )

    def test_cli_rejects_unit_and_exam_together(self) -> None:
        from scripts import study_session as cli_module

        code = cli_module.main(
            [
                "--course",
                "ECA1010_Test",
                "--start",
                "--unit-id",
                "UNIT-0001",
                "--exam-id",
                "EXAM-0001",
            ]
        )
        self.assertEqual(code, 1)


def _setup_multi_source_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    (course / "00_Master").mkdir(parents=True)
    save_source_registry(
        course,
        {
            "sources": [
                {"id": "SRC-0001", "title": "Unit A", "status": "study_pack_generated"},
                {"id": "SRC-0002", "title": "Unit B", "status": "study_pack_generated"},
            ]
        },
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


class TestUnitStudySession(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_multi_source_course(self.root)
        self.unit = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            source_ids=["SRC-0001"],
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_course_wide_scope_unchanged(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q1", "A1", root=self.root)
        add_mistake("ECA1010_Test", "SRC-0002", "Q2", "A2", root=self.root)
        items = build_study_session_items("ECA1010_Test", root=self.root, limit=10)
        sources = {item["source_id"] for item in items}
        self.assertIn("SRC-0001", sources)
        self.assertIn("SRC-0002", sources)

    def test_unit_session_only_unit_sources(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "In unit", "A", root=self.root)
        add_mistake("ECA1010_Test", "SRC-0002", "Out of unit", "B", root=self.root)
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            unit_id=self.unit["unit_id"],
        )
        self.assertTrue(items)
        source_level_types = {
            "mistake",
            "weak_point",
            "active_recall",
            "active_recall_unanswered",
            "flashcard",
            "flashcard_unreviewed",
        }
        source_items = [i for i in items if i["type"] in source_level_types]
        self.assertTrue(all(item["source_id"] == "SRC-0001" for item in source_items))

    def test_unit_session_excludes_other_sources(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0002", "Other", "X", root=self.root)
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            unit_id=self.unit["unit_id"],
        )
        self.assertEqual(items, [])

    def test_unit_session_includes_unanswered_recall(self) -> None:
        _write_active_recall_file(self.course, "SRC-0001")
        _write_active_recall_file(self.course, "SRC-0002")
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            unit_id=self.unit["unit_id"],
        )
        unanswered = [i for i in items if i["type"] == "active_recall_unanswered"]
        self.assertGreaterEqual(len(unanswered), 1)
        self.assertTrue(all(i["source_id"] == "SRC-0001" for i in unanswered))
        other = [i for i in items if i["source_id"] == "SRC-0002"]
        self.assertEqual(other, [])

    def test_unit_session_includes_unreviewed_flashcards(self) -> None:
        from studyforge.study.flashcards import flashcards_to_csv

        for source_id in ("SRC-0001", "SRC-0002"):
            csv_path = (
                self.course
                / "06_Study_Outputs"
                / "flashcards"
                / f"{source_id}_flashcards.csv"
            )
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.write_text(
                flashcards_to_csv(
                    [
                        {
                            "front": f"Q for {source_id}?",
                            "back": "answer",
                            "source_id": source_id,
                            "source_title": source_id,
                            "section": "Test",
                            "tags": [source_id],
                        }
                    ]
                ),
                encoding="utf-8",
            )
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            unit_id=self.unit["unit_id"],
        )
        flash_types = {"flashcard", "flashcard_unreviewed"}
        flash_items = [i for i in items if i["type"] in flash_types]
        self.assertGreaterEqual(len(flash_items), 1)
        self.assertTrue(all(i["source_id"] == "SRC-0001" for i in flash_items))

    def test_unit_session_json_metadata(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        summary = start_study_session(
            "ECA1010_Test",
            limit=5,
            root=self.root,
            unit_id=self.unit["unit_id"],
        )
        data = json.loads(
            get_study_session_log_path(self.course, summary["session_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(data["scope"], "unit")
        self.assertEqual(data["unit_id"], self.unit["unit_id"])
        self.assertEqual(data["unit_title"], "Inflation and CPI")

    def test_invalid_unit_id_raises(self) -> None:
        with self.assertRaises(StudyUnitNotFoundError):
            get_unit_scope_info("ECA1010_Test", "UNIT-9999", root=self.root)

    def test_empty_unit_session_warning(self) -> None:
        empty_unit = create_study_unit(
            "ECA1010_Test",
            "Empty topic",
            source_ids=[],
            root=self.root,
        )
        summary = start_study_session(
            "ECA1010_Test",
            limit=5,
            root=self.root,
            unit_id=empty_unit["unit_id"],
        )
        self.assertEqual(summary["item_count"], 0)
        self.assertIn("warning", summary)
        data = json.loads(
            get_study_session_log_path(self.course, summary["session_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(data["items"], [])
        self.assertIn("warning", data)

    def test_filter_items_by_source_ids(self) -> None:
        items = [
            {"source_id": "SRC-0001", "id": "a"},
            {"source_id": "SRC-0002", "id": "b"},
        ]
        filtered = filter_items_by_source_ids(items, {"SRC-0001"})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "a")


def _setup_exam_course(root: Path) -> tuple[Path, dict, dict, dict]:
    course = _setup_multi_source_course(root)
    save_source_registry(
        course,
        {
            "sources": [
                {"id": "SRC-0001", "title": "Unit A", "status": "study_pack_generated"},
                {"id": "SRC-0002", "title": "Unit B", "status": "study_pack_generated"},
                {"id": "SRC-0005", "title": "Homework", "status": "added"},
            ]
        },
    )
    unit1 = create_study_unit(
        "ECA1010_Test",
        "Inflation and CPI",
        source_ids=["SRC-0001"],
        root=root,
    )
    unit2 = create_study_unit(
        "ECA1010_Test",
        "GDP Deflator",
        source_ids=["SRC-0002"],
        root=root,
    )
    exam = create_exam_target(
        "ECA1010_Test",
        "Quiz 2",
        "2026-06-20",
        target_score=80,
        unit_ids=[unit1["unit_id"], unit2["unit_id"]],
        source_ids=["SRC-0005"],
        root=root,
    )
    return course, unit1, unit2, exam


class TestExamStudySession(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course, self.unit1, self.unit2, self.exam = _setup_exam_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_course_wide_scope_unchanged(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q1", "A1", root=self.root)
        add_mistake("ECA1010_Test", "SRC-9999", "Other", "X", root=self.root)
        items = build_study_session_items("ECA1010_Test", root=self.root, limit=10)
        sources = {item["source_id"] for item in items}
        self.assertIn("SRC-0001", sources)

    def test_unit_session_unchanged(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "In unit", "A", root=self.root)
        add_mistake("ECA1010_Test", "SRC-0002", "Out of unit", "B", root=self.root)
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            unit_id=self.unit1["unit_id"],
        )
        source_items = [
            i
            for i in items
            if i["type"] in {"mistake", "weak_point", "active_recall_unanswered"}
        ]
        self.assertTrue(all(item["source_id"] == "SRC-0001" for item in source_items))

    def test_exam_session_includes_scoped_sources_only(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "In scope", "A", root=self.root)
        add_mistake("ECA1010_Test", "SRC-0005", "Direct source", "B", root=self.root)
        add_mistake("ECA1010_Test", "SRC-9999", "Out of scope", "C", root=self.root)
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            exam_id=self.exam["exam_id"],
        )
        self.assertTrue(items)
        source_ids = {item["source_id"] for item in items}
        self.assertIn("SRC-0001", source_ids)
        self.assertIn("SRC-0005", source_ids)
        self.assertNotIn("SRC-9999", source_ids)

    def test_exam_session_includes_unit_level_items(self) -> None:
        add_mistake(
            "ECA1010_Test",
            self.unit1["unit_id"],
            "Unit mistake",
            "A",
            root=self.root,
        )
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            exam_id=self.exam["exam_id"],
        )
        unit_items = [i for i in items if i["source_id"] == self.unit1["unit_id"]]
        self.assertGreaterEqual(len(unit_items), 1)

    def test_exam_session_json_metadata(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        summary = start_study_session(
            "ECA1010_Test",
            limit=5,
            root=self.root,
            exam_id=self.exam["exam_id"],
        )
        self.assertEqual(summary["scope"], "exam")
        self.assertEqual(summary["exam_id"], "EXAM-0001")
        self.assertEqual(summary["exam_title"], "Quiz 2")
        self.assertEqual(summary["exam_date"], "2026-06-20")
        self.assertEqual(summary["target_score"], 80)
        data = json.loads(
            get_study_session_log_path(self.course, summary["session_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(data["scope"], "exam")
        self.assertEqual(data["exam_id"], "EXAM-0001")
        self.assertIn("unit_ids", data)
        self.assertIn("source_ids", data)
        self.assertIn(self.unit1["unit_id"], data["unit_ids"])
        self.assertIn("SRC-0005", data["source_ids"])

    def test_empty_exam_scope_warning(self) -> None:
        empty_exam = create_exam_target(
            "ECA1010_Test",
            "Empty exam",
            "2026-06-25",
            root=self.root,
        )
        summary = start_study_session(
            "ECA1010_Test",
            limit=5,
            root=self.root,
            exam_id=empty_exam["exam_id"],
        )
        self.assertEqual(summary["item_count"], 0)
        self.assertIn("warning", summary)
        self.assertIn("no units or sources", summary["warning"].lower())

    def test_invalid_exam_id_raises(self) -> None:
        with self.assertRaises(ExamTargetNotFoundError):
            get_exam_scope_info("ECA1010_Test", "EXAM-9999", root=self.root)

    def test_unit_id_and_exam_id_rejected(self) -> None:
        with self.assertRaises(ConflictingSessionScopeError):
            build_study_session_items(
                "ECA1010_Test",
                root=self.root,
                unit_id=self.unit1["unit_id"],
                exam_id=self.exam["exam_id"],
            )

    def test_filter_items_by_exam_scope(self) -> None:
        items = [
            {"source_id": "SRC-0001", "id": "a"},
            {"source_id": "SRC-9999", "id": "b"},
            {"source_id": "UNIT-0001", "id": "c"},
            {"source_id": "SRC-0002", "unit_id": "UNIT-0002", "id": "d"},
        ]
        filtered = filter_items_by_exam_scope(
            items,
            {"SRC-0001", "SRC-0005"},
            {"UNIT-0001"},
        )
        ids = {item["id"] for item in filtered}
        self.assertEqual(ids, {"a", "c"})

    def test_past_exam_date_adds_warning(self) -> None:
        past_exam = create_exam_target(
            "ECA1010_Test",
            "Past quiz",
            "2020-01-01",
            unit_ids=[self.unit1["unit_id"]],
            root=self.root,
        )
        scope = get_exam_scope_info(
            "ECA1010_Test", past_exam["exam_id"], root=self.root
        )
        self.assertTrue(
            any("past" in warning.lower() for warning in scope["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
