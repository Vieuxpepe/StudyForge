"""
Exam Readiness Score v1 — deterministic readiness from exam prep state (no AI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.exam_prep import collect_exam_prep_state, get_exam_prep_dir

MANY_DUE_FLASHCARDS_THRESHOLD = 5
MANY_RECALL_GAPS_THRESHOLD = 3


class ExamReadinessReportExistsError(Exception):
    """Raised when a readiness report exists and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_exam_readiness_report_paths(course_path: Path, exam_id: str) -> tuple[Path, Path]:
    """Return Markdown and JSON paths for an exam readiness report."""
    normalized = exam_id.strip().upper()
    base = get_exam_prep_dir(course_path)
    return (
        base / f"{normalized}_exam_readiness_report.md",
        base / f"{normalized}_exam_readiness_report.json",
    )


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _score_material_readiness(readiness: dict) -> int:
    score = 30
    if readiness.get("incomplete_sources"):
        score -= 10
    if readiness.get("units_without_synthesis"):
        score -= 8
    if readiness.get("units_without_unit_pack"):
        score -= 8
    return int(_clamp(score, 0, 30))


def _score_review_load(review: dict) -> int:
    due_count = len(review.get("due_flashcards") or []) + len(
        review.get("due_unit_flashcards") or []
    )
    recall_count = len(review.get("active_recall_needs_review") or []) + len(
        review.get("unit_recall_needs_review") or []
    )
    mistake_count = len(review.get("open_mistakes") or [])
    weak_count = len(review.get("open_weak_points") or [])

    score = 25
    score -= min(due_count, 8)
    score -= min(recall_count * 2, 8)
    score -= min(mistake_count * 2, 6)
    score -= min(weak_count * 2, 8)
    return int(_clamp(score, 0, 25))


def _score_mock_tests(mock_tests: dict, target_score: int | float | None) -> int:
    attempt_count = int(mock_tests.get("attempt_count", 0))
    latest_score = mock_tests.get("latest_score")
    if attempt_count == 0 or latest_score is None:
        return 10

    latest = float(latest_score)
    if target_score is not None:
        target = float(target_score)
        if latest >= target:
            return 30
        if latest >= target - 10:
            return 22
        if latest >= target - 20:
            return 15
        return 8

    if latest >= 80:
        return 30
    if latest >= 70:
        return 22
    if latest >= 60:
        return 15
    return 8


def _score_time_pressure(days_until_exam: int) -> int:
    if days_until_exam < 0:
        return 0
    if days_until_exam == 0:
        return 4
    if days_until_exam <= 2:
        return 7
    if days_until_exam <= 6:
        return 11
    return 15


def _status_from_score(score: int) -> str:
    if score >= 85:
        return "ready"
    if score >= 65:
        return "needs_review"
    if score >= 40:
        return "at_risk"
    return "not_ready"


def _build_blockers(state: dict) -> list[str]:
    readiness = state.get("readiness", {})
    review = state.get("review", {})
    mock_tests = state.get("mock_tests", {})
    exam = state.get("exam", {})
    days = int(state.get("days_until_exam", 0))

    blockers: list[str] = []

    incomplete = readiness.get("incomplete_sources") or []
    if incomplete:
        blockers.append(
            f"{len(incomplete)} source(s) in exam scope lack study packs."
        )

    no_synthesis = readiness.get("units_without_synthesis") or []
    if no_synthesis:
        blockers.append(f"{len(no_synthesis)} unit(s) lack imported synthesis.")

    no_pack = readiness.get("units_without_unit_pack") or []
    if no_pack:
        blockers.append(f"{len(no_pack)} unit(s) lack unit study packs.")

    attempt_count = int(mock_tests.get("attempt_count", 0))
    if attempt_count == 0:
        blockers.append("No mock test attempt yet.")

    latest_score = mock_tests.get("latest_score")
    target_score = exam.get("target_score")
    if (
        attempt_count > 0
        and latest_score is not None
        and target_score is not None
        and float(latest_score) < float(target_score)
    ):
        blockers.append(
            f"Latest mock score ({latest_score}%) is below target "
            f"({target_score}%)."
        )

    due_count = len(review.get("due_flashcards") or []) + len(
        review.get("due_unit_flashcards") or []
    )
    if due_count >= MANY_DUE_FLASHCARDS_THRESHOLD:
        blockers.append(f"{due_count} due flashcards.")
    elif due_count > 0:
        blockers.append(f"{due_count} due flashcard(s).")

    recall_count = len(review.get("active_recall_needs_review") or []) + len(
        review.get("unit_recall_needs_review") or []
    )
    if recall_count >= MANY_RECALL_GAPS_THRESHOLD:
        blockers.append(f"{recall_count} active recall gaps.")
    elif recall_count > 0:
        blockers.append(f"{recall_count} active recall gap(s).")

    mistake_count = len(review.get("open_mistakes") or [])
    if mistake_count > 0:
        blockers.append(f"{mistake_count} open mistake(s).")

    weak_count = len(review.get("open_weak_points") or [])
    if weak_count > 0:
        blockers.append(f"{weak_count} open weak point(s).")

    if days < 0:
        blockers.append("Exam date has passed.")
    elif days == 0:
        blockers.append("Exam is today.")

    return blockers


def _build_recommendations(state: dict, blockers: list[str]) -> list[str]:
    readiness = state.get("readiness", {})
    review = state.get("review", {})
    mock_tests = state.get("mock_tests", {})
    exam = state.get("exam", {})
    recommendations: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        if text not in seen:
            seen.add(text)
            recommendations.append(text)

    if readiness.get("incomplete_sources"):
        add("Process incomplete sources.")
    if readiness.get("units_without_unit_pack"):
        add("Generate missing unit packs.")
    if readiness.get("units_without_synthesis"):
        add("Import unit synthesis for exam units.")

    if int(mock_tests.get("attempt_count", 0)) == 0:
        add("Take a mock test.")

    due_count = len(review.get("due_flashcards") or []) + len(
        review.get("due_unit_flashcards") or []
    )
    if due_count > 0:
        add("Review due flashcards.")

    recall_count = len(review.get("active_recall_needs_review") or []) + len(
        review.get("unit_recall_needs_review") or []
    )
    if recall_count > 0:
        add("Redo active recall gaps.")

    if review.get("open_mistakes") or review.get("open_weak_points"):
        add("Review mistakes and weak points.")

    latest_score = mock_tests.get("latest_score")
    target_score = exam.get("target_score")
    if (
        int(mock_tests.get("attempt_count", 0)) > 0
        and latest_score is not None
        and target_score is not None
        and float(latest_score) < float(target_score)
    ):
        add("Retake a mock test and review weak topics.")

    add("Start an exam-focused study session.")

    if not recommendations and not blockers:
        add("Keep reviewing scoped material and track mock test progress.")

    return recommendations


def _build_state_summary(state: dict) -> dict:
    readiness = state.get("readiness", {})
    review = state.get("review", {})
    mock_tests = state.get("mock_tests", {})
    scope = state.get("scope", {})
    return {
        "unit_count": len(scope.get("unit_ids") or []),
        "source_count": len(scope.get("source_ids") or []),
        "incomplete_sources": len(readiness.get("incomplete_sources") or []),
        "units_without_synthesis": len(readiness.get("units_without_synthesis") or []),
        "units_without_unit_pack": len(readiness.get("units_without_unit_pack") or []),
        "due_flashcards": len(review.get("due_flashcards") or [])
        + len(review.get("due_unit_flashcards") or []),
        "recall_gaps": len(review.get("active_recall_needs_review") or [])
        + len(review.get("unit_recall_needs_review") or []),
        "open_mistakes": len(review.get("open_mistakes") or []),
        "open_weak_points": len(review.get("open_weak_points") or []),
        "mock_attempt_count": int(mock_tests.get("attempt_count", 0)),
        "latest_mock_score": mock_tests.get("latest_score"),
        "average_mock_score": mock_tests.get("average_score"),
    }


def calculate_exam_readiness_score(state: dict) -> dict:
    """Calculate deterministic exam readiness from ``collect_exam_prep_state()`` output."""
    readiness = state.get("readiness", {})
    review = state.get("review", {})
    mock_tests = state.get("mock_tests", {})
    exam = state.get("exam", {})
    days = int(state.get("days_until_exam", 0))

    material = _score_material_readiness(readiness)
    review_load = _score_review_load(review)
    mock_score = _score_mock_tests(mock_tests, exam.get("target_score"))
    time_score = _score_time_pressure(days)
    total = material + review_load + mock_score + time_score
    status = _status_from_score(total)
    blockers = _build_blockers(state)
    warnings = list(state.get("warnings") or [])
    recommendations = _build_recommendations(state, blockers)

    return {
        "score": total,
        "status": status,
        "breakdown": {
            "readiness": material,
            "review_load": review_load,
            "mock_tests": mock_score,
            "time": time_score,
        },
        "blockers": blockers,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def get_exam_readiness_report(
    course_name: str, exam_id: str, root: Path | None = None
) -> dict:
    """Load exam prep state and return a full readiness report."""
    state = collect_exam_prep_state(course_name, exam_id, root)
    exam = state.get("exam", {})
    readiness = calculate_exam_readiness_score(state)
    course_path = resolve_course_path(course_name, root)

    return {
        "course": course_path.name,
        "exam_id": str(exam.get("exam_id", exam_id)).strip().upper(),
        "title": str(exam.get("title", "")),
        "exam_date": str(exam.get("exam_date", "")),
        "days_until_exam": int(state.get("days_until_exam", 0)),
        "target_score": exam.get("target_score"),
        "scope": dict(state.get("scope", {})),
        "readiness": readiness,
        "state_summary": _build_state_summary(state),
    }


def build_exam_readiness_markdown(report: dict) -> str:
    """Render an exam readiness report as Markdown."""
    readiness = report.get("readiness", {})
    breakdown = readiness.get("breakdown", {})
    state_summary = report.get("state_summary", {})
    exam_id = report.get("exam_id", "")
    recommendations = readiness.get("recommendations") or []
    blockers = readiness.get("blockers") or []
    warnings = readiness.get("warnings") or []

    lines = [
        f"# Exam Readiness Report — {exam_id}",
        "",
        "Course:",
        str(report.get("course", "")),
        "",
        "Exam:",
        f"{exam_id} — {report.get('title', '')}",
        "",
        "Exam date:",
        str(report.get("exam_date", "")),
        "",
        "Days remaining:",
        str(report.get("days_until_exam", "")),
        "",
        "Target score:",
        f"{report.get('target_score', '—')}%"
        if report.get("target_score") is not None
        else "—",
        "",
        "Readiness score:",
        f"{readiness.get('score', 0)}%",
        "",
        "Status:",
        str(readiness.get("status", "")),
        "",
        "## Breakdown",
        "",
        f"- Material readiness: {breakdown.get('readiness', 0)}/30",
        f"- Review load: {breakdown.get('review_load', 0)}/25",
        f"- Mock tests: {breakdown.get('mock_tests', 0)}/30",
        f"- Time pressure: {breakdown.get('time', 0)}/15",
        "",
        "## Main Blockers",
        "",
    ]
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- No major blockers detected.")

    lines.extend(["", "## Recommendations", ""])
    if recommendations:
        for index, recommendation in enumerate(recommendations, start=1):
            lines.append(f"{index}. {recommendation}")
    else:
        lines.append("1. Keep reviewing scoped material.")

    lines.extend(["", "## State Summary", ""])
    lines.append(f"- Units in scope: {state_summary.get('unit_count', 0)}")
    lines.append(f"- Sources in scope: {state_summary.get('source_count', 0)}")
    lines.append(
        f"- Incomplete sources: {state_summary.get('incomplete_sources', 0)}"
    )
    lines.append(
        f"- Units without synthesis: {state_summary.get('units_without_synthesis', 0)}"
    )
    lines.append(
        f"- Units without unit pack: {state_summary.get('units_without_unit_pack', 0)}"
    )
    lines.append(f"- Due flashcards: {state_summary.get('due_flashcards', 0)}")
    lines.append(f"- Recall gaps: {state_summary.get('recall_gaps', 0)}")
    lines.append(f"- Open mistakes: {state_summary.get('open_mistakes', 0)}")
    lines.append(f"- Open weak points: {state_summary.get('open_weak_points', 0)}")
    lines.append(
        f"- Mock attempts: {state_summary.get('mock_attempt_count', 0)}"
    )
    latest_mock = state_summary.get("latest_mock_score")
    lines.append(
        f"- Latest mock score: {latest_mock if latest_mock is not None else '—'}%"
    )

    lines.extend(["", "## Next Study Action", ""])
    if recommendations:
        lines.append(recommendations[0])
    else:
        lines.append("Start an exam-focused study session.")

    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.extend(
        [
            "",
            "---",
            "",
            "This score is deterministic guidance only — not a guarantee of exam performance.",
            "",
        ]
    )
    return "\n".join(lines)


def export_exam_readiness_report(
    course_name: str,
    exam_id: str,
    root: Path | None = None,
    overwrite: bool = False,
) -> dict:
    """Write exam readiness Markdown and JSON under ``07_My_Work/exam_prep/``."""
    course_path = resolve_course_path(course_name, root)
    normalized = exam_id.strip().upper()
    md_path, json_path = get_exam_readiness_report_paths(course_path, normalized)

    if (md_path.is_file() or json_path.is_file()) and not overwrite:
        raise ExamReadinessReportExistsError(
            f"Exam readiness report already exists for {normalized}:\n"
            f"  - {md_path}\n"
            f"  - {json_path}\n"
            "Use --overwrite to replace."
        )

    report = get_exam_readiness_report(course_name, normalized, root)
    markdown = build_exam_readiness_markdown(report)
    generated = _now_iso()

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")

    result = {
        **report,
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
        "generated": generated,
    }

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return result


def get_exam_readiness_dashboard_hint(
    course_name: str,
    root: Path | None = None,
    *,
    session_in_progress: bool = False,
) -> dict | None:
    """
    Optional Today recommendation when nearest exam readiness is low and exam is soon.
    """
    if session_in_progress:
        return None

    from studyforge.study.exam_prep import get_nearest_active_exam_target

    nearest = get_nearest_active_exam_target(course_name, root)
    if nearest is None:
        return None

    days = int(nearest.get("days_until_exam", 999))
    if days < 0 or days > 7:
        return None

    report = get_exam_readiness_report(
        course_name, str(nearest.get("exam_id", "")), root
    )
    readiness = report.get("readiness", {})
    status = str(readiness.get("status", ""))
    if status not in {"at_risk", "not_ready"}:
        return None

    return {
        "key": "improve_exam_readiness",
        "label": "Open Exam Prep and improve readiness.",
        "reason": (
            f"{report.get('title', 'Exam')} readiness is {readiness.get('score', 0)}% "
            f"({status.replace('_', ' ')}) with {days} day(s) remaining."
        ),
    }
