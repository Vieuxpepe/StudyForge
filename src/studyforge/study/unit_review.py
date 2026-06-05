"""
Unit-Level Review v1 — active recall and flashcards from unit study packs (no AI).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.active_recall import (
    VALID_GRADES as RECALL_VALID_GRADES,
    InvalidGradeError,
    _summarize_log_dict,
    parse_active_recall_questions,
)
from studyforge.study.flashcard_review import (
    VALID_GRADES as FLASHCARD_VALID_GRADES,
    InvalidFlashcardGradeError,
    _effective_due_date,
    _is_card_due,
    _latest_review_by_card_id,
)
from studyforge.study.review_schedule import (
    build_review_date_reviewed,
    next_due_date_for_flashcard_grade,
    today_date_str,
)
from studyforge.study.study_units import (
    _normalize_unit_id,
    get_study_unit_summary,
    load_study_units,
)
from studyforge.study.unit_study_pack import (
    get_unit_study_pack_output_paths,
    unit_has_study_pack,
)

MY_WORK_DIR = Path("07_My_Work")
UNIT_RECALL_LOGS_SUBDIR = "unit_active_recall_logs"
UNIT_FLASHCARD_LOGS_SUBDIR = "unit_flashcard_logs"
UNIT_RECALL_LOG_SUFFIX = "_unit_active_recall_log.json"
UNIT_FLASHCARD_LOG_SUFFIX = "_unit_flashcard_review_log.json"

_NEEDS_REVIEW_FLASHCARD_GRADES = frozenset({"hard", "forgot", "skipped"})
_WEAK_RECALL_GRADES = frozenset({"wrong", "partial", "skipped"})


class UnitActiveRecallNotReadyError(Exception):
    """Raised when unit active recall file is missing."""


class UnitFlashcardsNotReadyError(Exception):
    """Raised when unit flashcard CSV is missing."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_unit_id_local(unit_id: str) -> str:
    return unit_id.strip().upper()


def _make_unit_question_id(unit_id: str, number: int) -> str:
    return f"UAR-{_normalize_unit_id_local(unit_id)}-Q{number:03d}"


def _make_unit_attempt_id(attempt_number: int) -> str:
    return f"UAR-ATTEMPT-{attempt_number:04d}"


def _make_unit_card_id(unit_id: str, index: int) -> str:
    return f"UFC-{_normalize_unit_id_local(unit_id)}-{index:04d}"


def _make_unit_review_id(review_number: int) -> str:
    return f"UFC-REVIEW-{review_number:04d}"


def get_unit_active_recall_path(course_path: Path, unit_id: str) -> Path:
    """Return path to the unit active recall Markdown file."""
    paths = get_unit_study_pack_output_paths(course_path, unit_id)
    return paths["unit_active_recall"]


def get_unit_active_recall_log_path(course_path: Path, unit_id: str) -> Path:
    """Return path to the unit active recall JSON log."""
    normalized = _normalize_unit_id_local(unit_id)
    return (
        course_path
        / MY_WORK_DIR
        / UNIT_RECALL_LOGS_SUBDIR
        / f"{normalized}{UNIT_RECALL_LOG_SUFFIX}"
    )


def get_unit_flashcard_review_log_path(course_path: Path, unit_id: str) -> Path:
    """Return path to the unit flashcard review JSON log."""
    normalized = _normalize_unit_id_local(unit_id)
    return (
        course_path
        / MY_WORK_DIR
        / UNIT_FLASHCARD_LOGS_SUBDIR
        / f"{normalized}{UNIT_FLASHCARD_LOG_SUFFIX}"
    )


def load_unit_active_recall_log(path: Path, unit_id: str) -> dict:
    """Load unit active recall log JSON or return empty structure."""
    normalized = _normalize_unit_id_local(unit_id)
    if not path.is_file():
        return {"unit_id": normalized, "attempts": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("unit_id", normalized)
    data.setdefault("attempts", [])
    return data


def save_unit_active_recall_log(path: Path, log: dict) -> None:
    """Write unit active recall log JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2)
        handle.write("\n")


def load_unit_flashcard_review_log(path: Path, unit_id: str) -> dict:
    """Load unit flashcard review log JSON or return empty structure."""
    normalized = _normalize_unit_id_local(unit_id)
    if not path.is_file():
        return {"unit_id": normalized, "reviews": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("unit_id", normalized)
    data.setdefault("reviews", [])
    return data


def save_unit_flashcard_review_log(path: Path, data: dict) -> None:
    """Write unit flashcard review log JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def _units_with_study_packs(course_name: str, root: Path | None = None) -> list[dict]:
    data = load_study_units(course_name, root)
    return [
        dict(unit)
        for unit in data.get("units", [])
        if unit_has_study_pack(unit)
    ]


def load_unit_active_recall_questions(
    course_name: str, unit_id: str, root: Path | None = None
) -> list[dict]:
    """Load and parse questions from the unit study pack active recall file."""
    course_path = resolve_course_path(course_name, root)
    get_study_unit_summary(course_name, unit_id, root)
    normalized = _normalize_unit_id_local(unit_id)
    recall_path = get_unit_active_recall_path(course_path, normalized)
    if not recall_path.is_file():
        raise UnitActiveRecallNotReadyError(
            f"Unit active recall file not found for {normalized}. "
            "Generate a unit study pack first."
        )
    text = recall_path.read_text(encoding="utf-8")
    parsed = parse_active_recall_questions(text, normalized)
    questions: list[dict] = []
    for index, entry in enumerate(parsed, start=1):
        questions.append(
            {
                "question_id": _make_unit_question_id(normalized, index),
                "unit_id": normalized,
                "question_number": index,
                "question": str(entry.get("question", "")),
            }
        )
    return questions


def load_unit_flashcards(
    course_name: str, unit_id: str, root: Path | None = None
) -> list[dict]:
    """Load flashcards from the unit study pack CSV."""
    course_path = resolve_course_path(course_name, root)
    summary = get_study_unit_summary(course_name, unit_id, root)
    normalized = _normalize_unit_id_local(unit_id)
    title = str(summary.get("title", normalized))
    csv_path = get_unit_study_pack_output_paths(course_path, normalized)[
        "unit_flashcards_csv"
    ]
    if not csv_path.is_file():
        raise UnitFlashcardsNotReadyError(
            f"Unit flashcard CSV not found for {normalized}. "
            "Generate a unit study pack first."
        )

    cards: list[dict] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            card_id = str(row.get("card_id", "")).strip()
            if not card_id:
                card_id = _make_unit_card_id(normalized, index)
            cards.append(
                {
                    "card_id": card_id,
                    "front": str(row.get("front", "")),
                    "back": str(row.get("back", "")),
                    "unit_id": normalized,
                    "unit_title": title,
                    "source_id": normalized,
                    "source_title": title,
                    "section": str(row.get("section", "")),
                    "tags": [
                        tag.strip()
                        for tag in str(row.get("tags", "")).split(",")
                        if tag.strip()
                    ],
                }
            )
    return cards


def _latest_attempt_by_question_id(log: dict) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for attempt in log.get("attempts", []):
        question_id = str(attempt.get("question_id", "")).strip()
        if not question_id:
            continue
        existing = latest.get(question_id)
        if existing is None:
            latest[question_id] = dict(attempt)
            continue
        if str(attempt.get("date_answered", "")) >= str(
            existing.get("date_answered", "")
        ):
            latest[question_id] = dict(attempt)
    return latest


def record_unit_active_recall_attempt(
    course_name: str,
    unit_id: str,
    question_id: str,
    question: str,
    user_answer: str,
    grade: str,
    notes: str | None = None,
    create_mistake: bool = False,
    create_weak_point: bool = False,
    weak_point_concept: str | None = None,
    root: Path | None = None,
) -> dict:
    """Append one self-graded unit active recall attempt."""
    grade_normalized = grade.strip().lower()
    if grade_normalized not in RECALL_VALID_GRADES:
        allowed = ", ".join(sorted(RECALL_VALID_GRADES))
        raise InvalidGradeError(f"Invalid grade {grade!r}. Allowed: {allowed}")

    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_unit_id_local(unit_id)
    get_study_unit_summary(course_name, unit_id, root)
    log_path = get_unit_active_recall_log_path(course_path, normalized)
    log = load_unit_active_recall_log(log_path, normalized)

    attempt_number = len(log.get("attempts", [])) + 1
    attempt = {
        "attempt_id": _make_unit_attempt_id(attempt_number),
        "unit_id": normalized,
        "question_id": question_id.strip(),
        "question": question,
        "user_answer": user_answer,
        "grade": grade_normalized,
        "notes": notes or "",
        "date_answered": _now_iso(),
    }
    log.setdefault("attempts", []).append(attempt)
    save_unit_active_recall_log(log_path, log)

    result: dict = {
        "course": course_path.name,
        "unit_id": normalized,
        "attempt_id": attempt["attempt_id"],
        "question_id": attempt["question_id"],
        "grade": grade_normalized,
        "log_path": str(log_path.resolve()),
        "attempt_count": len(log["attempts"]),
    }

    if grade_normalized in _WEAK_RECALL_GRADES:
        if create_mistake:
            from studyforge.study.mistakes import add_mistake

            mistake_summary = add_mistake(
                course_name,
                normalized,
                question,
                user_answer,
                question_id=question_id,
                why_wrong=notes or "",
                root=root,
            )
            result["mistake_id"] = mistake_summary["mistake_id"]
        if create_weak_point:
            from studyforge.study.weak_points import add_weak_point

            concept = (weak_point_concept or "").strip() or question[:80]
            weak_summary = add_weak_point(
                course_name,
                normalized,
                concept,
                why_hard=notes or "",
                what_to_review=question,
                root=root,
            )
            result["weak_point_id"] = weak_summary["weak_point_id"]

    return result


def summarize_unit_active_recall(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Return score summary and recent attempts for one unit."""
    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_unit_id_local(unit_id)
    log_path = get_unit_active_recall_log_path(course_path, normalized)
    log = load_unit_active_recall_log(log_path, normalized)
    summary = _summarize_log_dict(log)
    summary["unit_id"] = normalized
    summary["source_id"] = normalized
    return summary


def collect_unit_active_recall_needs_review_for_unit(
    course_name: str, unit_id: str, root: Path | None = None
) -> list[dict]:
    """Return latest weak unit active recall attempts for one unit."""
    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_unit_id_local(unit_id)
    log_path = get_unit_active_recall_log_path(course_path, normalized)
    if not log_path.is_file():
        return []

    log = load_unit_active_recall_log(log_path, normalized)
    latest = _latest_attempt_by_question_id(log)
    results: list[dict] = []
    for question_id, attempt in latest.items():
        grade = str(attempt.get("grade", "")).lower()
        if grade not in _WEAK_RECALL_GRADES:
            continue
        results.append(
            {
                "type": "unit_active_recall",
                "question_id": question_id,
                "unit_id": normalized,
                "source_id": normalized,
                "question": attempt.get("question", ""),
                "user_answer": attempt.get("user_answer", ""),
                "grade": grade,
                "notes": attempt.get("notes", ""),
                "attempt_id": attempt.get("attempt_id", ""),
                "date_answered": attempt.get("date_answered", ""),
                "title": str(attempt.get("question", ""))[:120],
                "details": f"Last grade: {grade}",
                "priority_reason": "Unit active recall needs review.",
            }
        )
    results.sort(key=lambda item: item.get("question_id", ""))
    return results


def collect_unit_active_recall_needs_review(
    course_name: str, root: Path | None = None
) -> list[dict]:
    """Scan all unit active recall logs and return weak latest attempts."""
    results: list[dict] = []
    for unit in _units_with_study_packs(course_name, root):
        unit_id = str(unit.get("unit_id", ""))
        if not unit_id:
            continue
        results.extend(
            collect_unit_active_recall_needs_review_for_unit(
                course_name, unit_id, root
            )
        )
    results.sort(key=lambda item: (item.get("unit_id", ""), item.get("question_id", "")))
    return results


def record_unit_flashcard_review(
    course_name: str,
    unit_id: str,
    card_id: str,
    front: str,
    back: str,
    grade: str,
    notes: str | None = None,
    create_weak_point: bool = False,
    weak_point_concept: str | None = None,
    reviewed_date: str | None = None,
    root: Path | None = None,
) -> dict:
    """Append one self-graded unit flashcard review."""
    grade_normalized = grade.strip().lower()
    if grade_normalized not in FLASHCARD_VALID_GRADES:
        allowed = ", ".join(sorted(FLASHCARD_VALID_GRADES))
        raise InvalidFlashcardGradeError(
            f"Invalid grade {grade!r}. Allowed: {allowed}"
        )

    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_unit_id_local(unit_id)
    log_path = get_unit_flashcard_review_log_path(course_path, normalized)
    log = load_unit_flashcard_review_log(log_path, normalized)

    review_number = len(log.get("reviews", [])) + 1
    date_reviewed, reviewed_day = build_review_date_reviewed(
        reviewed_date, _now_iso()
    )
    due_date = next_due_date_for_flashcard_grade(grade_normalized, reviewed_day)
    review = {
        "review_id": _make_unit_review_id(review_number),
        "unit_id": normalized,
        "card_id": card_id.strip(),
        "front": front,
        "back": back,
        "grade": grade_normalized,
        "notes": notes or "",
        "date_reviewed": date_reviewed,
        "due_date": due_date,
    }
    log.setdefault("reviews", []).append(review)
    save_unit_flashcard_review_log(log_path, log)

    result: dict = {
        "review_id": review["review_id"],
        "unit_id": normalized,
        "card_id": review["card_id"],
        "grade": grade_normalized,
        "due_date": due_date,
        "log_path": str(log_path.resolve()),
    }

    if create_weak_point and grade_normalized in {"hard", "forgot"}:
        from studyforge.study.weak_points import add_weak_point

        concept = (weak_point_concept or front[:80]).strip()
        if concept:
            wp = add_weak_point(
                course_name,
                normalized,
                concept,
                confidence_level=2,
                what_to_review=front,
                practice_needed="Review unit flashcard until easy.",
                root=root,
            )
            result["weak_point"] = wp

    return result


def summarize_unit_flashcard_reviews(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Return grade counts and due stats for one unit."""
    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_unit_id_local(unit_id)
    log_path = get_unit_flashcard_review_log_path(course_path, normalized)
    log = load_unit_flashcard_review_log(log_path, normalized)
    reviews = list(log.get("reviews", []))

    counts = {"easy": 0, "good": 0, "hard": 0, "forgot": 0, "skipped": 0}
    for review in reviews:
        grade = str(review.get("grade", "")).lower()
        if grade in counts:
            counts[grade] += 1

    latest = _latest_review_by_card_id(log)
    needs_review_count = sum(
        1
        for review in latest.values()
        if str(review.get("grade", "")).lower() in _NEEDS_REVIEW_FLASHCARD_GRADES
    )
    today = today_date_str()
    due_count = sum(
        1 for review in latest.values() if _is_card_due(review, today)
    )

    return {
        "unit_id": normalized,
        "review_count": len(reviews),
        "easy": counts["easy"],
        "good": counts["good"],
        "hard": counts["hard"],
        "forgot": counts["forgot"],
        "skipped": counts["skipped"],
        "needs_review_count": needs_review_count,
        "due_count": due_count,
        "recent_reviews": list(reversed(reviews[-10:])),
    }


def collect_due_unit_flashcards_for_unit(
    course_name: str,
    unit_id: str,
    root: Path | None = None,
    today: str | None = None,
) -> list[dict]:
    """Return unit flashcards whose latest review is due on or before today."""
    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_unit_id_local(unit_id)
    log_path = get_unit_flashcard_review_log_path(course_path, normalized)
    if not log_path.is_file():
        return []

    today_str = today or today_date_str()
    log = load_unit_flashcard_review_log(log_path, normalized)
    latest_by_card = _latest_review_by_card_id(log)
    results: list[dict] = []
    for card_id, review in latest_by_card.items():
        if not _is_card_due(review, today_str):
            continue
        grade = str(review.get("grade", "")).lower()
        effective_due = _effective_due_date(review) or today_str
        results.append(
            {
                "type": "unit_flashcard",
                "card_id": card_id,
                "unit_id": normalized,
                "source_id": normalized,
                "front": review.get("front", ""),
                "back": review.get("back", ""),
                "latest_grade": grade,
                "grade": grade,
                "due_date": effective_due,
                "notes": review.get("notes", ""),
                "review_id": review.get("review_id", ""),
                "date_reviewed": review.get("date_reviewed", ""),
                "section": "",
                "title": str(review.get("front", ""))[:120],
                "details": f"Due: {effective_due}",
                "priority_reason": "Unit flashcard due for review.",
            }
        )
    results.sort(key=lambda item: item.get("card_id", ""))
    return results


def collect_due_unit_flashcards(
    course_name: str,
    root: Path | None = None,
    today: str | None = None,
) -> list[dict]:
    """Return due unit flashcards across all units with study packs."""
    results: list[dict] = []
    for unit in _units_with_study_packs(course_name, root):
        unit_id = str(unit.get("unit_id", ""))
        if not unit_id:
            continue
        results.extend(
            collect_due_unit_flashcards_for_unit(
                course_name, unit_id, root=root, today=today
            )
        )
    results.sort(key=lambda item: (item.get("unit_id", ""), item.get("card_id", "")))
    return results


def collect_unanswered_unit_active_recall(
    course_name: str, unit_id: str, root: Path | None = None
) -> list[dict]:
    """Return unit active recall questions with no attempts yet."""
    normalized = _normalize_unit_id_local(unit_id)
    try:
        questions = load_unit_active_recall_questions(course_name, unit_id, root)
    except UnitActiveRecallNotReadyError:
        return []

    needs_review_ids = {
        str(item.get("question_id", "")).strip()
        for item in collect_unit_active_recall_needs_review_for_unit(
            course_name, unit_id, root
        )
    }

    course_path = resolve_course_path(course_name, root)
    log_path = get_unit_active_recall_log_path(course_path, normalized)
    log = load_unit_active_recall_log(log_path, normalized)
    latest = _latest_attempt_by_question_id(log)

    results: list[dict] = []
    for question in questions:
        question_id = str(question.get("question_id", "")).strip()
        if not question_id or question_id in needs_review_ids:
            continue
        if question_id in latest:
            continue
        results.append(
            {
                "type": "unit_active_recall_unanswered",
                "question_id": question_id,
                "unit_id": normalized,
                "source_id": normalized,
                "question": str(question.get("question", "")),
                "title": "Unanswered unit active recall question",
                "details": "Not answered yet.",
                "priority_reason": "Fresh unit question (not attempted yet).",
            }
        )
    return results


def collect_unreviewed_unit_flashcards(
    course_name: str, unit_id: str, root: Path | None = None
) -> list[dict]:
    """Return unit flashcards with no review log entry yet."""
    normalized = _normalize_unit_id_local(unit_id)
    try:
        cards = load_unit_flashcards(course_name, unit_id, root)
    except UnitFlashcardsNotReadyError:
        return []

    due_ids = {
        str(item.get("card_id", "")).strip()
        for item in collect_due_unit_flashcards_for_unit(
            course_name, unit_id, root
        )
    }

    course_path = resolve_course_path(course_name, root)
    log_path = get_unit_flashcard_review_log_path(course_path, normalized)
    log = load_unit_flashcard_review_log(log_path, normalized)
    reviewed_ids = {
        str(review.get("card_id", "")).strip()
        for review in log.get("reviews", [])
        if str(review.get("card_id", "")).strip()
    }

    results: list[dict] = []
    for card in cards:
        card_id = str(card.get("card_id", "")).strip()
        if not card_id or card_id in due_ids or card_id in reviewed_ids:
            continue
        results.append(
            {
                "type": "unit_flashcard_unreviewed",
                "card_id": card_id,
                "unit_id": normalized,
                "source_id": normalized,
                "front": card.get("front", ""),
                "back": card.get("back", ""),
                "section": card.get("section", ""),
                "title": str(card.get("front", ""))[:120],
                "details": "Not reviewed yet.",
                "priority_reason": "Fresh unit flashcard (not reviewed yet).",
            }
        )
    return results


def get_unit_review_counts(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Return due flashcard and recall gap counts for dashboard display."""
    due_flashcards = len(
        collect_due_unit_flashcards_for_unit(course_name, unit_id, root)
    )
    recall_gaps = len(
        collect_unit_active_recall_needs_review_for_unit(
            course_name, unit_id, root
        )
    )
    try:
        question_count = len(
            load_unit_active_recall_questions(course_name, unit_id, root)
        )
    except UnitActiveRecallNotReadyError:
        question_count = 0
    try:
        flashcard_count = len(load_unit_flashcards(course_name, unit_id, root))
    except UnitFlashcardsNotReadyError:
        flashcard_count = 0
    return {
        "unit_due_flashcards": due_flashcards,
        "unit_recall_gaps": recall_gaps,
        "unit_question_count": question_count,
        "unit_flashcard_count": flashcard_count,
    }
