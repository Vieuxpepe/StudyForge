#!/usr/bin/env python3
"""
Active Recall Mode v1 — list questions, record self-graded attempts, export summary.

Examples:
    python scripts/active_recall.py --course ECA1010_Microeconomics --source-id SRC-0001 --list
    python scripts/active_recall.py --course ECA1010_Microeconomics --source-id SRC-0001 --record \\
        --question-id AR-SRC-0001-Q001 --answer "My answer" --grade partial --notes "Confused CPI"
    python scripts/active_recall.py --course ECA1010_Microeconomics --source-id SRC-0001 --summary
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
from studyforge.study.active_recall import (  # noqa: E402
    ActiveRecallNotReadyError,
    InvalidGradeError,
    export_active_recall_summary_markdown,
    list_active_recall_questions,
    record_active_recall_attempt,
    summarize_active_recall_log,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Practice active recall with self-grading (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--list", action="store_true", help="List parsed questions.")
    parser.add_argument("--summary", action="store_true", help="Print summary and export Markdown.")
    parser.add_argument("--record", action="store_true", help="Record one graded attempt.")
    parser.add_argument("--question-id", help="Question ID for --record.")
    parser.add_argument("--question", help="Question text (optional if ID matches list).")
    parser.add_argument("--answer", default="", help="Your answer text.")
    parser.add_argument("--grade", help="correct, partial, wrong, or skipped.")
    parser.add_argument("--notes", default="", help="Optional notes.")
    parser.add_argument(
        "--create-mistake",
        action="store_true",
        help="For wrong/partial/skipped: also add a mistakes log entry.",
    )
    parser.add_argument(
        "--create-weak-point",
        action="store_true",
        help="For wrong/partial/skipped: also add a weak point entry.",
    )
    parser.add_argument(
        "--weak-point-concept",
        default="",
        help="Concept label when using --create-weak-point.",
    )
    return parser


def _print_summary(summary: dict) -> None:
    print("Active recall summary.\n")
    print(f"Source: {summary['source_id']}\n")
    print(f"Attempts: {summary['attempt_count']}")
    print(f"Correct: {summary['correct']}")
    print(f"Partial: {summary['partial']}")
    print(f"Wrong: {summary['wrong']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Accuracy: {summary['accuracy_percent']}%")
    print(f"Needs review: {summary['needs_review_count']}\n")
    if summary.get("recent_attempts"):
        print("Recent attempts:")
        for attempt in summary["recent_attempts"][:5]:
            print(
                f"  - {attempt.get('attempt_id')}: "
                f"{attempt.get('grade')} — {attempt.get('question', '')[:60]}"
            )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.list and not args.summary and not args.record:
        print("Error: specify --list, --record, or --summary.", file=sys.stderr)
        return 1

    try:
        if args.list:
            questions = list_active_recall_questions(args.course, args.source_id)
            if not questions:
                print("No questions found in active recall file.")
                return 0
            print(f"Active recall questions ({len(questions)}):\n")
            for item in questions:
                print(f"{item['question_id']} (#{item['question_number']})")
                print(f"  {item['question']}\n")
            return 0

        if args.record:
            if not args.question_id or not args.grade:
                print(
                    "Error: --record requires --question-id and --grade.",
                    file=sys.stderr,
                )
                return 1
            question_text = args.question or ""
            if not question_text:
                for item in list_active_recall_questions(args.course, args.source_id):
                    if item["question_id"] == args.question_id.strip():
                        question_text = item["question"]
                        break
            if not question_text:
                print(
                    "Error: provide --question or use a valid --question-id from --list.",
                    file=sys.stderr,
                )
                return 1
            result = record_active_recall_attempt(
                args.course,
                args.source_id,
                args.question_id,
                question_text,
                args.answer,
                args.grade,
                notes=args.notes or None,
                create_mistake=args.create_mistake,
                create_weak_point=args.create_weak_point,
                weak_point_concept=args.weak_point_concept or None,
            )
            print("Attempt saved.\n")
            print(f"Attempt ID: {result['attempt_id']}")
            print(f"Grade: {result['grade']}")
            print(f"Log: {result['log_path']}")
            if result.get("mistake_id"):
                print(f"Mistake: {result['mistake_id']}")
            if result.get("weak_point_id"):
                print(f"Weak point: {result['weak_point_id']}")
            print()
            return 0

        if args.summary:
            summary = summarize_active_recall_log(args.course, args.source_id)
            _print_summary(summary)
            path = export_active_recall_summary_markdown(args.course, args.source_id)
            print(f"Summary file: {path}\n")
            return 0

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ActiveRecallNotReadyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except InvalidGradeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
