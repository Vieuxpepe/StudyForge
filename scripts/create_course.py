#!/usr/bin/env python3
"""
Create a new StudyForge course by copying the course template.

Example:
    python scripts/create_course.py --code ECA1010 --name "Microeconomics"
    python scripts/create_course.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow imports from src/ when running as a script
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.courses import (  # noqa: E402
    CourseAlreadyExistsError,
    CourseValidationError,
    create_course,
    list_courses,
)
from studyforge.core.paths import find_project_root  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new StudyForge course from the template."
    )
    parser.add_argument(
        "--code",
        help="Course code (e.g. ECA1010). Required unless --list is used.",
    )
    parser.add_argument(
        "--name",
        help='Course name (e.g. "Microeconomics"). Required unless --list is used.',
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List existing courses and exit.",
    )
    return parser


def _cmd_list() -> int:
    root = find_project_root()
    courses = list_courses(root)
    print(f"StudyForge courses ({len(courses)}):\n")
    if not courses:
        print("  (none — create one with --code and --name)")
        return 0
    for course_path in courses:
        print(f"  - {course_path.name}")
    return 0


def _cmd_create(code: str, name: str) -> int:
    try:
        course_path = create_course(code, name)
    except CourseAlreadyExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except CourseValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Course created successfully.\n")
    print(f"  Code:   {code.strip()}")
    print(f"  Name:   {name.strip()}")
    print(f"  Folder: {course_path.name}")
    print(f"  Path:   {course_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return _cmd_list()

    if not args.code or not args.name:
        parser.error("--code and --name are required unless you use --list")

    return _cmd_create(args.code, args.name)


if __name__ == "__main__":
    raise SystemExit(main())
