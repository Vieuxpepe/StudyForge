"""
Create and list StudyForge course folders from the course template.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.paths import (
    find_project_root,
    get_course_template_dir,
    get_courses_dir,
    load_config,
)

# Characters not allowed in Windows file or folder names
_WINDOWS_INVALID = '<>:"/\\|?*'

# Course code: letters, digits, hyphen, underscore (2–32 chars after strip)
_COURSE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


class CourseAlreadyExistsError(Exception):
    """Raised when the target course folder already exists."""


class CourseValidationError(ValueError):
    """Raised when course code or name fails validation."""


def sanitize_folder_name(text: str) -> str:
    """
    Make ``text`` safe for a Windows folder name segment.

    - Removes invalid characters: < > : " / \\ | ? *
    - Replaces spaces with underscores
    - Collapses repeated underscores
    - Strips leading/trailing underscores
    - Preserves accented letters and other Unicode when allowed
    """
    cleaned = text.strip()
    for char in _WINDOWS_INVALID:
        cleaned = cleaned.replace(char, "")
    cleaned = cleaned.replace(" ", "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def build_course_folder_name(code: str, name: str) -> str:
    """
    Build folder name as COURSECODE_Course_Name.

    Example: ECA1010 + Microeconomics -> ECA1010_Microeconomics
    """
    safe_code = sanitize_folder_name(code.upper())
    safe_name = sanitize_folder_name(name)
    if not safe_code:
        raise CourseValidationError("Course code is empty after sanitization.")
    if not safe_name:
        raise CourseValidationError("Course name is empty after sanitization.")
    return f"{safe_code}_{safe_name}"


def validate_course_code(code: str) -> str:
    """Validate and return a normalized course code (stripped, unchanged case)."""
    value = code.strip()
    if not value:
        raise CourseValidationError("Course code cannot be empty.")
    if not _COURSE_CODE_PATTERN.match(value):
        raise CourseValidationError(
            "Course code must be 2–32 characters and use only letters, "
            "digits, hyphens, and underscores."
        )
    return value


def validate_course_name(name: str) -> str:
    """Validate and return a normalized course name (stripped)."""
    value = name.strip()
    if not value:
        raise CourseValidationError("Course name cannot be empty.")
    if len(value) > 120:
        raise CourseValidationError("Course name must be at most 120 characters.")
    return value


def _write_course_profile(
    course_dir: Path, code: str, name: str, folder_name: str
) -> None:
    """Write 00_Master/course_profile.md for a newly created course."""
    created = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    profile_path = course_dir / "00_Master" / "course_profile.md"
    content = f"""# Course Profile

Course code: {code}

Course name: {name}

Course folder: {folder_name}

Created: {created}

## Notes

This course was created from the StudyForge course template.
"""
    profile_path.write_text(content, encoding="utf-8")


def _write_pipeline_settings(
    course_dir: Path, code: str, name: str, folder_name: str
) -> None:
    """Write 00_Master/pipeline_settings.json for a newly created course."""
    settings_path = course_dir / "00_Master" / "pipeline_settings.json"
    payload = {
        "course_code": code,
        "course_name": name,
        "course_folder": folder_name,
        "pipeline_version": "0.1.0",
        "local_digest_enabled": True,
        "intermediate_audit_enabled": True,
        "final_audit_enabled": True,
        "flashcards_enabled_later": True,
        "sqlite_enabled_later": True,
        "vector_search_enabled_later": True,
    }
    with settings_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def create_course(code: str, name: str, root: Path | None = None) -> Path:
    """
    Copy the course template into a new course folder and update master files.

    Args:
        code: Course code (e.g. ECA1010).
        name: Human-readable course name (e.g. Microeconomics).
        root: Optional project root; detected automatically if omitted.

    Returns:
        Path to the new course directory.

    Raises:
        CourseValidationError: Invalid code or name.
        CourseAlreadyExistsError: Target folder already exists.
        FileNotFoundError: Template folder missing.
    """
    project_root = root or find_project_root()
    config = load_config(project_root)

    validated_code = validate_course_code(code)
    validated_name = validate_course_name(name)
    folder_name = build_course_folder_name(validated_code, validated_name)

    courses_dir = get_courses_dir(project_root, config)
    template_dir = get_course_template_dir(project_root, config)
    destination = courses_dir / folder_name

    if destination.exists():
        raise CourseAlreadyExistsError(
            f"Course folder already exists: {destination}\n"
            "No files were changed. Choose a different code or name."
        )

    if not template_dir.is_dir():
        raise FileNotFoundError(f"Course template not found: {template_dir}")

    # copytree fails if destination exists; we already checked above
    shutil.copytree(template_dir, destination)

    _write_course_profile(destination, validated_code, validated_name, folder_name)
    _write_pipeline_settings(destination, validated_code, validated_name, folder_name)

    return destination


def list_courses(root: Path | None = None) -> list[Path]:
    """
    List existing course directories (excluding the template).

    Returns paths sorted by folder name. Only includes directories.
    """
    project_root = root or find_project_root()
    config = load_config(project_root)
    courses_dir = get_courses_dir(project_root, config)
    template_name = config.get("default_course_template", "_Course_Template")

    if not courses_dir.is_dir():
        return []

    courses = [
        path
        for path in courses_dir.iterdir()
        if path.is_dir() and path.name != template_name and not path.name.startswith(".")
    ]
    return sorted(courses, key=lambda p: p.name.lower())
