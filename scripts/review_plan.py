#!/usr/bin/env python3
"""
Generate a deterministic daily review plan (no AI).

Examples:
    python scripts/review_plan.py --course ECA1010_Microeconomics
    python scripts/review_plan.py --course ECA1010_Microeconomics --limit 5 --overwrite
    python scripts/review_plan.py --course ECA1010_Microeconomics --date 2026-06-04
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.review_planner import (  # noqa: E402
    ReviewPlanExistsError,
    generate_review_plan,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate today's review session plan."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument(
        "--date",
        help="Plan date YYYY-MM-DD (default: today local).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum priority items (default 10).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing plan for this date.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        summary = generate_review_plan(
            args.course,
            date_str=args.date,
            limit=args.limit,
            overwrite=args.overwrite,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ReviewPlanExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Review plan generated.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Date:\n{summary['date']}\n")
    print(f"Open mistakes:\n{summary['mistake_count']}\n")
    print(f"Open weak points:\n{summary['weak_point_count']}\n")
    print(f"Active recall redo:\n{summary['active_recall_review_count']}\n")
    print(f"Top priorities:\n{summary['priority_count']}\n")
    print(f"Markdown:\n{summary['markdown_path']}\n")
    print(f"JSON:\n{summary['json_path']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
