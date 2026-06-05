"""
Exam Prep Planner v1 — deterministic prep plans from exam targets (no AI).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from studyforge.core.sources import list_sources, resolve_course_path
from studyforge.study.exam_targets import (
    get_exam_target,
    list_active_exam_targets,
)
from studyforge.study.flashcard_review import collect_due_flashcards
from studyforge.study.mock_tests import get_mock_test_log_path, load_mock_test_attempts
from studyforge.study.review_planner import (
    collect_active_recall_needs_review,
    collect_open_mistakes,
    collect_open_weak_points,
)
from studyforge.study.review_schedule import today_date_str
from studyforge.study.study_units import (
    _normalize_source_id,
    _normalize_unit_id,
    _source_has_study_pack,
    load_study_units,
)
from studyforge.study.unit_review import (
    collect_due_unit_flashcards,
    collect_unit_active_recall_needs_review,
)
from studyforge.study.unit_study_pack import unit_has_study_pack
from studyforge.study.unit_synthesis_import import unit_has_synthesis

MY_WORK_DIR = Path("07_My_Work")
EXAM_PREP_SUBDIR = "exam_prep"


class ExamPrepPlanExistsError(Exception):
    """Raised when an exam prep plan exists and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_exam_prep_dir(course_path: Path) -> Path:
    """Return ``07_My_Work/exam_prep/`` for a course."""
    return course_path / MY_WORK_DIR / EXAM_PREP_SUBDIR


def get_exam_prep_plan_paths(course_path: Path, exam_id: str) -> tuple[Path, Path]:
    """Return Markdown and JSON paths for an exam prep plan."""
    normalized = exam_id.strip().upper()
    base = get_exam_prep_dir(course_path)
    return (
        base / f"{normalized}_exam_prep_plan.md",
        base / f"{normalized}_exam_prep_plan.json",
    )


def get_days_until_exam(exam_date: str, today: str | None = None) -> int:
    """Return days from today to exam date (negative if past)."""
    exam_day = date.fromisoformat(exam_date.strip())
    today_day = date.fromisoformat((today or today_date_str()).strip())
    return (exam_day - today_day).days


def get_exam_scope_source_ids(
    course_name: str, exam_id: str, root: Path | None = None
) -> dict:
    """Expand exam units into source IDs and merge explicit sources."""
    exam = get_exam_target(course_name, exam_id, root)
    course_path = resolve_course_path(course_name, root)
    units_data = load_study_units(course_name, root)
    unit_map = {
        _normalize_unit_id(str(unit.get("unit_id", ""))): unit
        for unit in units_data.get("units", [])
        if unit.get("unit_id")
    }

    unit_ids = [
        _normalize_unit_id(uid)
        for uid in exam.get("unit_ids", [])
        if str(uid).strip()
    ]
    explicit_sources = [
        _normalize_source_id(sid)
        for sid in exam.get("source_ids", [])
        if str(sid).strip()
    ]

    warnings: list[str] = []
    source_ids: list[str] = []
    for sid in explicit_sources:
        if sid not in source_ids:
            source_ids.append(sid)

    for uid in unit_ids:
        unit = unit_map.get(uid)
        if unit is None:
            warnings.append(f"{uid} is listed on the exam but not found in study units.")
            continue
        for raw_sid in unit.get("source_ids", []):
            sid = _normalize_source_id(str(raw_sid))
            if sid and sid not in source_ids:
                source_ids.append(sid)

    return {
        "exam": dict(exam),
        "unit_ids": unit_ids,
        "source_ids": source_ids,
        "warnings": warnings,
    }


def _filter_by_source_ids(items: list[dict], source_id_set: set[str]) -> list[dict]:
    return [
        dict(item)
        for item in items
        if _normalize_source_id(str(item.get("source_id", ""))) in source_id_set
    ]


def _filter_mistakes_weak_points(
    items: list[dict], source_id_set: set[str], unit_id_set: set[str]
) -> list[dict]:
    results: list[dict] = []
    for item in items:
        sid = str(item.get("source_id", "")).strip().upper()
        if sid in source_id_set or sid in unit_id_set:
            results.append(dict(item))
    return results


def _filter_unit_items(items: list[dict], unit_id_set: set[str]) -> list[dict]:
    return [
        dict(item)
        for item in items
        if _normalize_unit_id(str(item.get("unit_id", item.get("source_id", ""))))
        in unit_id_set
    ]


def _collect_scope_mock_attempts(
    course_path: Path,
    *,
    source_id_set: set[str],
    unit_id_set: set[str],
) -> list[dict]:
    log_path = get_mock_test_log_path(course_path)
    log = load_mock_test_attempts(log_path)
    results: list[dict] = []
    for attempt in log.get("attempts", []):
        scope = str(attempt.get("scope", "")).lower()
        source_id = str(attempt.get("source_id", "")).strip().upper()
        unit_id = str(attempt.get("unit_id", "")).strip().upper()
        if scope == "source" and source_id in source_id_set:
            results.append(dict(attempt))
        elif scope == "unit" and unit_id in unit_id_set:
            results.append(dict(attempt))
    return results


def collect_exam_prep_state(
    course_name: str, exam_id: str, root: Path | None = None
) -> dict:
    """Collect readiness, review items, and mock test stats for exam scope."""
    course_path = resolve_course_path(course_name, root)
    scope_info = get_exam_scope_source_ids(course_name, exam_id, root)
    exam = scope_info["exam"]
    unit_ids = scope_info["unit_ids"]
    source_ids = scope_info["source_ids"]
    source_id_set = set(source_ids)
    unit_id_set = set(unit_ids)
    day = today_date_str()

    registry = {
        _normalize_source_id(str(entry.get("id", ""))): entry
        for entry in list_sources(course_name, root)
        if entry.get("id")
    }

    incomplete_sources: list[dict] = []
    for sid in source_ids:
        entry = registry.get(sid, {})
        has_pack = _source_has_study_pack(
            course_name, course_path, entry, sid, root
        )
        if not has_pack:
            incomplete_sources.append(
                {
                    "source_id": sid,
                    "title": entry.get("title", sid),
                    "status": entry.get("status", "unknown"),
                }
            )

    units_data = load_study_units(course_name, root)
    units_without_synthesis: list[dict] = []
    units_without_unit_pack: list[dict] = []
    for uid in unit_ids:
        unit = next(
            (
                u
                for u in units_data.get("units", [])
                if _normalize_unit_id(str(u.get("unit_id", ""))) == uid
            ),
            None,
        )
        if unit is None:
            continue
        entry = {
            "unit_id": uid,
            "title": unit.get("title", uid),
        }
        if not unit_has_synthesis(unit, course_path):
            units_without_synthesis.append(dict(entry))
        if not unit_has_study_pack(unit):
            units_without_unit_pack.append(dict(entry))

    due_flashcards = _filter_by_source_ids(
        collect_due_flashcards(course_name, root, today=day), source_id_set
    )
    due_unit_flashcards = _filter_unit_items(
        collect_due_unit_flashcards(course_name, root, today=day), unit_id_set
    )
    recall_needs_review = _filter_by_source_ids(
        collect_active_recall_needs_review(course_name, root), source_id_set
    )
    unit_recall_needs_review = _filter_unit_items(
        collect_unit_active_recall_needs_review(course_name, root), unit_id_set
    )
    open_mistakes = _filter_mistakes_weak_points(
        collect_open_mistakes(course_name, root), source_id_set, unit_id_set
    )
    open_weak_points = _filter_mistakes_weak_points(
        collect_open_weak_points(course_name, root), source_id_set, unit_id_set
    )

    mock_attempts = _collect_scope_mock_attempts(
        course_path,
        source_id_set=source_id_set,
        unit_id_set=unit_id_set,
    )
    percents = [float(a.get("percent", 0.0)) for a in mock_attempts]
    latest_score = percents[-1] if percents else None
    average_score = round(sum(percents) / len(percents), 1) if percents else None

    warnings = list(scope_info.get("warnings", []))
    days_until = get_days_until_exam(str(exam.get("exam_date", "")), day)
    if days_until < 0:
        warnings.append("Exam date is in the past — consider marking the target completed.")
    if incomplete_sources:
        warnings.append(
            f"{len(incomplete_sources)} source(s) in exam scope lack study packs."
        )

    return {
        "exam": exam,
        "days_until_exam": days_until,
        "scope": {
            "unit_ids": unit_ids,
            "source_ids": source_ids,
        },
        "readiness": {
            "incomplete_sources": incomplete_sources,
            "units_without_synthesis": units_without_synthesis,
            "units_without_unit_pack": units_without_unit_pack,
        },
        "review": {
            "due_flashcards": due_flashcards,
            "due_unit_flashcards": due_unit_flashcards,
            "active_recall_needs_review": recall_needs_review,
            "unit_recall_needs_review": unit_recall_needs_review,
            "open_mistakes": open_mistakes,
            "open_weak_points": open_weak_points,
        },
        "mock_tests": {
            "attempt_count": len(mock_attempts),
            "latest_score": latest_score,
            "average_score": average_score,
            "recent_attempts": list(reversed(mock_attempts[-5:])),
        },
        "warnings": warnings,
    }


def recommend_exam_prep_actions(state: dict) -> list[dict]:
    """Return deterministic recommended actions for exam prep."""
    exam = state.get("exam", {})
    days = int(state.get("days_until_exam", 0))
    readiness = state.get("readiness", {})
    review = state.get("review", {})
    mock_tests = state.get("mock_tests", {})
    target_score = exam.get("target_score")

    actions: list[dict] = []

    if days < 0:
        actions.append(
            {
                "key": "mark_exam_completed",
                "label": "Mark exam target completed or archived",
                "reason": "The exam date has passed.",
            }
        )
        return actions

    incomplete = readiness.get("incomplete_sources") or []
    if incomplete:
        actions.append(
            {
                "key": "process_incomplete_sources",
                "label": "Process incomplete sources",
                "reason": (
                    f"{len(incomplete)} source(s) in exam scope "
                    "do not have study packs yet."
                ),
            }
        )

    no_synthesis = readiness.get("units_without_synthesis") or []
    no_pack = readiness.get("units_without_unit_pack") or []
    if no_synthesis:
        actions.append(
            {
                "key": "create_unit_synthesis",
                "label": "Import unit synthesis for exam units",
                "reason": (
                    f"{len(no_synthesis)} unit(s) lack imported synthesis."
                ),
            }
        )
    if no_pack:
        actions.append(
            {
                "key": "generate_unit_study_pack",
                "label": "Generate unit study packs for exam units",
                "reason": f"{len(no_pack)} unit(s) lack a unit study pack.",
            }
        )

    attempt_count = int(mock_tests.get("attempt_count", 0))
    if attempt_count == 0 and days <= 7:
        actions.append(
            {
                "key": "generate_mock_test",
                "label": "Generate a mock test",
                "reason": (
                    f"Exam is in {days} day(s) and no mock test attempts "
                    "are recorded for this scope."
                ),
            }
        )

    latest_score = mock_tests.get("latest_score")
    if (
        target_score is not None
        and latest_score is not None
        and float(latest_score) < float(target_score)
    ):
        actions.append(
            {
                "key": "retake_mock_test",
                "label": "Retake mock test and review weak topics",
                "reason": (
                    f"Latest mock score ({latest_score}%) is below target "
                    f"({target_score}%)."
                ),
            }
        )

    due_count = len(review.get("due_flashcards") or []) + len(
        review.get("due_unit_flashcards") or []
    )
    recall_count = len(review.get("active_recall_needs_review") or []) + len(
        review.get("unit_recall_needs_review") or []
    )
    if due_count or recall_count:
        actions.append(
            {
                "key": "review_due_items",
                "label": "Review due flashcards and active recall gaps",
                "reason": (
                    f"{due_count} due flashcard(s) and {recall_count} "
                    "recall gap(s) in exam scope."
                ),
            }
        )

    mistake_count = len(review.get("open_mistakes") or [])
    weak_count = len(review.get("open_weak_points") or [])
    if mistake_count or weak_count:
        actions.append(
            {
                "key": "review_weak_areas",
                "label": "Review open mistakes and weak points",
                "reason": (
                    f"{mistake_count} open mistake(s) and {weak_count} "
                    "weak point(s) in exam scope."
                ),
            }
        )

    if not actions:
        actions.append(
            {
                "key": "maintain_review",
                "label": "Maintain light review until exam day",
                "reason": "Exam scope looks ready — keep reviewing on schedule.",
            }
        )

    return actions


def _build_seven_day_checklist(days_until: int) -> list[str]:
    if days_until >= 7:
        return [
            "Review all exam units and source study guides.",
            "Complete at least one mock test for the exam scope.",
            "Fix open mistakes and weak points from prior practice.",
            "Review due flashcards and active recall gaps.",
        ]
    if 3 <= days_until <= 6:
        return [
            "Focus on weak points and mistakes in exam scope.",
            "Retake a mock test and compare to your target score.",
            "Review unit synthesis and formula sheets.",
            "Clear due flashcards and recall gaps.",
        ]
    if 1 <= days_until <= 2:
        return [
            "Redo open mistakes from exam scope.",
            "Review due flashcards and high-priority recall gaps.",
            "Light mock test or practice quiz only.",
            "Skim formula sheet and must-memorize lists.",
        ]
    if days_until == 0:
        return [
            "Light review only — no cramming new material.",
            "Quick pass over mistakes and weak points.",
            "Review a few due flashcards if time allows.",
        ]
    return [
        "Exam date has passed — archive the target or plan a retake.",
    ]


def build_exam_prep_plan_markdown(
    course_name: str,
    exam_id: str,
    state: dict,
    actions: list[dict],
) -> str:
    """Render an exam prep plan as Markdown."""
    exam = state.get("exam", {})
    scope = state.get("scope", {})
    readiness = state.get("readiness", {})
    review = state.get("review", {})
    mock_tests = state.get("mock_tests", {})
    days = state.get("days_until_exam", 0)
    generated = _now_iso()

    lines = [
        f"# Exam Prep Plan — {exam.get('exam_id', exam_id)}",
        "",
        "Course:",
        course_name,
        "",
        "Exam:",
        str(exam.get("title", "")),
        "",
        "Date:",
        str(exam.get("exam_date", "")),
        "",
        "Days remaining:",
        str(days),
        "",
        "Target:",
        f"{exam.get('target_score', '—')}%"
        if exam.get("target_score") is not None
        else "—",
        "",
        "Generated:",
        generated,
        "",
        "---",
        "",
        "## Scope",
        "",
        "Units:",
        ", ".join(scope.get("unit_ids", [])) or "(none)",
        "",
        "Sources:",
        ", ".join(scope.get("source_ids", [])) or "(none)",
        "",
        "## Readiness",
        "",
    ]

    incomplete = readiness.get("incomplete_sources") or []
    if incomplete:
        for entry in incomplete:
            lines.append(
                f"- **{entry.get('source_id', '')}** — {entry.get('title', '')} "
                "(no study pack)"
            )
    else:
        lines.append("- All scoped sources have study packs.")

    no_synth = readiness.get("units_without_synthesis") or []
    if no_synth:
        lines.append("")
        lines.append("Units without synthesis:")
        for entry in no_synth:
            lines.append(f"- {entry.get('unit_id', '')} — {entry.get('title', '')}")

    no_pack = readiness.get("units_without_unit_pack") or []
    if no_pack:
        lines.append("")
        lines.append("Units without unit study pack:")
        for entry in no_pack:
            lines.append(f"- {entry.get('unit_id', '')} — {entry.get('title', '')}")

    lines.extend(["", "## Review Items", ""])
    lines.append(
        f"- Due source flashcards: {len(review.get('due_flashcards') or [])}"
    )
    lines.append(
        f"- Due unit flashcards: {len(review.get('due_unit_flashcards') or [])}"
    )
    lines.append(
        f"- Source active recall gaps: "
        f"{len(review.get('active_recall_needs_review') or [])}"
    )
    lines.append(
        f"- Unit active recall gaps: "
        f"{len(review.get('unit_recall_needs_review') or [])}"
    )
    lines.append(f"- Open mistakes: {len(review.get('open_mistakes') or [])}")
    lines.append(f"- Open weak points: {len(review.get('open_weak_points') or [])}")

    lines.extend(["", "## Mock Test Status", ""])
    lines.append(f"- Attempts in scope: {mock_tests.get('attempt_count', 0)}")
    lines.append(
        f"- Latest score: {mock_tests.get('latest_score', '—')}%"
    )
    lines.append(
        f"- Average score: {mock_tests.get('average_score', '—')}%"
    )

    lines.extend(["", "## Recommended Actions", ""])
    for index, action in enumerate(actions, start=1):
        lines.append(f"{index}. **{action.get('label', '')}**")
        lines.append(f"   - {action.get('reason', '')}")

    lines.extend(["", "## 7-Day Checklist", ""])
    for item in _build_seven_day_checklist(days):
        lines.append(f"- [ ] {item}")

    normalized_exam_id = str(exam.get("exam_id", exam_id)).strip().upper()
    lines.extend(
        [
            "",
            "## Study Session",
            "",
            f"You can start an exam-focused study session from StudyForge using "
            f"`{normalized_exam_id}`.",
            "",
        ]
    )

    lines.extend(
        [
            "",
            "## Final Exam Checklist",
            "",
            "- [ ] All included sources have study packs.",
            "- [ ] All units have unit packs where needed.",
            "- [ ] I completed at least one mock test.",
            "- [ ] I reviewed mistakes.",
            "- [ ] I reviewed weak points.",
            "- [ ] I reviewed due flashcards.",
            "- [ ] I can explain major formulas/methods.",
            "",
        ]
    )

    warnings = state.get("warnings") or []
    if warnings:
        lines.extend(["## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines)


def generate_exam_prep_plan(
    course_name: str,
    exam_id: str,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """Build and save exam prep plan Markdown + JSON."""
    course_path = resolve_course_path(course_name, root)
    normalized = exam_id.strip().upper()
    md_path, json_path = get_exam_prep_plan_paths(course_path, normalized)

    if (md_path.is_file() or json_path.is_file()) and not overwrite:
        raise ExamPrepPlanExistsError(
            f"Exam prep plan already exists for {normalized}:\n"
            f"  - {md_path}\n"
            f"  - {json_path}\n"
            "Use --overwrite to replace."
        )

    state = collect_exam_prep_state(course_name, normalized, root)
    actions = recommend_exam_prep_actions(state)
    markdown = build_exam_prep_plan_markdown(
        course_name, normalized, state, actions
    )

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")

    generated = _now_iso()
    result = {
        "course": course_path.name,
        "exam_id": normalized,
        "exam_title": state.get("exam", {}).get("title", ""),
        "days_until_exam": state.get("days_until_exam", 0),
        "action_count": len(actions),
        "warnings": list(state.get("warnings", [])),
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
        "generated": generated,
        "state": state,
        "recommended_actions": actions,
    }

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return result


def get_nearest_active_exam_target(
    course_name: str, root: Path | None = None, today: str | None = None
) -> dict | None:
    """Return the active exam target with the nearest exam_date (or None)."""
    day = today or today_date_str()
    active = list_active_exam_targets(course_name, root)
    if not active:
        return None

    def sort_key(target: dict) -> tuple[int, str]:
        exam_date = str(target.get("exam_date", ""))
        try:
            days = get_days_until_exam(exam_date, day)
        except ValueError:
            days = 99999
        return (days, exam_date)

    nearest = min(active, key=sort_key)
    return {
        **dict(nearest),
        "days_until_exam": get_days_until_exam(
            str(nearest.get("exam_date", "")), day
        ),
    }


def get_exam_prep_dashboard_hint(
    course_name: str, root: Path | None = None, today: str | None = None
) -> dict | None:
    """Optional Today recommendation when exam is soon and review items exist."""
    day = today or today_date_str()
    nearest = get_nearest_active_exam_target(course_name, root, day)
    if nearest is None:
        return None
    days = int(nearest.get("days_until_exam", 999))
    if days < 0 or days > 7:
        return None

    state = collect_exam_prep_state(
        course_name, str(nearest.get("exam_id", "")), root
    )
    review = state.get("review", {})
    has_review = bool(
        review.get("due_flashcards")
        or review.get("due_unit_flashcards")
        or review.get("active_recall_needs_review")
        or review.get("unit_recall_needs_review")
        or review.get("open_mistakes")
        or review.get("open_weak_points")
    )
    if not has_review:
        return None

    return {
        "key": "open_exam_prep",
        "label": "Open Exam Prep and generate/update your plan",
        "reason": (
            f"{nearest.get('title', 'Exam')} is in {days} day(s) "
            "and scoped review items are waiting."
        ),
    }
