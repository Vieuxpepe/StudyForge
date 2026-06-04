#!/usr/bin/env python3
"""
Export an intermediate audit packet for manual paste into Gemini / AI Studio.

Examples:
    python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1 --overwrite
    python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001 --only-needs-review --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.intermediate_packet import (  # noqa: E402
    LocalDigestNotFoundError,
    PacketOutputExistsError,
    build_intermediate_audit_packet,
)
from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export intermediate audit packet (Markdown + JSON)."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--source-id", required=True, help="Source ID (e.g. SRC-0001).")
    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        help="Include only the first N selected chunks.",
    )
    parser.add_argument(
        "--only-needs-review",
        action="store_true",
        help="Select chunks flagged by local digest review (fallback: all).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing packet Markdown and JSON.",
    )
    return parser


def _format_warnings(warnings: list[str]) -> str:
    if not warnings:
        return "None"
    return "\n".join(f"* {w}" for w in warnings)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        summary = build_intermediate_audit_packet(
            course_name=args.course,
            source_id=args.source_id,
            limit_chunks=args.limit_chunks,
            only_needs_review=args.only_needs_review,
            overwrite=args.overwrite,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except LocalDigestNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PacketOutputExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Intermediate audit packet exported.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Chunks included:\n{summary['selected_chunk_count']}\n")
    print(f"Packet:\n{summary['packet_path']}\n")
    print(f"JSON:\n{summary['packet_json_path']}\n")
    print(f"Warnings:\n\n{_format_warnings(summary['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
