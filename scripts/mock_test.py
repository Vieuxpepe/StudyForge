#!/usr/bin/env python3
"""
Mock Test / Exam Simulator v1 — generate tests and record self-graded attempts.

Examples:
    python scripts/mock_test.py --course ECA1010_Microeconomics --source-id SRC-0001 --generate
    python scripts/mock_test.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --generate --questions 15
    python scripts/mock_test.py --course ECA1010_Microeconomics --record --mock-test-id MT-SRC-0001-2026-06-04-120000 \\
        --scope source --source-id SRC-0001 --score 14 --total 20 --notes "Missed formulas" \\
        --weak-topic "CPI formula" --weak-topic "Nominal vs real"
    python scripts/mock_test.py --course ECA1010_Microeconomics --summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.mock_tests import (  # noqa: E402
    InvalidMockTestScopeError,
    InvalidMockTestScoreError,
    MockTestNotReadyError,
    generate_mock_test,
    record_mock_test_attempt,
    summarize_mock_test_attempts,
)
from studyforge.study.study_units import StudyUnitNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic mock tests from study material (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--generate", action="store_true", help="Generate a mock test.")
    parser.add_argument("--record", action="store_true", help="Record a self-graded attempt.")
    parser.add_argument("--summary", action="store_true", help="Print attempt summary.")
    parser.add_argument("--source-id", help="Source ID for source scope.")
    parser.add_argument("--unit-id", help="Unit ID for unit scope.")
    parser.add_argument("--questions", type=int, default=20, help="Question count (default 20).")
    parser.add_argument(
        "--no-flashcards",
        action="store_true",
        help="Exclude flashcard fronts from generated tests.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Reserved for future use.")
    parser.add_argument("--mock-test-id", help="Mock test ID for --record.")
    parser.add_argument("--scope", choices=["source", "unit"], help="Scope for --record.")
    parser.add_argument("--score", type=int, help="Correct answers for --record.")
    parser.add_argument("--total", type=int, help="Total questions for --record.")
    parser.add_argument("--notes", default="", help="Optional notes for --record.")
    parser.add_argument(
        "--weak-topic",
        action="append",
        default=[],
        help="Weak topic to log as weak point (repeatable).",
    )
    return parser


def _print_summary(summary: dict) -> None:
    print("Mock test attempt summary.\n")
    print(f"Course: {summary.get('course', '')}\n")
    print(f"Attempts: {summary.get('attempt_count', 0)}")
    print(f"Average score: {summary.get('average_percent', 0)}%\n")
    latest = summary.get("latest_attempt")
    if latest:
        print(
            f"Latest: {latest.get('mock_test_id')} — "
            f"{latest.get('score_correct')}/{latest.get('score_total')} "
            f"({latest.get('percent')}%)"
        )
        print()
    recent = summary.get("recent_attempts") or []
    if recent:
        print("Recent attempts:")
        for attempt in recent[:5]:
            print(
                f"  - {attempt.get('attempt_id')}: "
                f"{attempt.get('mock_test_id')} "
                f"{attempt.get('score_correct')}/{attempt.get('score_total')} "
                f"({attempt.get('percent')}%)"
            )
        print()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    actions = [args.generate, args.record, args.summary]
    if sum(1 for action in actions if action) != 1:
        parser.error("Choose exactly one of: --generate, --record, --summary")

    try:
        if args.generate:
            if args.source_id and args.unit_id:
                parser.error("Provide either --source-id or --unit-id, not both.")
            if args.source_id:
                result = generate_mock_test(
                    args.course,
                    "source",
                    source_id=args.source_id,
                    question_count=args.questions,
                    include_flashcards=not args.no_flashcards,
                    overwrite=args.overwrite,
                )
            elif args.unit_id:
                result = generate_mock_test(
                    args.course,
                    "unit",
                    unit_id=args.unit_id,
                    question_count=args.questions,
                    include_flashcards=not args.no_flashcards,
                    overwrite=args.overwrite,
                )
            else:
                parser.error("--generate requires --source-id or --unit-id")
            print("Mock test generated.\n")
            print(f"ID: {result['mock_test_id']}")
            print(f"Questions: {result['question_count']}")
            print(f"Markdown: {result['markdown_path']}")
            print(f"JSON: {result['json_path']}")
            return 0

        if args.record:
            if not args.mock_test_id or not args.scope:
                parser.error("--record requires --mock-test-id and --scope")
            if args.score is None or args.total is None:
                parser.error("--record requires --score and --total")
            if args.scope == "source" and not args.source_id:
                parser.error("--record with --scope source requires --source-id")
            if args.scope == "unit" and not args.unit_id:
                parser.error("--record with --scope unit requires --unit-id")
            result = record_mock_test_attempt(
                args.course,
                args.mock_test_id,
                args.scope,
                args.source_id,
                args.unit_id,
                args.score,
                args.total,
                notes=args.notes or None,
                weak_topics=args.weak_topic or None,
            )
            print(
                f"Recorded {result['attempt_id']}: "
                f"{result['score_correct']}/{result['score_total']} "
                f"({result['percent']}%)"
            )
            if result.get("weak_point_ids"):
                print(f"Weak points: {', '.join(result['weak_point_ids'])}")
            return 0

        if args.summary:
            _print_summary(summarize_mock_test_attempts(args.course))
            return 0

    except (
        CourseNotFoundError,
        StudyUnitNotFoundError,
        MockTestNotReadyError,
        InvalidMockTestScopeError,
        InvalidMockTestScoreError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
