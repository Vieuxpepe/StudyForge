#!/usr/bin/env python3
"""
Run one Pipeline Doctor recommended step (not autonomous).

Examples:
    python scripts/run_next_step.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/run_next_step.py --course ECA1010_Microeconomics --source-id SRC-0001 \\
        --base-url "http://192.168.2.152:1234/v1" --model "google/gemma-4-e4b"
    python scripts/run_next_step.py --course ECA1010_Microeconomics --source-id SRC-0001 --full-digest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.guided_workflow import (  # noqa: E402
    UnsupportedGuidedActionError,
    get_guided_next_action,
    run_guided_next_step,
)
from studyforge.core.sources import CourseNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one guided pipeline step (Pipeline Doctor next action)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--max-words", type=int, default=None)
    parser.add_argument("--overlap-words", type=int, default=None)
    parser.add_argument(
        "--full-digest",
        action="store_true",
        help="Digest all chunks (default: first chunk only).",
    )
    parser.add_argument("--only-needs-review", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    options: dict = {"overwrite": args.overwrite, "full_digest": args.full_digest}
    if args.base_url:
        options["base_url"] = args.base_url
    if args.model:
        options["model"] = args.model
    if args.max_tokens is not None:
        options["max_tokens"] = args.max_tokens
    if args.max_words is not None:
        options["max_words"] = args.max_words
    if args.overlap_words is not None:
        options["overlap_words"] = args.overlap_words
    if args.only_needs_review:
        options["only_needs_review"] = True

    try:
        guided = get_guided_next_action(args.course, args.source_id)
        print("Guided Workflow — next step\n")
        print(f"Action: {guided['label']} ({guided['key']})")
        print(f"Reason: {guided.get('reason', '')}\n")
        if guided.get("warning"):
            print(f"Note: {guided['warning']}\n")
        if not guided.get("can_run"):
            print("This step cannot be run automatically.")
            return 1

        result = run_guided_next_step(
            args.course,
            args.source_id,
            options=options,
        )
        print(f"Success: {result['message']}\n")
        summary = result.get("summary") or {}
        if summary:
            print("Summary:")
            print(json.dumps(summary, indent=2, default=str))
        return 0

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except UnsupportedGuidedActionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
