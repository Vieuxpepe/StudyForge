#!/usr/bin/env python3
"""
Rule-based quality review for local LM Studio digests (no AI).

Example:
    python scripts/review_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.digest_review import review_local_digest_for_source  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review local digest quality with deterministic rules."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--source-id", required=True, help="Source ID (e.g. SRC-0001).")
    parser.add_argument(
        "--min-words",
        type=int,
        default=200,
        help="Minimum word count before flagging a digest as very short (default: 200).",
    )
    return parser


def _format_warnings(warnings: list[str]) -> str:
    if not warnings:
        return "None"
    return "\n".join(f"* {w}" for w in warnings)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        summary = review_local_digest_for_source(
            course_name=args.course,
            source_id=args.source_id,
            min_words=args.min_words,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Local digest review complete.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Overall status:\n{summary['overall_status']}\n")
    print(f"Digests OK:\n{summary['digests_ok']}\n")
    print(f"Digests needing review:\n{summary['digests_needing_review']}\n")
    print(f"Report:\n{summary['report_path_md']}\n")
    print(f"JSON:\n{summary['report_path_json']}\n")
    print(f"Warnings:\n\n{_format_warnings(summary['warnings'])}")
    return 0 if summary["overall_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
