"""
Mock Test Detailed Grading v1 — per-question self-grading (no AI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.mock_tests import (
    MockTestNotFoundError,
    get_mock_tests_dir,
    load_mock_test_json,
    list_mock_tests,
    record_mock_test_attempt,
)

GRADED_SUBDIR = "graded"
VALID_GRADES = frozenset({"correct", "partial", "wrong", "skipped"})


class InvalidMockTestGradeError(ValueError):
    """Raised when a question grade is invalid."""


class MockTestQuestionNotFoundError(Exception):
    """Raised when mock_question_id is not in the mock test."""


class MockTestGradingAlreadyFinalizedError(Exception):
    """Raised when grading was already finalized as an attempt."""


class MockTestReviewExistsError(Exception):
    """Raised when a review Markdown exists and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_mock_test_grading_dir(course_path: Path) -> Path:
    """Return ``07_My_Work/mock_tests/graded/``."""
    return get_mock_tests_dir(course_path) / GRADED_SUBDIR


def get_mock_test_grading_path(course_path: Path, mock_test_id: str) -> Path:
    """Return path to per-question grading JSON for a mock test."""
    normalized = mock_test_id.strip()
    return get_mock_test_grading_dir(course_path) / f"{normalized}_grading.json"


def get_mock_test_review_path(course_path: Path, mock_test_id: str) -> Path:
    """Return path to exported mock test review Markdown."""
    normalized = mock_test_id.strip()
    return get_mock_test_grading_dir(course_path) / f"{normalized}_review.md"


def load_mock_test_grading(path: Path, mock_test_id: str) -> dict:
    """Load grading data or return an empty structure."""
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        data.setdefault("question_results", [])
        return data
    return {
        "mock_test_id": mock_test_id.strip(),
        "question_results": [],
    }


def save_mock_test_grading(path: Path, data: dict) -> None:
    """Write grading JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _validate_grade(grade: str) -> str:
    normalized = grade.strip().lower()
    if normalized not in VALID_GRADES:
        allowed = ", ".join(sorted(VALID_GRADES))
        raise InvalidMockTestGradeError(f"Invalid grade {grade!r}. Allowed: {allowed}")
    return normalized


def _tracker_source_id(mock_test: dict) -> str:
    scope = str(mock_test.get("scope", "")).lower()
    if scope == "unit":
        return str(mock_test.get("unit_id", "")).strip().upper()
    return str(mock_test.get("source_id", "")).strip().upper()


def _find_question(mock_test: dict, mock_question_id: str) -> dict:
    normalized = mock_question_id.strip()
    for question in mock_test.get("questions", []):
        if str(question.get("mock_question_id", "")).strip() == normalized:
            return dict(question)
    raise MockTestQuestionNotFoundError(
        f"Question not found in mock test: {mock_question_id}"
    )


def record_mock_question_result(
    course_name: str,
    mock_test_id: str,
    mock_question_id: str,
    grade: str,
    user_answer: str | None = None,
    notes: str | None = None,
    create_mistake: bool = False,
    create_weak_point: bool = False,
    weak_point_concept: str | None = None,
    root: Path | None = None,
) -> dict:
    """Record or update a per-question mock test grade."""
    course_path = resolve_course_path(course_name, root)
    normalized_grade = _validate_grade(grade)
    mock_test = load_mock_test_json(course_name, mock_test_id, root)
    question = _find_question(mock_test, mock_question_id)

    grading_path = get_mock_test_grading_path(course_path, mock_test_id)
    grading = load_mock_test_grading(grading_path, mock_test_id)
    if grading.get("finalized"):
        raise MockTestGradingAlreadyFinalizedError(
            f"Mock test grading already finalized for {mock_test_id}."
        )

    result_entry = {
        "mock_question_id": mock_question_id.strip(),
        "question": str(question.get("question", "")),
        "expected_answer": str(question.get("expected_answer", "")),
        "grade": normalized_grade,
        "user_answer": user_answer or "",
        "notes": notes or "",
        "date_graded": _now_iso(),
    }

    results = grading.setdefault("question_results", [])
    updated = False
    for index, existing in enumerate(results):
        if str(existing.get("mock_question_id", "")).strip() == mock_question_id.strip():
            results[index] = result_entry
            updated = True
            break
    if not updated:
        results.append(result_entry)

    grading["mock_test_id"] = mock_test_id.strip()
    save_mock_test_grading(grading_path, grading)

    applied: list[str] = ["grading"]
    tracker_source = _tracker_source_id(mock_test)

    if normalized_grade in {"wrong", "partial", "skipped"}:
        if create_mistake and tracker_source:
            from studyforge.study.mistakes import add_mistake

            mistake = add_mistake(
                course_name,
                tracker_source,
                result_entry["question"],
                result_entry["user_answer"],
                question_id=mock_question_id.strip(),
                correct_explanation=result_entry["expected_answer"],
                why_wrong=notes or f"Graded {normalized_grade} on mock test.",
                root=root,
            )
            applied.append("mistake")
            result_entry["mistake_id"] = mistake["mistake_id"]

        if create_weak_point and tracker_source:
            from studyforge.study.weak_points import add_weak_point

            concept = (weak_point_concept or result_entry["question"][:80]).strip()
            weak_point = add_weak_point(
                course_name,
                tracker_source,
                concept,
                confidence_level=2,
                why_hard=notes or f"Missed on mock test ({normalized_grade}).",
                what_to_review=result_entry["expected_answer"] or concept,
                practice_needed="Review missed mock test question and retry.",
                root=root,
            )
            applied.append("weak_point")
            result_entry["weak_point_id"] = weak_point["weak_point_id"]

    summary = summarize_mock_test_grading(course_name, mock_test_id, root)
    return {
        "mock_test_id": mock_test_id.strip(),
        "mock_question_id": mock_question_id.strip(),
        "grade": normalized_grade,
        "updated": updated,
        "applied": applied,
        "grading_path": str(grading_path.resolve()),
        "summary": summary,
    }


def summarize_mock_test_grading(
    course_name: str, mock_test_id: str, root: Path | None = None
) -> dict:
    """Summarize per-question grading for a mock test."""
    mock_test = load_mock_test_json(course_name, mock_test_id, root)
    course_path = resolve_course_path(course_name, root)
    grading_path = get_mock_test_grading_path(course_path, mock_test_id)
    grading = load_mock_test_grading(grading_path, mock_test_id)

    question_count = int(mock_test.get("question_count", len(mock_test.get("questions", []))))
    results = list(grading.get("question_results", []))
    graded_count = len(results)

    correct = sum(1 for item in results if item.get("grade") == "correct")
    partial = sum(1 for item in results if item.get("grade") == "partial")
    wrong = sum(1 for item in results if item.get("grade") == "wrong")
    skipped = sum(1 for item in results if item.get("grade") == "skipped")

    score_correct_equivalent = float(correct) + (partial * 0.5)
    percent = (
        round((score_correct_equivalent / graded_count) * 100.0, 1)
        if graded_count > 0
        else 0.0
    )
    needs_review_count = partial + wrong + skipped
    missed_questions = [
        {
            "mock_question_id": item.get("mock_question_id", ""),
            "question": item.get("question", ""),
            "expected_answer": item.get("expected_answer", ""),
            "user_answer": item.get("user_answer", ""),
            "grade": item.get("grade", ""),
            "notes": item.get("notes", ""),
        }
        for item in results
        if item.get("grade") in {"partial", "wrong", "skipped"}
    ]

    return {
        "mock_test_id": mock_test_id.strip(),
        "question_count": question_count,
        "graded_count": graded_count,
        "correct": correct,
        "partial": partial,
        "wrong": wrong,
        "skipped": skipped,
        "score_correct_equivalent": score_correct_equivalent,
        "score_total": graded_count,
        "percent": percent,
        "ungraded_count": max(0, question_count - graded_count),
        "needs_review_count": needs_review_count,
        "missed_questions": missed_questions,
        "finalized": bool(grading.get("finalized")),
        "finalized_attempt_id": grading.get("finalized_attempt_id"),
    }


def finalize_mock_test_grading(
    course_name: str,
    mock_test_id: str,
    notes: str | None = None,
    weak_topics: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """Finalize detailed grading and record a normal mock test attempt."""
    course_path = resolve_course_path(course_name, root)
    grading_path = get_mock_test_grading_path(course_path, mock_test_id)
    grading = load_mock_test_grading(grading_path, mock_test_id)
    if grading.get("finalized"):
        raise MockTestGradingAlreadyFinalizedError(
            f"Mock test grading already finalized for {mock_test_id}."
        )

    summary = summarize_mock_test_grading(course_name, mock_test_id, root)
    if summary["graded_count"] == 0:
        raise ValueError("Grade at least one question before finalizing.")

    mock_test = load_mock_test_json(course_name, mock_test_id, root)
    scope = str(mock_test.get("scope", "")).lower()
    score_correct = summary["score_correct_equivalent"]
    score_total = summary["graded_count"]

    note_parts: list[str] = []
    if notes:
        note_parts.append(notes.strip())
    note_parts.append(
        f"Detailed grading: {summary['score_correct_equivalent']}/"
        f"{summary['graded_count']} ({summary['percent']}%)"
    )
    combined_notes = " ".join(note_parts)

    attempt = record_mock_test_attempt(
        course_name,
        mock_test_id,
        scope,
        mock_test.get("source_id"),
        mock_test.get("unit_id"),
        score_correct,
        score_total,
        notes=combined_notes,
        weak_topics=weak_topics,
        root=root,
    )

    grading["finalized"] = True
    grading["finalized_attempt_id"] = attempt["attempt_id"]
    grading["date_finalized"] = _now_iso()
    save_mock_test_grading(grading_path, grading)

    return {
        **attempt,
        "grading_summary": summary,
        "detailed_score_correct_equivalent": summary["score_correct_equivalent"],
    }


def build_mock_test_review_markdown(
    course_name: str, mock_test_id: str, root: Path | None = None
) -> str:
    """Render a post-mock review report as Markdown."""
    mock_test = load_mock_test_json(course_name, mock_test_id, root)
    summary = summarize_mock_test_grading(course_name, mock_test_id, root)
    course_path = resolve_course_path(course_name, root)
    grading_path = get_mock_test_grading_path(course_path, mock_test_id)
    grading = load_mock_test_grading(grading_path, mock_test_id)

    scope = str(mock_test.get("scope", ""))
    scope_id = mock_test.get("source_id") or mock_test.get("unit_id") or ""

    lines = [
        f"# Mock Test Review — {mock_test_id}",
        "",
        "Course:",
        course_path.name,
        "",
        "Scope:",
        f"{scope} ({scope_id})",
        "",
        "Generated:",
        str(mock_test.get("date_generated", "")),
        "",
        "## Score Summary",
        "",
        f"- Questions: {summary.get('question_count', 0)}",
        f"- Graded: {summary.get('graded_count', 0)}",
        f"- Correct: {summary.get('correct', 0)}",
        f"- Partial: {summary.get('partial', 0)}",
        f"- Wrong: {summary.get('wrong', 0)}",
        f"- Skipped: {summary.get('skipped', 0)}",
        f"- Score: {summary.get('score_correct_equivalent', 0)}/"
        f"{summary.get('score_total', 0)} ({summary.get('percent', 0)}%)",
        f"- Ungraded: {summary.get('ungraded_count', 0)}",
        "",
    ]

    if grading.get("finalized"):
        lines.extend(
            [
                f"- Finalized attempt: `{grading.get('finalized_attempt_id', '')}`",
                f"- Date finalized: {grading.get('date_finalized', '')}",
                "",
            ]
        )

    lines.extend(["## Missed / Partial Questions", ""])
    missed = summary.get("missed_questions") or []
    if missed:
        for item in missed:
            lines.extend(
                [
                    f"### {item.get('mock_question_id', '')}",
                    "",
                    f"**Question:** {item.get('question', '')}",
                    "",
                    f"**Expected answer:** {item.get('expected_answer', '') or '(see study material)'}",
                    "",
                    f"**Your answer:** {item.get('user_answer', '') or '(none)'}",
                    "",
                    f"**Grade:** {item.get('grade', '')}",
                    "",
                ]
            )
            if item.get("notes"):
                lines.append(f"**Notes:** {item['notes']}")
                lines.append("")
    else:
        lines.append("No missed or partial questions recorded.")
        lines.append("")

    weak_topics: list[str] = []
    for item in missed:
        concept = str(item.get("question", ""))[:80].strip()
        if concept and concept not in weak_topics:
            weak_topics.append(concept)

    lines.extend(["## Weak Topics", ""])
    if weak_topics:
        for topic in weak_topics:
            lines.append(f"- {topic}")
    else:
        lines.append("- (none identified)")
    lines.append("")

    lines.extend(
        [
            "## Recommended Review Actions",
            "",
            "- Review missed questions.",
            "- Create or review weak points for recurring gaps.",
            "- Retake this mock test or generate a new one.",
            "",
        ]
    )
    return "\n".join(lines)


def export_mock_test_review(
    course_name: str,
    mock_test_id: str,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """Write mock test review Markdown under ``graded/``."""
    course_path = resolve_course_path(course_name, root)
    review_path = get_mock_test_review_path(course_path, mock_test_id)
    if review_path.is_file() and not overwrite:
        raise MockTestReviewExistsError(
            f"Mock test review already exists:\n  - {review_path}\n"
            "Use --overwrite to replace."
        )

    markdown = build_mock_test_review_markdown(course_name, mock_test_id, root)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(markdown, encoding="utf-8")

    summary = summarize_mock_test_grading(course_name, mock_test_id, root)
    return {
        "mock_test_id": mock_test_id.strip(),
        "review_path": str(review_path.resolve()),
        "summary": summary,
    }


def get_ungraded_mock_test_hint(
    course_name: str, root: Path | None = None
) -> dict | None:
    """Optional Today recommendation when the latest mock test has ungraded questions."""
    tests = list_mock_tests(course_name, root)
    if not tests:
        return None

    latest = tests[0]
    mock_test_id = latest.get("mock_test_id", "")
    if not mock_test_id:
        return None

    course_path = resolve_course_path(course_name, root)
    grading_path = get_mock_test_grading_path(course_path, mock_test_id)
    grading = load_mock_test_grading(grading_path, mock_test_id)
    if grading.get("finalized"):
        return None

    question_count = int(latest.get("question_count", 0))
    graded_count = len(grading.get("question_results", []))
    if graded_count >= question_count:
        return None

    remaining = question_count - graded_count
    return {
        "key": "finish_mock_grading",
        "label": "Finish grading your latest mock test.",
        "reason": (
            f"`{mock_test_id}` has {remaining} ungraded question(s) "
            f"({graded_count}/{question_count} done)."
        ),
    }
