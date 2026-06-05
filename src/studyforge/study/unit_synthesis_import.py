"""
Unit Synthesis Import v1 — versioned storage for manual unit syntheses (no API).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.study_units import (
    StudyUnitNotFoundError,
    _find_unit,
    _normalize_unit_id,
    get_study_unit_summary,
    load_study_units,
    save_study_units,
)

STUDY_OUTPUTS_BASE = Path("06_Study_Outputs")
STUDY_UNITS_SUBDIR = "study_units"
_REGISTRY_SUFFIX = "_synthesis_registry.json"

_SYNTHESIS_FILE_PATTERN = re.compile(
    r"^(?P<unit_id>UNIT-\d+)_synthesis_v(?P<version>\d{3})\.md$",
    re.IGNORECASE,
)

EXPECTED_SECTIONS: tuple[str, ...] = (
    "Unit Overview",
    "Core Concepts",
    "Merged Formula / Method Sheet",
    "Cross-Source Connections",
    "Conflicts or Uncertainties",
    "Must-Memorize List",
    "Must-Understand List",
    "Exam / Homework Traps",
    "Practice Questions",
    "Active Recall Questions",
    "Weak Points to Review",
    "Final Unit Checklist",
)

IMPORTANT_SECTIONS: frozenset[str] = frozenset(
    {
        "Core Concepts",
        "Merged Formula / Method Sheet",
        "Practice Questions",
        "Active Recall Questions",
    }
)


class SynthesisInputError(ValueError):
    """Raised when synthesis_text and synthesis_file are both or neither provided."""


class EmptySynthesisError(ValueError):
    """Raised when synthesis content is empty."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _word_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


def get_unit_synthesis_dir(course_path: Path, unit_id: str) -> Path:
    """Return ``06_Study_Outputs/study_units/UNIT-0001/`` (creates if missing)."""
    normalized = _normalize_unit_id(unit_id)
    path = course_path / STUDY_OUTPUTS_BASE / STUDY_UNITS_SUBDIR / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_unit_synthesis_registry_path(course_path: Path, unit_id: str) -> Path:
    """Return path to the unit synthesis registry JSON."""
    normalized = _normalize_unit_id(unit_id)
    return get_unit_synthesis_dir(course_path, unit_id) / f"{normalized}{_REGISTRY_SUFFIX}"


def load_unit_synthesis_registry(path: Path, unit_id: str) -> dict:
    """Load registry JSON, or return an empty registry if missing."""
    normalized = _normalize_unit_id(unit_id)
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if "syntheses" not in data or not isinstance(data["syntheses"], list):
            data["syntheses"] = []
        data["unit_id"] = normalized
        return data
    return {"unit_id": normalized, "syntheses": []}


def save_unit_synthesis_registry(path: Path, registry: dict) -> None:
    """Write unit synthesis registry JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _scan_versions_on_disk(synthesis_dir: Path, unit_id: str) -> list[int]:
    """Find version numbers from existing synthesis Markdown files."""
    versions: list[int] = []
    normalized = _normalize_unit_id(unit_id)
    if not synthesis_dir.is_dir():
        return versions
    for path in synthesis_dir.glob("*.md"):
        match = _SYNTHESIS_FILE_PATTERN.match(path.name)
        if match and match.group("unit_id").upper() == normalized:
            versions.append(int(match.group("version")))
    return versions


def get_next_unit_synthesis_version(
    registry: dict,
    synthesis_dir: Path | None = None,
    unit_id: str | None = None,
) -> int:
    """Determine the next synthesis version (starts at 1)."""
    versions: list[int] = []
    for entry in registry.get("syntheses", []):
        try:
            versions.append(int(entry.get("version", 0)))
        except (TypeError, ValueError):
            continue

    uid = unit_id or str(registry.get("unit_id", ""))
    if synthesis_dir and uid:
        versions.extend(_scan_versions_on_disk(synthesis_dir, uid))

    if not versions:
        return 1
    return max(versions) + 1


def build_unit_synthesis_file_name(unit_id: str, version: int) -> str:
    """Build versioned filename, e.g. UNIT-0001_synthesis_v001.md."""
    normalized = _normalize_unit_id(unit_id)
    return f"{normalized}_synthesis_v{version:03d}.md"


def build_unit_synthesis_id(unit_id: str, version: int) -> str:
    """Build synthesis ID, e.g. US-UNIT-0001-V001."""
    normalized = _normalize_unit_id(unit_id)
    return f"US-{normalized}-V{version:03d}"


def _section_present(text: str, section_name: str) -> bool:
    """Return True if a ``## section`` heading appears in the text."""
    pattern = re.compile(
        rf"^##\s+{re.escape(section_name)}\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(pattern.search(text))


def analyze_unit_synthesis_quality(text: str) -> dict:
    """
    Lightweight deterministic quality check for imported unit synthesis.

    Returns found/missing sections, word count, quality_status, and warnings.
    """
    found: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []

    if not re.search(r"^#\s+Unit\s+Synthesis\s*$", text, re.IGNORECASE | re.MULTILINE):
        warnings.append('Missing top-level heading "# Unit Synthesis".')

    for section in EXPECTED_SECTIONS:
        if _section_present(text, section):
            found.append(section)
        else:
            missing.append(section)

    count = _word_count(text)
    headings_found = len(found)

    if count < 100 or headings_found < 3:
        quality_status = "failed"
        if count < 100:
            warnings.append(f"Word count is low ({count} words; minimum 100).")
        if headings_found < 3:
            warnings.append(
                f"Only {headings_found} expected section(s) found (minimum 3)."
            )
    elif len(missing) >= 3 or any(s in missing for s in IMPORTANT_SECTIONS):
        quality_status = "needs_review"
        missing_important = [s for s in IMPORTANT_SECTIONS if s in missing]
        if missing_important:
            warnings.append(
                "Missing important sections: " + ", ".join(sorted(missing_important))
            )
        if len(missing) >= 3:
            warnings.append(f"{len(missing)} expected sections are missing.")
    else:
        quality_status = "ok"

    return {
        "found_sections": found,
        "missing_sections": missing,
        "word_count": count,
        "quality_status": quality_status,
        "warnings": warnings,
    }


def _read_synthesis_content(
    synthesis_text: str | None, synthesis_file: Path | None
) -> str:
    """Read synthesis body from inline text or a file (mutually exclusive)."""
    if synthesis_file is not None and synthesis_text is not None:
        raise SynthesisInputError(
            "Provide only one of synthesis_text or synthesis_file, not both."
        )
    if synthesis_file is None and synthesis_text is None:
        raise SynthesisInputError("Provide synthesis_text or synthesis_file.")

    if synthesis_file is not None:
        path = Path(synthesis_file)
        if not path.is_file():
            raise FileNotFoundError(f"Synthesis file not found: {path}")
        return path.read_text(encoding="utf-8")

    return synthesis_text if synthesis_text is not None else ""


def _update_study_unit_synthesis_fields(
    course_name: str,
    unit_id: str,
    *,
    synthesis_id: str,
    file_path: str,
    root: Path | None,
) -> None:
    """Update latest synthesis fields on the study unit in study_units.json."""
    data = load_study_units(course_name, root)
    unit = _find_unit(data.get("units", []), unit_id)
    unit["latest_synthesis_id"] = synthesis_id
    unit["latest_synthesis_path"] = file_path
    unit["date_synthesis_imported"] = _now_iso()
    unit["date_updated"] = _now_iso()
    save_study_units(course_name, data, root)


def get_latest_synthesis_quality(
    course_path: Path, unit_id: str, synthesis_id: str | None = None
) -> str:
    """Return quality_status for the latest (or given) synthesis from registry."""
    registry_path = get_unit_synthesis_registry_path(course_path, unit_id)
    if not registry_path.is_file():
        return ""
    registry = load_unit_synthesis_registry(registry_path, unit_id)
    syntheses = registry.get("syntheses", [])
    if not syntheses:
        return ""
    if synthesis_id:
        for entry in reversed(syntheses):
            if entry.get("synthesis_id") == synthesis_id:
                quality = entry.get("quality") or {}
                return str(quality.get("quality_status", ""))
        return ""
    latest = syntheses[-1]
    quality = latest.get("quality") or {}
    return str(quality.get("quality_status", ""))


def unit_has_synthesis(unit: dict, course_path: Path | None = None) -> bool:
    """Return True if the unit has an imported synthesis file on disk."""
    synthesis_id = str(unit.get("latest_synthesis_id", "")).strip()
    synthesis_path = str(unit.get("latest_synthesis_path", "")).strip()
    if synthesis_id and synthesis_path and Path(synthesis_path).is_file():
        return True
    if course_path is not None and synthesis_id:
        unit_id = str(unit.get("unit_id", ""))
        reg_path = get_unit_synthesis_registry_path(course_path, unit_id)
        if reg_path.is_file():
            registry = load_unit_synthesis_registry(reg_path, unit_id)
            return bool(registry.get("syntheses"))
    return False


def import_unit_synthesis(
    course_name: str,
    unit_id: str,
    synthesis_text: str | None = None,
    synthesis_file: Path | None = None,
    synthesizer_name: str = "ChatGPT",
    notes: str | None = None,
    root: Path | None = None,
) -> dict:
    """
    Import a manual unit synthesis as a new versioned Markdown file.

    Never overwrites previous versions. Updates study_units.json latest fields.
    """
    course_path = resolve_course_path(course_name, root)
    summary = get_study_unit_summary(course_name, unit_id, root)
    normalized_unit = _normalize_unit_id(unit_id)

    content = _read_synthesis_content(synthesis_text, synthesis_file)
    if not content.strip():
        raise EmptySynthesisError("Synthesis content is empty.")

    synthesis_dir = get_unit_synthesis_dir(course_path, normalized_unit)
    registry_path = get_unit_synthesis_registry_path(course_path, normalized_unit)
    registry = load_unit_synthesis_registry(registry_path, normalized_unit)

    warnings: list[str] = []
    if not registry_path.is_file() and _scan_versions_on_disk(
        synthesis_dir, normalized_unit
    ):
        warnings.append(
            "Synthesis registry was missing; next version was chosen from existing "
            "files on disk."
        )

    version = get_next_unit_synthesis_version(
        registry, synthesis_dir, normalized_unit
    )
    file_name = build_unit_synthesis_file_name(normalized_unit, version)
    file_path = synthesis_dir / file_name

    if file_path.exists():
        while file_path.exists():
            version += 1
            file_name = build_unit_synthesis_file_name(normalized_unit, version)
            file_path = synthesis_dir / file_name
        warnings.append(
            f"Expected new file was taken; using version {version:03d} instead."
        )

    file_path.write_text(content, encoding="utf-8")
    imported_at = _now_iso()
    synthesis_id = build_unit_synthesis_id(normalized_unit, version)
    quality = analyze_unit_synthesis_quality(content)
    warnings.extend(quality.get("warnings", []))

    registry_entry = {
        "version": version,
        "synthesis_id": synthesis_id,
        "file_path": str(file_path.resolve()),
        "date_imported": imported_at,
        "synthesizer_name": synthesizer_name.strip() or "ChatGPT",
        "notes": (notes or "").strip(),
        "word_count": quality["word_count"],
        "status": "imported",
        "quality": quality,
    }
    registry.setdefault("syntheses", []).append(registry_entry)
    save_unit_synthesis_registry(registry_path, registry)

    _update_study_unit_synthesis_fields(
        course_name,
        normalized_unit,
        synthesis_id=synthesis_id,
        file_path=str(file_path.resolve()),
        root=root,
    )

    return {
        "course": course_path.name,
        "unit_id": normalized_unit,
        "unit_title": summary.get("title", ""),
        "synthesis_id": synthesis_id,
        "file_path": str(file_path.resolve()),
        "registry_path": str(registry_path.resolve()),
        "word_count": quality["word_count"],
        "quality_status": quality["quality_status"],
        "quality": quality,
        "warnings": warnings,
    }
