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
