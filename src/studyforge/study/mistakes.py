"""
Mistakes log v1 — track wrong or partial answers (deterministic, no AI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path

MY_WORK_DIR = Path("07_My_Work")
MISTAKES_JSON = "mistakes_log.json"
MISTAKES_MD = "mistakes_log.md"

VALID_STATUSES = frozenset({"new", "reviewed_once", "still_weak", "mastered"})


class InvalidMistakeStatusError(ValueError):
    """Raised when mistake status is not allowed."""


class MistakeNotFoundError(Exception):
    """Raised when mistake_id is not in the log."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise InvalidMistakeStatusError(
            f"Invalid status {status!r}. Allowed: {allowed}"
        )
    return normalized


def _next_mistake_id(mistakes: list[dict]) -> str:
    return f"MISTAKE-{len(mistakes) + 1:04d}"


def get_mistakes_log_path(course_path: Path) -> Path:
    """Return path to the course mistakes JSON log."""
    return course_path / MY_WORK_DIR / MISTAKES_JSON


def get_mistakes_markdown_path(course_path: Path) -> Path:
    """Return path to the exported mistakes Markdown file."""
    return course_path / MY_WORK_DIR / MISTAKES_MD


def load_mistakes_log(path: Path) -> dict:
    """Load mistakes JSON or return an empty structure."""
    if not path.is_file():
        return {"mistakes": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if "mistakes" not in data:
        data["mistakes"] = []
    return data


def save_mistakes_log(path: Path, data: dict) -> None:
    """Write mistakes JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def _find_mistake(mistakes: list[dict], mistake_id: str) -> dict:
    target = mistake_id.strip().upper()
    for entry in mistakes:
        if str(entry.get("mistake_id", "")).upper() == target:
            return entry
    raise MistakeNotFoundError(f"Mistake not found: {mistake_id}")


def add_mistake(
    course_name: str,
    source_id: str,
    question: str,
    user_answer: str,
    question_id: str | None = None,
    correct_explanation: str | None = None,
    why_wrong: str | None = None,
    how_to_avoid: str | None = None,
    status: str = "new",
    root: Path | None = None,
) -> dict:
    """Append one mistake entry to the course log."""
    course_path = resolve_course_path(course_name, root)
    log_path = get_mistakes_log_path(course_path)
    data = load_mistakes_log(log_path)
    mistakes = data.setdefault("mistakes", [])

    status_normalized = _validate_status(status)
    timestamp = _now_iso()
    normalized_source = source_id.strip().upper()

    entry = {
        "mistake_id": _next_mistake_id(mistakes),
        "course": course_path.name,
        "source_id": normalized_source,
        "question_id": question_id or "",
        "question": question,
        "user_answer": user_answer,
        "correct_explanation": correct_explanation or "",
        "why_wrong": why_wrong or "",
        "how_to_avoid": how_to_avoid or "",
        "status": status_normalized,
        "date_created": timestamp,
        "date_updated": timestamp,
    }
    mistakes.append(entry)
    save_mistakes_log(log_path, data)

    return {
        "mistake_id": entry["mistake_id"],
        "log_path": str(log_path.resolve()),
        "status": status_normalized,
    }


def update_mistake_status(
    course_name: str,
    mistake_id: str,
    status: str,
    root: Path | None = None,
) -> dict:
    """Update status on an existing mistake."""
    course_path = resolve_course_path(course_name, root)
    log_path = get_mistakes_log_path(course_path)
    data = load_mistakes_log(log_path)
    entry = _find_mistake(data["mistakes"], mistake_id)
    entry["status"] = _validate_status(status)
    entry["date_updated"] = _now_iso()
    save_mistakes_log(log_path, data)
    return {
        "mistake_id": entry["mistake_id"],
        "status": entry["status"],
        "log_path": str(log_path.resolve()),
    }


def list_mistakes(course_name: str, root: Path | None = None) -> list[dict]:
    """Return all mistake entries for a course."""
    course_path = resolve_course_path(course_name, root)
    data = load_mistakes_log(get_mistakes_log_path(course_path))
    return list(data.get("mistakes", []))


def get_mistakes_pipeline_warning(course_name: str, root: Path | None = None) -> str | None:
    """Return a Pipeline Doctor warning if open mistakes exist."""
    if count_open_mistakes(course_name, root) > 0:
        return "Open mistakes remain. Review them before test day."
    return None


def count_open_mistakes(course_name: str, root: Path | None = None) -> int:
    """Count mistakes whose status is not mastered."""
    return sum(
        1
        for entry in list_mistakes(course_name, root)
        if str(entry.get("status", "")).lower() != "mastered"
    )


def export_mistakes_markdown(course_name: str, root: Path | None = None) -> Path:
    """Write mistakes log as Markdown."""
    course_path = resolve_course_path(course_name, root)
    log_path = get_mistakes_log_path(course_path)
    out_path = get_mistakes_markdown_path(course_path)
    data = load_mistakes_log(log_path)

    lines = ["# Mistakes Log", ""]
    mistakes = data.get("mistakes", [])
    if not mistakes:
        lines.append("No mistakes recorded yet.")
        lines.append("")
    else:
        for entry in mistakes:
            lines.extend(
                [
                    f"## {entry.get('mistake_id', 'MISTAKE')}",
                    "",
                    "Date:",
                    entry.get("date_created", ""),
                    "",
                    "Course:",
                    entry.get("course", course_path.name),
                    "",
                    "Source:",
                    entry.get("source_id", ""),
                    "",
                    "Question:",
                    entry.get("question", ""),
                    "",
                    "What I answered:",
                    entry.get("user_answer", ""),
                    "",
                    "Correct explanation:",
                    entry.get("correct_explanation", "") or "(not filled in)",
                    "",
                    "Why I got it wrong:",
                    entry.get("why_wrong", "") or "(not filled in)",
                    "",
                    "How to avoid it next time:",
                    entry.get("how_to_avoid", "") or "(not filled in)",
                    "",
                    "Status:",
                    entry.get("status", "new"),
                    "",
                ]
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
