#!/usr/bin/env python3
"""
Export flashcards as Markdown, CSV, and Anki TSV from the latest final audit (no AI).

Examples:
    python scripts/export_flashcards.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/export_flashcards.py --course ECA1010_Microeconomics --source-id SRC-0001 --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError, resolve_course_path  # noqa: E402
from studyforge.study.flashcards import (  # noqa: E402
    FlashcardExportExistsError,
    export_flashcards_from_sections,
)
from studyforge.study.study_pack import (  # noqa: E402
    FinalAuditNotFoundError,
    extract_sections,
    get_latest_final_audit,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export flashcards from the latest final audit (Markdown, CSV, Anki TSV)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing flashcard export files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        course_path = resolve_course_path(args.course)
        final_audit = get_latest_final_audit(course_path, args.source_id)
        sections = extract_sections(final_audit["text"])
        summary = export_flashcards_from_sections(
            args.course,
            args.source_id,
            sections,
            overwrite=args.overwrite,
        )

        print("Flashcards exported.\n")
        print(f"Course: {summary['course']}\n")
        print(f"Source: {summary['source_id']} - {summary['title']}\n")
        print(f"Card count: {summary['flashcard_count']}\n")
        print(f"Markdown: {summary['markdown_path']}\n")
        print(f"CSV: {summary['csv_path']}\n")
        print(f"Anki TSV: {summary['anki_tsv_path']}\n")

        warnings = summary.get("warnings") or []
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
            print()

        return 0

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FinalAuditNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FlashcardExportExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
