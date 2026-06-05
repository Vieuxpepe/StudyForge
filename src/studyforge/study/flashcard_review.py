"""
Flashcard Review Mode v1 — self-graded review with JSON logs (no AI).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.extraction_jobs import find_source_by_id
from studyforge.core.sources import load_source_registry, resolve_course_path
from studyforge.study.flashcards import get_flashcard_output_paths
from studyforge.study.review_schedule import (
    build_review_date_reviewed,
    is_due,
    latest_review_by_card,
    next_due_date_for_flashcard_grade,
    today_date_str,
)
from studyforge.study.weak_points import add_weak_point

MY_WORK_DIR = Path("07_My_Work")
FLASHCARD_LOGS_SUBDIR = "flashcard_logs"
REVIEW_LOG_SUFFIX = "_flashcard_review_log.json"

VALID_GRADES = frozenset({"easy", "good", "hard", "forgot", "skipped"})
_NEEDS_REVIEW_GRADES = frozenset({"hard", "forgot", "skipped"})


class InvalidFlashcardGradeError(ValueError):
    """Raised when a flashcard review grade is not allowed."""


class FlashcardsNotReadyError(Exception):
    """Raised when flashcard CSV export is missing."""


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _make_card_id(source_id: str, index: int) -> str:
    return f"FC-{_normalize_source_id(source_id)}-{index:04d}"


def _make_review_id(review_number: int) -> str:
    return f"FC-REVIEW-{review_number:04d}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_tags(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _resolve_flashcards_csv_path(
    course_path: Path, source_id: str, entry: dict
) -> Path:
    """Resolve flashcard CSV from registry, manifest, or default path."""
    registry_path = str(entry.get("flashcards_csv_path", "")).strip()
    if registry_path:
        candidate = Path(registry_path)
        if candidate.is_file():
            return candidate

    manifest_path = str(entry.get("study_pack_manifest_path", "")).strip()
    if manifest_path:
        manifest_file = Path(manifest_path)
        if manifest_file.is_file():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                csv_from_manifest = str(
                    manifest.get("outputs", {}).get("flashcards_csv", "")
                ).strip()
                if csv_from_manifest:
                    candidate = Path(csv_from_manifest)
                    if candidate.is_file():
                        return candidate
            except (OSError, json.JSONDecodeError):
                pass

    default_path = get_flashcard_output_paths(course_path, source_id)["csv"]
    if default_path.is_file():
        return default_path

    raise FlashcardsNotReadyError(
        f"Flashcard CSV not found for {source_id}. "
        "Generate a study pack or run export_flashcards.py first."
    )


def load_flashcards_for_source(
    course_name: str, source_id: str, root: Path | None = None
) -> list[dict]:
    """Load flashcards from the CSV export for a source."""
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    csv_path = _resolve_flashcards_csv_path(course_path, normalized_id, entry)

    cards: list[dict] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            card_id = str(row.get("card_id", "")).strip()
            if not card_id:
                card_id = _make_card_id(normalized_id, index)
            cards.append(
                {
                    "card_id": card_id,
                    "front": str(row.get("front", "")),
                    "back": str(row.get("back", "")),
                    "source_id": str(row.get("source_id", normalized_id)),
                    "source_title": str(row.get("source_title", entry.get("title", ""))),
                    "section": str(row.get("section", "")),
                    "tags": _parse_tags(str(row.get("tags", ""))),
                }
            )
    return cards


def get_flashcard_review_log_path(course_path: Path, source_id: str) -> Path:
    """Return ``07_My_Work/flashcard_logs/<source_id>_flashcard_review_log.json``."""
    normalized = _normalize_source_id(source_id)
    return (
        course_path
        / MY_WORK_DIR
        / FLASHCARD_LOGS_SUBDIR
        / f"{normalized}{REVIEW_LOG_SUFFIX}"
    )


def load_flashcard_review_log(path: Path, source_id: str) -> dict:
    """Load review log JSON or return an empty structure."""
    normalized = _normalize_source_id(source_id)
    if not path.is_file():
        return {"source_id": normalized, "reviews": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("source_id", normalized)
    data.setdefault("reviews", [])
    return data


def save_flashcard_review_log(path: Path, data: dict) -> None:
    """Write review log JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def _validate_grade(grade: str) -> str:
    normalized = grade.strip().lower()
    if normalized not in VALID_GRADES:
        allowed = ", ".join(sorted(VALID_GRADES))
        raise InvalidFlashcardGradeError(
            f"Invalid grade {grade!r}. Allowed: {allowed}"
        )
    return normalized



def _latest_review_by_card_id(log: dict) -> dict[str, dict]:
    return latest_review_by_card(list(log.get("reviews", [])))


def _reviewed_date_from_iso(date_reviewed: str) -> str:
    return date_reviewed[:10] if len(date_reviewed) >= 10 else today_date_str()


def _effective_due_date(review: dict) -> str | None:
    """Resolve due date from review entry, including legacy entries without due_date."""
    due_date = str(review.get("due_date", "")).strip()
    if due_date:
        return due_date

    grade = str(review.get("grade", "")).lower()
    reviewed = _reviewed_date_from_iso(str(review.get("date_reviewed", "")))

    if grade in _NEEDS_REVIEW_GRADES:
        return reviewed

    if grade in {"easy", "good"}:
        return next_due_date_for_flashcard_grade(grade, reviewed)

    return None


def _is_card_due(review: dict, today: str) -> bool:
    grade = str(review.get("grade", "")).lower()
    due_date = str(review.get("due_date", "")).strip()

    if due_date:
        return is_due(due_date, today)

    if grade in _NEEDS_REVIEW_GRADES:
        return True

    effective = _effective_due_date(review)
    if effective:
        return is_due(effective, today)
    return False


def _due_counts_from_latest(latest: dict[str, dict], today: str) -> tuple[int, int, int]:
    due_count = 0
    due_today_count = 0
    future_due_count = 0

    for review in latest.values():
        effective = _effective_due_date(review)
        if not effective:
            continue
        if is_due(effective, today):
            due_count += 1
            if effective == today:
                due_today_count += 1
        elif effective > today:
            future_due_count += 1

    return due_count, due_today_count, future_due_count


def record_flashcard_review(
    course_name: str,
    source_id: str,
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
    """Append one self-graded flashcard review to the log."""
    grade_normalized = _validate_grade(grade)
    course_path = resolve_course_path(course_name, root)
    normalized_id = _normalize_source_id(source_id)
    log_path = get_flashcard_review_log_path(course_path, normalized_id)
    log = load_flashcard_review_log(log_path, normalized_id)

    review_number = len(log.get("reviews", [])) + 1
    date_reviewed, reviewed_day = build_review_date_reviewed(
        reviewed_date, _now_iso()
    )
    due_date = next_due_date_for_flashcard_grade(grade_normalized, reviewed_day)
    review = {
        "review_id": _make_review_id(review_number),
        "source_id": normalized_id,
        "card_id": card_id.strip(),
        "front": front,
        "back": back,
        "grade": grade_normalized,
        "notes": notes or "",
        "date_reviewed": date_reviewed,
        "due_date": due_date,
    }
    log.setdefault("reviews", []).append(review)
    save_flashcard_review_log(log_path, log)

    result: dict = {
        "review_id": review["review_id"],
        "source_id": normalized_id,
        "card_id": review["card_id"],
        "grade": grade_normalized,
        "due_date": due_date,
        "log_path": str(log_path.resolve()),
    }

    if create_weak_point and grade_normalized in {"hard", "forgot"}:
        concept = (weak_point_concept or front[:80]).strip()
        if concept:
            wp = add_weak_point(
                course_name,
                normalized_id,
                concept,
                confidence_level=2,
                what_to_review=front,
                practice_needed="Review flashcard until easy.",
                root=root,
            )
            result["weak_point"] = wp

    return result


def summarize_flashcard_reviews(
    course_name: str, source_id: str, root: Path | None = None
) -> dict:
    """Return grade counts and recent reviews for one source."""
    course_path = resolve_course_path(course_name, root)
    normalized_id = _normalize_source_id(source_id)
    log_path = get_flashcard_review_log_path(course_path, normalized_id)
    log = load_flashcard_review_log(log_path, normalized_id)
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
        if str(review.get("grade", "")).lower() in _NEEDS_REVIEW_GRADES
    )
    today = today_date_str()
    due_count, due_today_count, future_due_count = _due_counts_from_latest(latest, today)

    recent_reviews = list(reversed(reviews[-10:]))

    return {
        "source_id": normalized_id,
        "review_count": len(reviews),
        "easy": counts["easy"],
        "good": counts["good"],
        "hard": counts["hard"],
        "forgot": counts["forgot"],
        "skipped": counts["skipped"],
        "needs_review_count": needs_review_count,
        "due_count": due_count,
        "due_today_count": due_today_count,
        "future_due_count": future_due_count,
        "recent_reviews": recent_reviews,
    }


def collect_due_flashcards(
    course_name: str,
    root: Path | None = None,
    today: str | None = None,
    source_id: str | None = None,
) -> list[dict]:
    """
    Return flashcards whose latest review is due on or before today.

    Includes hard/forgot/skipped without due_date for backward compatibility.
    Excludes non-due easy/good cards.
    """
    course_path = resolve_course_path(course_name, root)
    logs_dir = course_path / MY_WORK_DIR / FLASHCARD_LOGS_SUBDIR
    if not logs_dir.is_dir():
        return []

    today_str = today or today_date_str()
    normalized_filter = _normalize_source_id(source_id) if source_id else None

    results: list[dict] = []
    for log_path in sorted(logs_dir.glob(f"*{REVIEW_LOG_SUFFIX}")):
        log_source_id = log_path.name.replace(REVIEW_LOG_SUFFIX, "")
        if normalized_filter and _normalize_source_id(log_source_id) != normalized_filter:
            continue
        log = load_flashcard_review_log(log_path, log_source_id)
        latest_by_card = _latest_review_by_card_id(log)
        for card_id, review in latest_by_card.items():
            if not _is_card_due(review, today_str):
                continue
            grade = str(review.get("grade", "")).lower()
            effective_due = _effective_due_date(review) or today_str
            results.append(
                {
                    "card_id": card_id,
                    "source_id": review.get("source_id", log_source_id),
                    "front": review.get("front", ""),
                    "back": review.get("back", ""),
                    "latest_grade": grade,
                    "grade": grade,
                    "due_date": effective_due,
                    "notes": review.get("notes", ""),
                    "review_id": review.get("review_id", ""),
                    "date_reviewed": review.get("date_reviewed", ""),
                    "section": "",
                }
            )

    results.sort(key=lambda item: (item.get("source_id", ""), item.get("card_id", "")))
    return results


def collect_flashcards_needing_review(
    course_name: str, root: Path | None = None
) -> list[dict]:
    """
    Return flashcards due for review (delegates to ``collect_due_flashcards``).
    """
    return collect_due_flashcards(course_name, root=root)


def collect_unreviewed_flashcards(
    course_name: str, root: Path | None = None
) -> list[dict]:
    """Return flashcards with no review log entry yet."""
    course_path = resolve_course_path(course_name, root)
    registry = load_source_registry(course_path)
    needs_review_ids = {
        str(item.get("card_id", "")).strip()
        for item in collect_due_flashcards(course_name, root)
        if str(item.get("card_id", "")).strip()
    }

    results: list[dict] = []
    for entry in registry.get("sources", []):
        source_id = str(entry.get("id", "")).strip()
        if not source_id:
            continue
        try:
            cards = load_flashcards_for_source(course_name, source_id, root=root)
        except FlashcardsNotReadyError:
            continue

        log_path = get_flashcard_review_log_path(course_path, source_id)
        log = load_flashcard_review_log(log_path, source_id)
        reviewed_ids = {
            str(review.get("card_id", "")).strip()
            for review in log.get("reviews", [])
            if str(review.get("card_id", "")).strip()
        }

        for card in cards:
            card_id = str(card.get("card_id", "")).strip()
            if not card_id:
                continue
            if card_id in needs_review_ids or card_id in reviewed_ids:
                continue
            results.append(
                {
                    "type": "flashcard_unreviewed",
                    "source_id": card.get("source_id", source_id),
                    "card_id": card_id,
                    "front": card.get("front", ""),
                    "back": card.get("back", ""),
                    "section": card.get("section", ""),
                    "title": card.get("front", "")[:120],
                    "details": "Not reviewed yet.",
                }
            )

    results.sort(key=lambda item: (item["source_id"], item["card_id"]))
    return results


def get_first_unreviewed_card(
    cards: list[dict], log: dict
) -> dict | None:
    """Return the first card with no recorded review."""
    reviewed_ids = {
        str(review.get("card_id", "")).strip()
        for review in log.get("reviews", [])
    }
    for card in cards:
        if card["card_id"] not in reviewed_ids:
            return card
    return None


def get_flashcard_pipeline_warning(
    course_name: str, root: Path | None = None
) -> str | None:
    """Optional Pipeline Doctor hint when flashcard reviews need follow-up."""
    if collect_due_flashcards(course_name, root):
        return "Flashcard reviews show cards needing review."
    return None
