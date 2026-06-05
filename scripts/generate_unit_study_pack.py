#!/usr/bin/env python3
"""
Generate unit study pack files from the latest imported unit synthesis (no AI).

Examples:
    python scripts/generate_unit_study_pack.py --course ECA1010_Microeconomics --unit-id UNIT-0001
    python scripts/generate_unit_study_pack.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --overwrite
    python scripts/generate_unit_study_pack.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --diagnose-only --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.study_units import StudyUnitNotFoundError  # noqa: E402
from studyforge.study.unit_study_pack import (  # noqa: E402
    UnitStudyPackOutputExistsError,
    UnitSynthesisNotFoundError,
    _UNIT_SECTION_HEADINGS,
    diagnose_unit_study_pack,
    generate_unit_study_pack,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate unit study pack from latest imported unit synthesis."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--unit-id", required=True, help="Study unit ID, e.g. UNIT-0001.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing unit study pack output files.",
    )
    parser.add_argument(
        "--diagnose-only",
        action="store_true",
        help="Analyze unit synthesis sections without writing files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON summary to stdout.",
    )
    return parser


def _print_quality(quality: dict) -> None:
    print(f"Quality:\n{quality.get('quality_status', 'unknown')}\n")
    found = quality.get("found_sections") or []
    missing = quality.get("missing_sections") or []
    if found:
        print("Found sections:")
        for key in found:
            label = _UNIT_SECTION_HEADINGS.get(key, key)
            count = quality.get("section_word_counts", {}).get(key, 0)
            print(f"  - {key} ({label}): {count} words")
        print()
    if missing:
        print("Missing sections:")
        for key in missing:
            print(f"  - {key} ({_UNIT_SECTION_HEADINGS.get(key, key)})")
        print()
    print(f"Total extracted words:\n{quality.get('total_extracted_words', 0)}\n")
    for warning in quality.get("warnings") or []:
        print(f"Warning: {warning}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.diagnose_only:
            result = diagnose_unit_study_pack(args.course, args.unit_id)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Unit study pack diagnosis\n")
                print(f"Course:\n{result['course']}\n")
                print(f"Unit:\n{result['unit_id']}\n")
                print(f"Based on:\n{result.get('based_on_unit_synthesis_id', '')}\n")
                _print_quality(result.get("quality", {}))
            return 0

        result = generate_unit_study_pack(
            args.course,
            args.unit_id,
            overwrite=args.overwrite,
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Unit study pack generated.\n")
            print(f"Course:\n{result['course']}\n")
            print(f"Unit:\n{result['unit_id']} — {result.get('title', '')}\n")
            print(f"Based on:\n{result.get('based_on_unit_synthesis_id', '')}\n")
            print(f"Quality:\n{result.get('quality_status', '')}\n")
            print(f"Flashcards:\n{result.get('flashcard_count', 0)}\n")
            print(f"Manifest:\n{result.get('manifest_path', '')}\n")
            if result.get("warnings"):
                print("Warnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")
        return 0

    except (
        CourseNotFoundError,
        StudyUnitNotFoundError,
        UnitSynthesisNotFoundError,
        UnitStudyPackOutputExistsError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
