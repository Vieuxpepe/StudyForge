"""
Study Session Mode v1 — guided review through today's priorities (deterministic, no AI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import load_source_registry, resolve_course_path
from studyforge.study.mistakes import list_mistakes, update_mistake_status
from studyforge.study.review_planner import (
    collect_active_recall_needs_review,
    collect_open_mistakes,
    collect_open_weak_points,
    prioritize_review_items,
)
from studyforge.study.flashcard_review import (
    collect_due_flashcards,
    collect_unreviewed_flashcards,
)
from studyforge.study.weak_points import list_weak_points, update_weak_point

_RECALL_ITEM_TYPES = frozenset({"active_recall", "active_recall_unanswered"})
_FLASHCARD_ITEM_TYPES = frozenset({"flashcard", "flashcard_unreviewed"})

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
        "easy",
        "good",
        "hard",
        "forgot",
    }
)

_RECALL_RESULTS = frozenset({"correct", "partial", "wrong", "skipped"})
_FLASHCARD_RESULTS = frozenset({"easy", "good", "hard", "forgot", "skipped"})
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


def _resolve_active_recall_file_for_source(
    entry: dict, course_path: Path
) -> Path | None:
    """Return active recall Markdown path for a registry entry, or None."""
    from studyforge.study.active_recall import get_active_recall_file

    source_id = str(entry.get("id", "")).strip()
    if not source_id:
        return None

    has_study_pack = (
        bool(entry.get("active_recall_path"))
        or str(entry.get("status", "")).lower() == "study_pack_generated"
        or bool(entry.get("study_pack_manifest_path"))
    )
    if not has_study_pack:
        return None

    recall_path = get_active_recall_file(course_path, source_id)
    registry_path = str(entry.get("active_recall_path", "")).strip()
    if registry_path:
        candidate = Path(registry_path)
        if candidate.is_file():
            return candidate
    if recall_path.is_file():
        return recall_path
    return None


def _latest_attempt_by_question_id(log: dict) -> dict[str, dict]:
    """Return the most recent attempt per question_id."""
    latest: dict[str, dict] = {}
    for attempt in log.get("attempts", []):
        question_id = str(attempt.get("question_id", "")).strip()
        if not question_id:
            continue
        existing = latest.get(question_id)
        if existing is None:
            latest[question_id] = dict(attempt)
            continue
        existing_time = str(existing.get("date_answered", ""))
        attempt_time = str(attempt.get("date_answered", ""))
        if attempt_time >= existing_time:
            latest[question_id] = dict(attempt)
    return latest


def collect_unanswered_active_recall_questions(
    course_name: str,
    root: Path | None = None,
    limit_per_source: int | None = None,
) -> list[dict]:
    """
    Return active recall questions from study packs that have no attempts yet.

    Excludes questions whose latest attempt was correct, and questions already
    covered by ``collect_active_recall_needs_review()``.
    """
    from studyforge.study.active_recall import (
        get_active_recall_log_path,
        load_active_recall_log,
        parse_active_recall_questions,
    )

    course_path = resolve_course_path(course_name, root)
    registry = load_source_registry(course_path)
    needs_review_ids = {
        str(item.get("question_id", "")).strip()
        for item in collect_active_recall_needs_review(course_name, root)
        if str(item.get("question_id", "")).strip()
    }

    results: list[dict] = []
    for entry in registry.get("sources", []):
        recall_path = _resolve_active_recall_file_for_source(entry, course_path)
        if recall_path is None:
            continue

        source_id = str(entry.get("id", "")).strip()
        text = recall_path.read_text(encoding="utf-8")
        questions = parse_active_recall_questions(text, source_id)
        log_path = get_active_recall_log_path(course_path, source_id)
        log = load_active_recall_log(log_path)
        latest_by_question = _latest_attempt_by_question_id(log)

        source_count = 0
        for question in questions:
            question_id = str(question.get("question_id", "")).strip()
            if not question_id:
                continue
            if question_id in needs_review_ids:
                continue

            latest = latest_by_question.get(question_id)
            if latest is not None:
                grade = str(latest.get("grade", "")).lower()
                if grade == "correct":
                    continue
                continue

            results.append(
                {
                    "type": "active_recall_unanswered",
                    "source_id": source_id,
                    "question_id": question_id,
                    "question": str(question.get("question", "")),
                    "title": "Unanswered active recall question",
                    "details": "Not answered yet.",
                }
            )
            source_count += 1
            if limit_per_source is not None and source_count >= limit_per_source:
                break

    results.sort(key=lambda item: (item["source_id"], item["question_id"]))
    return results


def _flashcard_payload(entry: dict) -> dict:
    return {
        "card_id": entry.get("card_id", ""),
        "front": entry.get("front", ""),
        "back": entry.get("back", ""),
        "grade": entry.get("latest_grade", entry.get("grade", "")),
        "due_date": entry.get("due_date", ""),
        "section": entry.get("section", ""),
        "notes": entry.get("notes", ""),
    }


def _flashcard_session_item(card: dict, index: int, *, unreviewed: bool = False) -> dict:
    if unreviewed:
        return {
            "session_item_id": f"SESSION-ITEM-{index:04d}",
            "type": "flashcard_unreviewed",
            "source_id": str(card.get("source_id", "")),
            "title": str(card.get("title", card.get("front", ""))[:120]),
            "details": str(card.get("details", "Not reviewed yet.")),
            "priority_reason": "Fresh flashcard from study pack (not reviewed yet).",
            "payload": {
                "card_id": str(card.get("card_id", "")),
                "front": str(card.get("front", "")),
                "back": str(card.get("back", "")),
                "section": str(card.get("section", "")),
            },
        }
    due_date = str(card.get("due_date", "")).strip()
    details = f"Due: {due_date}" if due_date else str(card.get("notes", ""))
    return {
        "session_item_id": f"SESSION-ITEM-{index:04d}",
        "type": "flashcard",
        "source_id": str(card.get("source_id", "")),
        "title": str(card.get("front", ""))[:120],
        "details": details,
        "priority_reason": "Flashcard due for review.",
        "payload": _flashcard_payload(card),
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
    if item_type == "flashcard":
        return _flashcard_payload(item)
    return dict(item)


def build_study_session_items(
    course_name: str,
    root: Path | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Build session items: priorities, due flashcards, unanswered recall, unreviewed.

    Order: review priorities → due flashcards → unanswered active recall →
    unreviewed flashcards. Respects session limit and avoids duplicate card IDs.
    """
    mistakes = collect_open_mistakes(course_name, root)
    weak_points = collect_open_weak_points(course_name, root)
    recall_items = collect_active_recall_needs_review(course_name, root)

    priority = prioritize_review_items(
        mistakes, weak_points, recall_items, limit=limit
    )

    mistakes_by_id = {m["mistake_id"]: m for m in list_mistakes(course_name, root)}
    weak_by_id = {w["weak_point_id"]: w for w in list_weak_points(course_name, root)}

    session_items: list[dict] = []
    included_question_ids: set[str] = set()
    included_card_ids: set[str] = set()
    for index, item in enumerate(priority, start=1):
        item_type = item.get("type", "")
        payload = _enrich_priority_item(item, mistakes_by_id, weak_by_id)
        if item_type == "active_recall":
            question_id = str(payload.get("question_id", "")).strip()
            if question_id:
                included_question_ids.add(question_id)
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

    if len(session_items) < limit:
        due_cards = collect_due_flashcards(course_name, root)
        for card in due_cards:
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            session_items.append(_flashcard_session_item(card, index))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        unanswered = collect_unanswered_active_recall_questions(course_name, root)
        for question in unanswered:
            question_id = str(question.get("question_id", "")).strip()
            if not question_id or question_id in included_question_ids:
                continue
            index = len(session_items) + 1
            session_items.append(
                {
                    "session_item_id": f"SESSION-ITEM-{index:04d}",
                    "type": "active_recall_unanswered",
                    "source_id": str(question.get("source_id", "")),
                    "title": str(question.get("title", "")),
                    "details": str(question.get("details", "")),
                    "priority_reason": "Fresh question from study pack (not attempted yet).",
                    "payload": {
                        "question_id": question_id,
                        "question": str(question.get("question", "")),
                    },
                }
            )
            included_question_ids.add(question_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        unreviewed_cards = collect_unreviewed_flashcards(course_name, root)
        for card in unreviewed_cards:
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            session_items.append(_flashcard_session_item(card, index, unreviewed=True))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

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

    if item_type in _RECALL_ITEM_TYPES and result in _RECALL_RESULTS:
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
    elif item_type in _FLASHCARD_ITEM_TYPES and result in _FLASHCARD_RESULTS:
        from studyforge.study.flashcard_review import record_flashcard_review

        card_id = str(payload.get("card_id", ""))
        front = str(payload.get("front", item.get("title", "")))
        back = str(payload.get("back", ""))
        flashcard_summary = record_flashcard_review(
            course_name,
            source_id,
            card_id,
            front,
            back,
            result,
            notes=notes,
            create_weak_point=create_weak_point
            and result in {"hard", "forgot"},
            weak_point_concept=weak_point_concept,
            root=root,
        )
        applied["flashcard_review"] = flashcard_summary
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
    flashcard_grades: dict[str, int] = {}
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
                if item_type in _RECALL_ITEM_TYPES and result in _RECALL_RESULTS:
                    recall_grades[result] = recall_grades.get(result, 0) + 1
                if item_type in _FLASHCARD_ITEM_TYPES and result in _FLASHCARD_RESULTS:
                    flashcard_grades[result] = flashcard_grades.get(result, 0) + 1
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
    if flashcard_grades:
        lines.append("Flashcard grades:")
        for grade, count in sorted(flashcard_grades.items()):
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
