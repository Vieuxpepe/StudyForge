#!/usr/bin/env python3
"""
Add source material files to a StudyForge course.

Examples:
    python scripts/add_source.py --course ECA1010_Microeconomics --type textbook \\
        --file "C:\\Users\\you\\Downloads\\book.pdf" --title "Main Textbook"

    python scripts/add_source.py --course ECA1010_Microeconomics --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow imports from src/ when running as a script
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import (  # noqa: E402
    ALLOWED_SOURCE_TYPES,
    CourseNotFoundError,
    SourceFileError,
    SourceFileNotFoundError,
    SourceTypeError,
    add_source,
    get_source_registry_path,
    list_sources,
    resolve_course_path,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add or list source material for a StudyForge course."
    )
    parser.add_argument(
        "--course",
        required=True,
        help="Course folder name (e.g. ECA1010_Microeconomics).",
    )
    parser.add_argument(
        "--type",
        help=f"Source type: {', '.join(ALLOWED_SOURCE_TYPES)}",
    )
    parser.add_argument(
        "--file",
        help="Path to the file to copy into the course.",
    )
    parser.add_argument(
        "--title",
        help="Optional display title (defaults to the file name).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List registered sources for the course.",
    )
    return parser


def _cmd_list(course: str) -> int:
    try:
        course_path = resolve_course_path(course)
        sources = list_sources(course)
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Sources for {course_path.name} ({len(sources)}):\n")
    if not sources:
        print("  (none — add with --type and --file)")
        return 0

    for entry in sources:
        print(f"  {entry['id']}  [{entry['source_type']}]  {entry['title']}")
        print(f"    file: {entry.get('file_name', '')}")
        print(f"    path: {entry.get('stored_path', '')}")
        print()
    return 0


def _cmd_add(course: str, source_type: str, file_path: str, title: str | None) -> int:
    try:
        stored = add_source(
            course_name=course,
            source_type=source_type,
            file_path=Path(file_path),
            title=title,
        )
        course_path = resolve_course_path(course)
        registry_path = get_source_registry_path(course_path)
        stored_str = str(stored.resolve())
        entry = next(
            (e for e in list_sources(course) if e.get("stored_path") == stored_str),
            None,
        )
        source_id = entry["id"] if entry else "?"
        display_title = entry["title"] if entry else (title or Path(file_path).stem)
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceTypeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceFileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceFileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Source added successfully.\n")
    print(f"  ID:           {source_id}")
    print(f"  Title:        {display_title}")
    print(f"  Source type:  {source_type.strip().lower()}")
    print(f"  Copied file:  {stored}")
    print(f"  Registry:     {registry_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return _cmd_list(args.course)

    if not args.type or not args.file:
        parser.error("--type and --file are required unless you use --list")

    return _cmd_add(args.course, args.type, args.file, args.title)


if __name__ == "__main__":
    raise SystemExit(main())
