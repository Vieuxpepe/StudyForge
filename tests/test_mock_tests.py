"""Tests for Mock Test / Exam Simulator v1."""

from __future__ import annotations

import importlib.util
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
from studyforge.study.mock_tests import (  # noqa: E402
    InvalidMockTestScoreError,
    MockTestNotReadyError,
    build_mock_test_questions,
    generate_mock_test,
    get_mock_test_log_path,
    parse_flashcard_questions_from_csv,
    parse_questions_from_markdown,
    record_mock_test_attempt,
    summarize_mock_test_attempts,
)
from studyforge.study.study_units import create_study_unit  # noqa: E402
from studyforge.study.unit_study_pack import generate_unit_study_pack  # noqa: E402
from studyforge.study.unit_synthesis_import import import_unit_synthesis  # noqa: E402
from studyforge.study.weak_points import list_weak_points  # noqa: E402

QUIZ_TEXT = """# Practice Quiz

1. What is inflation?
2. Define CPI.
"""

RECALL_TEXT = """# Active Recall

1. What is inflation?
3. What is GDP?
"""

FLASHCARD_CSV = """front,back,section,tags
What is CPI?,Consumer Price Index,Formulas,CPI
Nominal vs real?,Adjust for inflation,Concepts,inflation
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


def _write_source_study_files(course: Path) -> None:
    base = course / "06_Study_Outputs"
    (base / "quizzes").mkdir(parents=True, exist_ok=True)
    (base / "active_recall").mkdir(parents=True, exist_ok=True)
    (base / "flashcards").mkdir(parents=True, exist_ok=True)
    (base / "quizzes" / "SRC-0001_practice_quiz.md").write_text(
        QUIZ_TEXT, encoding="utf-8"
    )
    (base / "active_recall" / "SRC-0001_active_recall.md").write_text(
        RECALL_TEXT, encoding="utf-8"
    )
    (base / "flashcards" / "SRC-0001_flashcards.csv").write_text(
        FLASHCARD_CSV, encoding="utf-8"
    )
    (base / "SRC-0001_study_pack_manifest.json").write_text(
        json.dumps({"quality": {"quality_status": "ok"}}),
        encoding="utf-8",
    )


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


class TestParseQuestions(unittest.TestCase):
    def test_parse_markdown_numbered_questions(self) -> None:
        questions = parse_questions_from_markdown(QUIZ_TEXT, source="practice_quiz")
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["source"], "practice_quiz")
        self.assertIn("inflation", questions[0]["question"].lower())

    def test_parse_markdown_bullet_questions(self) -> None:
        text = "# Quiz\n\n- What is elasticity?\n- Define surplus.\n"
        questions = parse_questions_from_markdown(text, source="active_recall")
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["source"], "active_recall")

    def test_parse_flashcard_csv(self) -> None:
        cards = parse_flashcard_questions_from_csv(FLASHCARD_CSV)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["source"], "flashcard")
        self.assertEqual(cards[0]["expected_answer"], "Consumer Price Index")
        self.assertIn("CPI", cards[0]["tags"])


class TestBuildMockTestQuestions(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        _write_source_study_files(self.course)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_build_source_mock_test_questions(self) -> None:
        questions = build_mock_test_questions(
            "ECA1010_Test",
            "source",
            source_id="SRC-0001",
            question_count=10,
            root=self.root,
        )
        self.assertGreaterEqual(len(questions), 3)
        self.assertTrue(all(q["mock_question_id"].startswith("MT-SRC-0001-Q") for q in questions))
        self.assertEqual(questions[0]["scope"], "source")
        self.assertEqual(questions[0]["source_id"], "SRC-0001")

    def test_deduplicate_questions(self) -> None:
        questions = build_mock_test_questions(
            "ECA1010_Test",
            "source",
            source_id="SRC-0001",
            question_count=20,
            root=self.root,
        )
        normalized = [q["question"].strip().lower() for q in questions]
        self.assertEqual(len(normalized), len(set(normalized)))

    def test_build_unit_mock_test_questions(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Inflation",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        import_unit_synthesis(
            "ECA1010_Test",
            unit["unit_id"],
            synthesis_text=_valid_synthesis_text(),
            root=self.root,
        )
        generate_unit_study_pack(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        unit_dir = (
            self.course
            / "06_Study_Outputs"
            / "study_units"
            / unit["unit_id"]
        )
        (unit_dir / f"{unit['unit_id']}_unit_practice_quiz.md").write_text(
            QUIZ_TEXT, encoding="utf-8"
        )
        (unit_dir / f"{unit['unit_id']}_unit_active_recall.md").write_text(
            RECALL_TEXT, encoding="utf-8"
        )
        questions = build_mock_test_questions(
            "ECA1010_Test",
            "unit",
            unit_id=unit["unit_id"],
            question_count=10,
            root=self.root,
        )
        self.assertGreaterEqual(len(questions), 2)
        self.assertTrue(
            all(q["mock_question_id"].startswith("MT-UNIT-0001-Q") for q in questions)
        )
        self.assertEqual(questions[0]["unit_id"], "UNIT-0001")


class TestGenerateMockTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        _write_source_study_files(self.course)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_generate_mock_test_writes_md_json(self) -> None:
        with patch(
            "studyforge.study.mock_tests._timestamp_for_filename",
            return_value="20260604_120000",
        ), patch(
            "studyforge.study.mock_tests._timestamp_for_id",
            return_value="20260604-120000",
        ):
            result = generate_mock_test(
                "ECA1010_Test",
                "source",
                source_id="SRC-0001",
                question_count=5,
                root=self.root,
            )
        md_path = Path(result["markdown_path"])
        json_path = Path(result["json_path"])
        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())
        self.assertEqual(result["mock_test_id"], "MT-SRC-0001-20260604-120000")
        md_text = md_path.read_text(encoding="utf-8")
        self.assertIn("# Mock Test — SRC-0001", md_text)
        self.assertIn("## Questions", md_text)
        self.assertIn("## Answer / Reference Key", md_text)
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["question_count"], len(saved["questions"]))


class TestMockTestAttempts(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_record_attempt(self) -> None:
        result = record_mock_test_attempt(
            "ECA1010_Test",
            "MT-SRC-0001-20260604-120000",
            "source",
            "SRC-0001",
            None,
            14,
            20,
            notes="Missed formulas",
            root=self.root,
        )
        self.assertEqual(result["percent"], 70.0)
        log_path = get_mock_test_log_path(self.course)
        log = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(log["attempts"][0]["attempt_id"], "MT-ATTEMPT-0001")

    def test_invalid_score_rejected(self) -> None:
        with self.assertRaises(InvalidMockTestScoreError):
            record_mock_test_attempt(
                "ECA1010_Test",
                "MT-SRC-0001-20260604-120000",
                "source",
                "SRC-0001",
                None,
                25,
                20,
                root=self.root,
            )

    def test_weak_topics_create_weak_points(self) -> None:
        record_mock_test_attempt(
            "ECA1010_Test",
            "MT-UNIT-0001-20260604-120000",
            "unit",
            None,
            "UNIT-0001",
            10,
            20,
            weak_topics=["CPI formula", "Nominal vs real"],
            root=self.root,
        )
        weak_points = list_weak_points("ECA1010_Test", root=self.root)
        concepts = {wp["concept"] for wp in weak_points}
        self.assertIn("CPI formula", concepts)
        self.assertIn("Nominal vs real", concepts)

    def test_summarize_attempts(self) -> None:
        record_mock_test_attempt(
            "ECA1010_Test",
            "MT-SRC-0001-A",
            "source",
            "SRC-0001",
            None,
            10,
            20,
            root=self.root,
        )
        record_mock_test_attempt(
            "ECA1010_Test",
            "MT-SRC-0001-B",
            "source",
            "SRC-0001",
            None,
            15,
            20,
            root=self.root,
        )
        summary = summarize_mock_test_attempts("ECA1010_Test", root=self.root)
        self.assertEqual(summary["attempt_count"], 2)
        self.assertEqual(summary["average_percent"], 62.5)
        self.assertEqual(len(summary["recent_attempts"]), 2)


class TestMockTestNotReady(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_study_files_raises(self) -> None:
        with self.assertRaises(MockTestNotReadyError):
            build_mock_test_questions(
                "ECA1010_Test",
                "source",
                source_id="SRC-0001",
                root=self.root,
            )


class TestMockTestCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        _write_source_study_files(self.course)
        scripts_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "mock_test.py"
        )
        spec = importlib.util.spec_from_file_location("mock_test_cli", scripts_path)
        assert spec and spec.loader
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cli_generate_source_smoke(self) -> None:
        with patch(
            "studyforge.core.sources.find_project_root", return_value=self.root
        ):
            code = self.module.main(
                [
                    "--course",
                    "ECA1010_Test",
                    "--source-id",
                    "SRC-0001",
                    "--generate",
                    "--questions",
                    "5",
                ]
            )
        self.assertEqual(code, 0)

    def test_cli_summary_smoke(self) -> None:
        record_mock_test_attempt(
            "ECA1010_Test",
            "MT-SRC-0001-X",
            "source",
            "SRC-0001",
            None,
            8,
            10,
            root=self.root,
        )
        with patch(
            "studyforge.core.sources.find_project_root", return_value=self.root
        ):
            code = self.module.main(
                ["--course", "ECA1010_Test", "--summary"]
            )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
