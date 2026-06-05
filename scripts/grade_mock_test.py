#!/usr/bin/env python3
"""
Mock Test Detailed Grading v1 — grade mock tests question-by-question.

Examples:
    python scripts/grade_mock_test.py --course ECA1010_Microeconomics --list
    python scripts/grade_mock_test.py --course ECA1010_Microeconomics --mock-test-id MT-SRC-0001-... --questions
    python scripts/grade_mock_test.py --course ECA1010_Microeconomics --mock-test-id MT-SRC-0001-... \\
        --grade-question MT-SRC-0001-Q001 --grade wrong --answer "idk" --create-weak-point
    python scripts/grade_mock_test.py --course ECA1010_Microeconomics --mock-test-id MT-SRC-0001-... --summary
    python scripts/grade_mock_test.py --course ECA1010_Microeconomics --mock-test-id MT-SRC-0001-... --finalize
    python scripts/grade_mock_test.py --course ECA1010_Microeconomics --mock-test-id MT-SRC-0001-... --export-review
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.mock_test_grading import (  # noqa: E402
    InvalidMockTestGradeError,
    MockTestGradingAlreadyFinalizedError,
    MockTestQuestionNotFoundError,
    MockTestReviewExistsError,
    export_mock_test_review,
    finalize_mock_test_grading,
    record_mock_question_result,
    summarize_mock_test_grading,
)
from studyforge.study.mock_tests import (  # noqa: E402
    MockTestNotFoundError,
    list_mock_tests,
    load_mock_test_json,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Grade mock tests question-by-question (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--list", action="store_true", help="List generated mock tests.")
    parser.add_argument("--mock-test-id", help="Mock test ID for grading actions.")
    parser.add_argument(
        "--questions",
        action="store_true",
        help="List questions in the mock test.",
    )
    parser.add_argument("--grade-question", help="Question ID to grade.")
    parser.add_argument(
        "--grade",
        choices=["correct", "partial", "wrong", "skipped"],
        help="Grade for --grade-question.",
    )
    parser.add_argument("--answer", default="", help="Your answer text.")
    parser.add_argument("--notes", default="", help="Optional notes.")
    parser.add_argument(
        "--create-mistake",
        action="store_true",
        help="Create mistake for wrong/partial/skipped grades.",
    )
    parser.add_argument(
        "--create-weak-point",
        action="store_true",
        help="Create weak point for wrong/partial/skipped grades.",
    )
    parser.add_argument("--weak-point-concept", default="")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show grading summary for the mock test.",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Finalize grading and record a mock test attempt.",
    )
    parser.add_argument(
        "--weak-topic",
        action="append",
        default=[],
        help="Weak topic for finalize (repeatable).",
    )
    parser.add_argument(
        "--export-review",
        action="store_true",
        help="Export post-mock review Markdown.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing review Markdown.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output where applicable.",
    )
    return parser


def _print_summary(summary: dict) -> None:
    print(f"Mock test: {summary.get('mock_test_id', '')}\n")
    print(f"Graded: {summary.get('graded_count', 0)}/{summary.get('question_count', 0)}")
    print(
        f"Correct: {summary.get('correct', 0)} · "
        f"Partial: {summary.get('partial', 0)} · "
        f"Wrong: {summary.get('wrong', 0)} · "
        f"Skipped: {summary.get('skipped', 0)}"
    )
    print(
        f"Score: {summary.get('score_correct_equivalent', 0)}/"
        f"{summary.get('score_total', 0)} ({summary.get('percent', 0)}%)\n"
    )
    missed = summary.get("missed_questions") or []
    if missed:
        print("Missed / partial:")
        for item in missed:
            print(
                f"  - {item.get('mock_question_id', '')}: "
                f"{item.get('grade', '')} — "
                f"{str(item.get('question', ''))[:60]}"
            )
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.list:
            tests = list_mock_tests(args.course)
            if args.json:
                print(json.dumps(tests, indent=2, ensure_ascii=False))
            else:
                print(f"Mock tests ({len(tests)}):\n")
                for test in tests:
                    print(
                        f"- {test.get('mock_test_id', '')} "
                        f"[{test.get('scope', '')}] "
                        f"{test.get('question_count', 0)} questions "
                        f"({test.get('date_generated', '')})"
                    )
                print()
            return 0

        if not args.mock_test_id:
            print("Error: --mock-test-id is required for this action.", file=sys.stderr)
            return 1

        if args.questions:
            mock_test = load_mock_test_json(args.course, args.mock_test_id)
            if args.json:
                print(json.dumps(mock_test.get("questions", []), indent=2, ensure_ascii=False))
            else:
                print(f"Questions in {args.mock_test_id}:\n")
                for question in mock_test.get("questions", []):
                    print(f"- {question.get('mock_question_id', '')}: "
                          f"{str(question.get('question', ''))[:80]}")
                print()
            return 0

        if args.grade_question:
            if not args.grade:
                print("Error: --grade is required with --grade-question.", file=sys.stderr)
                return 1
            result = record_mock_question_result(
                args.course,
                args.mock_test_id,
                args.grade_question,
                args.grade,
                user_answer=args.answer or None,
                notes=args.notes or None,
                create_mistake=args.create_mistake,
                create_weak_point=args.create_weak_point,
                weak_point_concept=args.weak_point_concept or None,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question graded.\n")
                print(f"Question: {result['mock_question_id']}")
                print(f"Grade: {result['grade']}")
                print(f"Applied: {', '.join(result.get('applied', []))}\n")
                _print_summary(result.get("summary", {}))
            return 0

        if args.summary:
            summary = summarize_mock_test_grading(args.course, args.mock_test_id)
            if args.json:
                print(json.dumps(summary, indent=2, ensure_ascii=False))
            else:
                _print_summary(summary)
            return 0

        if args.finalize:
            result = finalize_mock_test_grading(
                args.course,
                args.mock_test_id,
                notes=args.notes or None,
                weak_topics=args.weak_topic or None,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Mock test grading finalized.\n")
                print(f"Attempt: {result.get('attempt_id', '')}")
                print(
                    f"Score: {result.get('score_correct')}/"
                    f"{result.get('score_total')} ({result.get('percent')}%)"
                )
                print(f"Log: {result.get('log_path', '')}\n")
            return 0

        if args.export_review:
            result = export_mock_test_review(
                args.course,
                args.mock_test_id,
                overwrite=args.overwrite,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Mock test review exported.\n")
                print(f"Path: {result.get('review_path', '')}\n")
            return 0

        print(
            "Error: specify --list, --questions, --grade-question, --summary, "
            "--finalize, or --export-review.",
            file=sys.stderr,
        )
        return 1

    except (
        CourseNotFoundError,
        MockTestNotFoundError,
        MockTestQuestionNotFoundError,
        InvalidMockTestGradeError,
        MockTestGradingAlreadyFinalizedError,
        MockTestReviewExistsError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
