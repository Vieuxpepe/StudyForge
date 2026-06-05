"""
Course backup / export v1 — local zip archives (no cloud, no encryption).
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import CourseNotFoundError, resolve_course_path

APP_DATA_DIR = Path("08_App_Data")
BACKUP_SUBDIR = APP_DATA_DIR / "exports" / "backups"
BACKUP_INFO_FILENAME = "STUDYFORGE_BACKUP_INFO.md"

_EXCLUDED_DIR_NAMES = frozenset({"__pycache__"})
_EXCLUDED_FILE_NAMES = frozenset({".DS_Store"})
_EXCLUDED_SUFFIXES = (".tmp", ".bak", ".backup")
_SOURCE_MATERIAL_DIR = "01_Source_Material"


class BackupExistsError(Exception):
    """Raised when a backup file exists and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _backup_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S")


def _safe_course_token(course_name: str) -> str:
    """Keep letters, numbers, underscore, hyphen for backup filenames."""
    token = "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_"
        for ch in course_name.strip()
    )
    return token.strip("_") or "course"


def get_course_backup_dir(course_path: Path) -> Path:
    """Return ``08_App_Data/exports/backups/`` for a course."""
    return course_path / BACKUP_SUBDIR


def build_backup_name(course_name: str, timestamp: str | None = None) -> str:
    """
    Build a safe backup zip filename.

    Example: ``ECA1010_Microeconomics_backup_2026-06-04_153000.zip``
    """
    stamp = timestamp or _backup_timestamp()
    safe_stamp = stamp.replace(":", "-").replace(" ", "_")
    return f"{_safe_course_token(course_name)}_backup_{safe_stamp}.zip"


def _is_under_exports_backups(path: Path) -> bool:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "exports" and index + 1 < len(parts) and parts[index + 1] == "backups":
            return True
    return False


def should_exclude_from_backup(
    path: Path,
    include_sources: bool = True,
) -> bool:
    """
    Return True if ``path`` should not be included in a course backup.

    Excludes cache/temp files, existing backup zips, and optionally source PDFs.
    """
    if not path.is_file():
        return True

    if path.name in _EXCLUDED_FILE_NAMES:
        return True

    lower_name = path.name.lower()
    if lower_name.endswith(_EXCLUDED_SUFFIXES):
        return True

    if path.suffix.lower() == ".zip" and _is_under_exports_backups(path):
        return True

    if _EXCLUDED_DIR_NAMES & set(path.parts):
        return True

    if not include_sources and _SOURCE_MATERIAL_DIR in path.parts:
        return True

    return False


def _build_backup_info_markdown(
    course_name: str,
    *,
    include_sources: bool,
    date_created: str,
) -> str:
    return (
        "# StudyForge Course Backup\n\n"
        f"Course: {course_name}\n\n"
        f"Date created: {date_created}\n\n"
        f"Include source materials: {'true' if include_sources else 'false'}\n\n"
        "## Restore (manual — v1)\n\n"
        "Full automatic restore is not implemented yet.\n\n"
        "To restore manually:\n\n"
        "1. Close StudyForge if it is running.\n"
        "2. Unzip this archive.\n"
        "3. Copy the course folder into your StudyForge `courses/` directory, "
        "for example:\n\n"
        "   `C:\\StudyForge\\courses\\`\n\n"
        "4. Confirm `08_App_Data/source_registry.json` and your study logs are present.\n\n"
        "**Warning:** This backup may contain private PDFs, extracted text, audits, "
        "and study logs. Store it safely.\n"
    )


def create_course_backup(
    course_name: str,
    include_sources: bool = True,
    overwrite: bool = False,
    output_dir: Path | None = None,
    root: Path | None = None,
) -> dict:
    """
    Create a timestamped zip backup of a course folder.

    Raises:
        CourseNotFoundError, BackupExistsError.
    """
    course_path = resolve_course_path(course_name, root)
    course_folder_name = course_path.name

    target_dir = output_dir if output_dir is not None else get_course_backup_dir(course_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    backup_name = build_backup_name(course_folder_name)
    backup_path = target_dir / backup_name

    if backup_path.is_file() and not overwrite:
        raise BackupExistsError(
            f"Backup already exists: {backup_path}\nUse overwrite=True to replace."
        )

    date_created = _now_iso()
    warnings: list[str] = []
    file_count = 0
    total_bytes = 0

    info_arcname = f"{course_folder_name}/{BACKUP_INFO_FILENAME}"
    info_text = _build_backup_info_markdown(
        course_folder_name,
        include_sources=include_sources,
        date_created=date_created,
    )

    with zipfile.ZipFile(
        backup_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(info_arcname, info_text)
        file_count += 1
        total_bytes += len(info_text.encode("utf-8"))

        for file_path in sorted(course_path.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.resolve() == backup_path.resolve():
                continue
            if should_exclude_from_backup(
                file_path,
                include_sources=include_sources,
            ):
                continue

            relative = file_path.relative_to(course_path.parent)
            archive.write(file_path, arcname=str(relative).replace("\\", "/"))
            file_count += 1
            total_bytes += file_path.stat().st_size

    if not include_sources:
        warnings.append(
            "Source materials (01_Source_Material/) were excluded from this backup."
        )

    return {
        "course": course_folder_name,
        "backup_path": str(backup_path.resolve()),
        "file_count": file_count,
        "total_bytes": total_bytes,
        "include_sources": include_sources,
        "date_created": date_created,
        "warnings": warnings,
    }


def list_course_backups(
    course_name: str,
    root: Path | None = None,
    backup_dir: Path | None = None,
) -> list[dict]:
    """Return backup zip metadata sorted newest first."""
    course_path = resolve_course_path(course_name, root)
    directory = backup_dir if backup_dir is not None else get_course_backup_dir(course_path)
    if not directory.is_dir():
        return []

    entries: list[dict] = []
    for path in directory.glob("*_backup_*.zip"):
        if not path.is_file():
            continue
        modified = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).astimezone().isoformat(timespec="seconds")
        entries.append(
            {
                "path": str(path.resolve()),
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
                "modified": modified,
            }
        )

    entries.sort(key=lambda item: item["modified"], reverse=True)
    return entries


def format_bytes(size: int) -> str:
    """Human-readable byte size for CLI output."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"
