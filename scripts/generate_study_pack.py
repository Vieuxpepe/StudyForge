#!/usr/bin/env python3
"""
Generate study pack files from the latest imported final audit (no AI).

Examples:
    python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001 --overwrite
    python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001 --diagnose-only
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
    _SECTION_HEADINGS,
    diagnose_study_pack,
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
    parser.add_argument(
        "--diagnose-only",
        action="store_true",
        help="Analyze final audit sections without writing study pack files.",
    )
    return parser


def _print_quality_block(quality: dict) -> None:
    print(f"Quality:\n{quality.get('quality_status', 'unknown')}\n")
    found = quality.get("found_sections") or []
    missing = quality.get("missing_sections") or []
    placeholders = quality.get("placeholder_sections") or []
    if found:
        print("Found sections:")
        for key in found:
            label = _SECTION_HEADINGS.get(key, key)
            count = quality.get("section_word_counts", {}).get(key, 0)
            print(f"  - {key} ({label}): {count} words")
        print()
    if missing:
        print("Missing sections:")
        for key in missing:
            print(f"  - {key} ({_SECTION_HEADINGS.get(key, key)})")
        print()
    if placeholders:
        print("Thin sections (under 10 words):")
        for key in placeholders:
            print(f"  - {key} ({_SECTION_HEADINGS.get(key, key)})")
        print()
    print(f"Total extracted words:\n{quality.get('total_extracted_words', 0)}\n")
    warnings = quality.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def _print_diagnostic(report: dict) -> None:
    print("Study pack diagnostic\n")
    print(f"Source:\n{report['source_id']} - {report['title']}\n")
    print(f"Final audit:\n{report['based_on_final_audit_id']}\n")
    print(f"Audit file:\n{report.get('final_audit_path', '')}\n")
    _print_quality_block(report["quality"])
    extra = report.get("warnings") or []
    for warning in extra:
        if warning not in report["quality"].get("warnings", []):
            print(f"- {warning}")
    return None


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.diagnose_only:
            report = diagnose_study_pack(args.course, args.source_id)
            _print_diagnostic(report)
            return 0

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
    quality = summary.get("quality") or {}
    _print_quality_block(quality)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
