#!/usr/bin/env python3
"""
Import a manual unit synthesis (e.g. from ChatGPT/Gemini) into StudyForge.

Examples:
    python scripts/import_unit_synthesis.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --file "C:\\path\\unit_synthesis.md"
    python scripts/import_unit_synthesis.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --text "# Unit Synthesis\\n..."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.study_units import StudyUnitNotFoundError  # noqa: E402
from studyforge.study.unit_synthesis_import import (  # noqa: E402
    EmptySynthesisError,
    SynthesisInputError,
    import_unit_synthesis,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import a manual unit synthesis (versioned storage, no API)."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--unit-id", required=True, help="Study unit ID, e.g. UNIT-0001.")
    parser.add_argument("--file", help="Path to synthesis Markdown file.")
    parser.add_argument("--text", help="Inline synthesis text.")
    parser.add_argument(
        "--synthesizer-name",
        default="ChatGPT",
        help='Name of the external synthesizer (default: "ChatGPT").',
    )
    parser.add_argument("--notes", help="Optional notes about this import.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.file and args.text:
        print("Error: Provide only one of --file or --text.", file=sys.stderr)
        return 1
    if not args.file and not args.text:
        print("Error: Provide --file or --text.", file=sys.stderr)
        return 1

    try:
        summary = import_unit_synthesis(
            course_name=args.course,
            unit_id=args.unit_id,
            synthesis_text=args.text,
            synthesis_file=Path(args.file) if args.file else None,
            synthesizer_name=args.synthesizer_name,
            notes=args.notes,
        )
    except (
        CourseNotFoundError,
        StudyUnitNotFoundError,
        SynthesisInputError,
        EmptySynthesisError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Unit synthesis imported.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Unit:\n{summary['unit_id']} — {summary.get('unit_title', '')}\n")
    print(f"Synthesis ID:\n{summary['synthesis_id']}\n")
    print(f"Quality:\n{summary.get('quality_status', '')}\n")
    print(f"Saved:\n{summary['file_path']}\n")
    print(f"Registry:\n{summary['registry_path']}\n")
    if summary.get("warnings"):
        print("Warnings:")
        for warning in summary["warnings"]:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
