#!/usr/bin/env python3
"""
Extraction quality diagnostics — verify PDF text extraction before chunking/digesting.

Examples:
    python scripts/check_extraction_quality.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/check_extraction_quality.py --course ECA1010_Microeconomics --source-id SRC-0001 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.backup import format_bytes  # noqa: E402
from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.extraction.extraction_quality import run_extraction_quality_check  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze extracted PDF text quality (deterministic, no OCR/AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON report to stdout.",
    )
    return parser


def _print_report(report: dict) -> None:
    print("Extraction quality report\n")
    print(f"Course:\n{report.get('course', '')}\n")
    print(f"Source:\n{report.get('source_id', '')} - {report.get('title', '')}\n")
    print(f"Quality:\n{report.get('quality_status', 'unknown')}\n")
    print(f"Total pages:\n{report.get('total_pages', 0)}\n")
    print(f"Total words:\n{report.get('total_words', 0)}\n")
    print(f"Average words/page:\n{report.get('average_words_per_page', 0)}\n")
    print(f"Size (characters):\n{format_bytes(int(report.get('total_characters', 0)))}\n")

    warnings = report.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()

    print(f"Report JSON:\n{report.get('report_json_path', '')}\n")
    print(f"Report Markdown:\n{report.get('report_markdown_path', '')}\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        report = run_extraction_quality_check(args.course, args.source_id)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_report(report)
        return 0 if report.get("quality_status") != "failed" else 1

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
