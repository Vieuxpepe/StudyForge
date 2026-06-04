"""
Active Recall Mode v1 — practice questions one at a time with self-grading (no AI).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import resolve_course_path
from studyforge.study.study_pack import STUDY_OUTPUTS_BASE

ACTIVE_RECALL_SUBDIR = Path("active_recall")
MY_WORK_LOGS_DIR = Path("07_My_Work") / "active_recall_logs"

VALID_GRADES = frozenset({"correct", "partial", "wrong", "skipped"})

_SKIP_LINE_PREFIXES = (
    "course:",
    "source:",
    "instructions:",
    "based on",
)

_METADATA_HEADINGS = frozenset(
    {
        "active recall",
        "active recall questions",
        "instructions",
    }
)


class InvalidGradeError(ValueError):
    """Raised when grade is not correct, partial, wrong, or skipped."""


class ActiveRecallNotReadyError(Exception):
    """Raised when study pack active recall file is missing."""


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _make_question_id(source_id: str, number: int) -> str:
    return f"AR-{_normalize_source_id(source_id)}-Q{number:03d}"


def _make_attempt_id(attempt_number: int) -> str:
    return f"AR-ATTEMPT-{attempt_number:04d}"


def get_active_recall_file(course_path: Path, source_id: str) -> Path:
    """Return path to the generated active recall Markdown file."""
    normalized = _normalize_source_id(source_id)
    return (
        course_path
        / STUDY_OUTPUTS_BASE
        / ACTIVE_RECALL_SUBDIR
        / f"{normalized}_active_recall.md"
    )


def get_active_recall_log_path(course_path: Path, source_id: str) -> Path:
    """Return path to the JSON log for active recall attempts."""
    normalized = _normalize_source_id(source_id)
    return course_path / MY_WORK_LOGS_DIR / f"{normalized}_active_recall_log.json"


def get_active_recall_summary_path(course_path: Path, source_id: str) -> Path:
    """Return path to the exported Markdown summary."""
    normalized = _normalize_source_id(source_id)
    return course_path / MY_WORK_LOGS_DIR / f"{normalized}_active_recall_summary.md"


def _is_skippable_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped == "---":
        return True
    lower = stripped.lower()
    if stripped.startswith("# Active Recall"):
        return True
    if any(lower.startswith(prefix) for prefix in _SKIP_LINE_PREFIXES):
        return True
    if stripped.startswith("#"):
        title = re.sub(r"^#+\s*", "", stripped).strip().lower()
        if title in _METADATA_HEADINGS:
            return True
    return False


def parse_active_recall_questions(text: str, source_id: str = "SRC-0001") -> list[dict]:
    """
    Extract questions from active recall Markdown.

    Supports numbered lists, bullets, and ``## Question N`` blocks.
    """
    normalized = _normalize_source_id(source_id)
    raw_questions: list[tuple[int | None, str]] = []
    lines = text.splitlines()
    index = 0

    heading_number: int | None = None
    heading_lines: list[str] = []

    def flush_heading() -> None:
        nonlocal heading_number, heading_lines
        if heading_number is None:
            return
        body = " ".join(line.strip() for line in heading_lines if line.strip())
        if body:
            raw_questions.append((heading_number, body))
        heading_number = None
        heading_lines = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if _is_skippable_line(stripped):
            index += 1
            continue

        heading_match = re.match(
            r"^#{1,3}\s*Question\s*(\d+)\s*:?\s*(.*)$",
            stripped,
            re.IGNORECASE,
        )
        if heading_match:
            flush_heading()
            heading_number = int(heading_match.group(1))
            inline = heading_match.group(2).strip()
            if inline:
                raw_questions.append((heading_number, inline))
                heading_number = None
            index += 1
            continue

        numbered_match = re.match(r"^(\d+)[\.\)]\s+(.+)$", stripped)
        if numbered_match:
            flush_heading()
            raw_questions.append((int(numbered_match.group(1)), numbered_match.group(2).strip()))
            index += 1
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            flush_heading()
            raw_questions.append((None, bullet_match.group(1).strip()))
            index += 1
            continue

        if heading_number is not None:
            heading_lines.append(stripped)
            index += 1
            continue

        index += 1

    flush_heading()

    questions: list[dict] = []
    for seq, (_file_num, question_text) in enumerate(raw_questions, start=1):
        questions.append(
            {
                "question_id": _make_question_id(normalized, seq),
                "question_number": seq,
                "question": question_text,
            }
        )
    return questions


def load_active_recall_log(path: Path) -> dict:
    """Load JSON log or return an empty structure if missing."""
    if not path.is_file():
        source_id = "SRC-0000"
        match = re.search(r"(SRC-\d+)_active_recall_log\.json$", path.name, re.I)
        if match:
            source_id = match.group(1).upper()
        return {"source_id": source_id, "attempts": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if "attempts" not in data:
        data["attempts"] = []
    return data


def save_active_recall_log(path: Path, log: dict) -> None:
    """Write active recall log JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2)
        handle.write("\n")


def _resolve_active_recall_path(
    course_name: str, source_id: str, root: Path | None
) -> tuple[Path, Path]:
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized = _normalize_source_id(entry["id"])
    recall_path = get_active_recall_file(course_path, normalized)
    registry_path = entry.get("active_recall_path", "")
    if registry_path:
        candidate = Path(registry_path)
        if candidate.is_file():
            recall_path = candidate
    if not recall_path.is_file():
        raise ActiveRecallNotReadyError(
            f"Active recall file not found for {normalized}. "
            "Generate a study pack first."
        )
    return course_path, recall_path


def load_questions_for_source(
    course_name: str, source_id: str, root: Path | None = None
) -> list[dict]:
    """Load and parse questions from the study pack active recall file."""
    course_path, recall_path = _resolve_active_recall_path(course_name, source_id, root)
    text = recall_path.read_text(encoding="utf-8")
    return parse_active_recall_questions(text, source_id)


def _summarize_log_dict(log: dict, recent_limit: int = 10) -> dict:
    attempts = list(log.get("attempts", []))
    counts = {"correct": 0, "partial": 0, "wrong": 0, "skipped": 0}
    for attempt in attempts:
        grade = str(attempt.get("grade", "")).lower()
        if grade in counts:
            counts[grade] += 1

    graded = counts["correct"] + counts["partial"] + counts["wrong"]
    score = counts["correct"] + 0.5 * counts["partial"]
    if graded > 0:
        accuracy_percent = round(100.0 * score / graded, 1)
    else:
        accuracy_percent = 0.0

    needs_review_count = sum(
        1 for attempt in attempts if str(attempt.get("grade", "")).lower() != "correct"
    )

    recent = attempts[-recent_limit:] if recent_limit > 0 else []
    recent_attempts = list(reversed(recent))

    return {
        "source_id": log.get("source_id", ""),
        "attempt_count": len(attempts),
        "correct": counts["correct"],
        "partial": counts["partial"],
        "wrong": counts["wrong"],
        "skipped": counts["skipped"],
        "accuracy_percent": accuracy_percent,
        "needs_review_count": needs_review_count,
        "recent_attempts": recent_attempts,
    }


def record_active_recall_attempt(
    course_name: str,
    source_id: str,
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
    """
    Append one self-graded attempt to the active recall log.

    Raises:
        InvalidGradeError: Unknown grade value.
        ActiveRecallNotReadyError: Study pack active recall file missing.
    """
    grade_normalized = grade.strip().lower()
    if grade_normalized not in VALID_GRADES:
        allowed = ", ".join(sorted(VALID_GRADES))
        raise InvalidGradeError(
            f"Invalid grade {grade!r}. Allowed: {allowed}"
        )

    course_path, _recall_path = _resolve_active_recall_path(course_name, source_id, root)
    normalized = _normalize_source_id(source_id)
    log_path = get_active_recall_log_path(course_path, normalized)
    log = load_active_recall_log(log_path)
    log["source_id"] = normalized

    attempt_number = len(log.get("attempts", [])) + 1
    attempt = {
        "attempt_id": _make_attempt_id(attempt_number),
        "source_id": normalized,
        "question_id": question_id.strip(),
        "question": question,
        "user_answer": user_answer,
        "grade": grade_normalized,
        "notes": notes or "",
        "date_answered": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"
        ),
    }
    log.setdefault("attempts", []).append(attempt)
    save_active_recall_log(log_path, log)

    result: dict = {
        "course": course_path.name,
        "source_id": normalized,
        "attempt_id": attempt["attempt_id"],
        "question_id": attempt["question_id"],
        "grade": grade_normalized,
        "log_path": str(log_path.resolve()),
        "attempt_count": len(log["attempts"]),
    }

    if grade_normalized in {"wrong", "partial", "skipped"}:
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


def summarize_active_recall_log(
    course_name: str, source_id: str, root: Path | None = None
) -> dict:
    """Return score summary and recent attempts for one source."""
    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_source_id(source_id)
    find_source_by_id(course_name, source_id, root)
    log_path = get_active_recall_log_path(course_path, normalized)
    log = load_active_recall_log(log_path)
    log["source_id"] = normalized
    return _summarize_log_dict(log)


def export_active_recall_summary_markdown(
    course_name: str, source_id: str, root: Path | None = None
) -> Path:
    """Write a Markdown summary of active recall attempts."""
    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_source_id(source_id)
    find_source_by_id(course_name, source_id, root)
    log_path = get_active_recall_log_path(course_path, normalized)
    log = load_active_recall_log(log_path)
    summary = _summarize_log_dict(log, recent_limit=20)
    out_path = get_active_recall_summary_path(course_path, normalized)

    lines = [
        "# Active Recall Summary",
        "",
        f"Source: {normalized}",
        f"Course: {course_path.name}",
        "",
        "## Score summary",
        "",
        f"- Total attempts: {summary['attempt_count']}",
        f"- Correct: {summary['correct']}",
        f"- Partial: {summary['partial']}",
        f"- Wrong: {summary['wrong']}",
        f"- Skipped: {summary['skipped']}",
        f"- Accuracy (correct=1, partial=0.5, skipped excluded): {summary['accuracy_percent']}%",
        f"- Needs review (non-correct attempts): {summary['needs_review_count']}",
        "",
        "## Questions needing review",
        "",
    ]

    review_attempts = [
        attempt
        for attempt in log.get("attempts", [])
        if str(attempt.get("grade", "")).lower() in {"partial", "wrong", "skipped"}
    ]
    if review_attempts:
        for attempt in review_attempts:
            lines.append(
                f"- **{attempt.get('question_id', '?')}** ({attempt.get('grade', '?')}): "
                f"{attempt.get('question', '')}"
            )
    else:
        lines.append("- None yet.")

    lines.extend(["", "## Recent attempts", ""])
    if summary["recent_attempts"]:
        for attempt in summary["recent_attempts"]:
            lines.append(f"### {attempt.get('attempt_id', 'attempt')}")
            lines.append(f"- Question: {attempt.get('question', '')}")
            lines.append(f"- Grade: {attempt.get('grade', '')}")
            lines.append(f"- Answer: {attempt.get('user_answer', '')}")
            if attempt.get("notes"):
                lines.append(f"- Notes: {attempt.get('notes')}")
            lines.append(f"- Date: {attempt.get('date_answered', '')}")
            lines.append("")
    else:
        lines.append("No attempts recorded yet.")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def get_active_recall_pipeline_warnings(
    course_path: Path,
    source_id: str,
    study_pack_done: bool,
) -> list[str]:
    """Optional Pipeline Doctor hints based on active recall progress."""
    if not study_pack_done:
        return []
    normalized = _normalize_source_id(source_id)
    log_path = get_active_recall_log_path(course_path, normalized)
    log = load_active_recall_log(log_path)
    attempts = log.get("attempts", [])
    if not attempts:
        return ["Study pack exists. Start active recall to validate learning."]
    summary = _summarize_log_dict(log)
    graded = summary["correct"] + summary["partial"] + summary["wrong"]
    weak = summary["partial"] + summary["wrong"]
    if weak >= 3 or (
        graded >= 3 and summary["accuracy_percent"] < 50.0
    ):
        return ["Active recall shows weak areas. Review mistakes/weak points."]
    return []


def list_active_recall_questions(
    course_name: str, source_id: str, root: Path | None = None
) -> list[dict]:
    """Load questions for CLI/GUI listing."""
    return load_questions_for_source(course_name, source_id, root)


def get_first_unanswered_question(
    questions: list[dict], log: dict
) -> dict | None:
    """Return the first question with no recorded attempt."""
    attempted_ids = {
        str(attempt.get("question_id", ""))
        for attempt in log.get("attempts", [])
    }
    for item in questions:
        if item["question_id"] not in attempted_ids:
            return item
    return None
