#!/usr/bin/env python3
"""
Import a manual intermediate audit (e.g. from Gemini) into StudyForge.

Examples:
    python scripts/import_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\\path\\audit.md"
    python scripts/import_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --text "Audit content"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.intermediate_import import (  # noqa: E402
    AuditInputError,
    EmptyAuditError,
    LocalDigestNotReadyError,
    import_intermediate_audit,
)
from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import a manual intermediate audit (versioned storage)."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--source-id", required=True, help="Source ID (e.g. SRC-0001).")
    parser.add_argument("--file", help="Path to audit Markdown file.")
    parser.add_argument("--text", help="Inline audit text.")
    parser.add_argument(
        "--auditor-name",
        default="Gemini",
        help='Name of the auditor (default: "Gemini").',
    )
    parser.add_argument("--notes", help="Optional notes about this import.")
    return parser


def _format_warnings(warnings: list[str]) -> str:
    if not warnings:
        return "None"
    return "\n".join(f"  - {w}" for w in warnings)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.file and args.text:
        print("Error: Provide only one of --file or --text.", file=sys.stderr)
        return 1
    if not args.file and not args.text:
        print("Error: Provide --file or --text.", file=sys.stderr)
        return 1

    try:
        summary = import_intermediate_audit(
            course_name=args.course,
            source_id=args.source_id,
            audit_text=args.text,
            audit_file=Path(args.file) if args.file else None,
            auditor_name=args.auditor_name,
            notes=args.notes,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except LocalDigestNotReadyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except AuditInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except EmptyAuditError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Intermediate audit imported.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Audit ID:\n{summary['audit_id']}\n")
    print(f"Auditor:\n{summary['auditor_name']}\n")
    print(f"Saved:\n{summary['saved_path']}\n")
    print(f"Registry:\n{summary['registry_path']}\n")
    if summary.get("warnings"):
        print(f"Warnings:\n{_format_warnings(summary['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
