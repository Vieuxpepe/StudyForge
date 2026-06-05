"""
Backup verification and safe restore (dry-run + new-folder-only extract).
"""

from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

from studyforge.core.backup import BACKUP_INFO_FILENAME, format_bytes
from studyforge.core.paths import find_project_root, get_courses_dir, load_config

EXPECTED_COURSE_DIRS: tuple[str, ...] = (
    "00_Master",
    "01_Source_Material",
    "02_Extracted_Text",
    "03_Local_Digests",
    "04_Intermediate_Audits",
    "05_Final_Audits",
    "06_Study_Outputs",
    "07_My_Work",
    "08_App_Data",
)


class InvalidBackupError(Exception):
    """Raised when a backup zip cannot be verified or restored."""


class RestoreTargetExistsError(Exception):
    """Raised when restore would overwrite an existing course folder."""


class UnsafeZipPathError(Exception):
    """Raised when a zip member path is unsafe (zip slip)."""


def _normalize_member_name(name: str) -> str:
    return name.replace("\\", "/").rstrip("/")


def _is_unsafe_zip_member(name: str) -> bool:
    normalized = _normalize_member_name(name)
    if not normalized:
        return False
    if normalized.startswith("/") or normalized.startswith("//"):
        return True
    if len(normalized) >= 2 and normalized[1] == ":":
        return True
    parts = PurePosixPath(normalized).parts
    return ".." in parts


def _detect_course_folder(namelist: list[str]) -> str | None:
    roots: dict[str, int] = {}
    for raw_name in namelist:
        name = _normalize_member_name(raw_name)
        if not name:
            continue
        root = name.split("/", 1)[0]
        roots[root] = roots.get(root, 0) + 1

    if not roots:
        return None
    if len(roots) == 1:
        return next(iter(roots))

    for raw_name in namelist:
        name = _normalize_member_name(raw_name)
        parts = name.split("/")
        if len(parts) >= 2 and parts[1] == "08_App_Data":
            return parts[0]

    return max(roots, key=roots.get)


def _member_under_prefix(member: str, prefix: str) -> bool:
    normalized = _normalize_member_name(member)
    return normalized == prefix or normalized.startswith(f"{prefix}/")


def _resolve_courses_dir(courses_dir: Path | None, root: Path | None) -> Path:
    project_root = root or find_project_root()
    config = load_config(project_root)
    return courses_dir if courses_dir is not None else get_courses_dir(project_root, config)


def inspect_backup_zip(backup_path: Path) -> dict:
    """Inspect a course backup zip and report structure and counts."""
    path = Path(backup_path)
    result: dict = {
        "backup_path": str(path.resolve()) if path.exists() else str(path),
        "valid_zip": False,
        "course_folder": None,
        "file_count": 0,
        "total_bytes": 0,
        "contains_sources": False,
        "contains_study_outputs": False,
        "contains_app_data": False,
        "has_backup_info": False,
        "missing_expected_paths": [],
        "warnings": [],
        "errors": [],
    }

    if not path.is_file():
        result["errors"].append("Backup file does not exist.")
        return result

    if path.suffix.lower() != ".zip":
        result["errors"].append("File is not a .zip archive.")
        return result

    try:
        archive = zipfile.ZipFile(path, mode="r")
    except zipfile.BadZipFile:
        result["errors"].append("File is not a valid zip archive.")
        return result
    except OSError as exc:
        result["errors"].append(f"Cannot open zip: {exc}")
        return result

    with archive:
        namelist = archive.namelist()
        if not namelist:
            result["errors"].append("Zip archive is empty.")
            return result

        unsafe_members = [name for name in namelist if _is_unsafe_zip_member(name)]
        if unsafe_members:
            result["warnings"].append(
                f"Zip contains {len(unsafe_members)} unsafe path(s); restore would reject them."
            )

        course_folder = _detect_course_folder(namelist)
        if not course_folder:
            result["errors"].append("Could not detect course root folder inside zip.")
            return result

        result["valid_zip"] = True
        result["course_folder"] = course_folder

        source_prefix = f"{course_folder}/01_Source_Material"
        study_prefix = f"{course_folder}/06_Study_Outputs"
        app_prefix = f"{course_folder}/08_App_Data"
        info_path = f"{course_folder}/{BACKUP_INFO_FILENAME}"

        file_count = 0
        total_bytes = 0

        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                continue
            member = _normalize_member_name(info.filename)
            if not member:
                continue
            file_count += 1
            total_bytes += info.file_size

            if _member_under_prefix(member, source_prefix):
                result["contains_sources"] = True
            if _member_under_prefix(member, study_prefix):
                result["contains_study_outputs"] = True
            if _member_under_prefix(member, app_prefix):
                result["contains_app_data"] = True
            if member == info_path:
                result["has_backup_info"] = True

        result["file_count"] = file_count
        result["total_bytes"] = total_bytes

        missing: list[str] = []
        for folder in EXPECTED_COURSE_DIRS:
            prefix = f"{course_folder}/{folder}"
            if not any(_member_under_prefix(name, prefix) for name in namelist):
                missing.append(f"{folder}/")

        if not result["has_backup_info"]:
            missing.append(BACKUP_INFO_FILENAME)

        result["missing_expected_paths"] = missing

        if not result["contains_app_data"]:
            result["warnings"].append("No files found under 08_App_Data/.")
        if not result["has_backup_info"]:
            result["warnings"].append(f"Missing {BACKUP_INFO_FILENAME}.")
        if missing:
            result["warnings"].append(
                f"Missing {len(missing)} expected path(s) from a full course backup."
            )

    return result


def verify_backup(backup_path: Path) -> dict:
    """Inspect a backup zip and assign verification status."""
    report = inspect_backup_zip(backup_path)
    status = "ok"

    if not report["valid_zip"] or not report["course_folder"]:
        status = "failed"
    elif "08_App_Data/" in report["missing_expected_paths"]:
        status = "failed"
    elif report["errors"]:
        status = "failed"
    elif not report["has_backup_info"] or report["missing_expected_paths"]:
        status = "needs_review"

    report["status"] = status
    return report


def preview_restore_backup(
    backup_path: Path,
    courses_dir: Path | None = None,
    root: Path | None = None,
) -> dict:
    """Dry-run preview of restoring a backup into the courses directory."""
    report = verify_backup(backup_path)
    courses = _resolve_courses_dir(courses_dir, root)

    course_folder = report.get("course_folder") or ""
    target_path = courses / course_folder if course_folder else courses
    target_exists = target_path.is_dir() if course_folder else False

    warnings = list(report.get("warnings") or [])
    backup_valid = report.get("status") != "failed" and bool(report.get("valid_zip"))

    if target_exists:
        warnings.append(
            f"Target course folder already exists: {target_path}. "
            "Restore is blocked in v1."
        )
    if not backup_valid:
        warnings.append("Backup verification failed; restore is not safe.")

    safe_to_restore = backup_valid and not target_exists and bool(course_folder)

    return {
        "course_folder": course_folder,
        "target_path": str(target_path.resolve()) if course_folder else "",
        "target_exists": target_exists,
        "would_restore_files": int(report.get("file_count") or 0),
        "safe_to_restore": safe_to_restore,
        "status": report.get("status", "failed"),
        "warnings": warnings,
        "verification": report,
    }


def _validate_member_for_extract(
    member_name: str,
    course_folder: str,
    target_root: Path,
) -> Path:
    if _is_unsafe_zip_member(member_name):
        raise UnsafeZipPathError(f"Unsafe zip member path: {member_name}")

    normalized = _normalize_member_name(member_name)
    parts = PurePosixPath(normalized).parts
    if not parts or parts[0] != course_folder:
        raise UnsafeZipPathError(
            f"Unexpected zip member outside course folder '{course_folder}': {member_name}"
        )

    relative = Path(*parts[1:]) if len(parts) > 1 else Path()
    destination = (target_root / relative).resolve()
    target_resolved = target_root.resolve()
    if destination != target_resolved and target_resolved not in destination.parents:
        raise UnsafeZipPathError(f"Zip slip detected for member: {member_name}")

    return destination


def restore_backup_to_new_course(
    backup_path: Path,
    target_course_name: str | None = None,
    root: Path | None = None,
) -> dict:
    """
    Extract a verified backup into a new course folder (never overwrites).

    Raises:
        InvalidBackupError, RestoreTargetExistsError, UnsafeZipPathError.
    """
    report = verify_backup(backup_path)
    if report.get("status") == "failed" or not report.get("valid_zip"):
        errors = report.get("errors") or ["Backup verification failed."]
        raise InvalidBackupError("; ".join(errors))

    course_folder = report["course_folder"]
    assert course_folder

    target_name = (target_course_name or course_folder).strip()
    if not target_name:
        raise InvalidBackupError("Target course folder name cannot be empty.")

    courses = _resolve_courses_dir(None, root)
    target_path = courses / target_name

    if target_path.exists():
        raise RestoreTargetExistsError(
            f"Target course folder already exists: {target_path}\n"
            "Restore never overwrites existing courses in v1."
        )

    warnings = list(report.get("warnings") or [])
    files_restored = 0

    with zipfile.ZipFile(backup_path, mode="r") as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                continue

            destination = _validate_member_for_extract(
                info.filename,
                course_folder,
                target_path,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as dest:
                dest.write(source.read())
            files_restored += 1

    return {
        "course_folder": target_name,
        "source_course_folder": course_folder,
        "target_path": str(target_path.resolve()),
        "files_restored": files_restored,
        "status": report.get("status", "ok"),
        "warnings": warnings,
    }


def format_verification_summary(report: dict) -> str:
    """Build human-readable verification output for CLI."""
    lines = [
        f"Status: {report.get('status', 'unknown')}",
        f"Course folder: {report.get('course_folder') or '(none)'}",
        f"Files: {report.get('file_count', 0)}",
        f"Size: {format_bytes(int(report.get('total_bytes', 0)))}",
    ]
    missing = report.get("missing_expected_paths") or []
    if missing:
        lines.append("Missing paths:")
        for item in missing:
            lines.append(f"  - {item}")
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"  - {warning}")
    errors = report.get("errors") or []
    if errors:
        lines.append("Errors:")
        for error in errors:
            lines.append(f"  - {error}")
    return "\n".join(lines)
