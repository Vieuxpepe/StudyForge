#!/usr/bin/env python3
"""
Mistakes log v1 — list, add, update status, export Markdown.

Examples:
    python scripts/mistakes.py --course ECA1010_Microeconomics --list
    python scripts/mistakes.py --course ECA1010_Microeconomics --add --source-id SRC-0001 \\
        --question "What is CPI?" --answer "Consumer price" --why-wrong "Mixed terms"
    python scripts/mistakes.py --course ECA1010_Microeconomics --update-status MISTAKE-0001 --status mastered
    python scripts/mistakes.py --course ECA1010_Microeconomics --export
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.mistakes import (  # noqa: E402
    InvalidMistakeStatusError,
    MistakeNotFoundError,
    add_mistake,
    export_mistakes_markdown,
    list_mistakes,
    update_mistake_status,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage course mistakes log.")
    parser.add_argument("--course", required=True)
    parser.add_argument("--list", action="store_true", help="List all mistakes.")
    parser.add_argument("--export", action="store_true", help="Export Markdown.")
    parser.add_argument("--add", action="store_true", help="Add a mistake manually.")
    parser.add_argument("--source-id", help="Source ID for --add.")
    parser.add_argument("--question-id", default="", help="Optional question ID.")
    parser.add_argument("--question", help="Question text for --add.")
    parser.add_argument("--answer", default="", help="What you answered.")
    parser.add_argument("--correct-explanation", default="")
    parser.add_argument("--why-wrong", default="")
    parser.add_argument("--how-to-avoid", default="")
    parser.add_argument("--status", default="new", help="Status for --add.")
    parser.add_argument("--update-status", metavar="MISTAKE_ID", help="Update mistake status.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.list:
            mistakes = list_mistakes(args.course)
            if not mistakes:
                print("No mistakes recorded.")
                return 0
            print(f"Mistakes ({len(mistakes)}):\n")
            for entry in mistakes:
                print(f"{entry['mistake_id']} [{entry['status']}] — {entry['source_id']}")
                print(f"  Q: {entry['question'][:80]}")
                print(f"  A: {entry['user_answer'][:80]}\n")
            return 0

        if args.add:
            if not args.source_id or not args.question:
                print("Error: --add requires --source-id and --question.", file=sys.stderr)
                return 1
            result = add_mistake(
                args.course,
                args.source_id,
                args.question,
                args.answer,
                question_id=args.question_id or None,
                correct_explanation=args.correct_explanation or None,
                why_wrong=args.why_wrong or None,
                how_to_avoid=args.how_to_avoid or None,
                status=args.status,
            )
            print(f"Mistake added: {result['mistake_id']}")
            print(f"Log: {result['log_path']}\n")
            return 0

        if args.update_status:
            if not args.status:
                print("Error: --update-status requires --status.", file=sys.stderr)
                return 1
            result = update_mistake_status(
                args.course, args.update_status, args.status
            )
            print(f"Updated {result['mistake_id']} → {result['status']}\n")
            return 0

        if args.export:
            path = export_mistakes_markdown(args.course)
            mistakes = list_mistakes(args.course)
            print(f"Exported {len(mistakes)} mistake(s) to:\n{path}\n")
            return 0

        print("Error: specify --list, --add, --update-status, or --export.", file=sys.stderr)
        return 1

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (InvalidMistakeStatusError, MistakeNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
