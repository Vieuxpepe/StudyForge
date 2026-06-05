#!/usr/bin/env python3
"""
Exam Prep Planner v1 — generate deterministic exam prep plans.

Examples:
    python scripts/exam_prep.py --course ECA1010_Microeconomics --exam-id EXAM-0001
    python scripts/exam_prep.py --course ECA1010_Microeconomics --exam-id EXAM-0001 --export --overwrite
    python scripts/exam_prep.py --course ECA1010_Microeconomics --exam-id EXAM-0001 --json
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
    ExamPrepPlanExistsError,
    collect_exam_prep_state,
    generate_exam_prep_plan,
    recommend_exam_prep_actions,
)
from studyforge.study.exam_targets import ExamTargetNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate exam prep plans from exam targets (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--exam-id", required=True)
    parser.add_argument(
        "--export",
        action="store_true",
        help="Write Markdown and JSON plan files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing plan files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full plan result as JSON (implies --export).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.export or args.json:
            result = generate_exam_prep_plan(
                args.course,
                args.exam_id,
                overwrite=args.overwrite,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Exam prep plan generated.\n")
                print(f"Exam: {result.get('exam_title', '')}")
                print(f"Days until exam: {result.get('days_until_exam', '')}")
                print(f"Actions: {result.get('action_count', 0)}")
                print(f"Markdown: {result.get('markdown_path', '')}")
                print(f"JSON: {result.get('json_path', '')}")
                if result.get("warnings"):
                    print("\nWarnings:")
                    for warning in result["warnings"]:
                        print(f"  - {warning}")
            return 0

        state = collect_exam_prep_state(args.course, args.exam_id)
        actions = recommend_exam_prep_actions(state)
        print(f"Exam: {state.get('exam', {}).get('title', '')}")
        print(f"Days until exam: {state.get('days_until_exam', '')}")
        print(f"Recommended actions: {len(actions)}\n")
        for action in actions:
            print(f"- {action.get('label', '')}: {action.get('reason', '')}")
        if state.get("warnings"):
            print("\nWarnings:")
            for warning in state["warnings"]:
                print(f"  - {warning}")
        return 0

    except (
        CourseNotFoundError,
        ExamTargetNotFoundError,
        ExamPrepPlanExistsError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
