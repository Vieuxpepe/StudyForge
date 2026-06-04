#!/usr/bin/env python3
"""
Normalize final audit headings for Study Pack (deterministic, no AI).

Examples:
    python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001
    python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --overwrite
    python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --import-as-new-version --overwrite
    python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --export-repair-packet --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.final_audit_normalizer import (  # noqa: E402
    NormalizedAuditExistsError,
    RepairPacketExistsError,
    build_final_audit_repair_packet,
    normalize_latest_final_audit,
)
from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.study_pack import FinalAuditNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize final audit headings for Study Pack."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--import-as-new-version",
        action="store_true",
        help="Import normalized audit as a new final audit version.",
    )
    parser.add_argument(
        "--export-repair-packet",
        action="store_true",
        help="Export manual repair packet only (no normalization).",
    )
    parser.add_argument(
        "--audit-version",
        type=int,
        default=None,
        help="Use a specific final audit version (e.g. 1) instead of latest.",
    )
    return parser


def _print_normalization_summary(summary: dict) -> None:
    print("Final audit normalization\n")
    print(f"Latest final audit:\n{summary['source_final_audit_id']}\n")
    print(f"Quality:\n{summary['quality_status']}\n")
    print(f"Mapped headings count:\n{summary['mapped_count']}\n")
    if summary.get("missing_headings"):
        print("Missing headings:")
        for heading in summary["missing_headings"]:
            print(f"  - {heading}")
        print()
    if summary.get("mapped_headings"):
        print("Mapped headings:")
        for original, expected in summary["mapped_headings"].items():
            print(f"  - {original} -> {expected}")
        print()
    print(f"Normalized file:\n{summary['normalized_path']}\n")
    print(f"Report:\n{summary['report_path']}\n")
    if summary.get("imported_audit_id"):
        print(f"Imported new version:\n{summary['imported_audit_id']}\n")
        print(f"Saved at:\n{summary['imported_path']}\n")
    warnings = summary.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.export_repair_packet:
            summary = build_final_audit_repair_packet(
                args.course,
                args.source_id,
                overwrite=args.overwrite,
                audit_version=args.audit_version,
            )
            print("Final audit repair packet exported.\n")
            print(f"Source:\n{summary['source_id']} - {summary['title']}\n")
            print(f"Based on:\n{summary['source_final_audit_id']}\n")
            print(f"Repair packet:\n{summary['repair_packet_path']}\n")
            return 0

        summary = normalize_latest_final_audit(
            args.course,
            args.source_id,
            overwrite=args.overwrite,
            import_as_new_version=args.import_as_new_version,
            audit_version=args.audit_version,
        )
        _print_normalization_summary(summary)
        return 0

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SourceNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FinalAuditNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (NormalizedAuditExistsError, RepairPacketExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
