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
from studyforge.study.study_unit_dashboard import get_unit_source_ids
from studyforge.study.study_units import get_study_unit_summary
from studyforge.study.weak_points import list_weak_points, update_weak_point

_RECALL_ITEM_TYPES = frozenset(
    {"active_recall", "active_recall_unanswered", "unit_active_recall", "unit_active_recall_unanswered"}
)
_FLASHCARD_ITEM_TYPES = frozenset(
    {"flashcard", "flashcard_unreviewed", "unit_flashcard", "unit_flashcard_unreviewed"}
)

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


class ConflictingSessionScopeError(ValueError):
    """Raised when both unit_id and exam_id are provided."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _normalize_unit_id(unit_id: str) -> str:
    return unit_id.strip().upper()


def filter_items_by_source_ids(
    items: list[dict], source_ids: set[str]
) -> list[dict]:
    """Keep items whose ``source_id`` is in the given set (case-insensitive)."""
    if not source_ids:
        return []
    normalized = {_normalize_source_id(sid) for sid in source_ids}
    filtered: list[dict] = []
    for item in items:
        sid = _normalize_source_id(str(item.get("source_id", "")))
        if sid in normalized:
            filtered.append(item)
    return filtered


def filter_items_by_exam_scope(
    items: list[dict],
    source_ids: set[str],
    unit_ids: set[str],
) -> list[dict]:
    """Keep items whose source or unit ID falls within exam scope."""
    if not source_ids and not unit_ids:
        return []
    normalized_sources = {_normalize_source_id(sid) for sid in source_ids}
    normalized_units = {_normalize_unit_id(uid) for uid in unit_ids}
    filtered: list[dict] = []
    for item in items:
        source_id = _normalize_source_id(str(item.get("source_id", "")))
        unit_id = _normalize_unit_id(str(item.get("unit_id", "")))
        if (
            source_id in normalized_sources
            or source_id in normalized_units
            or unit_id in normalized_units
        ):
            filtered.append(dict(item))
    return filtered


def _validate_session_scope(unit_id: str | None, exam_id: str | None) -> None:
    if unit_id is not None and exam_id is not None:
        raise ConflictingSessionScopeError(
            "Provide either unit_id or exam_id for a study session, not both."
        )


def get_exam_scope_info(
    course_name: str, exam_id: str, root: Path | None = None
) -> dict:
    """
    Return session scope metadata for an exam-focused session.

    Raises ``ExamTargetNotFoundError`` when the exam target does not exist.
    """
    from studyforge.study.exam_prep import get_days_until_exam, get_exam_scope_source_ids

    scope_data = get_exam_scope_source_ids(course_name, exam_id, root)
    exam = scope_data["exam"]
    warnings = list(scope_data.get("warnings", []))

    try:
        days_until = get_days_until_exam(str(exam.get("exam_date", "")))
    except ValueError:
        days_until = 0
    if days_until < 0:
        warnings.append("Exam date is in the past; session is still allowed.")

    unit_ids = list(scope_data.get("unit_ids", []))
    source_ids = list(scope_data.get("source_ids", []))
    if not unit_ids and not source_ids:
        warnings.append("Exam target has no units or sources; session will be empty.")

    return {
        "scope": "exam",
        "exam_id": str(exam.get("exam_id", "")).strip().upper(),
        "exam_title": str(exam.get("title", "")),
        "exam_date": str(exam.get("exam_date", "")),
        "target_score": exam.get("target_score"),
        "unit_ids": unit_ids,
        "source_ids": source_ids,
        "warnings": warnings,
    }


def get_unit_scope_info(
    course_name: str, unit_id: str | None, root: Path | None = None
) -> dict:
    """
    Return session scope metadata for course-wide or unit-focused sessions.

    Raises ``StudyUnitNotFoundError`` when ``unit_id`` is set but not found.
    """
    if unit_id is None:
        return {
            "scope": "course",
            "unit_id": "",
            "unit_title": "",
            "source_ids": [],
        }

    summary = get_study_unit_summary(course_name, unit_id, root)
    source_ids = get_unit_source_ids(course_name, unit_id, root)
    return {
        "scope": "unit",
        "unit_id": _normalize_unit_id(str(summary.get("unit_id", ""))),
        "unit_title": str(summary.get("title", "")),
        "source_ids": source_ids,
    }


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


def _unit_recall_payload(entry: dict) -> dict:
    return {
        "question_id": entry.get("question_id", ""),
        "question": entry.get("question", ""),
        "user_answer": entry.get("user_answer", ""),
        "grade": entry.get("grade", ""),
        "attempt_id": entry.get("attempt_id", ""),
        "notes": entry.get("notes", ""),
        "unit_id": entry.get("unit_id", ""),
    }


def _unit_flashcard_session_item(card: dict, index: int, *, unreviewed: bool = False) -> dict:
    unit_id = str(card.get("unit_id", card.get("source_id", "")))
    if unreviewed:
        return {
            "session_item_id": f"SESSION-ITEM-{index:04d}",
            "type": "unit_flashcard_unreviewed",
            "source_id": unit_id,
            "unit_id": unit_id,
            "title": str(card.get("title", card.get("front", "")))[:120],
            "details": str(card.get("details", "Not reviewed yet.")),
            "priority_reason": "Fresh unit flashcard (not reviewed yet).",
            "payload": {
                "card_id": str(card.get("card_id", "")),
                "front": str(card.get("front", "")),
                "back": str(card.get("back", "")),
                "section": str(card.get("section", "")),
                "unit_id": unit_id,
            },
        }
    due_date = str(card.get("due_date", "")).strip()
    details = f"Due: {due_date}" if due_date else str(card.get("notes", ""))
    return {
        "session_item_id": f"SESSION-ITEM-{index:04d}",
        "type": "unit_flashcard",
        "source_id": unit_id,
        "unit_id": unit_id,
        "title": str(card.get("front", ""))[:120],
        "details": details,
        "priority_reason": "Unit flashcard due for review.",
        "payload": {
            "card_id": str(card.get("card_id", "")),
            "front": str(card.get("front", "")),
            "back": str(card.get("back", "")),
            "section": str(card.get("section", "")),
            "due_date": due_date,
            "unit_id": unit_id,
        },
    }


def _build_unit_scoped_session_items(
    course_name: str,
    unit_id: str,
    *,
    source_id_set: set[str],
    root: Path | None,
    limit: int,
) -> list[dict]:
    """Build session items for a unit-scoped session (unit + source-level items)."""
    from studyforge.study.unit_review import (
        collect_due_unit_flashcards_for_unit,
        collect_unit_active_recall_needs_review_for_unit,
        collect_unanswered_unit_active_recall,
        collect_unreviewed_unit_flashcards,
    )

    normalized_unit = unit_id.strip().upper()
    mistakes = filter_items_by_source_ids(
        collect_open_mistakes(course_name, root), source_id_set
    )
    weak_points = filter_items_by_source_ids(
        collect_open_weak_points(course_name, root), source_id_set
    )
    recall_items = filter_items_by_source_ids(
        collect_active_recall_needs_review(course_name, root), source_id_set
    )

    session_items: list[dict] = []
    included_question_ids: set[str] = set()
    included_card_ids: set[str] = set()

    def append_item(item: dict) -> None:
        session_items.append(item)

    for item in collect_unit_active_recall_needs_review_for_unit(
        course_name, normalized_unit, root
    ):
        if len(session_items) >= limit:
            break
        question_id = str(item.get("question_id", "")).strip()
        if not question_id or question_id in included_question_ids:
            continue
        index = len(session_items) + 1
        append_item(
            {
                "session_item_id": f"SESSION-ITEM-{index:04d}",
                "type": "unit_active_recall",
                "source_id": normalized_unit,
                "unit_id": normalized_unit,
                "title": str(item.get("title", "")),
                "details": str(item.get("details", "")),
                "priority_reason": str(item.get("priority_reason", "")),
                "payload": _unit_recall_payload(item),
            }
        )
        included_question_ids.add(question_id)

    if len(session_items) < limit:
        for card in collect_due_unit_flashcards_for_unit(
            course_name, normalized_unit, root
        ):
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            append_item(_unit_flashcard_session_item(card, index))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        mistakes_by_id = {m["mistake_id"]: m for m in list_mistakes(course_name, root)}
        weak_by_id = {w["weak_point_id"]: w for w in list_weak_points(course_name, root)}
        priority = prioritize_review_items(
            mistakes, weak_points, recall_items, limit=limit - len(session_items)
        )
        for item in priority:
            if len(session_items) >= limit:
                break
            item_type = item.get("type", "")
            payload = _enrich_priority_item(item, mistakes_by_id, weak_by_id)
            if item_type == "active_recall":
                question_id = str(payload.get("question_id", "")).strip()
                if question_id:
                    included_question_ids.add(question_id)
            index = len(session_items) + 1
            append_item(
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
        for question in collect_unanswered_unit_active_recall(
            course_name, normalized_unit, root
        ):
            question_id = str(question.get("question_id", "")).strip()
            if not question_id or question_id in included_question_ids:
                continue
            index = len(session_items) + 1
            append_item(
                {
                    "session_item_id": f"SESSION-ITEM-{index:04d}",
                    "type": "unit_active_recall_unanswered",
                    "source_id": normalized_unit,
                    "unit_id": normalized_unit,
                    "title": str(question.get("title", "")),
                    "details": str(question.get("details", "")),
                    "priority_reason": str(question.get("priority_reason", "")),
                    "payload": {
                        "question_id": question_id,
                        "question": str(question.get("question", "")),
                        "unit_id": normalized_unit,
                    },
                }
            )
            included_question_ids.add(question_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        for card in collect_unreviewed_unit_flashcards(
            course_name, normalized_unit, root
        ):
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            append_item(_unit_flashcard_session_item(card, index, unreviewed=True))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        unanswered = collect_unanswered_active_recall_questions(course_name, root)
        unanswered = filter_items_by_source_ids(unanswered, source_id_set)
        for question in unanswered:
            question_id = str(question.get("question_id", "")).strip()
            if not question_id or question_id in included_question_ids:
                continue
            index = len(session_items) + 1
            append_item(
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
        unreviewed_cards = filter_items_by_source_ids(
            unreviewed_cards, source_id_set
        )
        for card in unreviewed_cards:
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            append_item(_flashcard_session_item(card, index, unreviewed=True))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    return session_items


def _build_exam_scoped_session_items(
    course_name: str,
    *,
    unit_ids: list[str],
    source_id_set: set[str],
    unit_id_set: set[str],
    root: Path | None,
    limit: int,
) -> list[dict]:
    """Build session items for an exam-scoped session."""
    from studyforge.study.unit_review import (
        collect_due_unit_flashcards_for_unit,
        collect_unit_active_recall_needs_review_for_unit,
        collect_unanswered_unit_active_recall,
        collect_unreviewed_unit_flashcards,
    )

    session_items: list[dict] = []
    included_question_ids: set[str] = set()
    included_card_ids: set[str] = set()

    def append_item(item: dict) -> None:
        session_items.append(item)

    for normalized_unit in unit_ids:
        if len(session_items) >= limit:
            break
        for card in collect_due_unit_flashcards_for_unit(
            course_name, normalized_unit, root
        ):
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            append_item(_unit_flashcard_session_item(card, index))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    for normalized_unit in unit_ids:
        if len(session_items) >= limit:
            break
        for item in collect_unit_active_recall_needs_review_for_unit(
            course_name, normalized_unit, root
        ):
            question_id = str(item.get("question_id", "")).strip()
            if not question_id or question_id in included_question_ids:
                continue
            index = len(session_items) + 1
            append_item(
                {
                    "session_item_id": f"SESSION-ITEM-{index:04d}",
                    "type": "unit_active_recall",
                    "source_id": normalized_unit,
                    "unit_id": normalized_unit,
                    "title": str(item.get("title", "")),
                    "details": str(item.get("details", "")),
                    "priority_reason": str(item.get("priority_reason", "")),
                    "payload": _unit_recall_payload(item),
                }
            )
            included_question_ids.add(question_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        for card in filter_items_by_source_ids(
            collect_due_flashcards(course_name, root), source_id_set
        ):
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            append_item(_flashcard_session_item(card, index))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        for item in filter_items_by_source_ids(
            collect_active_recall_needs_review(course_name, root), source_id_set
        ):
            question_id = str(item.get("question_id", "")).strip()
            if not question_id or question_id in included_question_ids:
                continue
            index = len(session_items) + 1
            append_item(
                {
                    "session_item_id": f"SESSION-ITEM-{index:04d}",
                    "type": "active_recall",
                    "source_id": str(item.get("source_id", "")),
                    "title": str(item.get("title", "")),
                    "details": str(
                        item.get("details", "") or item.get("priority_reason", "")
                    ),
                    "priority_reason": str(item.get("priority_reason", "")),
                    "payload": _recall_payload(item),
                }
            )
            included_question_ids.add(question_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        for mistake in filter_items_by_exam_scope(
            collect_open_mistakes(course_name, root), source_id_set, unit_id_set
        ):
            index = len(session_items) + 1
            append_item(
                {
                    "session_item_id": f"SESSION-ITEM-{index:04d}",
                    "type": "mistake",
                    "source_id": str(mistake.get("source_id", "")),
                    "title": str(mistake.get("question", ""))[:120],
                    "details": str(mistake.get("user_answer", "")),
                    "priority_reason": "Open mistake in exam scope.",
                    "payload": _mistake_payload(mistake),
                }
            )
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        for weak_point in filter_items_by_exam_scope(
            collect_open_weak_points(course_name, root), source_id_set, unit_id_set
        ):
            index = len(session_items) + 1
            append_item(
                {
                    "session_item_id": f"SESSION-ITEM-{index:04d}",
                    "type": "weak_point",
                    "source_id": str(weak_point.get("source_id", "")),
                    "title": str(weak_point.get("concept", ""))[:120],
                    "details": str(weak_point.get("why_hard", "")),
                    "priority_reason": "Open weak point in exam scope.",
                    "payload": _weak_point_payload(weak_point),
                }
            )
            if len(session_items) >= limit:
                break

    for normalized_unit in unit_ids:
        if len(session_items) >= limit:
            break
        for question in collect_unanswered_unit_active_recall(
            course_name, normalized_unit, root
        ):
            question_id = str(question.get("question_id", "")).strip()
            if not question_id or question_id in included_question_ids:
                continue
            index = len(session_items) + 1
            append_item(
                {
                    "session_item_id": f"SESSION-ITEM-{index:04d}",
                    "type": "unit_active_recall_unanswered",
                    "source_id": normalized_unit,
                    "unit_id": normalized_unit,
                    "title": str(question.get("title", "")),
                    "details": str(question.get("details", "")),
                    "priority_reason": str(question.get("priority_reason", "")),
                    "payload": {
                        "question_id": question_id,
                        "question": str(question.get("question", "")),
                        "unit_id": normalized_unit,
                    },
                }
            )
            included_question_ids.add(question_id)
            if len(session_items) >= limit:
                break

    for normalized_unit in unit_ids:
        if len(session_items) >= limit:
            break
        for card in collect_unreviewed_unit_flashcards(
            course_name, normalized_unit, root
        ):
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            append_item(_unit_flashcard_session_item(card, index, unreviewed=True))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    if len(session_items) < limit:
        unanswered = filter_items_by_source_ids(
            collect_unanswered_active_recall_questions(course_name, root),
            source_id_set,
        )
        for question in unanswered:
            question_id = str(question.get("question_id", "")).strip()
            if not question_id or question_id in included_question_ids:
                continue
            index = len(session_items) + 1
            append_item(
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
        unreviewed_cards = filter_items_by_source_ids(
            collect_unreviewed_flashcards(course_name, root), source_id_set
        )
        for card in unreviewed_cards:
            card_id = str(card.get("card_id", "")).strip()
            if not card_id or card_id in included_card_ids:
                continue
            index = len(session_items) + 1
            append_item(_flashcard_session_item(card, index, unreviewed=True))
            included_card_ids.add(card_id)
            if len(session_items) >= limit:
                break

    return session_items


def build_study_session_items(
    course_name: str,
    root: Path | None = None,
    limit: int = 10,
    unit_id: str | None = None,
    exam_id: str | None = None,
) -> list[dict]:
    """
    Build session items: priorities, due flashcards, unanswered recall, unreviewed.

    Order: review priorities → due flashcards → unanswered active recall →
    unreviewed flashcards. Respects session limit and avoids duplicate card IDs.

    When ``unit_id`` is set, includes unit-level recall/flashcards first, then
    source-level items filtered to the unit's source IDs.

    When ``exam_id`` is set, includes only items from the exam target scope.
    """
    _validate_session_scope(unit_id, exam_id)

    if exam_id is not None:
        scope = get_exam_scope_info(course_name, exam_id, root)
        return _build_exam_scoped_session_items(
            course_name,
            unit_ids=list(scope["unit_ids"]),
            source_id_set=set(scope["source_ids"]),
            unit_id_set=set(scope["unit_ids"]),
            root=root,
            limit=limit,
        )

    if unit_id is not None:
        scope = get_unit_scope_info(course_name, unit_id, root)
        return _build_unit_scoped_session_items(
            course_name,
            unit_id,
            source_id_set=set(scope["source_ids"]),
            root=root,
            limit=limit,
        )

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


def _unit_review_plan_exists_today(
    course_path: Path, unit_id: str, root: Path | None = None
) -> bool:
    from studyforge.study.study_unit_dashboard import get_unit_review_plan_json_path

    return get_unit_review_plan_json_path(course_path, unit_id).is_file()


def _session_warning_from_scope(scope_info: dict) -> str | None:
    warnings = [
        str(warning).strip()
        for warning in scope_info.get("warnings", [])
        if str(warning).strip()
    ]
    if warnings:
        return "; ".join(warnings)
    return None


def start_study_session(
    course_name: str,
    limit: int = 10,
    root: Path | None = None,
    unit_id: str | None = None,
    exam_id: str | None = None,
) -> dict:
    """Create and save a new in-progress study session."""
    _validate_session_scope(unit_id, exam_id)
    course_path = resolve_course_path(course_name, root)
    if exam_id is not None:
        scope_info = get_exam_scope_info(course_name, exam_id, root)
    else:
        scope_info = get_unit_scope_info(course_name, unit_id, root)
    items = build_study_session_items(
        course_name,
        root,
        limit=limit,
        unit_id=unit_id,
        exam_id=exam_id,
    )
    session_id = _make_session_id()
    session: dict = {
        "session_id": session_id,
        "course": course_path.name,
        "scope": scope_info["scope"],
        "date_started": _now_iso(),
        "date_completed": None,
        "status": "in_progress",
        "limit": limit,
        "items": items,
        "completed_items": [],
    }
    warning: str | None = None
    if scope_info["scope"] == "unit":
        session["unit_id"] = scope_info["unit_id"]
        session["unit_title"] = scope_info["unit_title"]
        if not scope_info["source_ids"]:
            warning = "Study unit has no sources; session is empty."
            session["warning"] = warning
        if _unit_review_plan_exists_today(course_path, scope_info["unit_id"]):
            session["based_on_unit_review_plan"] = True
    elif scope_info["scope"] == "exam":
        session["exam_id"] = scope_info["exam_id"]
        session["exam_title"] = scope_info["exam_title"]
        session["exam_date"] = scope_info["exam_date"]
        if scope_info.get("target_score") is not None:
            session["target_score"] = scope_info["target_score"]
        session["unit_ids"] = list(scope_info.get("unit_ids", []))
        session["source_ids"] = list(scope_info.get("source_ids", []))
        warning = _session_warning_from_scope(scope_info)
        if warning:
            session["warning"] = warning
    log_path = _save_session(course_path, session)
    result = {
        "session_id": session_id,
        "course": course_path.name,
        "item_count": len(items),
        "log_path": str(log_path.resolve()),
        "status": "in_progress",
        "scope": scope_info["scope"],
    }
    if scope_info["scope"] == "unit":
        result["unit_id"] = scope_info["unit_id"]
        result["unit_title"] = scope_info["unit_title"]
    elif scope_info["scope"] == "exam":
        result["exam_id"] = scope_info["exam_id"]
        result["exam_title"] = scope_info["exam_title"]
        result["exam_date"] = scope_info["exam_date"]
        if scope_info.get("target_score") is not None:
            result["target_score"] = scope_info["target_score"]
        result["unit_ids"] = list(scope_info.get("unit_ids", []))
        result["source_ids"] = list(scope_info.get("source_ids", []))
    if warning:
        result["warning"] = warning
    return result


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

    if item_type in {"unit_active_recall", "unit_active_recall_unanswered"} and result in _RECALL_RESULTS:
        from studyforge.study.unit_review import record_unit_active_recall_attempt

        unit_id = str(payload.get("unit_id", source_id))
        question_id = str(payload.get("question_id", ""))
        question = str(payload.get("question", item.get("title", "")))
        answer_text = (user_answer or notes or "").strip()
        recall_summary = record_unit_active_recall_attempt(
            course_name,
            unit_id,
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
        applied["unit_active_recall"] = recall_summary
    elif item_type in {"active_recall", "active_recall_unanswered"} and result in _RECALL_RESULTS:
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
    elif item_type in {"unit_flashcard", "unit_flashcard_unreviewed"} and result in _FLASHCARD_RESULTS:
        from studyforge.study.unit_review import record_unit_flashcard_review

        unit_id = str(payload.get("unit_id", source_id))
        card_id = str(payload.get("card_id", ""))
        front = str(payload.get("front", item.get("title", "")))
        back = str(payload.get("back", ""))
        flashcard_summary = record_unit_flashcard_review(
            course_name,
            unit_id,
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
        applied["unit_flashcard_review"] = flashcard_summary
    elif item_type in {"flashcard", "flashcard_unreviewed"} and result in _FLASHCARD_RESULTS:
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

    scope = session.get("scope", "course")
    lines = [
        f"# Study Session Summary — {session_id}",
        "",
        "Course:",
        session.get("course", course_path.name),
        "",
        "Scope:",
        scope,
        "",
    ]
    if scope == "unit":
        lines.extend(
            [
                "Unit:",
                f"{session.get('unit_id', '')} — {session.get('unit_title', '')}",
                "",
            ]
        )
    elif scope == "exam":
        lines.extend(
            [
                "Exam:",
                f"{session.get('exam_id', '')} — {session.get('exam_title', '')}",
                "",
                "Date:",
                str(session.get("exam_date", "")),
                "",
            ]
        )
        if session.get("target_score") is not None:
            lines.extend(
                [
                    "Target:",
                    f"{session.get('target_score')}%",
                    "",
                ]
            )
        unit_ids = session.get("unit_ids") or []
        source_ids = session.get("source_ids") or []
        if unit_ids or source_ids:
            lines.extend(
                [
                    "Units:",
                    ", ".join(unit_ids) if unit_ids else "(none)",
                    "",
                    "Sources:",
                    ", ".join(source_ids) if source_ids else "(none)",
                    "",
                ]
            )
    if session.get("based_on_unit_review_plan"):
        lines.extend(
            [
                "Unit review plan:",
                "Today's unit review plan exists for this unit.",
                "",
            ]
        )
    if session.get("warning"):
        lines.extend(["Warning:", session["warning"], ""])

    lines.extend(
        [
            "Started:",
            session.get("date_started", ""),
            "",
            "Completed:",
            session.get("date_completed", "") or "(in progress)",
            "",
        ]
    )
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
