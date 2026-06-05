"""
Exam Targets v1 — define upcoming exams and what they cover (no AI).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import list_sources, resolve_course_path
from studyforge.study.study_units import (
    InvalidSourceIdError,
    StudyUnitNotFoundError,
    _normalize_source_id,
    _normalize_unit_id,
    _validate_source_ids,
    load_study_units,
)

MASTER_DIR = Path("00_Master")
EXAM_TARGETS_JSON = "exam_targets.json"

VALID_STATUSES = frozenset({"active", "completed", "archived"})
_EXAM_ID_PATTERN = re.compile(r"^EXAM-(\d+)$", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ExamTargetNotFoundError(Exception):
    """Raised when exam_id is not in exam_targets.json."""


class InvalidExamTargetStatusError(ValueError):
    """Raised when exam target status is not allowed."""


class InvalidExamDateError(ValueError):
    """Raised when exam_date is not YYYY-MM-DD."""


class InvalidTargetScoreError(ValueError):
    """Raised when target_score is outside 0–100."""


class InvalidExamUnitIdError(Exception):
    """Raised when a unit ID is not in study_units.json."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise InvalidExamTargetStatusError(
            f"Invalid status {status!r}. Allowed: {allowed}"
        )
    return normalized


def _validate_exam_date(exam_date: str) -> str:
    value = exam_date.strip()
    if not _DATE_PATTERN.match(value):
        raise InvalidExamDateError(
            f"Invalid exam_date {exam_date!r}. Use YYYY-MM-DD."
        )
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise InvalidExamDateError(
            f"Invalid exam_date {exam_date!r}. Use YYYY-MM-DD."
        ) from exc
    return value


def _validate_target_score(target_score: int | None) -> int | None:
    if target_score is None:
        return None
    score = int(target_score)
    if score < 0 or score > 100:
        raise InvalidTargetScoreError(
            f"target_score must be between 0 and 100, got {target_score}."
        )
    return score


def _validate_unit_ids(
    course_name: str, unit_ids: list[str], root: Path | None
) -> list[str]:
    data = load_study_units(course_name, root)
    known = {
        _normalize_unit_id(str(unit.get("unit_id", "")))
        for unit in data.get("units", [])
        if unit.get("unit_id")
    }
    normalized: list[str] = []
    for unit_id in unit_ids:
        uid = _normalize_unit_id(unit_id)
        if not uid:
            continue
        if uid not in known:
            raise InvalidExamUnitIdError(f"Study unit not found: {unit_id}")
        if uid not in normalized:
            normalized.append(uid)
    return normalized


def get_exam_targets_path(course_path: Path) -> Path:
    """Return ``00_Master/exam_targets.json`` for a course."""
    return course_path / MASTER_DIR / EXAM_TARGETS_JSON


def load_exam_targets(course_name: str, root: Path | None = None) -> dict:
    """Load exam targets JSON or return ``{"exam_targets": []}``."""
    course_path = resolve_course_path(course_name, root)
    path = get_exam_targets_path(course_path)
    if not path.is_file():
        return {"exam_targets": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if "exam_targets" not in data or not isinstance(data["exam_targets"], list):
        data["exam_targets"] = []
    return data


def save_exam_targets(
    course_name: str, data: dict, root: Path | None = None
) -> Path:
    """Write exam targets JSON (UTF-8)."""
    course_path = resolve_course_path(course_name, root)
    path = get_exam_targets_path(course_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    targets = data.get("exam_targets", [])
    if not isinstance(targets, list):
        targets = []
    payload = {"exam_targets": targets}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def get_next_exam_id(data: dict) -> str:
    """Return the next ``EXAM-0001`` style identifier."""
    max_num = 0
    for target in data.get("exam_targets", []):
        match = _EXAM_ID_PATTERN.match(str(target.get("exam_id", "")))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"EXAM-{max_num + 1:04d}"


def _find_exam_target(targets: list[dict], exam_id: str) -> dict:
    target_id = exam_id.strip().upper()
    for target in targets:
        if str(target.get("exam_id", "")).strip().upper() == target_id:
            return target
    raise ExamTargetNotFoundError(f"Exam target not found: {exam_id}")


def create_exam_target(
    course_name: str,
    title: str,
    exam_date: str,
    description: str | None = None,
    target_score: int | None = None,
    unit_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    status: str = "active",
    root: Path | None = None,
) -> dict:
    """Create and save a new exam target."""
    resolve_course_path(course_name, root)
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Exam title cannot be empty.")

    validated_date = _validate_exam_date(exam_date)
    validated_score = _validate_target_score(target_score)
    validated_status = _validate_status(status)
    validated_units = _validate_unit_ids(course_name, unit_ids or [], root)
    validated_sources = _validate_source_ids(course_name, source_ids or [], root)

    data = load_exam_targets(course_name, root)
    targets = data.setdefault("exam_targets", [])
    now = _now_iso()
    target = {
        "exam_id": get_next_exam_id(data),
        "title": clean_title,
        "description": (description or "").strip(),
        "exam_date": validated_date,
        "target_score": validated_score,
        "unit_ids": validated_units,
        "source_ids": validated_sources,
        "status": validated_status,
        "date_created": now,
        "date_updated": now,
    }
    targets.append(target)
    save_exam_targets(course_name, data, root)
    return dict(target)


def list_exam_targets(course_name: str, root: Path | None = None) -> list[dict]:
    """Return all exam targets for a course."""
    data = load_exam_targets(course_name, root)
    return [dict(target) for target in data.get("exam_targets", [])]


def list_active_exam_targets(course_name: str, root: Path | None = None) -> list[dict]:
    """Return exam targets with status ``active``."""
    return [
        dict(target)
        for target in list_exam_targets(course_name, root)
        if str(target.get("status", "")).lower() == "active"
    ]


def get_exam_target(
    course_name: str, exam_id: str, root: Path | None = None
) -> dict:
    """Return one exam target by ID."""
    data = load_exam_targets(course_name, root)
    return dict(_find_exam_target(data.get("exam_targets", []), exam_id))


def update_exam_target(
    course_name: str,
    exam_id: str,
    title: str | None = None,
    exam_date: str | None = None,
    description: str | None = None,
    target_score: int | None = None,
    unit_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    status: str | None = None,
    root: Path | None = None,
) -> dict:
    """Update fields on an existing exam target."""
    data = load_exam_targets(course_name, root)
    targets = data.setdefault("exam_targets", [])
    target = _find_exam_target(targets, exam_id)

    if title is not None:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Exam title cannot be empty.")
        target["title"] = clean_title
    if exam_date is not None:
        target["exam_date"] = _validate_exam_date(exam_date)
    if description is not None:
        target["description"] = description.strip()
    if target_score is not None:
        target["target_score"] = _validate_target_score(target_score)
    if unit_ids is not None:
        target["unit_ids"] = _validate_unit_ids(course_name, unit_ids, root)
    if source_ids is not None:
        target["source_ids"] = _validate_source_ids(course_name, source_ids, root)
    if status is not None:
        target["status"] = _validate_status(status)

    target["date_updated"] = _now_iso()
    save_exam_targets(course_name, data, root)
    return dict(target)


