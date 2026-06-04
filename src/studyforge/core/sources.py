"""
Add and list source material files for a StudyForge course.

Copies files into 01_Source_Material/<type>/ and records metadata in
08_App_Data/source_registry.json.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.paths import find_project_root, get_courses_dir, load_config

# Allowed source types and their folder names under 01_Source_Material
SOURCE_TYPE_FOLDERS: dict[str, str] = {
    "textbook": "textbook",
    "slides": "slides",
    "homework": "homework",
    "notes": "notes",
    "extra_readings": "extra_readings",
}

ALLOWED_SOURCE_TYPES: tuple[str, ...] = tuple(SOURCE_TYPE_FOLDERS.keys())

SOURCE_MATERIAL_DIR = Path("01_Source_Material")
REGISTRY_RELATIVE = Path("08_App_Data") / "source_registry.json"

_SOURCE_ID_PATTERN = re.compile(r"^SRC-(\d+)$", re.IGNORECASE)


class CourseNotFoundError(Exception):
    """Raised when the requested course folder does not exist."""


class SourceTypeError(ValueError):
    """Raised when source_type is not one of the allowed values."""


class SourceFileNotFoundError(FileNotFoundError):
    """Raised when the source file path does not exist."""


class SourceFileError(ValueError):
    """Raised when the path is not a regular file."""


def validate_source_type(source_type: str) -> str:
    """
    Validate and return a normalized source type (lowercase, stripped).

    Raises:
        SourceTypeError: Unknown or empty type.
    """
    value = source_type.strip().lower()
    if value not in SOURCE_TYPE_FOLDERS:
        allowed = ", ".join(ALLOWED_SOURCE_TYPES)
        raise SourceTypeError(
            f"Invalid source type: {source_type!r}. Allowed types: {allowed}"
        )
    return value


def get_source_folder(course_path: Path, source_type: str) -> Path:
    """Return 01_Source_Material/<type>/ for the course."""
    normalized = validate_source_type(source_type)
    folder_name = SOURCE_TYPE_FOLDERS[normalized]
    return course_path / SOURCE_MATERIAL_DIR / folder_name


def sanitize_file_name(filename: str) -> str:
    """
    Make a file name safe for Windows while keeping the extension.

    Uses the same invalid-character rules as course folder sanitization on the stem.
    """
    from studyforge.core.courses import sanitize_folder_name

    path = Path(filename.strip())
    suffix = path.suffix
    safe_stem = sanitize_folder_name(path.stem) or "file"
    return f"{safe_stem}{suffix}"


def resolve_course_path(course_name: str, root: Path | None = None) -> Path:
    """
    Resolve a course folder by exact or case-insensitive name.

    Raises:
        CourseNotFoundError: No matching course directory.
    """
    project_root = root or find_project_root()
    config = load_config(project_root)
    name = course_name.strip()
    if not name:
        raise CourseNotFoundError("Course name cannot be empty.")

    courses_dir = get_courses_dir(project_root, config)
    direct = courses_dir / name
    if direct.is_dir():
        template = config.get("default_course_template", "_Course_Template")
        if direct.name == template:
            raise CourseNotFoundError(
                f"Cannot add sources to the template folder: {direct}"
            )
        return direct

    # Case-insensitive fallback
    for course_dir in courses_dir.iterdir():
        if course_dir.is_dir() and course_dir.name.lower() == name.lower():
            template = config.get("default_course_template", "_Course_Template")
            if course_dir.name == template:
                raise CourseNotFoundError(
                    f"Cannot add sources to the template folder: {course_dir}"
                )
            return course_dir

    raise CourseNotFoundError(
        f"Course not found: {name}\n"
        f"Expected a folder under: {courses_dir}\n"
        "Use create_course.py or check the folder name with --list."
    )


def get_source_registry_path(course_path: Path) -> Path:
    """Return the path to 08_App_Data/source_registry.json for a course."""
    return course_path / REGISTRY_RELATIVE


def _registry_path(course_path: Path) -> Path:
    return get_source_registry_path(course_path)


def _load_registry(registry_path: Path) -> dict:
    """Load source_registry.json or return an empty registry."""
    if registry_path.is_file():
        with registry_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if "sources" not in data or not isinstance(data["sources"], list):
            data["sources"] = []
        return data
    return {"sources": []}


def _save_registry(registry_path: Path, data: dict) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def _next_source_id(sources: list[dict]) -> str:
    """Generate the next SRC-0001 style id."""
    max_num = 0
    for entry in sources:
        match = _SOURCE_ID_PATTERN.match(str(entry.get("id", "")))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"SRC-{max_num + 1:04d}"


def _unique_destination(folder: Path, file_name: str) -> Path:
    """
    Pick a destination path that does not overwrite an existing file.

    Examples: book.pdf, book_002.pdf, book_003.pdf
    """
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / file_name
    if not candidate.exists():
        return candidate

    path = Path(file_name)
    stem = path.stem
    suffix = path.suffix

    for index in range(2, 1000):
        numbered = f"{stem}_{index:03d}{suffix}"
        candidate = folder / numbered
        if not candidate.exists():
            return candidate

    raise OSError(f"Could not find a free file name in {folder} for {file_name}")


def add_source(
    course_name: str,
    source_type: str,
    file_path: Path,
    title: str | None = None,
    root: Path | None = None,
) -> Path:
    """
    Copy a source file into the course and append metadata to the registry.

    Args:
        course_name: Course folder name (e.g. ECA1010_Microeconomics).
        source_type: One of ALLOWED_SOURCE_TYPES.
        file_path: Path to the existing file to copy.
        title: Optional display title; defaults to the file stem.
        root: Optional project root.

    Returns:
        Path to the copied file inside the course.

    Raises:
        CourseNotFoundError, SourceTypeError, SourceFileNotFoundError, SourceFileError.
    """
    project_root = root or find_project_root()
    course_path = resolve_course_path(course_name, project_root)
    normalized_type = validate_source_type(source_type)

    source_file = Path(file_path)
    if not source_file.exists():
        raise SourceFileNotFoundError(f"Source file not found: {source_file}")
    if not source_file.is_file():
        raise SourceFileError(f"Not a file: {source_file}")

    dest_folder = get_source_folder(course_path, normalized_type)
    safe_name = sanitize_file_name(source_file.name)
    destination = _unique_destination(dest_folder, safe_name)

    # copy2 preserves timestamps; original file is untouched
    shutil.copy2(source_file, destination)

    display_title = (title or source_file.stem).strip() or source_file.stem
    registry_path = _registry_path(course_path)
    registry = _load_registry(registry_path)

    source_id = _next_source_id(registry["sources"])
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    entry = {
        "id": source_id,
        "title": display_title,
        "source_type": normalized_type,
        "original_path": str(source_file.resolve()),
        "stored_path": str(destination.resolve()),
        "file_name": destination.name,
        "file_extension": destination.suffix.lower(),
        "date_added": now,
        "status": "added",
    }
    registry["sources"].append(entry)
    _save_registry(registry_path, registry)

    return destination


def load_source_registry(course_path: Path) -> dict:
    """Load source_registry.json for a course (empty sources list if missing)."""
    return _load_registry(_registry_path(course_path))


def save_source_registry(course_path: Path, data: dict) -> None:
    """Write source_registry.json for a course."""
    _save_registry(_registry_path(course_path), data)


def list_sources(course_name: str, root: Path | None = None) -> list[dict]:
    """
    Return all source entries from the course registry (may be empty).

    Raises:
        CourseNotFoundError: Course folder missing.
    """
    course_path = resolve_course_path(course_name, root)
    registry_path = _registry_path(course_path)
    if not registry_path.is_file():
        return []
    registry = _load_registry(registry_path)
    return list(registry.get("sources", []))
