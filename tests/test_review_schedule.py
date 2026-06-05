"""Tests for lightweight flashcard due scheduling."""

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
    collect_due_flashcards,
    get_flashcard_review_log_path,
    record_flashcard_review,
    save_flashcard_review_log,
    summarize_flashcard_reviews,
)
from studyforge.study.flashcards import flashcards_to_csv  # noqa: E402
from studyforge.study.review_planner import generate_review_plan  # noqa: E402
from studyforge.study.review_schedule import (  # noqa: E402
    add_days,
    build_review_date_reviewed,
    is_due,
    latest_review_by_card,
    next_due_date_for_flashcard_grade,
    today_date_str,
)
from studyforge.study.study_session import build_study_session_items  # noqa: E402


class TestReviewSchedule(unittest.TestCase):
    def test_next_due_dates_by_grade(self) -> None:
        base = "2026-06-01"
        self.assertEqual(next_due_date_for_flashcard_grade("forgot", base), "2026-06-02")
        self.assertEqual(next_due_date_for_flashcard_grade("skipped", base), "2026-06-02")
        self.assertEqual(next_due_date_for_flashcard_grade("hard", base), "2026-06-03")
        self.assertEqual(next_due_date_for_flashcard_grade("good", base), "2026-06-05")
        self.assertEqual(next_due_date_for_flashcard_grade("easy", base), "2026-06-08")

    def test_add_days(self) -> None:
        self.assertEqual(add_days("2026-06-01", 7), "2026-06-08")

    def test_is_due(self) -> None:
        self.assertTrue(is_due("2026-06-01", "2026-06-04"))
        self.assertTrue(is_due("2026-06-04", "2026-06-04"))
        self.assertFalse(is_due("2026-06-10", "2026-06-04"))

    def test_latest_review_by_card(self) -> None:
        reviews = [
            {
                "card_id": "FC-SRC-0001-0001",
                "grade": "hard",
                "date_reviewed": "2026-06-01T10:00:00",
            },
            {
                "card_id": "FC-SRC-0001-0001",
                "grade": "easy",
                "date_reviewed": "2026-06-03T10:00:00",
            },
        ]
        latest = latest_review_by_card(reviews)
        self.assertEqual(latest["FC-SRC-0001-0001"]["grade"], "easy")

    def test_build_review_date_reviewed_explicit_day(self) -> None:
        date_reviewed, reviewed_day = build_review_date_reviewed(
            "2026-06-04",
            "2026-06-05T00:00:00",
        )
        self.assertEqual(reviewed_day, "2026-06-04")
        self.assertEqual(date_reviewed, "2026-06-04T12:00:00")

    def test_build_review_date_reviewed_defaults_to_now(self) -> None:
        date_reviewed, reviewed_day = build_review_date_reviewed(
            None,
            "2026-06-05T08:30:00-04:00",
        )
        self.assertEqual(date_reviewed, "2026-06-05T08:30:00-04:00")
        self.assertEqual(reviewed_day, "2026-06-05")

    def test_record_review_adds_due_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            result = record_flashcard_review(
                "ECA1010_Test",
                "SRC-0001",
                "FC-SRC-0001-0001",
                "Q",
                "A",
                "hard",
                reviewed_date="2026-06-04",
                root=root,
            )
            self.assertEqual(result["due_date"], "2026-06-06")
            log_path = get_flashcard_review_log_path(course, "SRC-0001")
            data = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(data["reviews"][0]["due_date"], "2026-06-06")
            self.assertEqual(data["reviews"][0]["date_reviewed"], "2026-06-04T12:00:00")

    def test_summarize_includes_due_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            log_path = get_flashcard_review_log_path(course, "SRC-0001")
            save_flashcard_review_log(
                log_path,
                {
                    "source_id": "SRC-0001",
                    "reviews": [
                        {
                            "review_id": "FC-REVIEW-0001",
                            "source_id": "SRC-0001",
                            "card_id": "FC-SRC-0001-0001",
                            "front": "Q1",
                            "back": "A1",
                            "grade": "hard",
                            "notes": "",
                            "date_reviewed": "2026-06-04T10:00:00",
                            "due_date": "2026-06-04",
                        },
                        {
                            "review_id": "FC-REVIEW-0002",
                            "source_id": "SRC-0001",
                            "card_id": "FC-SRC-0001-0002",
                            "front": "Q2",
                            "back": "A2",
                            "grade": "easy",
                            "notes": "",
                            "date_reviewed": "2026-06-04T10:00:00",
                            "due_date": "2026-06-11",
                        },
                    ],
                },
            )
            with patch(
                "studyforge.study.flashcard_review.today_date_str",
                return_value="2026-06-04",
            ):
                summary = summarize_flashcard_reviews(
                    "ECA1010_Test", "SRC-0001", root=root
                )
            self.assertEqual(summary["due_count"], 1)
            self.assertEqual(summary["due_today_count"], 1)
            self.assertEqual(summary["future_due_count"], 1)

    def test_collect_due_includes_hard_without_due_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            log_path = get_flashcard_review_log_path(course, "SRC-0001")
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
                "studyforge.study.flashcard_review.today_date_str",
                return_value="2026-06-04",
            ):
                due = collect_due_flashcards("ECA1010_Test", root=root)
            self.assertEqual(len(due), 1)

    def test_collect_due_excludes_non_due_easy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            log_path = get_flashcard_review_log_path(course, "SRC-0001")
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
                            "grade": "easy",
                            "notes": "",
                            "date_reviewed": "2026-06-04T10:00:00",
                            "due_date": "2026-06-11",
                        }
                    ],
                },
            )
            with patch(
                "studyforge.study.flashcard_review.today_date_str",
                return_value="2026-06-04",
            ):
                due = collect_due_flashcards("ECA1010_Test", root=root)
            self.assertEqual(len(due), 0)

    def test_review_planner_includes_due_flashcards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            log_path = get_flashcard_review_log_path(course, "SRC-0001")
            save_flashcard_review_log(
                log_path,
                {
                    "source_id": "SRC-0001",
                    "reviews": [
                        {
                            "review_id": "FC-REVIEW-0001",
                            "source_id": "SRC-0001",
                            "card_id": "FC-SRC-0001-0001",
                            "front": "Forgot",
                            "back": "A",
                            "grade": "forgot",
                            "notes": "",
                            "date_reviewed": "2026-06-04T10:00:00",
                            "due_date": "2026-06-04",
                        }
                    ],
                },
            )
            with patch(
                "studyforge.study.flashcard_review.today_date_str",
                return_value="2026-06-04",
            ):
                summary = generate_review_plan(
                    "ECA1010_Test", date_str="2026-06-04", root=root
                )
            self.assertEqual(summary["flashcards_due_count"], 1)
            text = Path(summary["markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("## Flashcards Due", text)

    def test_study_session_includes_due_flashcards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            log_path = get_flashcard_review_log_path(course, "SRC-0001")
            save_flashcard_review_log(
                log_path,
                {
                    "source_id": "SRC-0001",
                    "reviews": [
                        {
                            "review_id": "FC-REVIEW-0001",
                            "source_id": "SRC-0001",
                            "card_id": "FC-SRC-0001-0001",
                            "front": "Hard",
                            "back": "A",
                            "grade": "hard",
                            "notes": "",
                            "date_reviewed": "2026-06-04T10:00:00",
                        }
                    ],
                },
            )
            with patch(
                "studyforge.study.flashcard_review.today_date_str",
                return_value="2026-06-04",
            ):
                items = build_study_session_items("ECA1010_Test", root=root, limit=5)
            self.assertIn("flashcard", {item["type"] for item in items})

    @patch("scripts.flashcards_review.collect_due_flashcards")
    def test_cli_due(self, mock_due) -> None:
        from scripts import flashcards_review as cli_module

        mock_due.return_value = [
            {
                "card_id": "FC-SRC-0001-0001",
                "source_id": "SRC-0001",
                "front": "Q",
                "latest_grade": "hard",
                "due_date": "2026-06-04",
            }
        ]
        code = cli_module.main(["--course", "ECA1010_Test", "--due"])
        self.assertEqual(code, 0)
        mock_due.assert_called_once()

    def _setup_course(self, root: Path) -> Path:
        courses = root / "courses"
        course = courses / "ECA1010_Test"
        (course / "07_My_Work").mkdir(parents=True)
        (course / "08_App_Data").mkdir(parents=True)
        csv_path = course / "06_Study_Outputs" / "flashcards" / "SRC-0001_flashcards.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(
            flashcards_to_csv(
                [
                    {
                        "front": "Q1",
                        "back": "A1",
                        "source_id": "SRC-0001",
                        "source_title": "Book",
                        "section": "Test",
                        "tags": ["SRC-0001"],
                    }
                ]
            ),
            encoding="utf-8",
        )
        save_source_registry(
            course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Book",
                        "status": "study_pack_generated",
                        "flashcards_csv_path": str(csv_path.resolve()),
                    }
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


if __name__ == "__main__":
    unittest.main()
