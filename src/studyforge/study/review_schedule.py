"""
Lightweight due-date scheduling for flashcard reviews (deterministic, not SM-2).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

VALID_SCHEDULE_GRADES = frozenset({"easy", "good", "hard", "forgot", "skipped"})

_GRADE_INTERVAL_DAYS = {
    "forgot": 1,
    "skipped": 1,
    "hard": 2,
    "good": 4,
    "easy": 7,
}


def today_date_str() -> str:
    """Return local date as YYYY-MM-DD."""
    return date.today().isoformat()


def add_days(date_str: str, days: int) -> str:
    """Return YYYY-MM-DD after adding days to a date string."""
    base = date.fromisoformat(date_str.strip())
    return (base + timedelta(days=days)).isoformat()


def _reviewed_date_str(reviewed_date: str | None) -> str:
    if reviewed_date is None or not str(reviewed_date).strip():
        return today_date_str()
    value = str(reviewed_date).strip()
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    return today_date_str()


def build_review_date_reviewed(
    reviewed_date: str | None,
    default_iso: str,
) -> tuple[str, str]:
    """
    Return ``(date_reviewed, reviewed_day)`` for a flashcard review log entry.

    When ``reviewed_date`` is a date (YYYY-MM-DD) or ISO datetime, that value is
    used for scheduling. Otherwise ``default_iso`` (typically "now") is used.
    """
    if reviewed_date is not None and str(reviewed_date).strip():
        value = str(reviewed_date).strip()
        if "T" in value:
            return value, value[:10]
        day = _reviewed_date_str(value)
        return f"{day}T12:00:00", day
    reviewed_day = default_iso[:10] if len(default_iso) >= 10 else _reviewed_date_str(None)
    return default_iso, reviewed_day


def next_due_date_for_flashcard_grade(
    grade: str, reviewed_date: str | None = None
) -> str:
    """
    Return the next due date for a flashcard grade.

    Rules: forgot/skipped +1 day, hard +2, good +4, easy +7 from reviewed date.
    """
    grade_normalized = grade.strip().lower()
    if grade_normalized not in VALID_SCHEDULE_GRADES:
        raise ValueError(
            f"Invalid grade {grade!r}. Allowed: {', '.join(sorted(VALID_SCHEDULE_GRADES))}"
        )
    base = _reviewed_date_str(reviewed_date)
    return add_days(base, _GRADE_INTERVAL_DAYS[grade_normalized])


def is_due(due_date: str, today: str | None = None) -> bool:
    """Return True if due_date is on or before today."""
    today_str = today or today_date_str()
    return due_date.strip() <= today_str


def _parse_review_time(review: dict) -> str:
    return str(review.get("date_reviewed", ""))


def latest_review_by_card(reviews: list[dict]) -> dict[str, dict]:
    """Return the most recent review per card_id."""
    latest: dict[str, dict] = {}
    for review in reviews:
        card_id = str(review.get("card_id", "")).strip()
        if not card_id:
            continue
        existing = latest.get(card_id)
        if existing is None or _parse_review_time(review) >= _parse_review_time(existing):
            latest[card_id] = dict(review)
    return latest
