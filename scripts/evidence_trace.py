#!/usr/bin/env python3
"""
Evidence Trace Viewer v1 — inspect source → digest → audit chain.

Examples:
    python scripts/evidence_trace.py --course ECA1010_Microeconomics --source-id SRC-0001 --summary
    python scripts/evidence_trace.py --course ECA1010_Microeconomics --source-id SRC-0001 --chunks
    python scripts/evidence_trace.py --course ECA1010_Microeconomics --source-id SRC-0001 --chunk-id SRC-0001-CHUNK-0001
    python scripts/evidence_trace.py --course ECA1010_Microeconomics --source-id SRC-0001 --chunk-id SRC-0001-CHUNK-0001 --export
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
from studyforge.study.evidence_trace import (  # noqa: E402
    export_chunk_trace,
    get_chunk_trace,
    get_source_trace_summary,
    list_source_chunks,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect evidence chain for a source or chunk (deterministic, no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--summary", action="store_true", help="Show source trace summary.")
    parser.add_argument("--chunks", action="store_true", help="List chunks from manifest.")
    parser.add_argument("--chunk-id", help="Show trace for one chunk.")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export chunk trace Markdown (requires --chunk-id).",
    )
    return parser


def _print_summary(summary: dict) -> None:
    print(f"Evidence trace summary — {summary.get('course', '')}\n")
    print(f"Source: {summary.get('source_id', '')} — {summary.get('title', '')}")
    print(f"Registry status: {summary.get('registry_status', '')}\n")
    print("Available artifacts:")
    for key, value in (summary.get("available_artifacts") or {}).items():
        print(f"- {key}: {str(bool(value)).lower()}")
    print()
    paths = summary.get("paths") or {}
    if paths:
        print("Paths:")
        for key, value in paths.items():
            if value:
                print(f"- {key}: {value}")
        print()
    warnings = summary.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def _print_chunks(chunks: list[dict]) -> None:
    print(f"Chunks ({len(chunks)})\n")
    if not chunks:
        print("No chunks found.\n")
        return
    for chunk in chunks:
        print(
            f"- {chunk.get('chunk_id')} — pages {chunk.get('page_start')}–"
            f"{chunk.get('page_end')} — {chunk.get('word_count')} words"
        )
        print(f"  Path: {chunk.get('file_path', '')}")
    print()


def _print_chunk_trace(trace: dict) -> None:
    chunk_info = trace.get("chunk_info") or {}
    print(f"Evidence trace — {trace.get('chunk_id', '')}\n")
    print(f"Pages: {chunk_info.get('page_start')}–{chunk_info.get('page_end')}")
    print(f"Words: {chunk_info.get('word_count', 0)}\n")

    source_chunk = trace.get("source_chunk") or {}
    digest_chunk = trace.get("local_digest_chunk") or {}
    print(f"Source chunk: {source_chunk.get('path', '')}")
    print(f"Exists: {str(source_chunk.get('exists', False)).lower()}\n")
    print(f"Digest chunk: {digest_chunk.get('path', '')}")
    print(f"Exists: {str(digest_chunk.get('exists', False)).lower()}\n")

    print(f"Digest review mentions: {len(trace.get('digest_review_mentions') or [])}")
    print(f"Intermediate audit mentions: {len(trace.get('intermediate_audit_mentions') or [])}")
    print(f"Final audit mentions: {len(trace.get('final_audit_mentions') or [])}\n")

    warnings = trace.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.export:
            if not args.chunk_id:
                print("Error: --export requires --chunk-id", file=sys.stderr)
                return 1
            path = export_chunk_trace(args.course, args.source_id, args.chunk_id)
            trace = get_chunk_trace(args.course, args.source_id, args.chunk_id)
            _print_chunk_trace(trace)
            print(f"Exported:\n{path.resolve()}\n")
            return 0

        if args.chunk_id:
            trace = get_chunk_trace(args.course, args.source_id, args.chunk_id)
            _print_chunk_trace(trace)
            return 0

        if args.chunks:
            chunks = list_source_chunks(args.course, args.source_id)
            _print_chunks(chunks)
            return 0

        if args.summary or not (args.chunks or args.chunk_id):
            summary = get_source_trace_summary(args.course, args.source_id)
            _print_summary(summary)
            return 0

        print("Error: specify --summary, --chunks, or --chunk-id", file=sys.stderr)
        return 1

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
