#!/usr/bin/env python3
"""
Weak points tracker v1 — list, add, update, export Markdown.

Examples:
    python scripts/weak_points.py --course ECA1010_Microeconomics --list
    python scripts/weak_points.py --course ECA1010_Microeconomics --add --source-id SRC-0001 \\
        --concept "Average annual inflation" --confidence 2 --why-hard "Total vs average"
    python scripts/weak_points.py --course ECA1010_Microeconomics --update WEAK-0001 --confidence 4 --status improving
    python scripts/weak_points.py --course ECA1010_Microeconomics --export
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.weak_points import (  # noqa: E402
    InvalidConfidenceError,
    InvalidWeakPointStatusError,
    WeakPointNotFoundError,
    add_weak_point,
    export_weak_points_markdown,
    list_weak_points,
    update_weak_point,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage course weak points.")
    parser.add_argument("--course", required=True)
    parser.add_argument("--list", action="store_true", help="List weak points.")
    parser.add_argument("--export", action="store_true", help="Export Markdown.")
    parser.add_argument("--add", action="store_true", help="Add a weak point.")
    parser.add_argument("--source-id", help="Source ID for --add.")
    parser.add_argument("--concept", help="Concept label for --add.")
    parser.add_argument(
        "--confidence", type=int, default=None, help="1–5 (default 2 for --add)."
    )
    parser.add_argument("--why-hard", default="")
    parser.add_argument("--what-to-review", default="")
    parser.add_argument("--practice-needed", default="")
    parser.add_argument("--status", default=None, help="Default new for --add.")
    parser.add_argument("--update", metavar="WEAK_ID", help="Update weak point by ID.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.list:
            items = list_weak_points(args.course)
            if not items:
                print("No weak points recorded.")
                return 0
            print(f"Weak points ({len(items)}):\n")
            for entry in items:
                print(
                    f"{entry['weak_point_id']} [{entry['status']}] "
                    f"confidence {entry['confidence_level']} — {entry['concept'][:60]}"
                )
                print(f"  Source: {entry['source_id']}\n")
            return 0

        if args.add:
            if not args.source_id or not args.concept:
                print("Error: --add requires --source-id and --concept.", file=sys.stderr)
                return 1
            result = add_weak_point(
                args.course,
                args.source_id,
                args.concept,
                confidence_level=args.confidence if args.confidence is not None else 2,
                why_hard=args.why_hard or None,
                what_to_review=args.what_to_review or None,
                practice_needed=args.practice_needed or None,
                status=args.status or "new",
            )
            print(f"Weak point added: {result['weak_point_id']}")
            print(f"Log: {result['log_path']}\n")
            return 0

        if args.update:
            if args.confidence is None and args.status is None:
                print(
                    "Error: --update requires --confidence and/or --status.",
                    file=sys.stderr,
                )
                return 1
            result = update_weak_point(
                args.course,
                args.update,
                confidence_level=args.confidence,
                status=args.status,
            )
            print(
                f"Updated {result['weak_point_id']}: "
                f"confidence {result['confidence_level']}, status {result['status']}\n"
            )
            return 0

        if args.export:
            path = export_weak_points_markdown(args.course)
            items = list_weak_points(args.course)
            print(f"Exported {len(items)} weak point(s) to:\n{path}\n")
            return 0

        print("Error: specify --list, --add, --update, or --export.", file=sys.stderr)
        return 1

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (
        InvalidConfidenceError,
        InvalidWeakPointStatusError,
        WeakPointNotFoundError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
