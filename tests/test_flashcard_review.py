"""Tests for Flashcard Review Mode v1."""

from __future__ import annotations

import csv
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
    InvalidFlashcardGradeError,
    collect_flashcards_needing_review,
    collect_unreviewed_flashcards,
    get_flashcard_review_log_path,
    load_flashcard_review_log,
    load_flashcards_for_source,
    record_flashcard_review,
    save_flashcard_review_log,
    summarize_flashcard_reviews,
)
from studyforge.study.flashcards import flashcards_to_csv  # noqa: E402
from studyforge.study.review_planner import (  # noqa: E402
    build_review_plan_markdown,
    generate_review_plan,
    prioritize_review_items,
)
from studyforge.study.study_session import (  # noqa: E402
    build_study_session_items,
    record_session_item_result,
    start_study_session,
)
from studyforge.study.weak_points import list_weak_points  # noqa: E402

SAMPLE_CARDS = [
    {
        "front": "What is CPI?",
        "back": "Consumer Price Index",
        "source_id": "SRC-0001",
        "source_title": "Book",
        "section": "Must-Memorize List",
        "tags": ["SRC-0001", "must_memorize"],
    },
    {
        "front": "What is GDP?",
        "back": "Gross Domestic Product",
        "source_id": "SRC-0001",
        "source_title": "Book",
        "section": "Must-Memorize List",
        "tags": ["SRC-0001", "must_memorize"],
    },
]


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    csv_path = course / "06_Study_Outputs" / "flashcards" / "SRC-0001_flashcards.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    cards_with_ids = [
        {**SAMPLE_CARDS[0], "card_id": "FC-SRC-0001-0001"},
        {**SAMPLE_CARDS[1], "card_id": "FC-SRC-0001-0002"},
    ]
    rows = []
    for card in cards_with_ids:
        rows.append(
            {
                "front": card["front"],
                "back": card["back"],
                "source_id": card["source_id"],
                "source_title": card["source_title"],
                "section": card["section"],
                "tags": ", ".join(card["tags"]),
            }
        )
    csv_path.write_text(
        flashcards_to_csv(
            [
                {
                    "front": r["front"],
                    "back": r["back"],
                    "source_id": r["source_id"],
                    "source_title": r["source_title"],
                    "section": r["section"],
                    "tags": r["tags"].split(", "),
                }
                for r in rows
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


class TestFlashcardReview(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_flashcards_from_csv(self) -> None:
        cards = load_flashcards_for_source("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["card_id"], "FC-SRC-0001-0001")
        self.assertEqual(cards[0]["front"], "What is CPI?")

    def test_deterministic_card_ids_without_csv_column(self) -> None:
        csv_path = self.course / "06_Study_Outputs" / "flashcards" / "SRC-0001_flashcards.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(
                ["front", "back", "source_id", "source_title", "section", "tags"]
            )
            writer.writerow(
                ["Q1", "A1", "SRC-0001", "Book", "Section", "SRC-0001, tag"]
            )
        cards = load_flashcards_for_source("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(cards[0]["card_id"], "FC-SRC-0001-0001")

    def test_record_review_creates_log(self) -> None:
        result = record_flashcard_review(
            "ECA1010_Test",
            "SRC-0001",
            "FC-SRC-0001-0001",
            "What is CPI?",
            "Consumer Price Index",
            "good",
            root=self.root,
        )
        self.assertEqual(result["grade"], "good")
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
        log = load_flashcard_review_log(log_path, "SRC-0001")
        self.assertEqual(len(log["reviews"]), 1)
        self.assertEqual(log["reviews"][0]["review_id"], "FC-REVIEW-0001")

    def test_invalid_grade_rejected(self) -> None:
        with self.assertRaises(InvalidFlashcardGradeError):
            record_flashcard_review(
                "ECA1010_Test",
                "SRC-0001",
                "FC-SRC-0001-0001",
                "Q",
                "A",
                "bogus",
                root=self.root,
            )

    def test_summarize_counts_grades(self) -> None:
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
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
                        "grade": "easy",
                        "notes": "",
                        "date_reviewed": "2026-06-01T10:00:00",
                    },
                    {
                        "review_id": "FC-REVIEW-0002",
                        "source_id": "SRC-0001",
                        "card_id": "FC-SRC-0001-0002",
                        "front": "Q2",
                        "back": "A2",
                        "grade": "hard",
                        "notes": "",
                        "date_reviewed": "2026-06-02T10:00:00",
                    },
                ],
            },
        )
        summary = summarize_flashcard_reviews("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(summary["review_count"], 2)
        self.assertEqual(summary["easy"], 1)
        self.assertEqual(summary["hard"], 1)
        self.assertEqual(summary["needs_review_count"], 1)

    def test_latest_easy_excludes_from_needs_review(self) -> None:
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
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
                        "date_reviewed": "2026-06-01T10:00:00",
                    },
                    {
                        "review_id": "FC-REVIEW-0002",
                        "source_id": "SRC-0001",
                        "card_id": "FC-SRC-0001-0001",
                        "front": "Q",
                        "back": "A",
                        "grade": "easy",
                        "notes": "",
                        "date_reviewed": "2026-06-03T10:00:00",
                    },
                ],
            },
        )
        items = collect_flashcards_needing_review("ECA1010_Test", root=self.root)
        self.assertEqual(len(items), 0)

    def test_latest_hard_includes_needs_review(self) -> None:
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
        save_flashcard_review_log(
            log_path,
            {
                "source_id": "SRC-0001",
                "reviews": [
                    {
                        "review_id": "FC-REVIEW-0001",
                        "source_id": "SRC-0001",
                        "card_id": "FC-SRC-0001-0001",
                        "front": "What is CPI?",
                        "back": "CPI",
                        "grade": "forgot",
                        "notes": "oops",
                        "date_reviewed": "2026-06-04T10:00:00",
                    }
                ],
            },
        )
        items = collect_flashcards_needing_review("ECA1010_Test", root=self.root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["grade"], "forgot")

    def test_create_weak_point_on_hard(self) -> None:
        record_flashcard_review(
            "ECA1010_Test",
            "SRC-0001",
            "FC-SRC-0001-0001",
            "What is CPI?",
            "CPI",
            "hard",
            create_weak_point=True,
            weak_point_concept="CPI formula",
            root=self.root,
        )
        weak = list_weak_points("ECA1010_Test", root=self.root)
        self.assertEqual(len(weak), 1)
        self.assertEqual(weak[0]["concept"], "CPI formula")

    def test_review_planner_includes_flashcards(self) -> None:
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
        save_flashcard_review_log(
            log_path,
            {
                "source_id": "SRC-0001",
                "reviews": [
                    {
                        "review_id": "FC-REVIEW-0001",
                        "source_id": "SRC-0001",
                        "card_id": "FC-SRC-0001-0001",
                        "front": "Forgot card",
                        "back": "Answer",
                        "grade": "forgot",
                        "notes": "",
                        "date_reviewed": "2026-06-04T10:00:00",
                    }
                ],
            },
        )
        items = prioritize_review_items([], [], [], collect_flashcards_needing_review("ECA1010_Test", root=self.root))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "flashcard")

        text = build_review_plan_markdown(
            "ECA1010_Test",
            [],
            [],
            [],
            collect_flashcards_needing_review("ECA1010_Test", root=self.root),
            items,
            "2026-06-04",
        )
        self.assertIn("## Flashcards Due", text)
        self.assertIn("FC-SRC-0001-0001", text)

        summary = generate_review_plan(
            "ECA1010_Test", date_str="2026-06-04", root=self.root
        )
        self.assertEqual(summary["flashcards_due_count"], 1)

    def test_study_session_includes_flashcards_needing_review(self) -> None:
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
        save_flashcard_review_log(
            log_path,
            {
                "source_id": "SRC-0001",
                "reviews": [
                    {
                        "review_id": "FC-REVIEW-0001",
                        "source_id": "SRC-0001",
                        "card_id": "FC-SRC-0001-0001",
                        "front": "Hard card",
                        "back": "Answer",
                        "grade": "hard",
                        "notes": "",
                        "date_reviewed": "2026-06-04T10:00:00",
                    }
                ],
            },
        )
        items = build_study_session_items("ECA1010_Test", root=self.root, limit=5)
        types = {item["type"] for item in items}
        self.assertIn("flashcard", types)

    def test_study_session_fills_unreviewed_flashcards(self) -> None:
        items = build_study_session_items("ECA1010_Test", root=self.root, limit=5)
        unreviewed = [item for item in items if item["type"] == "flashcard_unreviewed"]
        self.assertEqual(len(unreviewed), 2)

    def test_study_session_record_flashcard_review(self) -> None:
        started = start_study_session("ECA1010_Test", limit=3, root=self.root)
        from studyforge.study.study_session import get_study_session_log_path

        session = json.loads(
            get_study_session_log_path(self.course, started["session_id"]).read_text(
                encoding="utf-8"
            )
        )
        item = session["items"][0]
        self.assertEqual(item["type"], "flashcard_unreviewed")
        record_session_item_result(
            "ECA1010_Test",
            started["session_id"],
            item["session_item_id"],
            "good",
            notes="Got it",
            root=self.root,
        )
        log = load_flashcard_review_log(
            get_flashcard_review_log_path(self.course, "SRC-0001"), "SRC-0001"
        )
        self.assertEqual(len(log["reviews"]), 1)
        self.assertEqual(log["reviews"][0]["grade"], "good")

    @patch("scripts.flashcards_review.load_flashcards_for_source")
    @patch("scripts.flashcards_review.summarize_flashcard_reviews")
    def test_cli_list(self, mock_summary, mock_load) -> None:
        from scripts import flashcards_review as cli_module

        mock_load.return_value = [{"card_id": "FC-SRC-0001-0001", "front": "Q"}]
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--source-id", "SRC-0001", "--list"]
        )
        self.assertEqual(code, 0)
        mock_load.assert_called_once()

    @patch("scripts.flashcards_review.summarize_flashcard_reviews")
    def test_cli_summary(self, mock_summary) -> None:
        from scripts import flashcards_review as cli_module

        mock_summary.return_value = {
            "source_id": "SRC-0001",
            "review_count": 2,
            "easy": 1,
            "good": 0,
            "hard": 1,
            "forgot": 0,
            "skipped": 0,
            "needs_review_count": 1,
            "recent_reviews": [],
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--source-id", "SRC-0001", "--summary"]
        )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
