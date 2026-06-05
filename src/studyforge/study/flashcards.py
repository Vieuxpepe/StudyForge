"""
Deterministic flashcard extraction and export from study pack sections (no AI).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import resolve_course_path

STUDY_OUTPUTS_BASE = Path("06_Study_Outputs")
FLASHCARDS_SUBDIR = "flashcards"

_PLACEHOLDER_MARKERS = (
    "not found in final audit.",
    "not found in original final audit.",
)

_SECTION_CONFIG: tuple[tuple[str, str, str], ...] = (
    ("must_memorize", "Must-Memorize List", "must_memorize"),
    ("formula_sheet", "Formula / Method Sheet", "formula_sheet"),
    ("exam_traps", "Exam / Homework Traps", "exam_traps"),
    ("must_understand", "Must-Understand List", "must_understand"),
)

_ACTIVE_RECALL_SECTION = ("active_recall", "Active Recall Questions", "active_recall")
_ACTIVE_RECALL_BACK = "Answer from study guide / final audit."


class FlashcardExportExistsError(Exception):
    """Raised when flashcard export files exist and overwrite was not requested."""


def split_bullets(text: str) -> list[str]:
    """
    Extract bullet points from Markdown section text.

    Supports ``-``, ``*``, numbered lists, and continuation lines on the next row.
    """
    if not text or not text.strip():
        return []

    items: list[str] = []
    current_parts: list[str] = []

    def flush() -> None:
        if not current_parts:
            return
        combined = clean_flashcard_text(" ".join(current_parts))
        if combined:
            items.append(combined)
        current_parts.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        bullet_match = re.match(r"^([\*\-]|\d+[\.\)])\s+(.*)$", stripped)
        if bullet_match:
            flush()
            current_parts.append(bullet_match.group(2).strip())
            continue

        if current_parts:
            current_parts.append(stripped)
            continue

    flush()
    return items


def clean_flashcard_text(text: str) -> str:
    """Normalize whitespace and strip common Markdown artifacts."""
    if not text:
        return ""

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)
    cleaned = re.sub(r"`(.+?)`", r"\1", cleaned)
    cleaned = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _is_placeholder_section(text: str) -> bool:
    normalized = clean_flashcard_text(text).lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def build_flashcard_from_bullet(
    bullet: str,
    source_id: str,
    source_title: str,
    section_name: str,
    *,
    tag_key: str,
) -> dict:
    """Build one flashcard dict from a bullet line."""
    cleaned = clean_flashcard_text(bullet)
    if ":" in cleaned:
        left, _, right = cleaned.partition(":")
        left = left.strip()
        right = right.strip()
        if left and right:
            if left.endswith("?"):
                front = left
            elif left.lower().startswith(("what ", "how ", "why ", "when ", "where ", "define ")):
                front = left if left.endswith("?") else f"{left}?"
            else:
                front = f"What is the {left}?"
            back = right
        else:
            front = "What should I remember about this concept?"
            back = cleaned
    else:
        front = "What should I remember about this concept?"
        back = cleaned

    normalized_id = source_id.strip().upper()
    return {
        "front": front,
        "back": back,
        "source_id": normalized_id,
        "source_title": source_title,
        "section": section_name,
        "tags": [normalized_id, tag_key],
    }


def _active_recall_questions(text: str) -> list[str]:
    """Extract question strings from active recall section text."""
    questions: list[str] = []
    for bullet in split_bullets(text):
        cleaned = clean_flashcard_text(bullet)
        if cleaned:
            questions.append(cleaned)
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^##\s+Question\s+\d+\s*$", stripped, re.IGNORECASE)
        if match:
            continue
        heading_body = re.match(r"^##\s+Question\s+\d+\s*(.+)$", stripped, re.IGNORECASE)
        if heading_body:
            body = clean_flashcard_text(heading_body.group(1))
            if body:
                questions.append(body)
    return questions


def _normalize_card_key(card: dict) -> str:
    front = clean_flashcard_text(str(card.get("front", ""))).lower()
    back = clean_flashcard_text(str(card.get("back", ""))).lower()
    return f"{front}|{back}"


def build_flashcards_from_sections(
    source_id: str,
    source_title: str,
    sections: dict,
) -> list[dict]:
    """Build deduplicated flashcards from extracted study pack sections."""
    cards: list[dict] = []
    seen: set[str] = set()

    def add_card(card: dict) -> None:
        key = _normalize_card_key(card)
        if key in seen:
            return
        seen.add(key)
        cards.append(card)

    for section_key, section_name, tag_key in _SECTION_CONFIG:
        body = sections.get(section_key, "")
        if _is_placeholder_section(body):
            continue
        for bullet in split_bullets(body):
            add_card(
                build_flashcard_from_bullet(
                    bullet,
                    source_id,
                    source_title,
                    section_name,
                    tag_key=tag_key,
                )
            )

    recall_key, recall_name, recall_tag = _ACTIVE_RECALL_SECTION
    recall_body = sections.get(recall_key, "")
    if not _is_placeholder_section(recall_body):
        for question in _active_recall_questions(recall_body):
            add_card(
                {
                    "front": question if question.endswith("?") else f"{question}?",
                    "back": _ACTIVE_RECALL_BACK,
                    "source_id": source_id.strip().upper(),
                    "source_title": source_title,
                    "section": recall_name,
                    "tags": [source_id.strip().upper(), recall_tag],
                }
            )

    return cards


def flashcards_to_markdown(
    cards: list[dict],
    course_name: str,
    source_id: str,
    source_title: str,
) -> str:
    """Render flashcards as Markdown."""
    lines = [
        "# Flashcards",
        "",
        "Course:",
        course_name,
        "",
        "Source:",
        f"{source_id} - {source_title}",
        "",
        "Card count:",
        str(len(cards)),
        "",
        "---",
        "",
    ]

    if not cards:
        lines.append("_(No flashcards generated from final audit sections.)_\n")
        return "\n".join(lines)

    for index, card in enumerate(cards, start=1):
        tags = ", ".join(str(tag) for tag in card.get("tags", []))
        lines.extend(
            [
                f"## Card {index}",
                "",
                "Front:",
                str(card.get("front", "")),
                "",
                "Back:",
                str(card.get("back", "")),
                "",
                "Source:",
                str(card.get("source_id", source_id)),
                "",
                "Section:",
                str(card.get("section", "")),
                "",
                "Tags:",
                tags,
                "",
            ]
        )

    return "\n".join(lines) + "\n"


def flashcards_to_csv(cards: list[dict]) -> str:
    """Render flashcards as CSV with standard columns."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["front", "back", "source_id", "source_title", "section", "tags"]
    )
    for card in cards:
        tags = ", ".join(str(tag) for tag in card.get("tags", []))
        writer.writerow(
            [
                card.get("front", ""),
                card.get("back", ""),
                card.get("source_id", ""),
                card.get("source_title", ""),
                card.get("section", ""),
                tags,
            ]
        )
    return buffer.getvalue()


def _anki_safe_tags(tags: list[str]) -> str:
    safe: list[str] = []
    for tag in tags:
        normalized = re.sub(r"\s+", "_", str(tag).strip().lower())
        normalized = re.sub(r"[^a-z0-9_\-]", "", normalized)
        if normalized:
            safe.append(normalized)
    return " ".join(safe)


def _anki_escape_field(text: str) -> str:
    return str(text).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def flashcards_to_anki_tsv(cards: list[dict]) -> str:
    """Render flashcards as Anki-compatible TSV (front, back, tags)."""
    lines: list[str] = []
    for card in cards:
        front = _anki_escape_field(card.get("front", ""))
        back = _anki_escape_field(card.get("back", ""))
        tags = _anki_safe_tags(list(card.get("tags", [])))
        lines.append(f"{front}\t{back}\t{tags}")
    return "\n".join(lines) + ("\n" if lines else "")


def get_flashcard_output_paths(course_path: Path, source_id: str) -> dict[str, Path]:
    """Return Markdown, CSV, and Anki TSV paths for a source."""
    normalized = source_id.strip().upper()
    base = course_path / STUDY_OUTPUTS_BASE / FLASHCARDS_SUBDIR
    return {
        "markdown": base / f"{normalized}_flashcards.md",
        "csv": base / f"{normalized}_flashcards.csv",
        "anki_tsv": base / f"{normalized}_flashcards_anki.tsv",
    }


def save_flashcard_exports(
    course_name: str,
    source_id: str,
    cards: list[dict],
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Write Markdown, CSV, and Anki TSV flashcard exports.

    Raises:
        FlashcardExportExistsError: Output exists and overwrite is False.
        SourceNotFoundError, CourseNotFoundError.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = source_id.strip().upper()
    title = str(entry.get("title", normalized_id))

    paths = get_flashcard_output_paths(course_path, normalized_id)
    existing = [str(path.resolve()) for path in paths.values() if path.is_file()]
    if existing and not overwrite:
        raise FlashcardExportExistsError(
            "Flashcard export already exists:\n"
            + "\n".join(f"  - {p}" for p in existing)
            + "\nUse --overwrite to replace."
        )

    paths["markdown"].parent.mkdir(parents=True, exist_ok=True)
    paths["markdown"].write_text(
        flashcards_to_markdown(cards, course_path.name, normalized_id, title),
        encoding="utf-8",
    )
    paths["csv"].write_text(flashcards_to_csv(cards), encoding="utf-8")
    paths["anki_tsv"].write_text(flashcards_to_anki_tsv(cards), encoding="utf-8")

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "flashcard_count": len(cards),
        "markdown_path": str(paths["markdown"].resolve()),
        "csv_path": str(paths["csv"].resolve()),
        "anki_tsv_path": str(paths["anki_tsv"].resolve()),
    }


def export_flashcards_from_sections(
    course_name: str,
    source_id: str,
    sections: dict,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """Build flashcards from sections and write all export formats."""
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = source_id.strip().upper()
    title = str(entry.get("title", normalized_id))
    cards = build_flashcards_from_sections(normalized_id, title, sections)
    result = save_flashcard_exports(
        course_name,
        normalized_id,
        cards,
        overwrite=overwrite,
        root=root,
    )
    result["warnings"] = flashcard_quality_warnings(len(cards))
    return result


def flashcard_quality_warnings(flashcard_count: int) -> list[str]:
    """Return quality warnings for flashcard generation."""
    warnings: list[str] = []
    if flashcard_count == 0:
        warnings.append(
            "No flashcards generated. Final audit may be missing "
            "memorization/formula/trap sections."
        )
    elif flashcard_count < 5:
        warnings.append(
            "Few flashcards generated. Review final audit section structure."
        )
    return warnings
