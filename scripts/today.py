#!/usr/bin/env python3
"""
Today Dashboard v1 — summary of what to study now (deterministic, no AI).

Examples:
    python scripts/today.py --course ECA1010_Microeconomics
    python scripts/today.py --course ECA1010_Microeconomics --export
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.study.today_dashboard import (  # noqa: E402
    export_today_dashboard,
    get_today_dashboard,
    get_today_dashboard_json_path,
)
from studyforge.core.sources import CourseNotFoundError, resolve_course_path  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Today dashboard — what to study now (deterministic)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument(
        "--export",
        action="store_true",
        help="Save Markdown and JSON under 07_My_Work/today_dashboard/.",
    )
    return parser


def _print_dashboard(dashboard: dict) -> None:
    summary = dashboard.get("summary", {})
    print(f"Today — {dashboard.get('course', '')}\n")
    print(f"Date: {dashboard.get('date', '')}\n")
    print(f"Due flashcards: {summary.get('due_flashcards', 0)}")
    print(f"Active recall needs review: {summary.get('active_recall_needs_review', 0)}")
    print(f"Open mistakes: {summary.get('open_mistakes', 0)}")
    print(f"Open weak points: {summary.get('open_weak_points', 0)}")
    print(
        f"Review plan today: {'yes' if summary.get('has_review_plan_today') else 'no'}"
    )
    print(f"Latest session: {summary.get('latest_session_status', 'none')}\n")

    actions = dashboard.get("recommended_actions") or []
    if actions:
        print("Recommended:")
        for action in actions:
            print(f"- {action.get('label', '')}")
        print()

    warnings = dashboard.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        dashboard = get_today_dashboard(args.course)
        _print_dashboard(dashboard)

        if args.export:
            path = export_today_dashboard(args.course)
            json_path = get_today_dashboard_json_path(
                resolve_course_path(args.course), dashboard["date"]
            )
            print(f"Exported Markdown: {path}\n")
            print(f"Exported JSON: {json_path}\n")

        return 0

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
