"""
Weak points tracker v1 — track concepts to strengthen (deterministic, no AI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path

MY_WORK_DIR = Path("07_My_Work")
WEAK_POINTS_JSON = "weak_points.json"
WEAK_POINTS_MD = "weak_points.md"

VALID_STATUSES = frozenset(
    {"new", "reviewing", "still_weak", "improving", "mastered"}
)


class InvalidConfidenceError(ValueError):
    """Raised when confidence level is not 1–5."""


class InvalidWeakPointStatusError(ValueError):
    """Raised when weak point status is not allowed."""


class WeakPointNotFoundError(Exception):
    """Raised when weak_point_id is not in the log."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _validate_confidence(level: int) -> int:
    if level < 1 or level > 5:
        raise InvalidConfidenceError(
            f"Confidence level must be 1–5, got {level}"
        )
    return level


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise InvalidWeakPointStatusError(
            f"Invalid status {status!r}. Allowed: {allowed}"
        )
    return normalized


def _next_weak_point_id(weak_points: list[dict]) -> str:
    return f"WEAK-{len(weak_points) + 1:04d}"


def get_weak_points_path(course_path: Path) -> Path:
    """Return path to the course weak points JSON file."""
    return course_path / MY_WORK_DIR / WEAK_POINTS_JSON


def get_weak_points_markdown_path(course_path: Path) -> Path:
    """Return path to the exported weak points Markdown file."""
    return course_path / MY_WORK_DIR / WEAK_POINTS_MD


def load_weak_points(path: Path) -> dict:
    """Load weak points JSON or return an empty structure."""
    if not path.is_file():
        return {"weak_points": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if "weak_points" not in data:
        data["weak_points"] = []
    return data


def save_weak_points(path: Path, data: dict) -> None:
    """Write weak points JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def _find_weak_point(weak_points: list[dict], weak_point_id: str) -> dict:
    target = weak_point_id.strip().upper()
    for entry in weak_points:
        if str(entry.get("weak_point_id", "")).upper() == target:
            return entry
    raise WeakPointNotFoundError(f"Weak point not found: {weak_point_id}")


def add_weak_point(
    course_name: str,
    source_id: str,
    concept: str,
    confidence_level: int = 2,
    why_hard: str | None = None,
    what_to_review: str | None = None,
    practice_needed: str | None = None,
    status: str = "new",
    root: Path | None = None,
) -> dict:
    """Append one weak point entry."""
    course_path = resolve_course_path(course_name, root)
    path = get_weak_points_path(course_path)
    data = load_weak_points(path)
    items = data.setdefault("weak_points", [])

    status_normalized = _validate_status(status)
    confidence = _validate_confidence(confidence_level)
    timestamp = _now_iso()

    entry = {
        "weak_point_id": _next_weak_point_id(items),
        "course": course_path.name,
        "source_id": source_id.strip().upper(),
        "concept": concept.strip(),
        "confidence_level": confidence,
        "why_hard": why_hard or "",
        "what_to_review": what_to_review or "",
        "practice_needed": practice_needed or "",
        "status": status_normalized,
        "date_created": timestamp,
        "date_updated": timestamp,
    }
    items.append(entry)
    save_weak_points(path, data)

    return {
        "weak_point_id": entry["weak_point_id"],
        "log_path": str(path.resolve()),
        "status": status_normalized,
        "confidence_level": confidence,
    }


def update_weak_point(
    course_name: str,
    weak_point_id: str,
    confidence_level: int | None = None,
    status: str | None = None,
    root: Path | None = None,
) -> dict:
    """Update confidence and/or status on a weak point."""
    if confidence_level is None and status is None:
        raise ValueError("Provide confidence_level and/or status to update.")

    course_path = resolve_course_path(course_name, root)
    path = get_weak_points_path(course_path)
    data = load_weak_points(path)
    entry = _find_weak_point(data["weak_points"], weak_point_id)

    if confidence_level is not None:
        entry["confidence_level"] = _validate_confidence(confidence_level)
    if status is not None:
        entry["status"] = _validate_status(status)
    entry["date_updated"] = _now_iso()
    save_weak_points(path, data)

    return {
        "weak_point_id": entry["weak_point_id"],
        "confidence_level": entry["confidence_level"],
        "status": entry["status"],
        "log_path": str(path.resolve()),
    }


def list_weak_points(course_name: str, root: Path | None = None) -> list[dict]:
    """Return all weak point entries for a course."""
    course_path = resolve_course_path(course_name, root)
    data = load_weak_points(get_weak_points_path(course_path))
    return list(data.get("weak_points", []))


def get_weak_points_pipeline_warning(course_name: str, root: Path | None = None) -> str | None:
    """Return a Pipeline Doctor warning if open weak points exist."""
    if count_open_weak_points(course_name, root) > 0:
        return "Weak points remain. Review/practice them."
    return None


def count_open_weak_points(course_name: str, root: Path | None = None) -> int:
    """Count weak points whose status is not mastered."""
    return sum(
        1
        for entry in list_weak_points(course_name, root)
        if str(entry.get("status", "")).lower() != "mastered"
    )


def export_weak_points_markdown(course_name: str, root: Path | None = None) -> Path:
    """Write weak points as Markdown."""
    course_path = resolve_course_path(course_name, root)
    path = get_weak_points_path(course_path)
    out_path = get_weak_points_markdown_path(course_path)
    data = load_weak_points(path)

    lines = ["# Weak Points", ""]
    items = data.get("weak_points", [])
    if not items:
        lines.append("No weak points recorded yet.")
        lines.append("")
    else:
        for entry in items:
            lines.extend(
                [
                    f"## {entry.get('weak_point_id', 'WEAK')} — {entry.get('concept', '')}",
                    "",
                    "Chapter/source:",
                    entry.get("source_id", ""),
                    "",
                    "Confidence level:",
                    str(entry.get("confidence_level", "")),
                    "",
                    "Why it feels hard:",
                    entry.get("why_hard", "") or "(not filled in)",
                    "",
                    "What I need to review:",
                    entry.get("what_to_review", "") or "(not filled in)",
                    "",
                    "Practice needed:",
                    entry.get("practice_needed", "") or "(not filled in)",
                    "",
                    "Status:",
                    entry.get("status", "new"),
                    "",
                ]
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
