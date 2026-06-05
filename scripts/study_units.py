#!/usr/bin/env python3
"""
Study Units v1 — group sources into named topics (organizational only, no AI).

Examples:
    python scripts/study_units.py --course ECA1010_Microeconomics --list
    python scripts/study_units.py --course ECA1010_Microeconomics --create \\
        --title "Inflation and CPI" --description "Quiz 2" \\
        --sources SRC-0001 SRC-0002 --tags quiz2 inflation
    python scripts/study_units.py --course ECA1010_Microeconomics --summary UNIT-0001
    python scripts/study_units.py --course ECA1010_Microeconomics --update UNIT-0001 --status completed
    python scripts/study_units.py --course ECA1010_Microeconomics --add-sources UNIT-0001 --sources SRC-0003
    python scripts/study_units.py --course ECA1010_Microeconomics --remove-sources UNIT-0001 --sources SRC-0002
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
from studyforge.study.study_units import (  # noqa: E402
    InvalidSourceIdError,
    InvalidStudyUnitStatusError,
    StudyUnitNotFoundError,
    add_sources_to_unit,
    create_study_unit,
    get_study_unit_summary,
    list_study_units,
    remove_sources_from_unit,
    update_study_unit,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage course study units (topic bundles)."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--list", action="store_true", help="List study units.")
    parser.add_argument("--create", action="store_true", help="Create a study unit.")
    parser.add_argument("--title", help="Title for --create or --update.")
    parser.add_argument("--description", default="", help="Description text.")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=[],
        help="Source IDs for --create, --add-sources, or --remove-sources.",
    )
    parser.add_argument(
        "--tags",
        nargs="*",
        default=[],
        help="Tags for --create (space-separated).",
    )
    parser.add_argument("--summary", metavar="UNIT_ID", help="Show unit summary.")
    parser.add_argument("--update", metavar="UNIT_ID", help="Update a study unit.")
    parser.add_argument("--status", help="New status for --update.")
    parser.add_argument(
        "--add-sources",
        metavar="UNIT_ID",
        help="Add sources to an existing unit.",
    )
    parser.add_argument(
        "--remove-sources",
        metavar="UNIT_ID",
        help="Remove sources from an existing unit.",
    )
    return parser


def _print_units(units: list[dict]) -> None:
    if not units:
        print("No study units defined.")
        return
    print(f"Study units ({len(units)}):\n")
    for unit in units:
        sources = ", ".join(unit.get("source_ids", [])) or "(none)"
        tags = ", ".join(unit.get("tags", [])) or "(none)"
        print(f"{unit['unit_id']} [{unit.get('status', 'active')}] — {unit['title']}")
        if unit.get("description"):
            print(f"  Description: {unit['description']}")
        print(f"  Sources: {sources}")
        print(f"  Tags: {tags}\n")


def _print_summary(summary: dict) -> None:
    print(f"Study unit: {summary['unit_id']} — {summary['title']}")
    if summary.get("description"):
        print(f"Description: {summary['description']}")
    print(f"Status: {summary.get('status', 'active')}")
    print(
        f"Sources: {summary.get('source_count', 0)} "
        f"(ready: {summary.get('ready_sources', 0)}, "
        f"incomplete: {summary.get('incomplete_sources', 0)})"
    )
    action = summary.get("recommended_action") or {}
    print(f"Recommended: {action.get('label', '')} — {action.get('reason', '')}")
    print("\nSources:")
    for source in summary.get("sources") or []:
        flags = []
        if source.get("has_study_pack"):
            flags.append("study_pack")
        if source.get("has_final_audit"):
            flags.append("final_audit")
        if source.get("has_active_recall"):
            flags.append("active_recall_file")
        flag_text = ", ".join(flags) if flags else "no outputs yet"
        print(
            f"  - {source['source_id']}: {source.get('title', '')} "
            f"[{source.get('status', '')}] ({flag_text})"
        )
    for warning in summary.get("warnings") or []:
        print(f"Warning: {warning}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.list:
            _print_units(list_study_units(args.course))
            return 0

        if args.create:
            if not args.title:
                print("Error: --create requires --title.", file=sys.stderr)
                return 1
            unit = create_study_unit(
                args.course,
                args.title,
                description=args.description or None,
                source_ids=args.sources,
                tags=args.tags,
            )
            print(f"Created {unit['unit_id']}: {unit['title']}")
            return 0

        if args.summary:
            summary = get_study_unit_summary(args.course, args.summary)
            _print_summary(summary)
            return 0

        if args.update:
            unit = update_study_unit(
                args.course,
                args.update,
                title=args.title,
                description=args.description if args.description else None,
                status=args.status,
            )
            print(f"Updated {unit['unit_id']}: {unit['title']} [{unit['status']}]")
            return 0

        if args.add_sources:
            if not args.sources:
                print("Error: --add-sources requires --sources.", file=sys.stderr)
                return 1
            unit = add_sources_to_unit(
                args.course, args.add_sources, args.sources
            )
            print(f"Updated {unit['unit_id']}: sources = {', '.join(unit['source_ids'])}")
            return 0

        if args.remove_sources:
            if not args.sources:
                print("Error: --remove-sources requires --sources.", file=sys.stderr)
                return 1
            unit = remove_sources_from_unit(
                args.course, args.remove_sources, args.sources
            )
            print(f"Updated {unit['unit_id']}: sources = {', '.join(unit['source_ids'])}")
            return 0

        print(
            "No action requested. Use --list, --create, --summary, --update, "
            "--add-sources, or --remove-sources.",
            file=sys.stderr,
        )
        return 1

    except (
        CourseNotFoundError,
        StudyUnitNotFoundError,
        InvalidSourceIdError,
        InvalidStudyUnitStatusError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
