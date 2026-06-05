#!/usr/bin/env python3
"""
Course Backup v1 — create local zip archives of gitignored course data.

Examples:
    python scripts/backup_course.py --course ECA1010_Microeconomics
    python scripts/backup_course.py --course ECA1010_Microeconomics --no-sources
    python scripts/backup_course.py --course ECA1010_Microeconomics --output-dir "D:\\StudyForge_Backups"
    python scripts/backup_course.py --course ECA1010_Microeconomics --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.backup import (  # noqa: E402
    BackupExistsError,
    create_course_backup,
    format_bytes,
    list_course_backups,
)
from studyforge.core.sources import CourseNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a local zip backup of a course folder (no cloud upload)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument(
        "--no-sources",
        action="store_true",
        help="Exclude 01_Source_Material/ (original PDFs) for a smaller backup.",
    )
    parser.add_argument(
        "--output-dir",
        help="Custom output directory (default: course 08_App_Data/exports/backups/).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace backup if the same filename already exists.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List existing backups for the course.",
    )
    return parser


def _print_backup_summary(summary: dict) -> None:
    print("Backup created.\n")
    print(f"Course:\n{summary.get('course', '')}\n")
    print(f"Include sources:\n{str(summary.get('include_sources', True)).lower()}\n")
    print(f"Files:\n{summary.get('file_count', 0)}\n")
    print(f"Size:\n{format_bytes(int(summary.get('total_bytes', 0)))}\n")
    print(f"Backup:\n{summary.get('backup_path', '')}\n")
    warnings = summary.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def _print_backup_list(backups: list[dict]) -> None:
    print(f"Backups ({len(backups)})\n")
    if not backups:
        print("No backups found.\n")
        return
    for entry in backups:
        print(f"- {entry.get('file_name', '')}")
        print(f"  Modified: {entry.get('modified', '')}")
        print(f"  Size: {format_bytes(int(entry.get('size_bytes', 0)))}")
        print(f"  Path: {entry.get('path', '')}")
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(args.output_dir) if args.output_dir else None

    try:
        if args.list:
            backups = list_course_backups(
                args.course,
                backup_dir=output_dir,
            )
            _print_backup_list(backups)
            return 0

        summary = create_course_backup(
            args.course,
            include_sources=not args.no_sources,
            overwrite=args.overwrite,
            output_dir=output_dir,
        )
        _print_backup_summary(summary)
        return 0

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except BackupExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
