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
from studyforge.study.study_units import count_active_study_units, list_study_units
from studyforge.study.exam_prep import get_exam_prep_dashboard_hint, get_nearest_active_exam_target
from studyforge.study.exam_readiness import (
    get_exam_readiness_dashboard_hint,
    get_exam_readiness_report,
)
from studyforge.study.exam_targets import list_active_exam_targets
from studyforge.study.mock_test_grading import get_ungraded_mock_test_hint
from studyforge.study.mock_tests import (
    get_mock_test_exam_prep_hint,
    summarize_mock_test_attempts,
)
from studyforge.study.unit_review import get_unit_review_counts

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
    active_study_units: int = 0,
) -> list[dict]:
    if not reviewable:
        if active_study_units > 0:
            return [
                {
                    "key": "review_active_units",
                    "label": "Review active study units",
                    "reason": "You have active study units to work through.",
                }
            ]
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

    active_study_units = count_active_study_units(course_name, root)
    active_units = []
    for unit in list_study_units(course_name, root):
        if str(unit.get("status", "")).lower() != "active":
            continue
        unit_id = str(unit.get("unit_id", ""))
        entry = {
            "unit_id": unit_id,
            "title": unit.get("title", ""),
            "has_synthesis": bool(str(unit.get("latest_synthesis_id", "")).strip()),
            "has_unit_pack": bool(
                str(unit.get("latest_unit_study_pack_manifest_path", "")).strip()
            ),
        }
        if entry["has_unit_pack"] and unit_id:
            counts = get_unit_review_counts(course_name, unit_id, root)
            entry["unit_due_flashcards"] = counts.get("unit_due_flashcards", 0)
            entry["unit_recall_gaps"] = counts.get("unit_recall_gaps", 0)
        active_units.append(entry)

    recommended_actions = _build_recommended_actions(
        reviewable=reviewable,
        has_review_plan_today=has_review_plan_today,
        latest_session_status=session_status,
        active_study_units=active_study_units,
    )
    mock_test_summary = summarize_mock_test_attempts(course_name, root)
    latest_mock_attempt = mock_test_summary.get("latest_attempt")
    exam_prep_hint = get_mock_test_exam_prep_hint(course_name, root)
    if exam_prep_hint:
        recommended_actions.append(exam_prep_hint)
    exam_dashboard_hint = get_exam_prep_dashboard_hint(course_name, root, day)
    if exam_dashboard_hint and session_status != "in_progress":
        recommended_actions.append(exam_dashboard_hint)
    readiness_hint = get_exam_readiness_dashboard_hint(
        course_name,
        root,
        session_in_progress=session_status == "in_progress",
    )
    if readiness_hint:
        recommended_actions.append(readiness_hint)
    if session_status != "in_progress":
        ungraded_hint = get_ungraded_mock_test_hint(course_name, root)
        if ungraded_hint:
            recommended_actions.append(ungraded_hint)

    active_exam_targets = list_active_exam_targets(course_name, root)
    nearest_exam = get_nearest_active_exam_target(course_name, root, day)
    nearest_exam_payload = None
    if nearest_exam:
        nearest_exam_payload = {
            "exam_id": nearest_exam.get("exam_id"),
            "title": nearest_exam.get("title"),
            "exam_date": nearest_exam.get("exam_date"),
            "days_until_exam": nearest_exam.get("days_until_exam"),
        }
        try:
            readiness_report = get_exam_readiness_report(
                course_name, str(nearest_exam.get("exam_id", "")), root
            )
            readiness = readiness_report.get("readiness", {})
            nearest_exam_payload["readiness_score"] = readiness.get("score")
            nearest_exam_payload["readiness_status"] = readiness.get("status")
        except Exception:
            pass

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
            "active_study_units": active_study_units,
            "active_units": active_units,
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
            "mock_test_attempt_count": mock_test_summary.get("attempt_count", 0),
            "mock_test_average_percent": mock_test_summary.get("average_percent", 0.0),
            "latest_mock_test_score": (
                {
                    "mock_test_id": latest_mock_attempt.get("mock_test_id"),
                    "score_correct": latest_mock_attempt.get("score_correct"),
                    "score_total": latest_mock_attempt.get("score_total"),
                    "percent": latest_mock_attempt.get("percent"),
                    "date_recorded": latest_mock_attempt.get("date_recorded"),
                }
                if latest_mock_attempt
                else None
            ),
            "active_exam_targets": len(active_exam_targets),
            "nearest_exam": nearest_exam_payload,
        },
        "active_units": active_units,
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
        f"- Active study units: {summary.get('active_study_units', 0)}",
        f"- Active exam targets: {summary.get('active_exam_targets', 0)}",
    ]
    nearest_exam = summary.get("nearest_exam")
    if nearest_exam:
        lines.append(
            f"- Nearest exam: {nearest_exam.get('title', '')} "
            f"({nearest_exam.get('exam_date', '')}) — "
            f"{nearest_exam.get('days_until_exam', '')} day(s) away"
        )
        if nearest_exam.get("readiness_score") is not None:
            lines.append(
                f"- Nearest exam readiness: {nearest_exam.get('readiness_score')}% "
                f"— {nearest_exam.get('readiness_status', '')}"
            )
    latest_mock = summary.get("latest_mock_test_score")
    if latest_mock:
        lines.append(
            f"- Latest mock test: {latest_mock.get('score_correct')}/"
            f"{latest_mock.get('score_total')} "
            f"({latest_mock.get('percent')}%) — `{latest_mock.get('mock_test_id', '')}`"
        )
    elif summary.get("mock_test_attempt_count", 0) == 0:
        lines.append("- Latest mock test: none yet")
    active_units = dashboard.get("active_units") or summary.get("active_units") or []
    if active_units:
        lines.append("- Active unit list:")
        for unit in active_units:
            markers = ""
            if unit.get("has_synthesis"):
                markers += " [synthesis]"
            if unit.get("has_unit_pack"):
                markers += " [unit pack]"
            extra = ""
            if unit.get("has_unit_pack"):
                due_fc = unit.get("unit_due_flashcards")
                recall_gaps = unit.get("unit_recall_gaps")
                if due_fc is not None or recall_gaps is not None:
                    extra = (
                        f" — unit due flashcards: {due_fc or 0}, "
                        f"unit recall gaps: {recall_gaps or 0}"
                    )
            lines.append(
                f"  - {unit.get('unit_id', '')}: {unit.get('title', '')}{markers}{extra}"
            )
    lines.extend(
        [
            f"- Review plan today: {'yes' if summary.get('has_review_plan_today') else 'no'}",
            f"- Latest session: {session_line}",
            "",
            "## Priority Items",
            "",
        ]
    )

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
