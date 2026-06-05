"""Tests for Mock Test Detailed Grading v1."""

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
from studyforge.study.mock_test_grading import (  # noqa: E402
    InvalidMockTestGradeError,
    MockTestGradingAlreadyFinalizedError,
    MockTestQuestionNotFoundError,
    MockTestReviewExistsError,
    build_mock_test_review_markdown,
    export_mock_test_review,
    finalize_mock_test_grading,
    get_mock_test_grading_path,
    get_mock_test_review_path,
    get_ungraded_mock_test_hint,
    record_mock_question_result,
    summarize_mock_test_grading,
)
from studyforge.study.mock_tests import (  # noqa: E402
    MockTestNotFoundError,
    generate_mock_test,
    list_mock_tests,
    load_mock_test_json,
)
from studyforge.study.mistakes import list_mistakes  # noqa: E402
from studyforge.study.today_dashboard import get_today_dashboard  # noqa: E402
from studyforge.study.weak_points import list_weak_points  # noqa: E402

QUIZ_TEXT = """# Practice Quiz

1. What is inflation?
2. Define CPI.
"""

RECALL_TEXT = """# Active Recall

1. What is inflation?
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


def _write_source_study_files(course: Path) -> None:
    base = course / "06_Study_Outputs"
    (base / "quizzes").mkdir(parents=True, exist_ok=True)
    (base / "active_recall").mkdir(parents=True, exist_ok=True)
    (base / "quizzes" / "SRC-0001_practice_quiz.md").write_text(
        QUIZ_TEXT, encoding="utf-8"
    )
    (base / "active_recall" / "SRC-0001_active_recall.md").write_text(
        RECALL_TEXT, encoding="utf-8"
    )
    (base / "SRC-0001_study_pack_manifest.json").write_text(
        json.dumps({"quality": {"quality_status": "ok"}}),
        encoding="utf-8",
    )


def _generate_test(root: Path) -> dict:
    with patch(
        "studyforge.study.mock_tests._timestamp_for_filename",
        return_value="20260604_120000",
    ), patch(
        "studyforge.study.mock_tests._timestamp_for_id",
        return_value="20260604-120000",
    ):
        return generate_mock_test(
            "ECA1010_Test",
            "source",
            source_id="SRC-0001",
            question_count=5,
            include_flashcards=False,
            root=root,
        )


class TestMockTestLoading(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        _write_source_study_files(self.course)
        self.generated = _generate_test(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_mock_tests(self) -> None:
        tests = list_mock_tests("ECA1010_Test", root=self.root)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0]["mock_test_id"], self.generated["mock_test_id"])
        self.assertEqual(tests[0]["scope"], "source")
        self.assertGreater(tests[0]["question_count"], 0)

    def test_load_mock_test_json(self) -> None:
        data = load_mock_test_json(
            "ECA1010_Test", self.generated["mock_test_id"], root=self.root
        )
        self.assertEqual(data["mock_test_id"], self.generated["mock_test_id"])
        self.assertGreater(len(data["questions"]), 0)

    def test_load_missing_raises(self) -> None:
        with self.assertRaises(MockTestNotFoundError):
            load_mock_test_json("ECA1010_Test", "MT-MISSING", root=self.root)


class TestMockTestGrading(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        _write_source_study_files(self.course)
        self.generated = _generate_test(self.root)
        self.mock_test_id = self.generated["mock_test_id"]
        self.question_id = self.generated["questions"][0]["mock_question_id"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_record_question_result(self) -> None:
        result = record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            self.question_id,
            "correct",
            user_answer="Rising prices",
            root=self.root,
        )
        self.assertEqual(result["grade"], "correct")
        self.assertFalse(result["updated"])
        grading_path = get_mock_test_grading_path(self.course, self.mock_test_id)
        self.assertTrue(grading_path.is_file())

    def test_update_existing_question_result(self) -> None:
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            self.question_id,
            "wrong",
            root=self.root,
        )
        result = record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            self.question_id,
            "partial",
            user_answer="Maybe inflation",
            root=self.root,
        )
        self.assertTrue(result["updated"])
        summary = summarize_mock_test_grading(
            "ECA1010_Test", self.mock_test_id, root=self.root
        )
        self.assertEqual(summary["graded_count"], 1)
        self.assertEqual(summary["partial"], 1)

    def test_invalid_grade_rejected(self) -> None:
        with self.assertRaises(InvalidMockTestGradeError):
            record_mock_question_result(
                "ECA1010_Test",
                self.mock_test_id,
                self.question_id,
                "bogus",
                root=self.root,
            )

    def test_invalid_question_id_rejected(self) -> None:
        with self.assertRaises(MockTestQuestionNotFoundError):
            record_mock_question_result(
                "ECA1010_Test",
                self.mock_test_id,
                "MT-SRC-0001-Q999",
                "wrong",
                root=self.root,
            )

    def test_summarize_partial_scoring(self) -> None:
        questions = self.generated["questions"][:3]
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            questions[0]["mock_question_id"],
            "correct",
            root=self.root,
        )
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            questions[1]["mock_question_id"],
            "partial",
            root=self.root,
        )
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            questions[2]["mock_question_id"],
            "wrong",
            root=self.root,
        )
        summary = summarize_mock_test_grading(
            "ECA1010_Test", self.mock_test_id, root=self.root
        )
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["partial"], 1)
        self.assertEqual(summary["wrong"], 1)
        self.assertEqual(summary["score_correct_equivalent"], 1.5)
        self.assertEqual(summary["score_total"], 3)
        self.assertEqual(summary["percent"], 50.0)
        self.assertEqual(len(summary["missed_questions"]), 2)

    def test_create_weak_point_from_wrong(self) -> None:
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            self.question_id,
            "wrong",
            user_answer="idk",
            create_weak_point=True,
            weak_point_concept="Inflation basics",
            root=self.root,
        )
        weak_points = list_weak_points("ECA1010_Test", root=self.root)
        concepts = {wp["concept"] for wp in weak_points}
        self.assertIn("Inflation basics", concepts)

    def test_finalize_records_mock_attempt(self) -> None:
        for question in self.generated["questions"]:
            record_mock_question_result(
                "ECA1010_Test",
                self.mock_test_id,
                question["mock_question_id"],
                "correct",
                root=self.root,
            )
        result = finalize_mock_test_grading(
            "ECA1010_Test",
            self.mock_test_id,
            notes="First graded mock",
            root=self.root,
        )
        self.assertEqual(result["score_correct"], len(self.generated["questions"]))
        self.assertIn("attempt_id", result)
        grading_path = get_mock_test_grading_path(self.course, self.mock_test_id)
        grading = json.loads(grading_path.read_text(encoding="utf-8"))
        self.assertTrue(grading["finalized"])
        self.assertIn("finalized_attempt_id", grading)

        with self.assertRaises(MockTestGradingAlreadyFinalizedError):
            finalize_mock_test_grading(
                "ECA1010_Test", self.mock_test_id, root=self.root
            )

    def test_finalize_preserves_partial_credit_percent(self) -> None:
        questions = self.generated["questions"][:2]
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            questions[0]["mock_question_id"],
            "correct",
            root=self.root,
        )
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            questions[1]["mock_question_id"],
            "partial",
            root=self.root,
        )

        result = finalize_mock_test_grading(
            "ECA1010_Test",
            self.mock_test_id,
            root=self.root,
        )

        self.assertEqual(result["score_correct"], 1.5)
        self.assertEqual(result["score_total"], 2)
        self.assertEqual(result["percent"], 75.0)

    def test_export_review_writes_markdown(self) -> None:
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            self.question_id,
            "wrong",
            user_answer="no idea",
            notes="Forgot formula",
            root=self.root,
        )
        result = export_mock_test_review(
            "ECA1010_Test", self.mock_test_id, root=self.root
        )
        review_path = Path(result["review_path"])
        self.assertTrue(review_path.is_file())
        text = review_path.read_text(encoding="utf-8")
        self.assertIn("# Mock Test Review", text)
        self.assertIn("## Score Summary", text)
        self.assertIn(self.question_id, text)

        with self.assertRaises(MockTestReviewExistsError):
            export_mock_test_review(
                "ECA1010_Test", self.mock_test_id, root=self.root
            )

    def test_build_review_markdown_includes_blockers(self) -> None:
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            self.question_id,
            "partial",
            root=self.root,
        )
        md = build_mock_test_review_markdown(
            "ECA1010_Test", self.mock_test_id, root=self.root
        )
        self.assertIn("## Missed / Partial Questions", md)
        self.assertIn("Recommended Review Actions", md)

    def test_ungraded_hint(self) -> None:
        record_mock_question_result(
            "ECA1010_Test",
            self.mock_test_id,
            self.question_id,
            "correct",
            root=self.root,
        )
        hint = get_ungraded_mock_test_hint("ECA1010_Test", root=self.root)
        self.assertIsNotNone(hint)
        self.assertEqual(hint["key"], "finish_mock_grading")

    def test_today_shows_ungraded_hint(self) -> None:
        hint = get_ungraded_mock_test_hint("ECA1010_Test", root=self.root)
        self.assertIsNotNone(hint)
        dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        keys = [action["key"] for action in dashboard["recommended_actions"]]
        self.assertIn("finish_mock_grading", keys)


class TestGradeMockTestCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        _write_source_study_files(self.course)
        self.generated = _generate_test(self.root)
        scripts_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "grade_mock_test.py"
        )
        spec = importlib.util.spec_from_file_location("grade_mock_test_cli", scripts_path)
        assert spec and spec.loader
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @patch("studyforge.core.sources.find_project_root")
    def test_cli_list_smoke(self, mock_root) -> None:
        mock_root.return_value = self.root
        code = self.module.main(["--course", "ECA1010_Test", "--list"])
        self.assertEqual(code, 0)

    @patch("studyforge.core.sources.find_project_root")
    def test_cli_questions_and_summary_smoke(self, mock_root) -> None:
        mock_root.return_value = self.root
        mock_id = self.generated["mock_test_id"]
        code = self.module.main(
            ["--course", "ECA1010_Test", "--mock-test-id", mock_id, "--questions"]
        )
        self.assertEqual(code, 0)
        qid = self.generated["questions"][0]["mock_question_id"]
        code = self.module.main(
            [
                "--course",
                "ECA1010_Test",
                "--mock-test-id",
                mock_id,
                "--grade-question",
                qid,
                "--grade",
                "wrong",
                "--answer",
                "idk",
            ]
        )
        self.assertEqual(code, 0)
        code = self.module.main(
            ["--course", "ECA1010_Test", "--mock-test-id", mock_id, "--summary"]
        )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
