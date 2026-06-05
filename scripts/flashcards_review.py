#!/usr/bin/env python3
"""
Flashcard Review Mode v1 — list, review, summarize, and list due cards (no AI).

Examples:
    python scripts/flashcards_review.py --course ECA1010_Microeconomics --source-id SRC-0001 --list
    python scripts/flashcards_review.py --course ECA1010_Microeconomics --source-id SRC-0001 --record --card-id FC-SRC-0001-0001 --grade hard --notes "Forgot formula"
    python scripts/flashcards_review.py --course ECA1010_Microeconomics --source-id SRC-0001 --summary
    python scripts/flashcards_review.py --course ECA1010_Microeconomics --source-id SRC-0001 --due
    python scripts/flashcards_review.py --course ECA1010_Microeconomics --due
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.flashcard_review import (  # noqa: E402
    FlashcardsNotReadyError,
    InvalidFlashcardGradeError,
    collect_due_flashcards,
    load_flashcards_for_source,
    record_flashcard_review,
    summarize_flashcard_reviews,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Self-graded flashcard review with lightweight due scheduling."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument(
        "--source-id",
        help="Source id (required for --list, --summary, --record).",
    )
    parser.add_argument("--list", action="store_true", help="List flashcards.")
    parser.add_argument("--summary", action="store_true", help="Show review summary.")
    parser.add_argument("--due", action="store_true", help="List due flashcards.")
    parser.add_argument("--record", action="store_true", help="Record one review.")
    parser.add_argument("--card-id", help="Card id for --record.")
    parser.add_argument("--grade", help="Grade: easy, good, hard, forgot, skipped.")
    parser.add_argument("--notes", default="", help="Optional notes.")
    parser.add_argument(
        "--create-weak-point",
        action="store_true",
        help="Create weak point when grade is hard or forgot.",
    )
    parser.add_argument("--weak-point-concept", default="")
    return parser


def _print_list(cards: list[dict]) -> None:
    print(f"Flashcards ({len(cards)})\n")
    for card in cards:
        front = str(card.get("front", ""))[:70]
        print(f"- {card.get('card_id', '')}: {front}")
    print()


def _print_due(cards: list[dict]) -> None:
    print(f"Due flashcards ({len(cards)})\n")
    for card in cards:
        front = str(card.get("front", ""))[:60]
        print(
            f"- {card.get('card_id', '')} "
            f"({card.get('source_id', '')}) "
            f"grade={card.get('latest_grade', card.get('grade', ''))} "
            f"due={card.get('due_date', '')}: {front}"
        )
    print()


def _print_summary(summary: dict) -> None:
    print("Flashcard review summary\n")
    print(f"Source: {summary.get('source_id')}\n")
    print(f"Reviews: {summary.get('review_count')}\n")
    print(
        "Grades: "
        f"easy={summary.get('easy', 0)}, "
        f"good={summary.get('good', 0)}, "
        f"hard={summary.get('hard', 0)}, "
        f"forgot={summary.get('forgot', 0)}, "
        f"skipped={summary.get('skipped', 0)}\n"
    )
    print(f"Needs review: {summary.get('needs_review_count', 0)}\n")
    print(
        f"Due: {summary.get('due_count', 0)} "
        f"(today: {summary.get('due_today_count', 0)}, "
        f"future: {summary.get('future_due_count', 0)})\n"
    )
    recent = summary.get("recent_reviews") or []
    if recent:
        print("Recent reviews:")
        for review in recent:
            due = review.get("due_date", "")
            due_text = f", due {due}" if due else ""
            print(
                f"  - {review.get('review_id')} "
                f"({review.get('card_id')}): {review.get('grade')}{due_text}"
            )
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.list and not args.summary and not args.record and not args.due:
        print(
            "Error: specify --list, --summary, --record, or --due.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.due:
            due_cards = collect_due_flashcards(
                args.course,
                source_id=args.source_id,
            )
            _print_due(due_cards)
            return 0

        if not args.source_id:
            print(
                "Error: --source-id is required for this action.",
                file=sys.stderr,
            )
            return 1

        if args.list:
            cards = load_flashcards_for_source(args.course, args.source_id)
            _print_list(cards)
            return 0

        if args.summary:
            summary = summarize_flashcard_reviews(args.course, args.source_id)
            _print_summary(summary)
            return 0

        if args.record:
            if not args.card_id or not args.grade:
                print(
                    "Error: --record requires --card-id and --grade.",
                    file=sys.stderr,
                )
                return 1
            cards = load_flashcards_for_source(args.course, args.source_id)
            card = next(
                (item for item in cards if item.get("card_id") == args.card_id),
                None,
            )
            if card is None:
                print(f"Error: card not found: {args.card_id}", file=sys.stderr)
                return 1
            result = record_flashcard_review(
                args.course,
                args.source_id,
                args.card_id,
                str(card.get("front", "")),
                str(card.get("back", "")),
                args.grade,
                notes=args.notes or None,
                create_weak_point=args.create_weak_point,
                weak_point_concept=args.weak_point_concept or None,
            )
            print("Flashcard review recorded.\n")
            print(f"Review: {result.get('review_id')}\n")
            print(f"Grade: {result.get('grade')}\n")
            print(f"Due date: {result.get('due_date')}\n")
            if result.get("weak_point"):
                print(f"Weak point: {result['weak_point'].get('weak_point_id')}\n")
            return 0

        return 1

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FlashcardsNotReadyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except InvalidFlashcardGradeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
