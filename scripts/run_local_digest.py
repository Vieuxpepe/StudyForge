#!/usr/bin/env python3
"""
Run local LM Studio digests for each chunk of a registered source.

Examples:
    python scripts/check_lm_studio.py
    python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1
    python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.digest_jobs import (  # noqa: E402
    DEFAULT_DIGEST_MAX_TOKENS,
    DigestOutputExistsError,
    LMStudioNotAvailableError,
    SourceNotChunkedError,
    run_local_digest_for_source,
)
from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.llm.lm_studio_client import (  # noqa: E402
    DEFAULT_BASE_URL,
    LMStudioAPIError,
    LMStudioConnectionError,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local LM Studio digests for a chunked source."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--source-id", required=True, help="Source ID (e.g. SRC-0001).")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"LM Studio API URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument("--model", help="Model ID (default: first from /models).")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_DIGEST_MAX_TOKENS,
        help=f"Max tokens per chunk completion (default: {DEFAULT_DIGEST_MAX_TOKENS}).",
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        help="Process only the first N chunks (for testing).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing digest files for this source.",
    )
    return parser


def _format_warnings(warnings: list[str]) -> str:
    if not warnings:
        return "None"
    return "\n".join(f"  - {w}" for w in warnings)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        summary = run_local_digest_for_source(
            course_name=args.course,
            source_id=args.source_id,
            base_url=args.base_url,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            limit_chunks=args.limit_chunks,
            overwrite=args.overwrite,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotChunkedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except DigestOutputExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except LMStudioNotAvailableError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (LMStudioConnectionError, LMStudioAPIError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    label = (
        "Local digest complete."
        if summary["status"] == "local_digest_complete"
        else "Local digest finished with issues."
    )
    print(f"{label}\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Model:\n{summary['model']}\n")
    print(
        f"Chunks processed:\n"
        f"{summary['chunk_count_processed']} / {summary['chunk_count_total']}\n"
    )
    print(f"Combined digest:\n{summary['combined_digest_path']}\n")
    print(f"Log:\n{summary['log_path']}\n")
    print(f"Warnings:\n{_format_warnings(summary['warnings'])}")
    return 0 if summary["chunk_count_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
