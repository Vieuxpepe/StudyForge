#!/usr/bin/env python3
"""
Run automated intermediate audit via Google AI (Gemma 4 on Gemini API).

Requires GOOGLE_API_KEY or config/local_secrets.json (see local_secrets.example.json).

Examples:
    python scripts/run_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/run_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --model gemma-4-31b-it --only-needs-review
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.intermediate_audit_jobs import run_intermediate_audit_for_source  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.llm.google_genai_client import (  # noqa: E402
    DEFAULT_GEMMA_4_26B_MODEL,
    DEFAULT_GEMMA_4_31B_MODEL,
    GoogleGenAIAPIError,
    GoogleGenAIConfigError,
    GoogleGenAIConnectionError,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run intermediate audit with Google AI and import the result."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--model",
        default=DEFAULT_GEMMA_4_26B_MODEL,
        help=f"Google AI model id (default: {DEFAULT_GEMMA_4_26B_MODEL}; also {DEFAULT_GEMMA_4_31B_MODEL})",
    )
    parser.add_argument("--api-key", help="Override API key (else env or local_secrets.json)")
    parser.add_argument("--limit-chunks", type=int, default=None)
    parser.add_argument("--only-needs-review", action="store_true")
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=4.0,
        help="Seconds between API calls (rate limit; 0 to disable)",
    )
    parser.add_argument("--notes", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        summary = run_intermediate_audit_for_source(
            args.course,
            args.source_id,
            model=args.model,
            api_key=args.api_key,
            limit_chunks=args.limit_chunks,
            only_needs_review=args.only_needs_review,
            max_output_tokens=args.max_output_tokens,
            request_interval_seconds=args.request_interval,
            notes=args.notes,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except GoogleGenAIConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (GoogleGenAIConnectionError, GoogleGenAIAPIError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Intermediate audit imported.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Model:\n{summary['model']}\n")
    print(f"Chunks audited:\n{summary['chunk_count']}\n")
    print(f"Saved:\n{summary.get('saved_path', '')}\n")
    if summary.get("warnings"):
        print("Warnings:")
        for w in summary["warnings"]:
            print(f"  - {w}")
    return 0 if summary.get("status") == "imported" else 1


if __name__ == "__main__":
    raise SystemExit(main())
