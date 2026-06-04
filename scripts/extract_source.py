#!/usr/bin/env python3
"""
Extract text from a registered PDF source in a StudyForge course.

Example:
    python scripts/extract_source.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/extract_source.py --course ECA1010_Microeconomics --source-id SRC-0001 --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import (  # noqa: E402
    ExtractionOutputExistsError,
    NotPdfSourceError,
    SourceNotFoundError,
    extract_registered_source,
)
from studyforge.core.sources import (  # noqa: E402
    CourseNotFoundError,
    SourceFileNotFoundError,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract text from a registered PDF source."
    )
    parser.add_argument(
        "--course",
        required=True,
        help="Course folder name (e.g. ECA1010_Microeconomics).",
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="Source ID from source_registry.json (e.g. SRC-0001).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing extracted text and log files.",
    )
    return parser


def _format_warnings(warnings: list[str]) -> str:
    if not warnings:
        return "None"
    return "\n".join(f"  - {w}" for w in warnings)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        summary = extract_registered_source(
            course_name=args.course,
            source_id=args.source_id,
            overwrite=args.overwrite,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NotPdfSourceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceFileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ExtractionOutputExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError, RuntimeError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Extraction complete.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Pages:\n{summary['total_pages']}\n")
    print(f"Words:\n{summary['total_words']}\n")
    print(f"Extracted text:\n{summary['extracted_text_path']}\n")
    print(f"Extraction log:\n{summary['extraction_log_path']}\n")
    print(f"Warnings:\n{_format_warnings(summary['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
