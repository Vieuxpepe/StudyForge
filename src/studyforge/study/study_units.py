"""
Study Units v1 — group multiple sources into a named topic/exam target (no AI).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.pipeline_status import get_pipeline_status
from studyforge.core.sources import (
    CourseNotFoundError,
    list_sources,
    resolve_course_path,
)
from studyforge.study.active_recall import (
    get_active_recall_file,
    get_active_recall_log_path,
    load_active_recall_log,
)
from studyforge.study.flashcard_review import (
    get_flashcard_review_log_path,
    load_flashcard_review_log,
)

MASTER_DIR = Path("00_Master")
STUDY_UNITS_JSON = "study_units.json"

VALID_STATUSES = frozenset({"active", "paused", "completed", "archived"})
_UNIT_ID_PATTERN = re.compile(r"^UNIT-(\d+)$", re.IGNORECASE)


class StudyUnitNotFoundError(Exception):
    """Raised when unit_id is not in study_units.json."""


class InvalidStudyUnitStatusError(ValueError):
    """Raised when unit status is not allowed."""


class InvalidSourceIdError(ValueError):
    """Raised when a source ID is not in the course registry."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _normalize_unit_id(unit_id: str) -> str:
    return unit_id.strip().upper()


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise InvalidStudyUnitStatusError(
            f"Invalid status {status!r}. Allowed: {allowed}"
        )
    return normalized


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    result: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if value and value not in result:
            result.append(value)
    return result


def get_study_units_path(course_path: Path) -> Path:
    """Return ``00_Master/study_units.json`` for a course."""
    return course_path / MASTER_DIR / STUDY_UNITS_JSON


def load_study_units(course_name: str, root: Path | None = None) -> dict:
    """Load study units JSON or return ``{"units": []}``."""
    course_path = resolve_course_path(course_name, root)
    path = get_study_units_path(course_path)
    if not path.is_file():
        return {"units": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if "units" not in data or not isinstance(data["units"], list):
        data["units"] = []
    return data


def save_study_units(
    course_name: str, data: dict, root: Path | None = None
) -> Path:
    """Write study units JSON (UTF-8)."""
    course_path = resolve_course_path(course_name, root)
    path = get_study_units_path(course_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    units = data.get("units", [])
    if not isinstance(units, list):
        units = []
    payload = {"units": units}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def get_next_unit_id(data: dict) -> str:
    """Return the next ``UNIT-0001`` style identifier."""
    max_num = 0
    for unit in data.get("units", []):
        match = _UNIT_ID_PATTERN.match(str(unit.get("unit_id", "")))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"UNIT-{max_num + 1:04d}"


def _registry_source_ids(course_name: str, root: Path | None) -> set[str]:
    return {
        _normalize_source_id(str(entry.get("id", "")))
        for entry in list_sources(course_name, root)
        if entry.get("id")
    }


def _validate_source_ids(
    course_name: str, source_ids: list[str], root: Path | None
) -> list[str]:
    registry_ids = _registry_source_ids(course_name, root)
    normalized: list[str] = []
    for source_id in source_ids:
        sid = _normalize_source_id(source_id)
        if not sid:
            continue
        if sid not in registry_ids:
            raise InvalidSourceIdError(
                f"Source not found in registry: {source_id}"
            )
        if sid not in normalized:
            normalized.append(sid)
    return normalized


def _find_unit(units: list[dict], unit_id: str) -> dict:
    target = _normalize_unit_id(unit_id)
    for unit in units:
        if _normalize_unit_id(str(unit.get("unit_id", ""))) == target:
            return unit
    raise StudyUnitNotFoundError(f"Study unit not found: {unit_id}")


def create_study_unit(
    course_name: str,
    title: str,
    description: str | None = None,
    source_ids: list[str] | None = None,
    tags: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """Create and save a new study unit."""
    resolve_course_path(course_name, root)
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Study unit title cannot be empty.")

    data = load_study_units(course_name, root)
    units = data.setdefault("units", [])
    validated_sources = _validate_source_ids(
        course_name, source_ids or [], root
    )
    now = _now_iso()
    unit = {
        "unit_id": get_next_unit_id(data),
        "title": clean_title,
        "description": (description or "").strip(),
        "source_ids": validated_sources,
        "tags": _normalize_tags(tags),
        "status": "active",
        "date_created": now,
        "date_updated": now,
    }
    units.append(unit)
    save_study_units(course_name, data, root)
    return dict(unit)


def list_study_units(course_name: str, root: Path | None = None) -> list[dict]:
    """Return all study units for a course."""
    data = load_study_units(course_name, root)
    return [dict(unit) for unit in data.get("units", [])]


def count_active_study_units(course_name: str, root: Path | None = None) -> int:
    """Return the number of units with status ``active``."""
    return sum(
        1
        for unit in list_study_units(course_name, root)
        if str(unit.get("status", "")).lower() == "active"
    )


def update_study_unit(
    course_name: str,
    unit_id: str,
    title: str | None = None,
    description: str | None = None,
    source_ids: list[str] | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    root: Path | None = None,
) -> dict:
    """Update fields on an existing study unit."""
    data = load_study_units(course_name, root)
    units = data.setdefault("units", [])
    unit = _find_unit(units, unit_id)

    if title is not None:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Study unit title cannot be empty.")
        unit["title"] = clean_title
    if description is not None:
        unit["description"] = description.strip()
    if source_ids is not None:
        unit["source_ids"] = _validate_source_ids(course_name, source_ids, root)
    if tags is not None:
        unit["tags"] = _normalize_tags(tags)
    if status is not None:
        unit["status"] = _validate_status(status)

    unit["date_updated"] = _now_iso()
    save_study_units(course_name, data, root)
    return dict(unit)


def add_sources_to_unit(
    course_name: str,
    unit_id: str,
    source_ids: list[str],
    root: Path | None = None,
) -> dict:
    """Append source IDs to a unit (no duplicates)."""
    data = load_study_units(course_name, root)
    units = data.setdefault("units", [])
    unit = _find_unit(units, unit_id)
    validated = _validate_source_ids(course_name, source_ids, root)
    existing = [_normalize_source_id(sid) for sid in unit.get("source_ids", [])]
    for sid in validated:
        if sid not in existing:
            existing.append(sid)
    unit["source_ids"] = existing
    unit["date_updated"] = _now_iso()
    save_study_units(course_name, data, root)
    return dict(unit)


def remove_sources_from_unit(
    course_name: str,
    unit_id: str,
    source_ids: list[str],
    root: Path | None = None,
) -> dict:
    """Remove source IDs from a unit."""
    data = load_study_units(course_name, root)
    units = data.setdefault("units", [])
    unit = _find_unit(units, unit_id)
    remove_set = {_normalize_source_id(sid) for sid in source_ids}
    unit["source_ids"] = [
        sid
        for sid in unit.get("source_ids", [])
        if _normalize_source_id(str(sid)) not in remove_set
    ]
    unit["date_updated"] = _now_iso()
    save_study_units(course_name, data, root)
    return dict(unit)


def _manifest_exists(course_path: Path, entry: dict, source_id: str) -> bool:
    manifest_path = entry.get("study_pack_manifest_path", "")
    if manifest_path and Path(manifest_path).is_file():
        return True
    default = course_path / "06_Study_Outputs" / f"{source_id}_study_pack_manifest.json"
    return default.is_file()


def _source_has_study_pack(
    course_name: str,
    course_path: Path,
    entry: dict,
    source_id: str,
    root: Path | None,
) -> bool:
    if _manifest_exists(course_path, entry, source_id):
        return True
    try:
        pipeline = get_pipeline_status(course_name, source_id, root)
        return bool(pipeline.get("steps", {}).get("study_pack_generated", {}).get("done"))
    except Exception:
        return False


def _source_has_final_audit(entry: dict, course_path: Path, source_id: str) -> bool:
    audit_path = entry.get("latest_final_audit_path", "")
    if audit_path and Path(audit_path).is_file():
        return True
    fa_dir = course_path / "05_Final_Audits" / source_id
    if fa_dir.is_dir():
        return any(fa_dir.glob("*.md"))
    return False


def _source_has_active_recall_file(course_path: Path, source_id: str) -> bool:
    return get_active_recall_file(course_path, source_id).is_file()


def _source_has_study_activity(
    course_path: Path,
    source_id: str,
) -> bool:
    recall_log = load_active_recall_log(
        get_active_recall_log_path(course_path, source_id)
    )
    flashcard_log = load_flashcard_review_log(
        get_flashcard_review_log_path(course_path, source_id),
        source_id,
    )
    if recall_log.get("attempts"):
        return True
    if flashcard_log.get("reviews"):
        return True
    return False


def _build_unit_recommended_action(
    *,
    incomplete_count: int,
    ready_count: int,
    sources_with_activity: int,
    source_count: int,
) -> dict[str, str]:
    if incomplete_count > 0:
        noun = "source" if incomplete_count == 1 else "sources"
        return {
            "key": "process_incomplete_sources",
            "label": "Process incomplete sources",
            "reason": (
                f"{incomplete_count} {noun} "
                f"{'does' if incomplete_count == 1 else 'do'} not have a study pack yet."
            ),
        }
    if source_count > 0 and sources_with_activity == 0:
        return {
            "key": "start_studying_unit",
            "label": "Start studying this unit",
            "reason": "All sources have study packs but no study activity yet.",
        }
    if ready_count > 0:
        return {
            "key": "continue_reviewing_unit",
            "label": "Continue reviewing this unit",
            "reason": "Sources in this unit have study activity to continue.",
        }
    return {
        "key": "add_sources",
        "label": "Add sources to this unit",
        "reason": "This unit has no sources yet.",
    }


def get_study_unit_summary(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Return readiness summary for one study unit."""
    course_path = resolve_course_path(course_name, root)
    data = load_study_units(course_name, root)
    unit = _find_unit(data.get("units", []), unit_id)

    registry = {
        _normalize_source_id(str(entry.get("id", ""))): entry
        for entry in list_sources(course_name, root)
        if entry.get("id")
    }

    sources_summary: list[dict] = []
    ready_count = 0
    incomplete_count = 0
    sources_with_activity = 0
    warnings: list[str] = []

    for raw_sid in unit.get("source_ids", []):
        sid = _normalize_source_id(str(raw_sid))
        entry = registry.get(sid)
        if entry is None:
            warnings.append(f"{sid} is no longer in the source registry.")
            sources_summary.append(
                {
                    "source_id": sid,
                    "title": sid,
                    "status": "missing",
                    "has_study_pack": False,
                    "has_final_audit": False,
                    "has_active_recall": False,
                }
            )
            incomplete_count += 1
            continue

        has_pack = _source_has_study_pack(
            course_name, course_path, entry, sid, root
        )
        has_final = _source_has_final_audit(entry, course_path, sid)
        has_recall_file = _source_has_active_recall_file(course_path, sid)
        has_activity = _source_has_study_activity(course_path, sid)

        if has_pack:
            ready_count += 1
        else:
            incomplete_count += 1
        if has_activity:
            sources_with_activity += 1

        registry_status = str(entry.get("status", "added"))
        sources_summary.append(
            {
                "source_id": sid,
                "title": entry.get("title", sid),
                "status": registry_status,
                "has_study_pack": has_pack,
                "has_final_audit": has_final,
                "has_active_recall": has_recall_file,
            }
        )

    source_count = len(sources_summary)
    recommended_action = _build_unit_recommended_action(
        incomplete_count=incomplete_count,
        ready_count=ready_count,
        sources_with_activity=sources_with_activity,
        source_count=source_count,
    )

    return {
        "unit_id": unit.get("unit_id", ""),
        "title": unit.get("title", ""),
        "description": unit.get("description", ""),
        "status": unit.get("status", "active"),
        "tags": list(unit.get("tags", [])),
        "source_count": source_count,
        "sources": sources_summary,
        "ready_sources": ready_count,
        "incomplete_sources": incomplete_count,
        "warnings": warnings,
        "recommended_action": recommended_action,
    }
