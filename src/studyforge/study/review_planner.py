"""
Review Session Planner v1 — deterministic daily review plan (no AI).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.active_recall import load_active_recall_log
from studyforge.study.flashcard_review import collect_due_flashcards
from studyforge.study.mistakes import list_mistakes
from studyforge.study.weak_points import list_weak_points

MY_WORK_DIR = Path("07_My_Work")
REVIEW_SESSIONS_DIR = "review_sessions"
ACTIVE_RECALL_LOGS_DIR = MY_WORK_DIR / "active_recall_logs"
RECALL_LOG_SUFFIX = "_active_recall_log.json"


class ReviewPlanExistsError(Exception):
    """Raised when review plan files exist and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _local_today_str() -> str:
    return date.today().isoformat()


def _normalize_date_str(date_str: str | None) -> str:
    if date_str is None or not date_str.strip():
        return _local_today_str()
    value = date_str.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise ValueError(f"date_str must be YYYY-MM-DD, got {date_str!r}")
    return value


def get_review_sessions_dir(course_path: Path) -> Path:
    """Return directory for review session plans."""
    return course_path / MY_WORK_DIR / REVIEW_SESSIONS_DIR


def get_review_plan_path(course_path: Path, date_str: str | None = None) -> Path:
    """Return Markdown path for a dated review plan."""
    day = _normalize_date_str(date_str)
    return get_review_sessions_dir(course_path) / f"{day}_review_plan.md"


def get_review_plan_json_path(course_path: Path, date_str: str | None = None) -> Path:
    """Return JSON path for a dated review plan summary."""
    day = _normalize_date_str(date_str)
    return get_review_sessions_dir(course_path) / f"{day}_review_plan.json"


def collect_open_mistakes(course_name: str, root: Path | None = None) -> list[dict]:
    """Return mistakes whose status is not mastered."""
    return [
        entry
        for entry in list_mistakes(course_name, root)
        if str(entry.get("status", "")).lower() != "mastered"
    ]


def collect_open_weak_points(course_name: str, root: Path | None = None) -> list[dict]:
    """Return weak points whose status is not mastered."""
    return [
        entry
        for entry in list_weak_points(course_name, root)
        if str(entry.get("status", "")).lower() != "mastered"
    ]


def _parse_attempt_time(attempt: dict) -> str:
    return str(attempt.get("date_answered", ""))


def collect_active_recall_needs_review(
    course_name: str, root: Path | None = None
) -> list[dict]:
    """
    Scan active recall logs and return latest weak attempts per question.

    Excludes questions whose most recent attempt was correct.
    """
    course_path = resolve_course_path(course_name, root)
    logs_dir = course_path / ACTIVE_RECALL_LOGS_DIR
    if not logs_dir.is_dir():
        return []

    weak_grades = {"wrong", "partial", "skipped"}
    latest_by_question: dict[str, dict] = {}

    for log_path in sorted(logs_dir.glob(f"*{RECALL_LOG_SUFFIX}")):
        log = load_active_recall_log(log_path)
        for attempt in log.get("attempts", []):
            question_id = str(attempt.get("question_id", "")).strip()
            if not question_id:
                question_id = (
                    f"{attempt.get('source_id', 'SRC-0000')}:"
                    f"{attempt.get('question', '')[:40]}"
                )
            existing = latest_by_question.get(question_id)
            if existing is None or _parse_attempt_time(attempt) >= _parse_attempt_time(
                existing
            ):
                latest_by_question[question_id] = dict(attempt)

    results: list[dict] = []
    for question_id, attempt in latest_by_question.items():
        grade = str(attempt.get("grade", "")).lower()
        if grade in weak_grades:
            results.append(
                {
                    "question_id": question_id,
                    "source_id": attempt.get("source_id", ""),
                    "question": attempt.get("question", ""),
                    "user_answer": attempt.get("user_answer", ""),
                    "grade": grade,
                    "notes": attempt.get("notes", ""),
                    "attempt_id": attempt.get("attempt_id", ""),
                    "date_answered": attempt.get("date_answered", ""),
                }
            )

    results.sort(key=lambda item: (item.get("source_id", ""), item.get("question_id", "")))
    return results


def _mistake_priority_tier(entry: dict) -> int:
    status = str(entry.get("status", "")).lower()
    if status in {"new", "still_weak"}:
        return 2
    if status == "reviewed_once":
        return 7
    return 8


def _weak_point_priority_tier(entry: dict) -> int:
    confidence = int(entry.get("confidence_level", 3))
    if confidence <= 2:
        return 3
    if confidence == 3:
        return 6
    return 8


def _recall_priority_tier(entry: dict) -> int:
    grade = str(entry.get("grade", "")).lower()
    if grade == "wrong":
        return 1
    if grade == "partial":
        return 4
    if grade == "skipped":
        return 5
    return 9


def _flashcard_priority_tier(entry: dict) -> int:
    grade = str(entry.get("latest_grade", entry.get("grade", ""))).lower()
    if grade == "forgot":
        return 1
    if grade == "hard":
        return 4
    if grade == "skipped":
        return 5
    if grade == "good":
        return 6
    if grade == "easy":
        return 7
    return 9


def _priority_reason_for_item(item: dict) -> str:
    item_type = item["type"]
    if item_type == "active_recall":
        grade = str(item.get("grade", "")).lower()
        if grade == "wrong":
            return "Wrong active recall attempt (highest priority)."
        if grade == "partial":
            return "Partial active recall attempt — redo without notes."
        return "Skipped active recall question — try again."
    if item_type == "flashcard":
        grade = str(item.get("latest_grade", item.get("grade", ""))).lower()
        due = str(item.get("due_date", "")).strip()
        due_note = f" (due {due})" if due else ""
        if grade == "forgot":
            return f"Forgotten flashcard due for review{due_note}."
        if grade == "hard":
            return f"Hard flashcard due for review{due_note}."
        if grade == "skipped":
            return f"Skipped flashcard due for review{due_note}."
        return f"Flashcard due for review{due_note}."
    if item_type == "mistake":
        status = str(item.get("status", "")).lower()
        if status in {"new", "still_weak"}:
            return "Open mistake that is still weak or new."
        return "Mistake reviewed once — confirm understanding."
    confidence = int(item.get("confidence_level", 3))
    if confidence <= 2:
        return "Weak point with low confidence (1–2)."
    return "Weak point with medium confidence (3)."


def _mistake_to_priority_item(entry: dict) -> dict:
    return {
        "type": "mistake",
        "id": entry.get("mistake_id", ""),
        "source_id": entry.get("source_id", ""),
        "title": (entry.get("question", "") or "")[:120],
        "priority_reason": "",
        "details": entry.get("why_wrong", "") or entry.get("user_answer", ""),
        "status": entry.get("status", ""),
        "_tier": _mistake_priority_tier(entry),
    }


def _weak_point_to_priority_item(entry: dict) -> dict:
    return {
        "type": "weak_point",
        "id": entry.get("weak_point_id", ""),
        "source_id": entry.get("source_id", ""),
        "title": entry.get("concept", ""),
        "priority_reason": "",
        "details": entry.get("what_to_review", "") or entry.get("why_hard", ""),
        "confidence_level": entry.get("confidence_level", ""),
        "status": entry.get("status", ""),
        "_tier": _weak_point_priority_tier(entry),
    }


def _recall_to_priority_item(entry: dict) -> dict:
    return {
        "type": "active_recall",
        "id": entry.get("attempt_id", entry.get("question_id", "")),
        "source_id": entry.get("source_id", ""),
        "title": (entry.get("question", "") or "")[:120],
        "priority_reason": "",
        "details": entry.get("user_answer", ""),
        "grade": entry.get("grade", ""),
        "question_id": entry.get("question_id", ""),
        "_tier": _recall_priority_tier(entry),
    }


def _flashcard_to_priority_item(entry: dict) -> dict:
    grade = str(entry.get("latest_grade", entry.get("grade", "")))
    return {
        "type": "flashcard",
        "id": entry.get("card_id", ""),
        "source_id": entry.get("source_id", ""),
        "title": (entry.get("front", "") or "")[:120],
        "priority_reason": "",
        "details": entry.get("notes", ""),
        "grade": grade,
        "latest_grade": grade,
        "due_date": entry.get("due_date", ""),
        "card_id": entry.get("card_id", ""),
        "front": entry.get("front", ""),
        "back": entry.get("back", ""),
        "_tier": _flashcard_priority_tier(entry),
    }


def prioritize_review_items(
    mistakes: list[dict],
    weak_points: list[dict],
    recall_items: list[dict],
    flashcard_items: list[dict] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return top priority review items using simple deterministic rules."""
    candidates: list[dict] = []
    for entry in mistakes:
        candidates.append(_mistake_to_priority_item(entry))
    for entry in weak_points:
        candidates.append(_weak_point_to_priority_item(entry))
    for entry in recall_items:
        candidates.append(_recall_to_priority_item(entry))
    for entry in flashcard_items or []:
        candidates.append(_flashcard_to_priority_item(entry))

    candidates.sort(key=lambda item: (item["_tier"], item.get("id", "")))

    selected: list[dict] = []
    for item in candidates[: max(0, limit)]:
        clean = {key: value for key, value in item.items() if not key.startswith("_")}
        clean["priority_reason"] = _priority_reason_for_item(item)
        selected.append(clean)
    return selected


def build_review_plan_markdown(
    course_name: str,
    mistakes: list[dict],
    weak_points: list[dict],
    recall_items: list[dict],
    flashcard_items: list[dict],
    priority_items: list[dict],
    date_str: str,
) -> str:
    """Build the full review plan Markdown document."""
    generated = _now_iso()
    lines = [
        f"# Review Plan — {date_str}",
        "",
        "Course:",
        course_name,
        "",
        "Generated:",
        generated,
        "",
        "---",
        "",
        "## Today's Top Priorities",
        "",
    ]

    if priority_items:
        for index, item in enumerate(priority_items, start=1):
            lines.append(f"{index}. **{item.get('type', '')}** — `{item.get('id', '')}`")
            lines.append(f"   - Source: {item.get('source_id', '')}")
            lines.append(f"   - Title: {item.get('title', '')}")
            lines.append(f"   - Reason: {item.get('priority_reason', '')}")
            if item.get("details"):
                lines.append(f"   - Details: {item.get('details', '')}")
            lines.append("")
    else:
        lines.append("No priority items — nothing needs review today.")
        lines.append("")

    lines.extend(["---", "", "## Open Mistakes", ""])
    if mistakes:
        for entry in mistakes:
            lines.extend(
                [
                    f"### {entry.get('mistake_id', 'MISTAKE')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Question:** {entry.get('question', '')}",
                    f"- **Why wrong:** {entry.get('why_wrong', '') or '(not filled in)'}",
                    f"- **How to avoid:** {entry.get('how_to_avoid', '') or '(not filled in)'}",
                    f"- **Status:** {entry.get('status', 'new')}",
                    "",
                ]
            )
    else:
        lines.append("No open mistakes.")
        lines.append("")

    lines.extend(["## Weak Points", ""])
    if weak_points:
        for entry in weak_points:
            lines.extend(
                [
                    f"### {entry.get('weak_point_id', 'WEAK')} — {entry.get('concept', '')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Confidence:** {entry.get('confidence_level', '')}",
                    f"- **What to review:** {entry.get('what_to_review', '') or '(not filled in)'}",
                    f"- **Practice needed:** {entry.get('practice_needed', '') or '(not filled in)'}",
                    f"- **Status:** {entry.get('status', 'new')}",
                    "",
                ]
            )
    else:
        lines.append("No open weak points.")
        lines.append("")

    lines.extend(["## Active Recall Redo", ""])
    if recall_items:
        for entry in recall_items:
            lines.extend(
                [
                    f"### {entry.get('question_id', 'question')}",
                    "",
                    f"- **Question:** {entry.get('question', '')}",
                    f"- **Last grade:** {entry.get('grade', '')}",
                    f"- **Last answer:** {entry.get('user_answer', '')}",
                    f"- **Notes:** {entry.get('notes', '') or '(none)'}",
                    "",
                ]
            )
    else:
        lines.append("No active recall questions need redo.")
        lines.append("")

    lines.extend(["## Flashcards Due", ""])
    if flashcard_items:
        for entry in flashcard_items:
            lines.extend(
                [
                    f"### {entry.get('card_id', 'card')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Front:** {entry.get('front', '')}",
                    f"- **Latest grade:** {entry.get('latest_grade', entry.get('grade', ''))}",
                    f"- **Due date:** {entry.get('due_date', '')}",
                    f"- **Notes:** {entry.get('notes', '') or '(none)'}",
                    "",
                ]
            )
    else:
        lines.append("No flashcards due for review.")
        lines.append("")

    lines.extend(
        [
            "## Suggested Review Tasks",
            "",
            "- Redo all wrong active recall questions.",
            "- Review flashcards due today.",
            "- Review each weak point with confidence 1–2.",
            "- Re-answer at least 5 active recall questions without notes.",
            "- Mark mastered only after explaining the concept without looking.",
            "",
            "## End of Session Checklist",
            "",
            "- [ ] I reviewed each top-priority mistake.",
            "- [ ] I redid wrong/partial active recall questions.",
            "- [ ] I reviewed due flashcards.",
            "- [ ] I updated mistake statuses.",
            "- [ ] I updated weak-point confidence.",
            "- [ ] I wrote down any new confusion.",
            "",
        ]
    )
    return "\n".join(lines)


def has_reviewable_items(
    course_name: str, root: Path | None = None
) -> bool:
    """True if there are mistakes, weak points, or recall items to plan."""
    return bool(
        collect_open_mistakes(course_name, root)
        or collect_open_weak_points(course_name, root)
        or collect_active_recall_needs_review(course_name, root)
        or collect_due_flashcards(course_name, root)
    )


def get_review_plan_pipeline_hint(
    course_name: str, root: Path | None = None
) -> str | None:
    """Optional Pipeline Doctor hint when review planning would help."""
    if has_reviewable_items(course_name, root):
        return "Generate a review plan to organize today's study session."
    return None


def generate_review_plan(
    course_name: str,
    date_str: str | None = None,
    limit: int = 10,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Collect review data and write Markdown + JSON plan files.

    Raises:
        ReviewPlanExistsError: Plan files exist and overwrite is False.
    """
    course_path = resolve_course_path(course_name, root)
    day = _normalize_date_str(date_str)
    md_path = get_review_plan_path(course_path, day)
    json_path = get_review_plan_json_path(course_path, day)

    if (md_path.is_file() or json_path.is_file()) and not overwrite:
        raise ReviewPlanExistsError(
            f"Review plan already exists for {day}:\n"
            f"  - {md_path}\n"
            f"  - {json_path}\n"
            "Use --overwrite to replace."
        )

    mistakes = collect_open_mistakes(course_name, root)
    weak_points = collect_open_weak_points(course_name, root)
    recall_items = collect_active_recall_needs_review(course_name, root)
    flashcard_items = collect_due_flashcards(course_name, root)
    priority_items = prioritize_review_items(
        mistakes, weak_points, recall_items, flashcard_items, limit=limit
    )

    markdown = build_review_plan_markdown(
        course_path.name,
        mistakes,
        weak_points,
        recall_items,
        flashcard_items,
        priority_items,
        day,
    )

    sessions_dir = get_review_sessions_dir(course_path)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")

    generated = _now_iso()
    summary = {
        "course": course_path.name,
        "date": day,
        "mistake_count": len(mistakes),
        "weak_point_count": len(weak_points),
        "active_recall_review_count": len(recall_items),
        "flashcards_due_count": len(flashcard_items),
        "priority_count": len(priority_items),
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
        "generated": generated,
    }

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    return summary
