"""Tests for Review Session Planner v1."""

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
from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.active_recall import (  # noqa: E402
    get_active_recall_log_path,
    save_active_recall_log,
)
from studyforge.study.mistakes import add_mistake, update_mistake_status  # noqa: E402
from studyforge.study.review_planner import (  # noqa: E402
    ReviewPlanExistsError,
    build_review_plan_markdown,
    collect_active_recall_needs_review,
    collect_open_mistakes,
    collect_open_weak_points,
    generate_review_plan,
    get_review_plan_json_path,
    get_review_plan_path,
    prioritize_review_items,
)
from studyforge.study.weak_points import add_weak_point  # noqa: E402


class TestReviewPlanner(unittest.TestCase):
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
        save_source_registry(
            self.course,
            {"sources": [{"id": "SRC-0001", "title": "Book", "status": "added"}]},
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_collect_open_mistakes_excludes_mastered(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q1", "A1", root=self.root)
        add_mistake("ECA1010_Test", "SRC-0001", "Q2", "A2", root=self.root)
        update_mistake_status(
            "ECA1010_Test", "MISTAKE-0002", "mastered", root=self.root
        )
        open_items = collect_open_mistakes("ECA1010_Test", root=self.root)
        self.assertEqual(len(open_items), 1)
        self.assertEqual(open_items[0]["mistake_id"], "MISTAKE-0001")

    def test_collect_open_weak_points_excludes_mastered(self) -> None:
        add_weak_point("ECA1010_Test", "SRC-0001", "Concept A", root=self.root)
        from studyforge.study.weak_points import update_weak_point

        add_weak_point("ECA1010_Test", "SRC-0001", "Concept B", root=self.root)
        update_weak_point(
            "ECA1010_Test", "WEAK-0002", status="mastered", root=self.root
        )
        open_items = collect_open_weak_points("ECA1010_Test", root=self.root)
        self.assertEqual(len(open_items), 1)

    def test_recall_latest_correct_excludes_question(self) -> None:
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
                        "question": "What is inflation?",
                        "user_answer": "bad",
                        "grade": "wrong",
                        "notes": "",
                        "date_answered": "2026-01-01T10:00:00",
                    },
                    {
                        "attempt_id": "AR-ATTEMPT-0002",
                        "source_id": "SRC-0001",
                        "question_id": "AR-SRC-0001-Q001",
                        "question": "What is inflation?",
                        "user_answer": "good",
                        "grade": "correct",
                        "notes": "",
                        "date_answered": "2026-01-02T10:00:00",
                    },
                ],
            },
        )
        items = collect_active_recall_needs_review("ECA1010_Test", root=self.root)
        self.assertEqual(len(items), 0)

    def test_recall_latest_wrong_includes_question(self) -> None:
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
                        "question_id": "AR-SRC-0001-Q002",
                        "question": "CPI?",
                        "user_answer": "ok",
                        "grade": "partial",
                        "notes": "",
                        "date_answered": "2026-01-01T10:00:00",
                    },
                    {
                        "attempt_id": "AR-ATTEMPT-0002",
                        "source_id": "SRC-0001",
                        "question_id": "AR-SRC-0001-Q002",
                        "question": "CPI?",
                        "user_answer": "bad",
                        "grade": "wrong",
                        "notes": "",
                        "date_answered": "2026-01-03T10:00:00",
                    },
                ],
            },
        )
        items = collect_active_recall_needs_review("ECA1010_Test", root=self.root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["grade"], "wrong")

    def test_priority_ordering(self) -> None:
        recall_wrong = [
            {
                "question_id": "AR-SRC-0001-Q001",
                "source_id": "SRC-0001",
                "question": "Wrong Q",
                "user_answer": "x",
                "grade": "wrong",
                "attempt_id": "AR-ATTEMPT-0001",
                "notes": "",
            }
        ]
        recall_partial = [
            {
                "question_id": "AR-SRC-0001-Q002",
                "source_id": "SRC-0001",
                "question": "Partial Q",
                "user_answer": "y",
                "grade": "partial",
                "attempt_id": "AR-ATTEMPT-0002",
                "notes": "",
            }
        ]
        mistakes = [
            {
                "mistake_id": "MISTAKE-0001",
                "source_id": "SRC-0001",
                "question": "Mistake new",
                "user_answer": "a",
                "status": "new",
            },
            {
                "mistake_id": "MISTAKE-0002",
                "source_id": "SRC-0001",
                "question": "Mistake reviewed",
                "user_answer": "b",
                "status": "reviewed_once",
            },
        ]
        weak_points = [
            {
                "weak_point_id": "WEAK-0001",
                "source_id": "SRC-0001",
                "concept": "Low conf",
                "confidence_level": 1,
                "status": "new",
            },
            {
                "weak_point_id": "WEAK-0002",
                "source_id": "SRC-0001",
                "concept": "Mid conf",
                "confidence_level": 3,
                "status": "new",
            },
        ]
        items = prioritize_review_items(
            mistakes, weak_points, recall_wrong + recall_partial, limit=10
        )
        types_order = [item["type"] for item in items]
        self.assertEqual(types_order[0], "active_recall")
        self.assertEqual(items[0].get("grade"), "wrong")
        self.assertIn("mistake", types_order[1:3])
        self.assertIn("weak_point", types_order)

    def test_review_plan_markdown_and_json(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        summary = generate_review_plan(
            "ECA1010_Test",
            date_str="2026-06-04",
            limit=5,
            root=self.root,
        )
        md_path = Path(summary["markdown_path"])
        json_path = Path(summary["json_path"])
        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())
        text = md_path.read_text(encoding="utf-8")
        self.assertIn("# Review Plan — 2026-06-04", text)
        self.assertIn("Today's Top Priorities", text)
        self.assertIn("End of Session Checklist", text)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["date"], "2026-06-04")
        self.assertEqual(data["mistake_count"], 1)

    def test_overwrite_refusal(self) -> None:
        generate_review_plan(
            "ECA1010_Test", date_str="2026-06-05", root=self.root
        )
        with self.assertRaises(ReviewPlanExistsError):
            generate_review_plan(
                "ECA1010_Test", date_str="2026-06-05", root=self.root
            )

    def test_overwrite_allowed(self) -> None:
        first = generate_review_plan(
            "ECA1010_Test", date_str="2026-06-06", root=self.root
        )
        second = generate_review_plan(
            "ECA1010_Test",
            date_str="2026-06-06",
            overwrite=True,
            root=self.root,
        )
        self.assertEqual(first["markdown_path"], second["markdown_path"])

    def test_build_markdown_empty(self) -> None:
        text = build_review_plan_markdown(
            "ECA1010_Test", [], [], [], [], [], "2026-06-01"
        )
        self.assertIn("No priority items", text)

    def test_pipeline_review_plan_hint(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(
            any(
                "review plan" in w.lower()
                for w in status["warnings"]
            )
        )

    def test_cli_style_generation(self) -> None:
        """Smoke test matching scripts/review_plan.py entry point."""
        summary = generate_review_plan("ECA1010_Test", limit=3, root=self.root)
        self.assertEqual(
            get_review_plan_path(self.course).name,
            Path(summary["markdown_path"]).name,
        )


if __name__ == "__main__":
    unittest.main()
