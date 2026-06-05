#!/usr/bin/env python3
"""
Unit-Level Review v1 — list and record unit active recall and flashcards.

Examples:
    python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --list-recall
    python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --record-recall \\
        --question-id UAR-UNIT-0001-Q001 --answer "My answer" --grade partial
    python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --list-flashcards
    python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --record-flashcard \\
        --card-id UFC-UNIT-0001-0001 --grade hard
    python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.active_recall import InvalidGradeError  # noqa: E402
from studyforge.study.flashcard_review import InvalidFlashcardGradeError  # noqa: E402
from studyforge.study.study_units import StudyUnitNotFoundError  # noqa: E402
from studyforge.study.unit_review import (  # noqa: E402
    UnitActiveRecallNotReadyError,
    UnitFlashcardsNotReadyError,
    collect_due_unit_flashcards_for_unit,
    collect_unit_active_recall_needs_review_for_unit,
    load_unit_active_recall_questions,
    load_unit_flashcards,
    record_unit_active_recall_attempt,
    record_unit_flashcard_review,
    summarize_unit_active_recall,
    summarize_unit_flashcard_reviews,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Practice unit-level active recall and flashcards (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--list-recall", action="store_true", help="List unit recall questions.")
    parser.add_argument("--list-flashcards", action="store_true", help="List unit flashcards.")
    parser.add_argument("--summary", action="store_true", help="Print unit review summary.")
    parser.add_argument("--record-recall", action="store_true", help="Record one recall attempt.")
    parser.add_argument("--record-flashcard", action="store_true", help="Record one flashcard review.")
    parser.add_argument("--question-id", help="Question ID for --record-recall.")
    parser.add_argument("--card-id", help="Card ID for --record-flashcard.")
    parser.add_argument("--question", help="Question text (optional if ID matches list).")
    parser.add_argument("--front", help="Flashcard front (optional if ID matches list).")
    parser.add_argument("--back", help="Flashcard back (optional if ID matches list).")
    parser.add_argument("--answer", default="", help="Your answer text for recall.")
    parser.add_argument("--grade", help="Recall: correct/partial/wrong/skipped; flashcard: easy/good/hard/forgot/skipped.")
    parser.add_argument("--notes", default="", help="Optional notes.")
    parser.add_argument(
        "--create-mistake",
        action="store_true",
        help="For wrong/partial/skipped recall: also add a mistakes log entry.",
    )
    parser.add_argument(
        "--create-weak-point",
        action="store_true",
        help="Also add a weak point entry when appropriate.",
    )
    parser.add_argument(
        "--weak-point-concept",
        default="",
        help="Concept label when using --create-weak-point.",
    )
    return parser


def _resolve_question_text(
    course_name: str, unit_id: str, question_id: str, question: str | None
) -> str:
    if question and question.strip():
        return question.strip()
    for entry in load_unit_active_recall_questions(course_name, unit_id):
        if entry.get("question_id") == question_id:
            return str(entry.get("question", ""))
    return ""


def _resolve_flashcard(
    course_name: str, unit_id: str, card_id: str, front: str | None, back: str | None
) -> tuple[str, str]:
    resolved_front = (front or "").strip()
    resolved_back = (back or "").strip()
    if resolved_front and resolved_back:
        return resolved_front, resolved_back
    for card in load_unit_flashcards(course_name, unit_id):
        if card.get("card_id") == card_id:
            return (
                resolved_front or str(card.get("front", "")),
                resolved_back or str(card.get("back", "")),
            )
    return resolved_front, resolved_back


def _print_recall_summary(course_name: str, unit_id: str) -> None:
    summary = summarize_unit_active_recall(course_name, unit_id)
    print("Unit active recall summary.\n")
    print(f"Unit: {summary.get('unit_id', unit_id)}\n")
    print(f"Attempts: {summary.get('attempt_count', 0)}")
    print(f"Correct: {summary.get('correct', 0)}")
    print(f"Partial: {summary.get('partial', 0)}")
    print(f"Wrong: {summary.get('wrong', 0)}")
    print(f"Skipped: {summary.get('skipped', 0)}")
    print(f"Accuracy: {summary.get('accuracy_percent', 0)}%")
    print(f"Needs review: {summary.get('needs_review_count', 0)}\n")
    needs_review = collect_unit_active_recall_needs_review_for_unit(course_name, unit_id)
    if needs_review:
        print("Questions needing review:")
        for item in needs_review:
            print(
                f"  - {item.get('question_id')}: "
                f"{str(item.get('question', ''))[:60]} ({item.get('grade')})"
            )
        print()


def _print_flashcard_summary(course_name: str, unit_id: str) -> None:
    summary = summarize_unit_flashcard_reviews(course_name, unit_id)
    print("Unit flashcard review summary.\n")
    print(f"Unit: {summary.get('unit_id', unit_id)}\n")
    print(f"Reviews: {summary.get('review_count', 0)}")
    print(f"Easy: {summary.get('easy', 0)}")
    print(f"Good: {summary.get('good', 0)}")
    print(f"Hard: {summary.get('hard', 0)}")
    print(f"Forgot: {summary.get('forgot', 0)}")
    print(f"Skipped: {summary.get('skipped', 0)}")
    print(f"Due today: {summary.get('due_count', 0)}\n")
    due = collect_due_unit_flashcards_for_unit(course_name, unit_id)
    if due:
        print("Due flashcards:")
        for card in due:
            print(
                f"  - {card.get('card_id')}: "
                f"{str(card.get('front', ''))[:60]} (due {card.get('due_date')})"
            )
        print()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    actions = [
        args.list_recall,
        args.list_flashcards,
        args.summary,
        args.record_recall,
        args.record_flashcard,
    ]
    if sum(1 for action in actions if action) != 1:
        parser.error(
            "Choose exactly one of: --list-recall, --list-flashcards, --summary, "
            "--record-recall, --record-flashcard"
        )

    try:
        if args.list_recall:
            questions = load_unit_active_recall_questions(args.course, args.unit_id)
            print(f"Unit active recall questions ({len(questions)}):\n")
            for entry in questions:
                print(f"  {entry['question_id']}: {entry['question']}")
            return 0

        if args.list_flashcards:
            cards = load_unit_flashcards(args.course, args.unit_id)
            print(f"Unit flashcards ({len(cards)}):\n")
            for card in cards:
                print(
                    f"  {card['card_id']}: {card['front']} → {card['back']}"
                )
            return 0

        if args.summary:
            _print_recall_summary(args.course, args.unit_id)
            _print_flashcard_summary(args.course, args.unit_id)
            return 0

        if args.record_recall:
            if not args.question_id or not args.grade:
                parser.error("--record-recall requires --question-id and --grade")
            question_text = _resolve_question_text(
                args.course, args.unit_id, args.question_id, args.question
            )
            result = record_unit_active_recall_attempt(
                args.course,
                args.unit_id,
                args.question_id,
                question_text,
                args.answer,
                args.grade,
                notes=args.notes or None,
                create_mistake=args.create_mistake,
                create_weak_point=args.create_weak_point,
                weak_point_concept=args.weak_point_concept or None,
            )
            print(
                f"Recorded {result['attempt_id']} "
                f"({result['grade']}) for {result['question_id']}"
            )
            return 0

        if args.record_flashcard:
            if not args.card_id or not args.grade:
                parser.error("--record-flashcard requires --card-id and --grade")
            front, back = _resolve_flashcard(
                args.course, args.unit_id, args.card_id, args.front, args.back
            )
            result = record_unit_flashcard_review(
                args.course,
                args.unit_id,
                args.card_id,
                front,
                back,
                args.grade,
                notes=args.notes or None,
                create_weak_point=args.create_weak_point,
                weak_point_concept=args.weak_point_concept or None,
            )
            print(
                f"Recorded {result['review_id']} "
                f"({result['grade']}) for {result['card_id']} — due {result['due_date']}"
            )
            return 0

    except (
        CourseNotFoundError,
        StudyUnitNotFoundError,
        UnitActiveRecallNotReadyError,
        UnitFlashcardsNotReadyError,
        InvalidGradeError,
        InvalidFlashcardGradeError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
