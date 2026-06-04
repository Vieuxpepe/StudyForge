"""
Study Session Mode v1 — guided review through today's priorities (deterministic, no AI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.mistakes import list_mistakes, update_mistake_status
from studyforge.study.review_planner import (
    collect_active_recall_needs_review,
    collect_open_mistakes,
    collect_open_weak_points,
    prioritize_review_items,
)
from studyforge.study.weak_points import list_weak_points, update_weak_point

MY_WORK_DIR = Path("07_My_Work")
STUDY_SESSIONS_SUBDIR = "study_sessions"

VALID_SESSION_RESULTS = frozenset(
    {
        "completed",
        "correct",
        "partial",
        "wrong",
        "skipped",
        "mastered",
        "still_weak",
        "reviewed_once",
        "reviewing",
        "improving",
        "new",
    }
)

_RECALL_RESULTS = frozenset({"correct", "partial", "wrong", "skipped"})
_MISTAKE_RESULTS = frozenset({"reviewed_once", "still_weak", "mastered", "completed"})
_WEAK_RESULTS = frozenset(
    {"still_weak", "mastered", "completed", "reviewing", "improving", "new"}
)


class InvalidSessionResultError(ValueError):
    """Raised when a session result value is not allowed."""


class StudySessionNotFoundError(Exception):
    """Raised when the session JSON log does not exist."""


class StudySessionItemNotFoundError(Exception):
    """Raised when session_item_id is not in the session."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _make_session_id() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"SESSION-{stamp}"


def get_study_session_log_dir(course_path: Path) -> Path:
    """Return ``07_My_Work/study_sessions/`` for a course."""
    return course_path / MY_WORK_DIR / STUDY_SESSIONS_SUBDIR


def get_study_session_log_path(course_path: Path, session_id: str) -> Path:
    """Return path to ``<session_id>.json``."""
    safe_id = session_id.strip()
    return get_study_session_log_dir(course_path) / f"{safe_id}.json"


def get_study_session_summary_path(course_path: Path, session_id: str) -> Path:
    """Return path to ``<session_id>_summary.md``."""
    safe_id = session_id.strip()
    return get_study_session_log_dir(course_path) / f"{safe_id}_summary.md"


def _validate_result(result: str) -> str:
    normalized = result.strip().lower()
    if normalized not in VALID_SESSION_RESULTS:
        allowed = ", ".join(sorted(VALID_SESSION_RESULTS))
        raise InvalidSessionResultError(
            f"Invalid result {result!r}. Allowed: {allowed}"
        )
    return normalized


def _mistake_payload(entry: dict) -> dict:
    return {
        "mistake_id": entry.get("mistake_id", ""),
        "question_id": entry.get("question_id", ""),
        "question": entry.get("question", ""),
        "user_answer": entry.get("user_answer", ""),
        "correct_explanation": entry.get("correct_explanation", ""),
        "why_wrong": entry.get("why_wrong", ""),
        "how_to_avoid": entry.get("how_to_avoid", ""),
        "status": entry.get("status", ""),
    }


def _weak_point_payload(entry: dict) -> dict:
    return {
        "weak_point_id": entry.get("weak_point_id", ""),
        "concept": entry.get("concept", ""),
        "why_hard": entry.get("why_hard", ""),
        "what_to_review": entry.get("what_to_review", ""),
        "practice_needed": entry.get("practice_needed", ""),
        "confidence_level": entry.get("confidence_level", 3),
        "status": entry.get("status", ""),
    }


def _recall_payload(entry: dict) -> dict:
    return {
        "question_id": entry.get("question_id", ""),
        "question": entry.get("question", ""),
        "user_answer": entry.get("user_answer", ""),
        "grade": entry.get("grade", ""),
        "attempt_id": entry.get("attempt_id", ""),
        "notes": entry.get("notes", ""),
    }


def _enrich_priority_item(item: dict, mistakes_by_id: dict, weak_by_id: dict) -> dict:
    item_type = item.get("type", "")
    item_id = str(item.get("id", ""))
    if item_type == "mistake" and item_id in mistakes_by_id:
        return _mistake_payload(mistakes_by_id[item_id])
    if item_type == "weak_point" and item_id in weak_by_id:
        return _weak_point_payload(weak_by_id[item_id])
    if item_type == "active_recall":
        return _recall_payload(item)
    return dict(item)


def build_study_session_items(
    course_name: str,
    root: Path | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Build prioritized session items from open mistakes, weak points, and recall gaps.
    """
    mistakes = collect_open_mistakes(course_name, root)
    weak_points = collect_open_weak_points(course_name, root)
    recall_items = collect_active_recall_needs_review(course_name, root)

    priority = prioritize_review_items(mistakes, weak_points, recall_items, limit=limit)

    mistakes_by_id = {m["mistake_id"]: m for m in list_mistakes(course_name, root)}
    weak_by_id = {w["weak_point_id"]: w for w in list_weak_points(course_name, root)}

    session_items: list[dict] = []
    for index, item in enumerate(priority, start=1):
        item_type = item.get("type", "")
        payload = _enrich_priority_item(item, mistakes_by_id, weak_by_id)
        session_items.append(
            {
                "session_item_id": f"SESSION-ITEM-{index:04d}",
                "type": item_type,
                "source_id": str(item.get("source_id", "")),
                "title": str(item.get("title", "")),
                "details": str(
                    item.get("details", "") or item.get("priority_reason", "")
                ),
                "priority_reason": str(item.get("priority_reason", "")),
                "payload": payload,
            }
        )
    return session_items


def _load_session(course_path: Path, session_id: str) -> dict:
    path = get_study_session_log_path(course_path, session_id)
    if not path.is_file():
        raise StudySessionNotFoundError(f"Study session not found: {session_id}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _save_session(course_path: Path, session: dict) -> Path:
    session_id = str(session["session_id"])
    path = get_study_session_log_path(course_path, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(session, handle, indent=2)
        handle.write("\n")
    return path


def start_study_session(
    course_name: str,
    limit: int = 10,
    root: Path | None = None,
) -> dict:
    """Create and save a new in-progress study session."""
    course_path = resolve_course_path(course_name, root)
    items = build_study_session_items(course_name, root, limit=limit)
    session_id = _make_session_id()
    session = {
        "session_id": session_id,
        "course": course_path.name,
        "date_started": _now_iso(),
        "date_completed": None,
        "status": "in_progress",
        "limit": limit,
        "items": items,
        "completed_items": [],
    }
    log_path = _save_session(course_path, session)
    return {
        "session_id": session_id,
        "course": course_path.name,
        "item_count": len(items),
        "log_path": str(log_path.resolve()),
        "status": "in_progress",
    }


def get_latest_study_session(
    course_name: str, root: Path | None = None
) -> dict | None:
    """Return the most recently modified session log, or None."""
    course_path = resolve_course_path(course_name, root)
    log_dir = get_study_session_log_dir(course_path)
    if not log_dir.is_dir():
        return None
    candidates = [
        path
        for path in log_dir.glob("SESSION-*.json")
        if not path.name.endswith("_summary.md")
    ]
    if not candidates:
        return None
    latest_path = max(candidates, key=lambda path: path.stat().st_mtime)
    with latest_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _find_session_item(session: dict, session_item_id: str) -> dict:
    target = session_item_id.strip().upper()
    for item in session.get("items", []):
        if str(item.get("session_item_id", "")).upper() == target:
            return item
    raise StudySessionItemNotFoundError(
        f"Session item not found: {session_item_id}"
    )


def _upsert_completed(session: dict, entry: dict) -> None:
    completed = session.setdefault("completed_items", [])
    item_id = entry["session_item_id"]
    for index, existing in enumerate(completed):
        if existing.get("session_item_id") == item_id:
            completed[index] = entry
            return
    completed.append(entry)


def _apply_item_side_effects(
    course_name: str,
    item: dict,
    result: str,
    *,
    user_answer: str | None = None,
    notes: str | None = None,
    create_mistake: bool = False,
    create_weak_point: bool = False,
    weak_point_concept: str | None = None,
    confidence_level: int | None = None,
    root: Path | None = None,
) -> dict:
    """Update mistakes, weak points, or active recall logs when appropriate."""
    applied: dict = {}
    item_type = item.get("type", "")
    payload = item.get("payload", {})
    source_id = str(item.get("source_id", ""))

    if item_type == "active_recall" and result in _RECALL_RESULTS:
        from studyforge.study.active_recall import record_active_recall_attempt

        question_id = str(payload.get("question_id", ""))
        question = str(payload.get("question", item.get("title", "")))
        answer_text = (user_answer or notes or "").strip()
        recall_summary = record_active_recall_attempt(
            course_name,
            source_id,
            question_id,
            question,
            answer_text,
            result,
            notes=notes,
            create_mistake=create_mistake and result in {"wrong", "partial", "skipped"},
            create_weak_point=create_weak_point
            and result in {"wrong", "partial", "skipped"},
            weak_point_concept=weak_point_concept,
            root=root,
        )
        applied["active_recall"] = recall_summary
    elif item_type == "mistake" and result in _MISTAKE_RESULTS - {"completed"}:
        mistake_id = str(payload.get("mistake_id", ""))
        if mistake_id and result in {"reviewed_once", "still_weak", "mastered"}:
            applied["mistake"] = update_mistake_status(
                course_name, mistake_id, result, root=root
            )
    elif item_type == "weak_point":
        weak_id = str(payload.get("weak_point_id", ""))
        if weak_id:
            status_arg = result if result in _WEAK_RESULTS else None
            if status_arg and status_arg != "completed":
                applied["weak_point"] = update_weak_point(
                    course_name,
                    weak_id,
                    confidence_level=confidence_level,
                    status=status_arg,
                    root=root,
                )
            elif confidence_level is not None:
                applied["weak_point"] = update_weak_point(
                    course_name,
                    weak_id,
                    confidence_level=confidence_level,
                    root=root,
                )

    return applied


def record_session_item_result(
    course_name: str,
    session_id: str,
    session_item_id: str,
    result: str,
    notes: str | None = None,
    user_answer: str | None = None,
    create_mistake: bool = False,
    create_weak_point: bool = False,
    weak_point_concept: str | None = None,
    confidence_level: int | None = None,
    root: Path | None = None,
) -> dict:
    """Record result for one session item and optionally update trackers."""
    result_normalized = _validate_result(result)
    course_path = resolve_course_path(course_name, root)
    session = _load_session(course_path, session_id)
    item = _find_session_item(session, session_item_id)

    applied = _apply_item_side_effects(
        course_name,
        item,
        result_normalized,
        user_answer=user_answer,
        notes=notes,
        create_mistake=create_mistake,
        create_weak_point=create_weak_point,
        weak_point_concept=weak_point_concept,
        confidence_level=confidence_level,
        root=root,
    )

    completed_entry = {
        "session_item_id": item["session_item_id"],
        "type": item["type"],
        "source_id": item.get("source_id", ""),
        "result": result_normalized,
        "notes": notes or "",
        "user_answer": user_answer or "",
        "date_completed": _now_iso(),
        "applied": applied,
    }
    _upsert_completed(session, completed_entry)
    _save_session(course_path, session)

    return {
        "session_id": session_id,
        "session_item_id": item["session_item_id"],
        "result": result_normalized,
        "applied": applied,
        "completed_count": len(session.get("completed_items", [])),
        "item_count": len(session.get("items", [])),
    }


def complete_study_session(
    course_name: str, session_id: str, root: Path | None = None
) -> dict:
    """Mark session as complete."""
    course_path = resolve_course_path(course_name, root)
    session = _load_session(course_path, session_id)
    session["status"] = "complete"
    session["date_completed"] = _now_iso()
    log_path = _save_session(course_path, session)
    return {
        "session_id": session_id,
        "status": "complete",
        "date_completed": session["date_completed"],
        "log_path": str(log_path.resolve()),
        "completed_count": len(session.get("completed_items", [])),
        "item_count": len(session.get("items", [])),
    }


def _duration_minutes(session: dict) -> str | None:
    started = session.get("date_started", "")
    completed = session.get("date_completed") or _now_iso()
    if not started:
        return None
    try:
        start_dt = datetime.fromisoformat(started)
        end_dt = datetime.fromisoformat(completed)
        delta = end_dt - start_dt
        minutes = max(0, int(delta.total_seconds() // 60))
        return str(minutes)
    except ValueError:
        return None


def export_study_session_summary(
    course_name: str, session_id: str, root: Path | None = None
) -> Path:
    """Write Markdown summary for a study session."""
    course_path = resolve_course_path(course_name, root)
    session = _load_session(course_path, session_id)
    items = session.get("items", [])
    completed = session.get("completed_items", [])
    completed_by_id = {
        c["session_item_id"]: c for c in completed if c.get("session_item_id")
    }

    duration = _duration_minutes(session)
    recall_grades: dict[str, int] = {}
    mistakes_reviewed = 0
    weak_reviewed = 0

    lines = [
        f"# Study Session Summary — {session_id}",
        "",
        "Course:",
        session.get("course", course_path.name),
        "",
        "Started:",
        session.get("date_started", ""),
        "",
        "Completed:",
        session.get("date_completed", "") or "(in progress)",
        "",
    ]
    if duration is not None:
        lines.extend(["Duration (minutes):", duration, ""])

    lines.extend(
        [
            "Items in session:",
            str(len(items)),
            "",
            "Items completed:",
            str(len(completed)),
            "",
            "## Results by item",
            "",
        ]
    )

    if not items:
        lines.append("No priority items were available for this session.")
        lines.append("")
    else:
        for item in items:
            item_id = item.get("session_item_id", "")
            done = completed_by_id.get(item_id)
            lines.append(f"### {item_id} — {item.get('type', '')}")
            lines.append("")
            lines.append(f"- Source: {item.get('source_id', '')}")
            lines.append(f"- Title: {item.get('title', '')}")
            if item.get("priority_reason"):
                lines.append(f"- Priority: {item['priority_reason']}")
            if done:
                lines.append(f"- Result: {done.get('result', '')}")
                if done.get("notes"):
                    lines.append(f"- Notes: {done['notes']}")
                item_type = item.get("type", "")
                result = str(done.get("result", "")).lower()
                if item_type == "active_recall" and result in _RECALL_RESULTS:
                    recall_grades[result] = recall_grades.get(result, 0) + 1
                if item_type == "mistake":
                    mistakes_reviewed += 1
                if item_type == "weak_point":
                    weak_reviewed += 1
            else:
                lines.append("- Result: (not completed in session)")
            lines.append("")

    lines.extend(["## Session stats", ""])
    if recall_grades:
        lines.append("Active recall grades:")
        for grade, count in sorted(recall_grades.items()):
            lines.append(f"- {grade}: {count}")
        lines.append("")
    lines.append(f"Mistake items touched: {mistakes_reviewed}")
    lines.append(f"Weak point items touched: {weak_reviewed}")
    lines.append("")

    remaining = len(items) - len(completed)
    lines.extend(["## Next suggested actions", ""])
    if remaining > 0:
        lines.append(
            f"- Finish {remaining} remaining item(s) in a follow-up session or on Review Tracker."
        )
    if recall_grades.get("wrong") or recall_grades.get("partial"):
        lines.append("- Revisit weak active recall questions on the Active Recall page.")
    if mistakes_reviewed:
        lines.append("- Check Mistakes Log for items still marked still_weak.")
    if weak_reviewed:
        lines.append("- Update weak points confidence after more practice.")
    if not items:
        lines.append(
            "- Generate a review plan or complete active recall practice to build session items."
        )
    if remaining == 0 and items:
        lines.append("- Session queue complete. Consider starting a new session tomorrow.")
    lines.append("")

    out_path = get_study_session_summary_path(course_path, session_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
