#!/usr/bin/env python3
"""
Study Unit Dashboard v1 — aggregate readiness and review data for a unit.

Examples:
    python scripts/study_unit_dashboard.py --course ECA1010_Microeconomics --unit-id UNIT-0001
    python scripts/study_unit_dashboard.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --export
    python scripts/study_unit_dashboard.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --review-plan
    python scripts/study_unit_dashboard.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --json
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
from studyforge.study.study_unit_dashboard import (  # noqa: E402
    UnitReviewPlanExistsError,
    export_unit_dashboard,
    generate_unit_review_plan,
    get_study_unit_dashboard,
)
from studyforge.study.study_units import StudyUnitNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Study unit dashboard and unit review plans (no AI)."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--unit-id", required=True, help="Study unit ID, e.g. UNIT-0001.")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export dashboard Markdown and JSON.",
    )
    parser.add_argument(
        "--review-plan",
        action="store_true",
        help="Generate a unit-specific review plan for today.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Priority item limit for --review-plan (default: 10).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing unit review plan for today.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print dashboard JSON to stdout.",
    )
    return parser


def _print_dashboard(dashboard: dict) -> None:
    review = dashboard.get("review_summary") or {}
    action = dashboard.get("recommended_action") or {}
    print(f"Study Unit Dashboard — {dashboard.get('unit_id', '')}")
    print(f"Course: {dashboard.get('course', '')}")
    print(f"Unit: {dashboard.get('title', '')}")
    print(f"Status: {dashboard.get('status', '')}")
    print(
        f"Sources: {dashboard.get('source_count', 0)} "
        f"(ready: {dashboard.get('ready_sources', 0)}, "
        f"incomplete: {dashboard.get('incomplete_sources', 0)})"
    )
    print(
        f"Review — flashcards: {review.get('due_flashcards', 0)}, "
        f"recall: {review.get('active_recall_needs_review', 0)}, "
        f"mistakes: {review.get('open_mistakes', 0)}, "
        f"weak points: {review.get('open_weak_points', 0)}"
    )
    print(f"Recommended: {action.get('label', '')} — {action.get('reason', '')}")
    print("\nSources:")
    for source in dashboard.get("sources") or []:
        pack = "yes" if source.get("has_study_pack") else "no"
        print(
            f"  - {source.get('source_id', '')}: {source.get('title', '')} "
            f"[{source.get('status', '')}] study_pack={pack} "
            f"next={source.get('recommended_action', '')}"
        )
    for warning in dashboard.get("warnings") or []:
        print(f"Warning: {warning}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.review_plan:
            result = generate_unit_review_plan(
                args.course,
                args.unit_id,
                limit=args.limit,
                overwrite=args.overwrite,
            )
            print(
                f"Unit review plan written for {result['unit_id']} "
                f"({result['unit_title']})"
            )
            print(f"Markdown: {result['markdown_path']}")
            print(f"JSON: {result['json_path']}")
            print(
                f"Priorities: {result['priority_count']} "
                f"(mistakes={result['mistake_count']}, "
                f"weak={result['weak_point_count']}, "
                f"recall={result['active_recall_review_count']}, "
                f"flashcards={result['flashcards_due_count']})"
            )
            return 0

        if args.export:
            result = export_unit_dashboard(args.course, args.unit_id)
            print(f"Exported dashboard for {result['unit_id']}")
            print(f"Markdown: {result['markdown_path']}")
            print(f"JSON: {result['json_path']}")
            if args.json:
                print(json.dumps(result["dashboard"], indent=2, ensure_ascii=False))
            return 0

        dashboard = get_study_unit_dashboard(args.course, args.unit_id)
        if args.json:
            print(json.dumps(dashboard, indent=2, ensure_ascii=False))
        else:
            _print_dashboard(dashboard)
        return 0

    except (
        CourseNotFoundError,
        StudyUnitNotFoundError,
        UnitReviewPlanExistsError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
