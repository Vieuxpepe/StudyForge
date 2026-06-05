#!/usr/bin/env python3
"""
Unit Synthesis Packet v1 — export multi-source material for manual AI synthesis (no API).

Examples:
    python scripts/unit_synthesis_packet.py --course ECA1010_Microeconomics --unit-id UNIT-0001
    python scripts/unit_synthesis_packet.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --overwrite
    python scripts/unit_synthesis_packet.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --no-learning-state
    python scripts/unit_synthesis_packet.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --json
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
from studyforge.study.unit_synthesis_packet import (  # noqa: E402
    UnitSynthesisPacketExistsError,
    build_unit_synthesis_packet,
)
from studyforge.study.study_units import StudyUnitNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export unit synthesis packet for manual use with external AI (no API)."
    )
    parser.add_argument("--course", required=True, help="Course folder name.")
    parser.add_argument("--unit-id", required=True, help="Study unit ID, e.g. UNIT-0001.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing synthesis packet files.",
    )
    parser.add_argument(
        "--no-learning-state",
        action="store_true",
        help="Exclude mistakes, weak points, flashcards, and recall gaps.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print metadata JSON to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        result = build_unit_synthesis_packet(
            args.course,
            args.unit_id,
            include_learning_state=not args.no_learning_state,
            overwrite=args.overwrite,
        )
        if args.json:
            print(json.dumps(result["metadata"], indent=2, ensure_ascii=False))
        else:
            print(f"Unit: {result['unit_id']} — {result['unit_title']}")
            print(f"Sources: {result['source_count']}")
            print(f"Packet: {result['packet_path']}")
            if result.get("warnings"):
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")
        return 0

    except (
        CourseNotFoundError,
        StudyUnitNotFoundError,
        UnitSynthesisPacketExistsError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
