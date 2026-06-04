#!/usr/bin/env python3
"""
Check connection to LM Studio's local OpenAI-compatible API.

Examples:
    python scripts/check_lm_studio.py
    python scripts/check_lm_studio.py --base-url http://localhost:1234/v1
    python scripts/check_lm_studio.py --base-url "http://192.168.2.152:1234/v1"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.llm.lm_studio_client import (  # noqa: E402
    DEFAULT_BASE_URL,
    check_lm_studio_connection,
    choose_default_model,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check LM Studio API connection.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"LM Studio API base URL (default: {DEFAULT_BASE_URL})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    base_url = args.base_url
    result = check_lm_studio_connection(base_url=base_url)

    print("LM Studio connection check\n")
    print(f"  Checking: {base_url}")
    print(f"  Base URL: {result['base_url']}")
    print(f"  OK:       {result['ok']}")

    if result["ok"]:
        models = result["models"]
        print(f"  Models:   {len(models)} available")
        for model_id in models:
            print(f"    - {model_id}")
        default = choose_default_model(result)
        if default:
            print(f"\n  Default model (first listed): {default}")
        return 0

    print(f"  Error:    {result['error']}")
    print("\nMake sure LM Studio is running and a model is loaded.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
