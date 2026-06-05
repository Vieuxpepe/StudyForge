#!/usr/bin/env python3
"""
Exam Readiness Score v1 — deterministic readiness for exam targets.

Examples:
    python scripts/exam_readiness.py --course ECA1010_Microeconomics --exam-id EXAM-0001
    python scripts/exam_readiness.py --course ECA1010_Microeconomics --exam-id EXAM-0001 --export
    python scripts/exam_readiness.py --course ECA1010_Microeconomics --exam-id EXAM-0001 --export --overwrite
    python scripts/exam_readiness.py --course ECA1010_Microeconomics --exam-id EXAM-0001 --json
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
from studyforge.study.exam_readiness import (  # noqa: E402
    ExamReadinessReportExistsError,
    export_exam_readiness_report,
    get_exam_readiness_report,
)
from studyforge.study.exam_targets import ExamTargetNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate deterministic exam readiness scores (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--exam-id", required=True)
    parser.add_argument(
        "--export",
        action="store_true",
        help="Write Markdown and JSON readiness report files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing readiness report files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full report as JSON.",
    )
    return parser


def _print_report(report: dict) -> None:
    readiness = report.get("readiness", {})
    blockers = readiness.get("blockers") or []
    recommendations = readiness.get("recommendations") or []

    print(f"Exam readiness — {report.get('title', '')}\n")
    print(f"Score:\n{readiness.get('score', 0)}%\n")
    print(f"Status:\n{readiness.get('status', '')}\n")

    print("Top blockers:")
    if blockers:
        for blocker in blockers[:5]:
            print(f"- {blocker}")
    else:
        print("- None")
    print()

    print("Recommendations:")
    if recommendations:
        for recommendation in recommendations[:5]:
            print(f"- {recommendation}")
    else:
        print("- Start an exam-focused study session.")
    print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.export:
            result = export_exam_readiness_report(
                args.course,
                args.exam_id,
                overwrite=args.overwrite,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Exam readiness report exported.\n")
                print(f"Exam: {result.get('title', '')}")
                print(f"Score: {result.get('readiness', {}).get('score', 0)}%")
                print(f"Status: {result.get('readiness', {}).get('status', '')}")
                print(f"Markdown: {result.get('markdown_path', '')}")
                print(f"JSON: {result.get('json_path', '')}")
            return 0

        report = get_exam_readiness_report(args.course, args.exam_id)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            _print_report(report)
        return 0

    except (
        CourseNotFoundError,
        ExamTargetNotFoundError,
        ExamReadinessReportExistsError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
