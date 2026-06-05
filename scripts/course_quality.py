#!/usr/bin/env python3
"""
Course Quality Report v1 — trust/readiness summary across all sources.

Examples:
    python scripts/course_quality.py --course ECA1010_Microeconomics
    python scripts/course_quality.py --course ECA1010_Microeconomics --export
    python scripts/course_quality.py --course ECA1010_Microeconomics --json
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
from studyforge.study.course_quality import (  # noqa: E402
    export_course_quality_report,
    get_course_quality_report,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Course quality report — readiness across all sources (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument(
        "--export",
        action="store_true",
        help="Save Markdown/JSON under 08_App_Data/reports/.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON report.",
    )
    return parser


def _print_report(report: dict) -> None:
    print(f"Course Quality Report — {report.get('course', '')}\n")
    print(f"Date: {report.get('date', '')}\n")
    print(f"Sources: {report.get('source_count', 0)}")
    print(f"Ready: {report.get('ready_count', 0)}")
    print(f"Needs review: {report.get('needs_review_count', 0)}")
    print(f"Failed: {report.get('failed_count', 0)}\n")

    attention = [
        item
        for item in report.get("sources") or []
        if item.get("quality_status") != "ok"
    ]
    if attention:
        print("Sources needing attention:\n")
        for source in attention:
            action = source.get("recommended_action") or {}
            print(f"- {source.get('source_id')} — {source.get('title', '')}")
            print(f"  Status: {source.get('quality_status', '')}")
            print(f"  Action: {action.get('label', '')}")
            if source.get("warnings"):
                print(f"  Warning: {source['warnings'][0]}")
            print()
    else:
        print("All sources are ready to study.\n")

    actions = report.get("recommended_next_actions") or []
    if actions:
        print("Course recommendations:")
        for action in actions:
            sources_text = ", ".join(action.get("source_ids") or [])
            print(f"- {action.get('label', '')} ({sources_text})")
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.export:
            result = export_course_quality_report(args.course)
            report = result["report"]
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                _print_report(report)
                print(f"Report JSON:\n{result.get('report_json_path', '')}\n")
                print(f"Report Markdown:\n{result.get('report_markdown_path', '')}\n")
            return 0

        report = get_course_quality_report(args.course)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_report(report)
        return 0

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
