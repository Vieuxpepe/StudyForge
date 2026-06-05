#!/usr/bin/env python3
"""
Exam Targets v1 — define upcoming exams and what they cover.

Examples:
    python scripts/exam_targets.py --course ECA1010_Microeconomics --list
    python scripts/exam_targets.py --course ECA1010_Microeconomics --create \\
        --title "Quiz 2" --date 2026-06-20 --target-score 80 \\
        --units UNIT-0001 UNIT-0002 --sources SRC-0005
    python scripts/exam_targets.py --course ECA1010_Microeconomics --update EXAM-0001 --status completed
    python scripts/exam_targets.py --course ECA1010_Microeconomics --summary EXAM-0001
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
from studyforge.study.exam_prep import (  # noqa: E402
    collect_exam_prep_state,
    get_days_until_exam,
    get_exam_scope_source_ids,
    recommend_exam_prep_actions,
)
from studyforge.study.exam_targets import (  # noqa: E402
    ExamTargetNotFoundError,
    InvalidExamDateError,
    InvalidExamTargetStatusError,
    InvalidExamUnitIdError,
    InvalidTargetScoreError,
    create_exam_target,
    get_exam_target,
    list_exam_targets,
    update_exam_target,
)
from studyforge.study.study_units import InvalidSourceIdError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage exam targets for a course (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--list", action="store_true", help="List exam targets.")
    parser.add_argument("--create", action="store_true", help="Create an exam target.")
    parser.add_argument("--update", metavar="EXAM_ID", help="Update an exam target.")
    parser.add_argument("--summary", metavar="EXAM_ID", help="Show exam prep summary.")
    parser.add_argument("--title", help="Title for --create or --update.")
    parser.add_argument("--date", help="Exam date YYYY-MM-DD.")
    parser.add_argument("--description", default="", help="Description text.")
    parser.add_argument("--target-score", type=int, help="Target score 0–100.")
    parser.add_argument(
        "--units",
        nargs="*",
        default=[],
        help="Unit IDs for --create or --update.",
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        default=[],
        help="Source IDs for --create or --update.",
    )
    parser.add_argument("--status", help="Status: active, completed, archived.")
    return parser


def _print_targets(targets: list[dict]) -> None:
    if not targets:
        print("No exam targets defined.")
        return
    print(f"Exam targets ({len(targets)}):\n")
    for target in targets:
        units = ", ".join(target.get("unit_ids", [])) or "(none)"
        sources = ", ".join(target.get("source_ids", [])) or "(none)"
        score = target.get("target_score")
        score_text = f"{score}%" if score is not None else "—"
        print(
            f"{target['exam_id']} [{target.get('status', 'active')}] — "
            f"{target['title']} ({target.get('exam_date', '')})"
        )
        if target.get("description"):
            print(f"  Description: {target['description']}")
        print(f"  Target: {score_text}")
        print(f"  Units: {units}")
        print(f"  Sources: {sources}\n")


def _print_summary(course_name: str, exam_id: str) -> None:
    target = get_exam_target(course_name, exam_id)
    scope = get_exam_scope_source_ids(course_name, exam_id)
    state = collect_exam_prep_state(course_name, exam_id)
    actions = recommend_exam_prep_actions(state)
    days = get_days_until_exam(str(target.get("exam_date", "")))

    print(f"Exam target: {target['exam_id']} — {target['title']}")
    print(f"Date: {target.get('exam_date', '')} ({days} day(s) remaining)")
    if target.get("target_score") is not None:
        print(f"Target score: {target['target_score']}%")
    print(f"Status: {target.get('status', 'active')}")
    print(f"Units: {', '.join(scope.get('unit_ids', [])) or '(none)'}")
    print(f"Sources: {', '.join(scope.get('source_ids', [])) or '(none)'}\n")

    readiness = state.get("readiness", {})
    review = state.get("review", {})
    mock_tests = state.get("mock_tests", {})
    print("Readiness:")
    print(f"  Incomplete sources: {len(readiness.get('incomplete_sources', []))}")
    print(
        f"  Units without synthesis: "
        f"{len(readiness.get('units_without_synthesis', []))}"
    )
    print(
        f"  Units without unit pack: "
        f"{len(readiness.get('units_without_unit_pack', []))}"
    )
    print("Review:")
    print(f"  Due flashcards: {len(review.get('due_flashcards', []))}")
    print(f"  Due unit flashcards: {len(review.get('due_unit_flashcards', []))}")
    print(
        f"  Active recall gaps: "
        f"{len(review.get('active_recall_needs_review', []))}"
    )
    print(
        f"  Unit recall gaps: "
        f"{len(review.get('unit_recall_needs_review', []))}"
    )
    print(f"  Open mistakes: {len(review.get('open_mistakes', []))}")
    print(f"  Open weak points: {len(review.get('open_weak_points', []))}")
    print("Mock tests:")
    print(f"  Attempts: {mock_tests.get('attempt_count', 0)}")
    print(f"  Latest score: {mock_tests.get('latest_score', '—')}%")
    print(f"  Average score: {mock_tests.get('average_score', '—')}%\n")

    if actions:
        print("Recommended actions:")
        for action in actions:
            print(f"  - {action.get('label', '')}: {action.get('reason', '')}")
        print()

    if state.get("warnings"):
        print("Warnings:")
        for warning in state["warnings"]:
            print(f"  - {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    actions = [args.list, args.create, bool(args.update), bool(args.summary)]
    if sum(1 for action in actions if action) != 1:
        parser.error("Choose exactly one of: --list, --create, --update, --summary")

    try:
        if args.list:
            _print_targets(list_exam_targets(args.course))
            return 0

        if args.create:
            if not args.title or not args.date:
                parser.error("--create requires --title and --date")
            target = create_exam_target(
                args.course,
                args.title,
                args.date,
                description=args.description or None,
                target_score=args.target_score,
                unit_ids=args.units,
                source_ids=args.sources,
                status=args.status or "active",
            )
            print(f"Created {target['exam_id']}: {target['title']}")
            print(json.dumps(target, indent=2))
            return 0

        if args.update:
            target = update_exam_target(
                args.course,
                args.update,
                title=args.title,
                exam_date=args.date,
                description=args.description if args.description else None,
                target_score=args.target_score,
                unit_ids=args.units if args.units else None,
                source_ids=args.sources if args.sources else None,
                status=args.status,
            )
            print(f"Updated {target['exam_id']}")
            print(json.dumps(target, indent=2))
            return 0

        if args.summary:
            _print_summary(args.course, args.summary)
            return 0

    except (
        CourseNotFoundError,
        ExamTargetNotFoundError,
        InvalidExamDateError,
        InvalidExamTargetStatusError,
        InvalidTargetScoreError,
        InvalidExamUnitIdError,
        InvalidSourceIdError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
