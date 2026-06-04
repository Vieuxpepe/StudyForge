#!/usr/bin/env python3
"""
Chunk extracted source text into page-aware source packets.

Examples:
    python scripts/chunk_source.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/chunk_source.py --course ECA1010_Microeconomics --source-id SRC-0001 \\
        --max-words 1000 --overlap-words 100 --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.chunking_jobs import (  # noqa: E402
    ChunkOutputExistsError,
    SourceNotExtractedError,
    chunk_registered_source,
)
from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chunk extracted Markdown for a registered source."
    )
    parser.add_argument(
        "--course",
        required=True,
        help="Course folder name (e.g. ECA1010_Microeconomics).",
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="Source ID (e.g. SRC-0001).",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=1200,
        help="Target maximum words per chunk (default: 1200).",
    )
    parser.add_argument(
        "--overlap-words",
        type=int,
        default=150,
        help="Words repeated from the previous chunk (default: 150).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing chunk files and manifest for this source.",
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
        summary = chunk_registered_source(
            course_name=args.course,
            source_id=args.source_id,
            max_words=args.max_words,
            overlap_words=args.overlap_words,
            overwrite=args.overwrite,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotExtractedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ChunkOutputExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Chunking complete.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Chunks:\n{summary['chunk_count']}\n")
    print(f"Manifest:\n{summary['chunk_manifest_path']}\n")
    print(f"Chunk folder:\n{summary['chunk_folder']}\n")
    print(f"Warnings:\n{_format_warnings(summary['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
