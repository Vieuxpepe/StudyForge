#!/usr/bin/env python3
"""
Verify course backup zips and preview or perform safe restore to a new folder.

Examples:
    python scripts/verify_backup.py --file "C:\\path\\to\\backup.zip"
    python scripts/verify_backup.py --file "C:\\path\\to\\backup.zip" --preview-restore
    python scripts/verify_backup.py --file "C:\\path\\to\\backup.zip" --restore-as ECA1010_Restored_Test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.backup_restore import (  # noqa: E402
    InvalidBackupError,
    RestoreTargetExistsError,
    UnsafeZipPathError,
    format_verification_summary,
    preview_restore_backup,
    restore_backup_to_new_course,
    verify_backup,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a course backup zip and optionally preview or restore safely."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to backup .zip file.",
    )
    parser.add_argument(
        "--preview-restore",
        action="store_true",
        help="Dry-run restore preview (does not extract).",
    )
    parser.add_argument(
        "--restore-as",
        metavar="COURSE_FOLDER",
        help="Restore backup into a new course folder name (never overwrites).",
    )
    return parser


def _print_preview(preview: dict) -> None:
    print(format_verification_summary(preview.get("verification") or {}))
    print()
    print(f"Target path:\n{preview.get('target_path', '')}\n")
    print(f"Target exists:\n{str(preview.get('target_exists', False)).lower()}\n")
    print(f"Would restore files:\n{preview.get('would_restore_files', 0)}\n")
    print(f"Safe to restore:\n{str(preview.get('safe_to_restore', False)).lower()}\n")
    warnings = preview.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def _print_restore_summary(summary: dict) -> None:
    print("Restore complete.\n")
    print(f"Course folder:\n{summary.get('course_folder', '')}\n")
    if summary.get("source_course_folder") != summary.get("course_folder"):
        print(f"Source course folder:\n{summary.get('source_course_folder', '')}\n")
    print(f"Files restored:\n{summary.get('files_restored', 0)}\n")
    print(f"Target path:\n{summary.get('target_path', '')}\n")
    warnings = summary.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    backup_path = Path(args.file)

    try:
        if args.restore_as is not None:
            summary = restore_backup_to_new_course(
                backup_path,
                target_course_name=args.restore_as,
            )
            _print_restore_summary(summary)
            return 0

        if args.preview_restore:
            preview = preview_restore_backup(backup_path)
            _print_preview(preview)
            return 0

        report = verify_backup(backup_path)
        print(format_verification_summary(report))
        print()
        return 0 if report.get("status") != "failed" else 1

    except RestoreTargetExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except InvalidBackupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except UnsafeZipPathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
