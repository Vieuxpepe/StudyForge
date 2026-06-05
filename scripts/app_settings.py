#!/usr/bin/env python3
"""
Show or reset local app preferences (config/local_app_settings.json).

Examples:
    python scripts/app_settings.py --show
    python scripts/app_settings.py --reset
    python scripts/app_settings.py --set-lm-url "http://192.168.2.152:1234/v1" --set-model "google/gemma-4-e4b"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.app_settings import (  # noqa: E402
    get_app_settings_path,
    get_default_app_settings,
    load_app_settings,
    save_app_settings,
    update_app_settings,
    validate_app_settings,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage local StudyForge app settings (no API keys)."
    )
    parser.add_argument("--show", action="store_true", help="Print current settings JSON.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset settings file to defaults.",
    )
    parser.add_argument(
        "--set-lm-url",
        metavar="URL",
        help="Set LM Studio base URL.",
    )
    parser.add_argument(
        "--set-model",
        metavar="MODEL",
        help="Set default LM Studio model name.",
    )
    return parser


def _print_settings() -> int:
    settings = load_app_settings()
    path = get_app_settings_path()
    print(f"Settings file: {path}")
    print(json.dumps(settings, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.reset:
        path = save_app_settings(get_default_app_settings())
        print(f"Reset settings to defaults: {path}")
        return 0

    updates: dict = {}
    if args.set_lm_url:
        updates.setdefault("lm_studio", {})["base_url"] = args.set_lm_url
    if args.set_model:
        updates.setdefault("lm_studio", {})["default_model"] = args.set_model

    if updates:
        merged = update_app_settings(updates)
        errors = validate_app_settings(merged)
        if errors:
            for error in errors:
                print(f"Warning: {error}", file=sys.stderr)
        path = get_app_settings_path()
        print(f"Updated settings: {path}")
        print(json.dumps(merged, indent=2, ensure_ascii=False))
        return 0

    if args.show or len(sys.argv) == 1:
        return _print_settings()

    print("No action requested. Use --show, --reset, or --set-* options.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
