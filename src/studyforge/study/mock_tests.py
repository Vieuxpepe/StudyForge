"""
Mock Test / Exam Simulator v1 — deterministic tests from study material (no AI).
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import list_sources, resolve_course_path
from studyforge.study.active_recall import get_active_recall_file
from studyforge.study.flashcards import get_flashcard_output_paths
from studyforge.study.study_pack import STUDY_OUTPUTS_BASE
from studyforge.study.study_units import (
    _normalize_unit_id,
    get_study_unit_summary,
)
from studyforge.study.unit_study_pack import (
    get_unit_study_pack_output_paths,
    unit_has_study_pack,
)

MY_WORK_DIR = Path("07_My_Work")
MOCK_TESTS_SUBDIR = "mock_tests"
MOCK_TEST_ATTEMPTS_FILE = "mock_test_attempts.json"

_VALID_SCOPES = frozenset({"source", "unit"})
_QUESTION_SOURCES = frozenset({"practice_quiz", "active_recall", "flashcard"})

_SKIP_LINE_PREFIXES = (
    "course:",
    "source:",
    "unit:",
    "instructions:",
    "based on",
    "generated:",
    "scope:",
)

_METADATA_HEADINGS = frozenset(
    {
        "mock test",
        "practice quiz",
        "active recall",
        "active recall questions",
        "instructions",
        "questions",
        "answer / reference key",
        "answer key",
    }
)


class InvalidMockTestScopeError(ValueError):
    """Raised when scope is not source or unit."""


class MockTestNotReadyError(Exception):
    """Raised when no study material is available to build a mock test."""


class InvalidMockTestScoreError(ValueError):
    """Raised when score values are invalid."""


class MockTestNotFoundError(Exception):
    """Raised when a mock test JSON file cannot be found."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _timestamp_for_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _normalize_question_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _is_skippable_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped == "---":
        return True
    lower = stripped.lower()
    if stripped.startswith("# Mock Test"):
        return True
    if any(lower.startswith(prefix) for prefix in _SKIP_LINE_PREFIXES):
        return True
    if stripped.startswith("#"):
        title = re.sub(r"^#+\s*", "", stripped).strip().lower()
        if title in _METADATA_HEADINGS:
            return True
    return False


def parse_questions_from_markdown(
    text: str,
    *,
    source: str = "practice_quiz",
) -> list[dict]:
    """
    Extract questions from practice quiz or active recall Markdown.

    Supports numbered lists, bullets, and ``## Question N`` headings.
    """
    if source not in {"practice_quiz", "active_recall"}:
        raise ValueError(f"Invalid markdown source: {source}")

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
            raw_questions.append(
                (int(numbered_match.group(1)), numbered_match.group(2).strip())
            )
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

    results: list[dict] = []
    for _file_num, question_text in raw_questions:
        if not question_text.strip():
            continue
        results.append(
            {
                "question": question_text,
                "source": source,
                "raw": question_text,
            }
        )
    return results


def parse_flashcard_questions_from_csv(
    csv_text: str,
    limit: int | None = None,
) -> list[dict]:
    """Parse flashcard CSV rows; use front as question and back as expected answer."""
    reader = csv.DictReader(io.StringIO(csv_text))
    results: list[dict] = []
    for row in reader:
        front = str(row.get("front", "")).strip()
        if not front:
            continue
        back = str(row.get("back", "")).strip()
        tags_raw = str(row.get("tags", "")).strip()
        tags = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]
        results.append(
            {
                "question": front,
                "expected_answer": back,
                "source": "flashcard",
                "tags": tags,
            }
        )
        if limit is not None and len(results) >= limit:
            break
    return results


def get_mock_tests_dir(course_path: Path) -> Path:
    """Return ``07_My_Work/mock_tests/`` for a course."""
    return course_path / MY_WORK_DIR / MOCK_TESTS_SUBDIR


def get_mock_test_log_path(course_path: Path) -> Path:
    """Return path to the mock test attempts JSON log."""
    return get_mock_tests_dir(course_path) / MOCK_TEST_ATTEMPTS_FILE


def _source_study_paths(course_path: Path, source_id: str) -> dict[str, Path]:
    normalized = _normalize_source_id(source_id)
    flashcard_paths = get_flashcard_output_paths(course_path, normalized)
    base = course_path / STUDY_OUTPUTS_BASE
    return {
        "practice_quiz": base / "quizzes" / f"{normalized}_practice_quiz.md",
        "active_recall": get_active_recall_file(course_path, normalized),
        "flashcards_csv": flashcard_paths["csv"],
    }


def _load_scope_study_texts(
    course_path: Path,
    *,
    scope: str,
    source_id: str | None,
    unit_id: str | None,
) -> dict[str, str]:
    """Load raw text from available study files for the given scope."""
    texts: dict[str, str] = {}
    if scope == "source":
        normalized = _normalize_source_id(str(source_id))
        paths = _source_study_paths(course_path, normalized)
        for key, path in paths.items():
            if path.is_file():
                texts[key] = path.read_text(encoding="utf-8")
    elif scope == "unit":
        normalized = _normalize_unit_id(str(unit_id))
        paths = get_unit_study_pack_output_paths(course_path, normalized)
        mapping = {
            "practice_quiz": "unit_practice_quiz",
            "active_recall": "unit_active_recall",
            "flashcards_csv": "unit_flashcards_csv",
        }
        for text_key, path_key in mapping.items():
            path = paths[path_key]
            if path.is_file():
                texts[text_key] = path.read_text(encoding="utf-8")
    return texts


def _deduplicate_questions(candidates: list[dict]) -> list[dict]:
    """Remove duplicate questions by normalized question text (first wins)."""
    seen: set[str] = set()
    unique: list[dict] = []
    for item in candidates:
        key = _normalize_question_text(str(item.get("question", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(dict(item))
    return unique


def _select_questions(
    candidates: list[dict],
    question_count: int,
) -> list[dict]:
    """Select up to question_count in practice_quiz → active_recall → flashcard order."""
    ordered_sources = ("practice_quiz", "active_recall", "flashcard")
    selected: list[dict] = []
    for source_name in ordered_sources:
        for item in candidates:
            if str(item.get("source", "")) != source_name:
                continue
            selected.append(item)
            if len(selected) >= question_count:
                return selected
    return selected


def _make_mock_question_id(scope: str, scope_id: str, number: int) -> str:
    normalized = scope_id.strip().upper()
    if scope == "source":
        return f"MT-{_normalize_source_id(normalized)}-Q{number:03d}"
    return f"MT-{_normalize_unit_id(normalized)}-Q{number:03d}"


def _make_mock_test_id(scope: str, scope_id: str, timestamp: str) -> str:
    normalized = scope_id.strip().upper()
    if scope == "source":
        return f"MT-{_normalize_source_id(normalized)}-{timestamp}"
    return f"MT-{_normalize_unit_id(normalized)}-{timestamp}"


def build_mock_test_questions(
    course_name: str,
    scope: str,
    source_id: str | None = None,
    unit_id: str | None = None,
    question_count: int = 20,
    include_flashcards: bool = True,
    root: Path | None = None,
) -> list[dict]:
    """Build deduplicated mock test questions from existing study material."""
    scope_normalized = scope.strip().lower()
    if scope_normalized not in _VALID_SCOPES:
        allowed = ", ".join(sorted(_VALID_SCOPES))
        raise InvalidMockTestScopeError(f"Invalid scope {scope!r}. Allowed: {allowed}")

    course_path = resolve_course_path(course_name, root)
    if scope_normalized == "source":
        if not source_id:
            raise InvalidMockTestScopeError("source_id is required for source scope.")
        normalized_source = _normalize_source_id(source_id)
        scope_id = normalized_source
        normalized_unit: str | None = None
    else:
        if not unit_id:
            raise InvalidMockTestScopeError("unit_id is required for unit scope.")
        get_study_unit_summary(course_name, unit_id, root)
        normalized_unit = _normalize_unit_id(unit_id)
        scope_id = normalized_unit
        normalized_source = None

    texts = _load_scope_study_texts(
        course_path,
        scope=scope_normalized,
        source_id=normalized_source,
        unit_id=normalized_unit,
    )
    if not texts:
        label = normalized_source or normalized_unit or scope
        raise MockTestNotReadyError(
            f"No study material found for {scope} scope ({label}). "
            "Generate a study pack first."
        )

    candidates: list[dict] = []
    if "practice_quiz" in texts:
        for item in parse_questions_from_markdown(
            texts["practice_quiz"], source="practice_quiz"
        ):
            candidates.append({**item, "expected_answer": ""})

    if "active_recall" in texts:
        for item in parse_questions_from_markdown(
            texts["active_recall"], source="active_recall"
        ):
            candidates.append({**item, "expected_answer": ""})

    if include_flashcards and "flashcards_csv" in texts:
        candidates.extend(parse_flashcard_questions_from_csv(texts["flashcards_csv"]))

    unique = _deduplicate_questions(candidates)
    if not unique:
        raise MockTestNotReadyError(
            "Study files exist but no questions could be parsed. "
            "Check practice quiz, active recall, or flashcard content."
        )

    selected = _select_questions(unique, max(1, question_count))
    results: list[dict] = []
    for index, item in enumerate(selected, start=1):
        results.append(
            {
                "mock_question_id": _make_mock_question_id(
                    scope_normalized, scope_id, index
                ),
                "question": str(item.get("question", "")),
                "expected_answer": str(item.get("expected_answer", "")),
                "source": str(item.get("source", "")),
                "scope": scope_normalized,
                "source_id": normalized_source,
                "unit_id": normalized_unit,
            }
        )
    return results


def build_mock_test_markdown(
    *,
    course_name: str,
    scope: str,
    scope_id: str,
    mock_test_id: str,
    questions: list[dict],
    date_generated: str,
) -> str:
    """Render a mock test as Markdown with questions and answer key."""
    lines = [
        f"# Mock Test — {scope_id}",
        "",
        "Course:",
        course_name,
        "",
        "Scope:",
        scope,
        "",
        "Generated:",
        date_generated,
        "",
        "Instructions:",
        "- Answer without looking at notes.",
        "- Self-grade afterward.",
        "- Log mistakes and weak points.",
        "",
        "---",
        "",
        "## Questions",
        "",
    ]

    for index, question in enumerate(questions, start=1):
        lines.extend(
            [
                f"### Question {index}",
                "",
                str(question.get("question", "")),
                "",
            ]
        )

    lines.extend(["---", "", "## Answer / Reference Key", ""])
    lines.append("Keep this section collapsed mentally; do not look before answering.")
    lines.append("")

    for index, question in enumerate(questions, start=1):
        expected = str(question.get("expected_answer", "")).strip()
        lines.extend([f"### Question {index}", ""])
        if expected:
            lines.append(f"Expected answer/reference:\n{expected}")
        else:
            lines.append("Check the study guide/final audit.")
        lines.append("")

    return "\n".join(lines)


def generate_mock_test(
    course_name: str,
    scope: str,
    source_id: str | None = None,
    unit_id: str | None = None,
    question_count: int = 20,
    include_flashcards: bool = True,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """Build questions and write mock test Markdown + JSON (timestamped filenames)."""
    _ = overwrite  # reserved; each run creates a new timestamped file
    scope_normalized = scope.strip().lower()
    questions = build_mock_test_questions(
        course_name,
        scope_normalized,
        source_id=source_id,
        unit_id=unit_id,
        question_count=question_count,
        include_flashcards=include_flashcards,
        root=root,
    )

    course_path = resolve_course_path(course_name, root)
    normalized_source: str | None = None
    normalized_unit: str | None = None
    if scope_normalized == "source":
        normalized_source = _normalize_source_id(str(source_id))
        scope_id = normalized_source
    else:
        normalized_unit = _normalize_unit_id(str(unit_id))
        scope_id = normalized_unit

    file_ts = _timestamp_for_filename()
    id_ts = _timestamp_for_id()
    mock_test_id = _make_mock_test_id(scope_normalized, scope_id, id_ts)
    date_generated = _now_iso()

    out_dir = get_mock_tests_dir(course_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{scope_id}_MOCKTEST_{file_ts}.md"
    json_path = out_dir / f"{scope_id}_MOCKTEST_{file_ts}.json"

    markdown = build_mock_test_markdown(
        course_name=course_path.name,
        scope=scope_normalized,
        scope_id=scope_id,
        mock_test_id=mock_test_id,
        questions=questions,
        date_generated=date_generated,
    )
    md_path.write_text(markdown, encoding="utf-8")

    result = {
        "mock_test_id": mock_test_id,
        "course": course_path.name,
        "scope": scope_normalized,
        "source_id": normalized_source if scope_normalized == "source" else None,
        "unit_id": normalized_unit if scope_normalized == "unit" else None,
        "question_count": len(questions),
        "questions": questions,
        "date_generated": date_generated,
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
    }

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return result


def load_mock_test_attempts(path: Path) -> dict:
    """Load mock test attempts log or return empty structure."""
    if not path.is_file():
        return {"attempts": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("attempts", [])
    return data


def save_mock_test_attempts(path: Path, data: dict) -> None:
    """Write mock test attempts log JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _make_attempt_id(attempt_number: int) -> str:
    return f"MT-ATTEMPT-{attempt_number:04d}"


def _normalize_score_correct(value: int | float) -> int | float:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _validate_scores(
    score_correct: int | float, score_total: int
) -> tuple[int | float, int]:
    if score_total <= 0:
        raise InvalidMockTestScoreError("score_total must be greater than 0.")
    correct_value = float(score_correct)
    if correct_value < 0 or correct_value > score_total:
        raise InvalidMockTestScoreError(
            f"score_correct must be between 0 and {score_total}."
        )
    return _normalize_score_correct(score_correct), score_total


def record_mock_test_attempt(
    course_name: str,
    mock_test_id: str,
    scope: str,
    source_id: str | None,
    unit_id: str | None,
    score_correct: int | float,
    score_total: int,
    notes: str | None = None,
    weak_topics: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """Append one self-graded mock test attempt; optionally create weak points."""
    scope_normalized = scope.strip().lower()
    if scope_normalized not in _VALID_SCOPES:
        allowed = ", ".join(sorted(_VALID_SCOPES))
        raise InvalidMockTestScopeError(f"Invalid scope {scope!r}. Allowed: {allowed}")

    correct, total = _validate_scores(score_correct, int(score_total))
    percent = round((correct / total) * 100.0, 1)

    course_path = resolve_course_path(course_name, root)
    log_path = get_mock_test_log_path(course_path)
    log = load_mock_test_attempts(log_path)

    attempt_number = len(log.get("attempts", [])) + 1
    topics = [topic.strip() for topic in (weak_topics or []) if topic.strip()]
    attempt = {
        "attempt_id": _make_attempt_id(attempt_number),
        "mock_test_id": mock_test_id.strip(),
        "course": course_path.name,
        "scope": scope_normalized,
        "source_id": _normalize_source_id(source_id) if source_id else None,
        "unit_id": _normalize_unit_id(unit_id) if unit_id else None,
        "score_correct": correct,
        "score_total": total,
        "percent": percent,
        "notes": notes or "",
        "weak_topics": topics,
        "date_recorded": _now_iso(),
    }
    log.setdefault("attempts", []).append(attempt)
    save_mock_test_attempts(log_path, log)

    result: dict = {
        "attempt_id": attempt["attempt_id"],
        "mock_test_id": attempt["mock_test_id"],
        "score_correct": correct,
        "score_total": total,
        "percent": percent,
        "log_path": str(log_path.resolve()),
        "attempt_count": len(log["attempts"]),
    }

    if topics:
        from studyforge.study.weak_points import add_weak_point

        weak_point_ids: list[str] = []
        tracker_source = (
            attempt["source_id"]
            if scope_normalized == "source"
            else attempt["unit_id"]
        )
        if tracker_source:
            for topic in topics:
                wp = add_weak_point(
                    course_name,
                    tracker_source,
                    topic,
                    confidence_level=2,
                    why_hard=notes or "Missed on mock test.",
                    what_to_review=topic,
                    practice_needed="Review in study guide and retry mock test.",
                    root=root,
                )
                weak_point_ids.append(wp["weak_point_id"])
        result["weak_point_ids"] = weak_point_ids

    return result


def summarize_mock_test_attempts(
    course_name: str, root: Path | None = None
) -> dict:
    """Return attempt counts, average score, and recent attempts."""
    course_path = resolve_course_path(course_name, root)
    log_path = get_mock_test_log_path(course_path)
    log = load_mock_test_attempts(log_path)
    attempts = [
        dict(item)
        for item in log.get("attempts", [])
        if str(item.get("course", course_path.name)) == course_path.name
    ]

    if not attempts:
        return {
            "course": course_path.name,
            "attempt_count": 0,
            "average_percent": 0.0,
            "recent_attempts": [],
            "latest_attempt": None,
        }

    percents = [float(item.get("percent", 0.0)) for item in attempts]
    average = round(sum(percents) / len(percents), 1)
    recent = list(reversed(attempts[-10:]))
    latest = dict(attempts[-1])

    return {
        "course": course_path.name,
        "attempt_count": len(attempts),
        "average_percent": average,
        "recent_attempts": recent,
        "latest_attempt": latest,
    }


def course_has_study_packs(course_name: str, root: Path | None = None) -> bool:
    """Return True when at least one source or unit study pack exists."""
    course_path = resolve_course_path(course_name, root)
    for entry in list_sources(course_name, root):
        manifest = course_path / STUDY_OUTPUTS_BASE / (
            f"{_normalize_source_id(str(entry.get('id', '')))}_study_pack_manifest.json"
        )
        if manifest.is_file():
            return True
    from studyforge.study.study_units import load_study_units

    data = load_study_units(course_name, root)
    for unit in data.get("units", []):
        if unit_has_study_pack(unit):
            return True
    return False


def load_mock_test_json(
    course_name: str, mock_test_id: str, root: Path | None = None
) -> dict:
    """Load a generated mock test JSON by ``mock_test_id``."""
    course_path = resolve_course_path(course_name, root)
    out_dir = get_mock_tests_dir(course_path)
    normalized_id = mock_test_id.strip()
    if not out_dir.is_dir():
        raise MockTestNotFoundError(
            f"Mock test not found: {normalized_id} (no mock_tests directory)."
        )

    for json_path in sorted(out_dir.glob("*.json"), reverse=True):
        if json_path.name == MOCK_TEST_ATTEMPTS_FILE:
            continue
        try:
            with json_path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            continue
        if str(data.get("mock_test_id", "")).strip() == normalized_id:
            return dict(data)

    raise MockTestNotFoundError(f"Mock test not found: {normalized_id}")


def list_mock_tests(course_name: str, root: Path | None = None) -> list[dict]:
    """Return summaries of generated mock tests, newest first."""
    course_path = resolve_course_path(course_name, root)
    out_dir = get_mock_tests_dir(course_path)
    if not out_dir.is_dir():
        return []

    summaries: list[dict] = []
    for json_path in out_dir.glob("*.json"):
        if json_path.name == MOCK_TEST_ATTEMPTS_FILE:
            continue
        try:
            with json_path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            continue
        mock_test_id = str(data.get("mock_test_id", "")).strip()
        if not mock_test_id:
            continue
        md_path = json_path.with_suffix(".md")
        if not md_path.is_file():
            md_candidate = Path(str(data.get("markdown_path", "")))
            md_path = md_candidate if md_candidate.is_file() else md_path
        summaries.append(
            {
                "mock_test_id": mock_test_id,
                "scope": str(data.get("scope", "")),
                "source_id": data.get("source_id"),
                "unit_id": data.get("unit_id"),
                "question_count": int(data.get("question_count", 0)),
                "date_generated": str(data.get("date_generated", "")),
                "json_path": str(json_path.resolve()),
                "markdown_path": str(md_path.resolve()) if md_path.is_file() else "",
            }
        )

    summaries.sort(
        key=lambda item: str(item.get("date_generated", "")),
        reverse=True,
    )
    return summaries


def get_mock_test_exam_prep_hint(
    course_name: str, root: Path | None = None
) -> dict | None:
    """Optional recommendation when study packs exist but no mock attempts yet."""
    summary = summarize_mock_test_attempts(course_name, root)
    if summary["attempt_count"] > 0:
        return None
    if not course_has_study_packs(course_name, root):
        return None
    return {
        "key": "generate_mock_test",
        "label": "Generate a mock test before exam prep",
        "reason": "Study packs are ready — try a timed practice test.",
    }
