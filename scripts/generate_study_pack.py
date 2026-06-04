#!/usr/bin/env python3
"""
Generate study pack files from the latest imported final audit (no AI).

Examples:
    python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001 --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.study_pack import (  # noqa: E402
    FinalAuditNotFoundError,
    StudyPackOutputExistsError,
    generate_study_pack,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate study pack files from the latest final audit."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing study pack output files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        summary = generate_study_pack(
            args.course,
            args.source_id,
            overwrite=args.overwrite,
        )
    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FinalAuditNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except StudyPackOutputExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Study pack generated.\n")
    print(f"Course:\n{summary['course']}\n")
    print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
    print(f"Based on:\n{summary['based_on_final_audit_id']}\n")
    print("Outputs:\n")
    outputs = summary.get("outputs", {})
    labels = {
        "final_study_guide": "Final study guide",
        "flashcards": "Flashcards",
        "formula_sheet": "Formula sheet",
        "practice_quiz": "Practice quiz",
        "active_recall": "Active recall",
        "weak_points_seed": "Weak points seed",
    }
    for key, label in labels.items():
        print(f"* {label}: {outputs.get(key, '')}")
    print(f"\nManifest:\n{summary.get('manifest_path', '')}\n")
    if summary.get("warnings"):
        print("Warnings:")
        for warning in summary["warnings"]:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
