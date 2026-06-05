"""
Today Dashboard v1 — aggregate what to study now (deterministic, no AI).
"""

from __future__ import annotations

import json
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.flashcard_review import collect_due_flashcards
from studyforge.study.review_planner import (
    collect_active_recall_needs_review,
    collect_open_mistakes,
    collect_open_weak_points,
    get_review_plan_json_path,
    get_review_plan_path,
    prioritize_review_items,
)
from studyforge.study.review_schedule import today_date_str
from studyforge.study.study_session import get_latest_study_session

MY_WORK_DIR = Path("07_My_Work")
TODAY_DASHBOARD_SUBDIR = "today_dashboard"


def get_today_dashboard_dir(course_path: Path) -> Path:
    """Return ``07_My_Work/today_dashboard/`` for a course."""
    return course_path / MY_WORK_DIR / TODAY_DASHBOARD_SUBDIR


def get_today_dashboard_markdown_path(course_path: Path, date_str: str | None = None) -> Path:
    day = date_str or today_date_str()
    return get_today_dashboard_dir(course_path) / f"{day}_today_dashboard.md"


def get_today_dashboard_json_path(course_path: Path, date_str: str | None = None) -> Path:
    day = date_str or today_date_str()
    return get_today_dashboard_dir(course_path) / f"{day}_today_dashboard.json"


def _has_reviewable_items(
    mistakes: list[dict],
    weak_points: list[dict],
    recall_items: list[dict],
    due_flashcards: list[dict],
) -> bool:
    return bool(mistakes or weak_points or recall_items or due_flashcards)


def _latest_session_status(session: dict | None) -> str:
    if session is None:
        return "none"
    status = str(session.get("status", "")).lower()
    if status == "in_progress":
        return "in_progress"
    if status == "complete":
        return "complete"
    return "none"


def _build_recommended_actions(
    *,
    reviewable: bool,
    has_review_plan_today: bool,
    latest_session_status: str,
) -> list[dict]:
    if not reviewable:
        return [
            {
                "key": "nothing_due",
                "label": "Nothing urgent due",
                "reason": (
                    "No due flashcards, weak active recall, open mistakes, "
                    "or open weak points."
                ),
            }
        ]

    if latest_session_status == "in_progress":
        return [
            {
                "key": "continue_study_session",
                "label": "Continue study session",
                "reason": "You have a study session in progress.",
            }
        ]

    if has_review_plan_today and latest_session_status == "complete":
        return [
            {
                "key": "review_complete_or_start_new",
                "label": "Review session results or start a new session",
                "reason": "Today's study session is marked complete.",
            }
        ]

    if not has_review_plan_today:
        return [
            {
                "key": "generate_review_plan",
                "label": "Generate today's review plan",
                "reason": "You have reviewable items and no plan for today.",
            }
        ]

    return [
        {
            "key": "start_study_session",
            "label": "Start study session",
            "reason": "Today's review plan is ready.",
        }
    ]


def get_today_dashboard(
    course_name: str, root: Path | None = None
) -> dict:
    """Build the Today dashboard dict for a course."""
    course_path = resolve_course_path(course_name, root)
    day = today_date_str()

    mistakes = collect_open_mistakes(course_name, root)
    weak_points = collect_open_weak_points(course_name, root)
    recall_items = collect_active_recall_needs_review(course_name, root)
    due_flashcards = collect_due_flashcards(course_name, root, today=day)

    reviewable = _has_reviewable_items(
        mistakes, weak_points, recall_items, due_flashcards
    )
    plan_path = get_review_plan_path(course_path, day)
    has_review_plan_today = plan_path.is_file()

    latest_session = get_latest_study_session(course_name, root)
    session_status = _latest_session_status(latest_session)

    priority_items = prioritize_review_items(
        mistakes,
        weak_points,
        recall_items,
        due_flashcards,
        limit=10,
    )

    recommended_actions = _build_recommended_actions(
        reviewable=reviewable,
        has_review_plan_today=has_review_plan_today,
        latest_session_status=session_status,
    )

    warnings: list[str] = []
    if reviewable and not has_review_plan_today and session_status != "in_progress":
        warnings.append(
            "Review items are waiting — generate today's review plan when ready."
        )
    if session_status == "in_progress" and latest_session:
        completed = len(latest_session.get("completed_items", []))
        total = len(latest_session.get("items", []))
        if total and completed < total:
            warnings.append(
                f"Study session in progress: {completed}/{total} items completed."
            )

    return {
        "course": course_path.name,
        "date": day,
        "summary": {
            "due_flashcards": len(due_flashcards),
            "active_recall_needs_review": len(recall_items),
            "open_mistakes": len(mistakes),
            "open_weak_points": len(weak_points),
            "has_review_plan_today": has_review_plan_today,
            "latest_session_status": session_status,
            "latest_session_id": (
                str(latest_session.get("session_id", ""))
                if latest_session
                else None
            ),
            "review_plan_path": str(plan_path.resolve()) if has_review_plan_today else None,
            "review_plan_json_path": (
                str(get_review_plan_json_path(course_path, day).resolve())
                if has_review_plan_today
                else None
            ),
        },
        "priority_items": priority_items,
        "recommended_actions": recommended_actions,
        "warnings": warnings,
    }


def build_today_dashboard_markdown(dashboard: dict) -> str:
    """Render Today dashboard as Markdown."""
    day = dashboard.get("date", "")
    course = dashboard.get("course", "")
    summary = dashboard.get("summary", {})
    session_status = summary.get("latest_session_status", "none")
    session_id = summary.get("latest_session_id")
    session_line = session_status
    if session_id:
        session_line = f"{session_status} (`{session_id}`)"

    lines = [
        f"# Today Dashboard — {day}",
        "",
        "Course:",
        course,
        "",
        "## Summary",
        "",
        f"- Due flashcards: {summary.get('due_flashcards', 0)}",
        f"- Active recall needing review: {summary.get('active_recall_needs_review', 0)}",
        f"- Open mistakes: {summary.get('open_mistakes', 0)}",
        f"- Open weak points: {summary.get('open_weak_points', 0)}",
        f"- Review plan today: {'yes' if summary.get('has_review_plan_today') else 'no'}",
        f"- Latest session: {session_line}",
        "",
        "## Priority Items",
        "",
    ]

    priority_items = dashboard.get("priority_items") or []
    if priority_items:
        for index, item in enumerate(priority_items, start=1):
            lines.append(
                f"{index}. **{item.get('type', '')}** — `{item.get('id', '')}`"
            )
            lines.append(f"   - Source: {item.get('source_id', '')}")
            lines.append(f"   - Title: {item.get('title', '')}")
            lines.append(f"   - Reason: {item.get('priority_reason', '')}")
            if item.get("due_date"):
                lines.append(f"   - Due date: {item['due_date']}")
            lines.append("")
    else:
        lines.append("No priority items for today.")
        lines.append("")

    lines.extend(["## Recommended Actions", ""])
    actions = dashboard.get("recommended_actions") or []
    if actions:
        for action in actions:
            lines.append(f"- **{action.get('label', '')}** (`{action.get('key', '')}`)")
            lines.append(f"  - {action.get('reason', '')}")
        lines.append("")
    else:
        lines.append("No recommended actions.")
        lines.append("")

    lines.extend(["## Warnings", ""])
    warnings = dashboard.get("warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    else:
        lines.append("No warnings.")
        lines.append("")

    return "\n".join(lines) + "\n"


def export_today_dashboard(
    course_name: str, root: Path | None = None
) -> Path:
    """Write Today dashboard Markdown and JSON; return Markdown path."""
    course_path = resolve_course_path(course_name, root)
    dashboard = get_today_dashboard(course_name, root)
    day = dashboard["date"]

    out_dir = get_today_dashboard_dir(course_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = get_today_dashboard_markdown_path(course_path, day)
    json_path = get_today_dashboard_json_path(course_path, day)

    md_path.write_text(build_today_dashboard_markdown(dashboard), encoding="utf-8")
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(dashboard, handle, indent=2)
        handle.write("\n")

    return md_path
