#!/usr/bin/env python3
"""
Print pipeline status and next recommended action for a course source.

Example:
    python scripts/pipeline_status.py --course ECA1010_Microeconomics --source-id SRC-0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.pipeline_status import STEP_ORDER, get_pipeline_status  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show StudyForge pipeline status and next recommended step."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--source-id", required=True, help="Source ID (e.g. SRC-0001).")
    return parser


def _format_warnings(warnings: list[str]) -> str:
    if not warnings:
        return "  (none)"
    return "\n".join(f"  - {w}" for w in warnings)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        status = get_pipeline_status(args.course, args.source_id)
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Pipeline status\n")
    print(f"Source:\n  {status['source_id']} — {status['title']}\n")
    print(f"Course:\n  {status['course']}\n")
    print(f"Registry status:\n  {status['registry_status']}\n")

    print("Step checklist:")
    for key, label in STEP_ORDER:
        step = status["steps"][key]
        mark = "x" if step["done"] else " "
        detail = step.get("details") or ""
        line = f"  [{mark}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)

    print(f"\nCompleted ({len(status['completed_steps'])}):")
    for name in status["completed_steps"]:
        print(f"  - {name}")
    if not status["completed_steps"]:
        print("  (none)")

    print(f"\nMissing ({len(status['missing_steps'])}):")
    for name in status["missing_steps"]:
        print(f"  - {name}")
    if not status["missing_steps"]:
        print("  (none)")

    print(f"\nWarnings:\n{_format_warnings(status['warnings'])}\n")

    action = status["next_action"]
    print("Next recommended action:")
    print(f"  {action['label']} ({action['key']})")
    print(f"  Reason: {action['reason']}")
    if action.get("gui_hint"):
        print(f"  Hint: {action['gui_hint']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
