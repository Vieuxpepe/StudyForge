"""Tests for Unit-Level Review Integration v1."""

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

from studyforge.core.sources import resolve_course_path, save_source_registry  # noqa: E402
from studyforge.study.study_session import (  # noqa: E402
    build_study_session_items,
    record_session_item_result,
    start_study_session,
)
from studyforge.study.study_unit_dashboard import generate_unit_review_plan  # noqa: E402
from studyforge.study.study_units import create_study_unit  # noqa: E402
from studyforge.study.unit_review import (  # noqa: E402
    collect_due_unit_flashcards,
    collect_due_unit_flashcards_for_unit,
    collect_unit_active_recall_needs_review,
    collect_unit_active_recall_needs_review_for_unit,
    get_unit_active_recall_log_path,
    get_unit_flashcard_review_log_path,
    load_unit_active_recall_questions,
    load_unit_flashcards,
    record_unit_active_recall_attempt,
    record_unit_flashcard_review,
    summarize_unit_active_recall,
    summarize_unit_flashcard_reviews,
)
from studyforge.study.unit_study_pack import (  # noqa: E402
    generate_unit_study_pack,
    get_unit_study_pack_output_paths,
)
from studyforge.study.unit_synthesis_import import import_unit_synthesis  # noqa: E402

UNIT_ACTIVE_RECALL_TEXT = """# Unit Active Recall

Course:
ECA1010_Test

Unit:
UNIT-0001 — Inflation and CPI

Instructions:
Ask one question at a time.

1. What is inflation?
2. Define CPI.
"""


def _valid_synthesis_text() -> str:
    sections = "\n".join(
        f"## {name}\n"
        f"- Detail about {name} with enough words for quality checks.\n"
        for name in (
            "Unit Overview",
            "Core Concepts",
            "Merged Formula / Method Sheet",
            "Cross-Source Connections",
            "Conflicts or Uncertainties",
            "Must-Memorize List",
            "Must-Understand List",
            "Exam / Homework Traps",
            "Practice Questions",
            "Active Recall Questions",
            "Weak Points to Review",
            "Final Unit Checklist",
        )
    )
    return f"# Unit Synthesis\n\n{sections}\n"


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "00_Master").mkdir(parents=True)
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {"sources": [{"id": "SRC-0001", "title": "Book", "status": "study_pack_generated"}]},
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


def _setup_unit_with_pack(root: Path) -> tuple[Path, dict]:
    course = _setup_course(root)
    unit = create_study_unit(
        "ECA1010_Test",
        "Inflation and CPI",
        source_ids=["SRC-0001"],
        root=root,
    )
    import_unit_synthesis(
        "ECA1010_Test",
        unit["unit_id"],
        synthesis_text=_valid_synthesis_text(),
        root=root,
    )
    generate_unit_study_pack("ECA1010_Test", unit["unit_id"], root=root)
    paths = get_unit_study_pack_output_paths(course, unit["unit_id"])
    paths["unit_active_recall"].write_text(UNIT_ACTIVE_RECALL_TEXT, encoding="utf-8")
    return course, unit


class TestUnitActiveRecall(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course, self.unit = _setup_unit_with_pack(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_unit_active_recall_questions(self) -> None:
        questions = load_unit_active_recall_questions(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["question_id"], "UAR-UNIT-0001-Q001")
        self.assertEqual(questions[0]["unit_id"], "UNIT-0001")
        self.assertEqual(questions[0]["question_number"], 1)
        self.assertIn("inflation", questions[0]["question"].lower())

    def test_record_unit_active_recall_attempt(self) -> None:
        result = record_unit_active_recall_attempt(
            "ECA1010_Test",
            self.unit["unit_id"],
            "UAR-UNIT-0001-Q001",
            "What is inflation?",
            "Rising prices",
            "partial",
            root=self.root,
        )
        self.assertEqual(result["grade"], "partial")
        log_path = get_unit_active_recall_log_path(self.course, self.unit["unit_id"])
        self.assertTrue(log_path.is_file())
        log = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(log["attempts"][0]["attempt_id"], "UAR-ATTEMPT-0001")
        self.assertEqual(log["attempts"][0]["unit_id"], "UNIT-0001")

    def test_summarize_unit_active_recall(self) -> None:
        record_unit_active_recall_attempt(
            "ECA1010_Test",
            self.unit["unit_id"],
            "UAR-UNIT-0001-Q001",
            "What is inflation?",
            "answer",
            "correct",
            root=self.root,
        )
        record_unit_active_recall_attempt(
            "ECA1010_Test",
            self.unit["unit_id"],
            "UAR-UNIT-0001-Q002",
            "Define CPI.",
            "wrong",
            "wrong",
            root=self.root,
        )
        summary = summarize_unit_active_recall(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertEqual(summary["attempt_count"], 2)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["wrong"], 1)
        self.assertEqual(summary["needs_review_count"], 1)

    def test_collect_unit_active_recall_needs_review(self) -> None:
        record_unit_active_recall_attempt(
            "ECA1010_Test",
            self.unit["unit_id"],
            "UAR-UNIT-0001-Q001",
            "What is inflation?",
            "a",
            "wrong",
            root=self.root,
        )
        record_unit_active_recall_attempt(
            "ECA1010_Test",
            self.unit["unit_id"],
            "UAR-UNIT-0001-Q001",
            "What is inflation?",
            "b",
            "correct",
            root=self.root,
        )
        needs = collect_unit_active_recall_needs_review_for_unit(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertEqual(needs, [])
        record_unit_active_recall_attempt(
            "ECA1010_Test",
            self.unit["unit_id"],
            "UAR-UNIT-0001-Q002",
            "Define CPI.",
            "c",
            "partial",
            root=self.root,
        )
        needs = collect_unit_active_recall_needs_review(
            "ECA1010_Test", root=self.root
        )
        self.assertEqual(len(needs), 1)
        self.assertEqual(needs[0]["question_id"], "UAR-UNIT-0001-Q002")


class TestUnitFlashcards(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course, self.unit = _setup_unit_with_pack(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_unit_flashcards(self) -> None:
        cards = load_unit_flashcards(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertGreaterEqual(len(cards), 1)
        self.assertTrue(cards[0]["card_id"].startswith("UFC-UNIT-0001-"))
        self.assertEqual(cards[0]["unit_id"], "UNIT-0001")

    def test_record_unit_flashcard_review_with_due_date(self) -> None:
        cards = load_unit_flashcards(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        card = cards[0]
        result = record_unit_flashcard_review(
            "ECA1010_Test",
            self.unit["unit_id"],
            card["card_id"],
            card["front"],
            card["back"],
            "hard",
            reviewed_date="2026-06-04",
            root=self.root,
        )
        self.assertEqual(result["grade"], "hard")
        self.assertEqual(result["due_date"], "2026-06-06")
        log_path = get_unit_flashcard_review_log_path(self.course, self.unit["unit_id"])
        self.assertTrue(log_path.is_file())

    def test_collect_due_unit_flashcards(self) -> None:
        cards = load_unit_flashcards(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        card = cards[0]
        record_unit_flashcard_review(
            "ECA1010_Test",
            self.unit["unit_id"],
            card["card_id"],
            card["front"],
            card["back"],
            "hard",
            reviewed_date="2026-06-04",
            root=self.root,
        )
        due = collect_due_unit_flashcards_for_unit(
            "ECA1010_Test",
            self.unit["unit_id"],
            root=self.root,
            today="2026-06-10",
        )
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["card_id"], card["card_id"])
        course_due = collect_due_unit_flashcards(
            "ECA1010_Test", root=self.root, today="2026-06-10"
        )
        self.assertEqual(len(course_due), 1)

    def test_summarize_unit_flashcard_reviews(self) -> None:
        cards = load_unit_flashcards(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        record_unit_flashcard_review(
            "ECA1010_Test",
            self.unit["unit_id"],
            cards[0]["card_id"],
            cards[0]["front"],
            cards[0]["back"],
            "good",
            root=self.root,
        )
        summary = summarize_unit_flashcard_reviews(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertEqual(summary["review_count"], 1)
        self.assertEqual(summary["good"], 1)


class TestUnitStudySessionIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course, self.unit = _setup_unit_with_pack(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unit_session_includes_unit_unanswered_recall(self) -> None:
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            unit_id=self.unit["unit_id"],
        )
        unanswered = [
            i for i in items if i["type"] == "unit_active_recall_unanswered"
        ]
        self.assertGreaterEqual(len(unanswered), 1)
        self.assertEqual(unanswered[0]["unit_id"], "UNIT-0001")

    def test_unit_session_includes_unit_unreviewed_flashcards(self) -> None:
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=10,
            unit_id=self.unit["unit_id"],
        )
        unreviewed = [i for i in items if i["type"] == "unit_flashcard_unreviewed"]
        self.assertGreaterEqual(len(unreviewed), 1)
        self.assertEqual(unreviewed[0]["unit_id"], "UNIT-0001")

    def test_unit_session_records_unit_recall_result(self) -> None:
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=5,
            unit_id=self.unit["unit_id"],
        )
        recall_item = next(
            i for i in items if i["type"] == "unit_active_recall_unanswered"
        )
        summary = start_study_session(
            "ECA1010_Test",
            limit=5,
            root=self.root,
            unit_id=self.unit["unit_id"],
        )
        record_session_item_result(
            "ECA1010_Test",
            summary["session_id"],
            recall_item["session_item_id"],
            "partial",
            user_answer="My answer",
            root=self.root,
        )
        log_path = get_unit_active_recall_log_path(self.course, self.unit["unit_id"])
        self.assertTrue(log_path.is_file())
        log = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(log["attempts"][-1]["grade"], "partial")

    def test_unit_session_records_unit_flashcard_result(self) -> None:
        items = build_study_session_items(
            "ECA1010_Test",
            root=self.root,
            limit=5,
            unit_id=self.unit["unit_id"],
        )
        flash_item = next(
            i for i in items if i["type"] == "unit_flashcard_unreviewed"
        )
        summary = start_study_session(
            "ECA1010_Test",
            limit=5,
            root=self.root,
            unit_id=self.unit["unit_id"],
        )
        record_session_item_result(
            "ECA1010_Test",
            summary["session_id"],
            flash_item["session_item_id"],
            "good",
            root=self.root,
        )
        log_path = get_unit_flashcard_review_log_path(self.course, self.unit["unit_id"])
        self.assertTrue(log_path.is_file())
        log = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(log["reviews"][-1]["grade"], "good")


class TestUnitReviewPlanIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course, self.unit = _setup_unit_with_pack(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unit_review_plan_includes_unit_level_items(self) -> None:
        record_unit_active_recall_attempt(
            "ECA1010_Test",
            self.unit["unit_id"],
            "UAR-UNIT-0001-Q001",
            "What is inflation?",
            "bad",
            "wrong",
            root=self.root,
        )
        with patch(
            "studyforge.study.study_unit_dashboard._local_today_str",
            return_value="2026-06-04",
        ):
            result = generate_unit_review_plan(
                "ECA1010_Test",
                self.unit["unit_id"],
                root=self.root,
            )
        md = Path(result["markdown_path"]).read_text(encoding="utf-8")
        self.assertIn("## Unit Active Recall", md)
        self.assertIn("UAR-UNIT-0001-Q001", md)
        self.assertIn("## Unit Flashcards Due", md)
        self.assertIn("## Unit-Level New Practice", md)
        self.assertGreaterEqual(result["unit_active_recall_review_count"], 1)


class TestUnitReviewCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course, self.unit = _setup_unit_with_pack(self.root)
        scripts_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "unit_review.py"
        )
        import importlib.util

        spec = importlib.util.spec_from_file_location("unit_review_cli", scripts_path)
        assert spec and spec.loader
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_cli(self, *extra: str) -> tuple[int, str]:
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        args = [
            "--course",
            "ECA1010_Test",
            "--unit-id",
            self.unit["unit_id"],
            *extra,
        ]
        with patch(
            "studyforge.core.sources.find_project_root", return_value=self.root
        ):
            with redirect_stdout(buffer):
                code = self.module.main(args)
        return code, buffer.getvalue()

    def test_cli_list_recall_smoke(self) -> None:
        code, output = self._run_cli("--list-recall")
        self.assertEqual(code, 0)
        self.assertIn("UAR-UNIT-0001-Q001", output)

    def test_cli_summary_smoke(self) -> None:
        code, output = self._run_cli("--summary")
        self.assertEqual(code, 0)
        self.assertIn("Unit active recall summary", output)


if __name__ == "__main__":
    unittest.main()
