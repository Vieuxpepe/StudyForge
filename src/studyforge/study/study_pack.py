"""
Deterministic study pack generation from the latest imported final audit.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.audits.final_import import (
    get_final_audit_dir,
    get_final_audit_registry_path,
    load_final_audit_registry,
)
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import (
    load_source_registry,
    resolve_course_path,
    save_source_registry,
)
from studyforge.study.flashcards import (
    build_flashcards_from_sections,
    flashcard_quality_warnings,
    flashcards_to_anki_tsv,
    flashcards_to_csv,
    flashcards_to_markdown,
    get_flashcard_output_paths,
)

STUDY_OUTPUTS_BASE = Path("06_Study_Outputs")

_FINAL_AUDIT_FILE_SUFFIX = "_final_audit_v"
_REGISTRY_SUFFIX = "_final_audit_registry.json"

_SECTION_HEADINGS = {
    "final_verdict": "Final Verdict",
    "corrections": "Corrections That Matter Most",
    "missing_concepts": "Missing Concepts",
    "better_explanations": "Better Explanations",
    "must_memorize": "Must-Memorize List",
    "must_understand": "Must-Understand List",
    "formula_sheet": "Formula / Method Sheet",
    "exam_traps": "Exam / Homework Traps",
    "practice_questions": "Practice Questions",
    "active_recall": "Active Recall Questions",
    "final_checklist": "Final Study Checklist",
    "remaining_uncertainties": "Remaining Uncertainties",
}

_MISSING_SECTION = "Not found in final audit."

IMPORTANT_SECTION_KEYS = (
    "must_memorize",
    "must_understand",
    "formula_sheet",
    "practice_questions",
    "active_recall",
)

_MIN_PLACEHOLDER_WORDS = 10
_MIN_TOTAL_WORDS_FAILED = 100
_MIN_MISSING_SECTIONS_FAILED = 6
_MIN_MISSING_SECTIONS_NEEDS_REVIEW = 3
_MIN_TEMPLATE_HEADINGS = 3

NORMALIZER_SUGGESTION = (
    "Final audit headings may not match StudyForge's expected template. "
    "Try `python scripts/normalize_final_audit.py --course <course> --source-id <id>` "
    "or use the GUI Final Audit Normalizer."
)


class FinalAuditNotFoundError(Exception):
    """Raised when no final audit exists for the source."""


class StudyPackOutputExistsError(Exception):
    """Raised when study pack outputs exist and overwrite was not requested."""


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _heading_level(line: str) -> int | None:
    match = re.match(r"^(#+)\s+", line.strip())
    if match:
        return len(match.group(1))
    return None


def _heading_title(line: str) -> str:
    return re.sub(r"^#+\s+", "", line.strip()).strip()


def extract_markdown_section(text: str, heading: str) -> str:
    """
    Extract body text under a Markdown heading until the next heading of the
    same or higher level (fewer or equal ``#`` count).
    """
    if not text.strip() or not heading.strip():
        return ""

    lines = text.splitlines()
    target = heading.strip().lower()
    start_index: int | None = None
    section_level: int | None = None

    for index, line in enumerate(lines):
        level = _heading_level(line)
        if level is None:
            continue
        title = _heading_title(line).lower()
        if title == target or title.startswith(target):
            start_index = index + 1
            section_level = level
            break

    if start_index is None or section_level is None:
        return ""

    collected: list[str] = []
    for line in lines[start_index:]:
        level = _heading_level(line)
        if level is not None and level <= section_level:
            break
        collected.append(line)

    return "\n".join(collected).strip()


def extract_sections(text: str) -> dict[str, str]:
    """Parse standard final audit sections into a dict."""
    sections: dict[str, str] = {}
    for key, heading in _SECTION_HEADINGS.items():
        body = extract_markdown_section(text, heading)
        sections[key] = body if body else _MISSING_SECTION
    return sections


def _section_word_count(body: str) -> int:
    if not body or body == _MISSING_SECTION:
        return 0
    return len(body.split())


def _is_section_missing(body: str) -> bool:
    return not body.strip() or body.strip() == _MISSING_SECTION


def analyze_study_pack_sections(sections: dict[str, str]) -> dict:
    """
    Score extracted final-audit sections for study pack usefulness.

    Returns found/missing/placeholder lists, word counts, quality_status, warnings.
    """
    found_sections: list[str] = []
    missing_sections: list[str] = []
    placeholder_sections: list[str] = []
    section_word_counts: dict[str, int] = {}
    warnings: list[str] = []

    for key in _SECTION_HEADINGS:
        body = sections.get(key, _MISSING_SECTION)
        count = _section_word_count(body)
        section_word_counts[key] = count

        if _is_section_missing(body):
            missing_sections.append(key)
            continue

        found_sections.append(key)
        if count < _MIN_PLACEHOLDER_WORDS:
            placeholder_sections.append(key)
            warnings.append(
                f"Section '{_SECTION_HEADINGS[key]}' has only {count} words "
                f"(may be too thin for study use)."
            )

    total_extracted_words = sum(section_word_counts.values())
    missing_count = len(missing_sections)
    important_missing = [
        key for key in IMPORTANT_SECTION_KEYS if key in missing_sections
    ]

    for key in important_missing:
        warnings.append(
            f"Missing important section: {key} ({_SECTION_HEADINGS[key]})"
        )

    if total_extracted_words < _MIN_TOTAL_WORDS_FAILED:
        warnings.append(
            f"Only {total_extracted_words} words extracted from the final audit "
            f"(under {_MIN_TOTAL_WORDS_FAILED})."
        )

    if missing_count >= _MIN_MISSING_SECTIONS_FAILED:
        warnings.append(
            f"{missing_count} of {len(_SECTION_HEADINGS)} expected sections are missing."
        )

    quality_status = "ok"
    if (
        total_extracted_words < _MIN_TOTAL_WORDS_FAILED
        or missing_count >= _MIN_MISSING_SECTIONS_FAILED
    ):
        quality_status = "failed"
        warnings.insert(
            0,
            "Study pack quality is poor — re-export or fix the final audit template.",
        )
    elif (
        missing_count >= _MIN_MISSING_SECTIONS_NEEDS_REVIEW
        or important_missing
    ):
        quality_status = "needs_review"
        warnings.append(
            "Study pack generated from limited final audit content."
        )

    if quality_status in {"needs_review", "failed"}:
        if NORMALIZER_SUGGESTION not in warnings:
            warnings.append(NORMALIZER_SUGGESTION)

    deduped_final: list[str] = []
    for warning in warnings:
        if warning not in deduped_final:
            deduped_final.append(warning)

    return {
        "found_sections": found_sections,
        "missing_sections": missing_sections,
        "placeholder_sections": placeholder_sections,
        "section_word_counts": section_word_counts,
        "total_extracted_words": total_extracted_words,
        "quality_status": quality_status,
        "warnings": deduped_final,
    }


def count_final_audit_headings_in_text(text: str) -> int:
    """Count how many expected final-audit section headings were found."""
    sections = extract_sections(text)
    return sum(1 for body in sections.values() if not _is_section_missing(body))


def get_final_audit_template_warning(text: str) -> str | None:
    """
    Warn if imported final audit may not match the expected template.

    Returns None if enough headings were detected.
    """
    count = count_final_audit_headings_in_text(text)
    if count < _MIN_TEMPLATE_HEADINGS:
        return (
            "Final audit may not follow expected template. "
            f"Only {count} of {len(_SECTION_HEADINGS)} expected headings were found. "
            "Study pack generation may be weak."
        )
    return None


def diagnose_study_pack(
    course_name: str,
    source_id: str,
    root: Path | None = None,
) -> dict:
    """
    Load latest final audit, extract sections, and return quality analysis only.

    Does not write study pack files or update the registry.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    final_audit = get_latest_final_audit(course_path, normalized_id)
    audit_entry = final_audit["entry"]
    audit_id = str(audit_entry.get("audit_id", "unknown"))
    sections = extract_sections(final_audit["text"])
    quality = analyze_study_pack_sections(sections)
    template_warning = get_final_audit_template_warning(final_audit["text"])

    warnings = list(quality.get("warnings", []))
    if template_warning and template_warning not in warnings:
        warnings.insert(0, template_warning)

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "based_on_final_audit_id": audit_id,
        "final_audit_path": final_audit["file_path"],
        "quality": quality,
        "warnings": warnings,
    }


def _find_latest_audit_on_disk(audit_dir: Path, source_id: str) -> dict | None:
    normalized = _normalize_source_id(source_id)
    prefix = f"{normalized}{_FINAL_AUDIT_FILE_SUFFIX}"
    candidates = sorted(
        [
            path
            for path in audit_dir.glob("*.md")
            if path.name.startswith(prefix) and "packet" not in path.name.lower()
        ],
        key=lambda path: path.name,
    )
    if not candidates:
        return None
    latest_path = candidates[-1]
    match = re.search(r"v(\d{3})\.md$", latest_path.name, re.IGNORECASE)
    version = int(match.group(1)) if match else 1
    return {
        "version": version,
        "audit_id": f"FA-{normalized}-V{version:03d}",
        "auditor_name": "unknown",
        "file_path": str(latest_path.resolve()),
        "date_imported": "",
        "notes": "",
        "status": "imported",
    }


def get_latest_final_audit(course_path: Path, source_id: str) -> dict:
    """
    Load the latest final audit registry entry and Markdown text.

    Raises:
        FinalAuditNotFoundError: No audit file available.
    """
    normalized = _normalize_source_id(source_id)
    audit_dir = get_final_audit_dir(course_path, normalized)
    registry_path = get_final_audit_registry_path(course_path, normalized)
    registry = load_final_audit_registry(registry_path, normalized)

    audits = list(registry.get("audits", []))
    entry: dict | None = None

    if audits:
        entry = max(audits, key=lambda item: int(item.get("version", 0)))
    else:
        entry = _find_latest_audit_on_disk(audit_dir, normalized)

    if not entry:
        raise FinalAuditNotFoundError(
            f"No final audit found for {normalized}. Import a final audit first."
        )

    file_path = Path(entry.get("file_path", ""))
    if not file_path.is_file():
        version = int(entry.get("version", 1))
        file_path = audit_dir / f"{normalized}_final_audit_v{version:03d}.md"
    if not file_path.is_file():
        raise FinalAuditNotFoundError(
            f"Final audit file missing for {normalized}: {file_path}"
        )

    text = file_path.read_text(encoding="utf-8")
    return {
        "entry": entry,
        "text": text,
        "registry_path": str(registry_path.resolve()) if registry_path.is_file() else "",
        "file_path": str(file_path.resolve()),
    }


def _section_block(title: str, body: str) -> str:
    content = body if body and body != _MISSING_SECTION else _MISSING_SECTION
    return f"## {title}\n\n{content}\n"


def build_final_study_guide(
    course_name: str, source: dict, sections: dict, audit_id: str
) -> str:
    """Build the main final study guide Markdown."""
    source_id = source.get("id", "")
    title = source.get("title", source_id)
    big_picture_parts = []
    if sections.get("final_verdict") != _MISSING_SECTION:
        big_picture_parts.append(sections["final_verdict"])
    if sections.get("better_explanations") != _MISSING_SECTION:
        big_picture_parts.append(sections["better_explanations"])
    big_picture = (
        "\n\n".join(big_picture_parts)
        if big_picture_parts
        else _MISSING_SECTION
    )

    lines = [
        "# Final Study Guide",
        "",
        "Course:",
        course_name,
        "",
        "Source:",
        f"{source_id} - {title}",
        "",
        "Based on final audit:",
        audit_id,
        "",
        "---",
        "",
        _section_block("Big Picture", big_picture),
        _section_block("Corrections That Matter Most", sections["corrections"]),
        _section_block("Missing Concepts", sections["missing_concepts"]),
        _section_block("Better Explanations", sections["better_explanations"]),
        _section_block("Must-Memorize List", sections["must_memorize"]),
        _section_block("Must-Understand List", sections["must_understand"]),
        _section_block("Formula / Method Sheet", sections["formula_sheet"]),
        _section_block("Exam / Homework Traps", sections["exam_traps"]),
        _section_block("Final Study Checklist", sections["final_checklist"]),
        _section_block("Remaining Uncertainties", sections["remaining_uncertainties"]),
    ]
    return "\n".join(lines) + "\n"


def _bullet_lines(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("-", "*")):
            item = re.sub(r"^[\*\-]\s+", "", stripped).strip()
            if item:
                items.append(item)
        elif re.match(r"^\d+[\.\)]\s+", stripped):
            item = re.sub(r"^\d+[\.\)]\s+", "", stripped).strip()
            if item:
                items.append(item)
    return items


def build_flashcards(course_name: str, source: dict, sections: dict) -> str:
    """Build Markdown flashcards from memorization-related sections."""
    source_id = str(source.get("id", ""))
    title = str(source.get("title", source_id))
    cards = build_flashcards_from_sections(source_id, title, sections)
    return flashcards_to_markdown(cards, course_name, source_id, title)


def write_flashcard_exports(
    course_name: str,
    source: dict,
    sections: dict,
    course_path: Path,
) -> tuple[dict[str, str], int]:
    """Write Markdown, CSV, and Anki TSV flashcard files; return paths and count."""
    source_id = str(source.get("id", ""))
    title = str(source.get("title", source_id))
    cards = build_flashcards_from_sections(source_id, title, sections)
    paths = get_flashcard_output_paths(course_path, source_id)
    paths["markdown"].parent.mkdir(parents=True, exist_ok=True)
    paths["markdown"].write_text(
        flashcards_to_markdown(cards, course_name, source_id, title),
        encoding="utf-8",
    )
    paths["csv"].write_text(flashcards_to_csv(cards), encoding="utf-8")
    paths["anki_tsv"].write_text(flashcards_to_anki_tsv(cards), encoding="utf-8")
    written = {
        "flashcards": str(paths["markdown"].resolve()),
        "flashcards_csv": str(paths["csv"].resolve()),
        "flashcards_anki_tsv": str(paths["anki_tsv"].resolve()),
    }
    return written, len(cards)


def build_practice_quiz(course_name: str, source: dict, sections: dict) -> str:
    source_id = source.get("id", "")
    title = source.get("title", source_id)
    body = sections.get("practice_questions", _MISSING_SECTION)
    return (
        f"# Practice Quiz\n\n"
        f"Course:\n{course_name}\n\n"
        f"Source:\n{source_id} - {title}\n\n"
        f"Instructions:\n"
        f"Answer these without looking at the study guide first. "
        f"Then check against the final audit or final study guide.\n\n"
        f"---\n\n"
        f"{body}\n"
    )


def build_active_recall(course_name: str, source: dict, sections: dict) -> str:
    source_id = source.get("id", "")
    title = source.get("title", source_id)
    body = sections.get("active_recall", _MISSING_SECTION)
    return (
        f"# Active Recall\n\n"
        f"Course:\n{course_name}\n\n"
        f"Source:\n{source_id} - {title}\n\n"
        f"Instructions:\n"
        f"Ask one question at a time. Mark each answer correct, partial, or wrong.\n\n"
        f"---\n\n"
        f"{body}\n"
    )


def build_formula_sheet(course_name: str, source: dict, sections: dict) -> str:
    source_id = source.get("id", "")
    title = source.get("title", source_id)
    primary = sections.get("formula_sheet", _MISSING_SECTION)
    extra_parts: list[str] = []
    if sections.get("must_memorize") != _MISSING_SECTION:
        extra_parts.append(
            "## From Must-Memorize List\n\n" + sections["must_memorize"]
        )
    if sections.get("corrections") != _MISSING_SECTION:
        extra_parts.append(
            "## From Corrections That Matter Most\n\n" + sections["corrections"]
        )

    lines = [
        "# Formula Sheet",
        "",
        "Course:",
        course_name,
        "",
        "Source:",
        f"{source_id} - {title}",
        "",
        "---",
        "",
        "## Formula / Method Sheet",
        "",
        primary,
        "",
    ]
    if primary == _MISSING_SECTION and extra_parts:
        lines.append("## Additional formulas and rules\n")
        lines.extend(extra_parts)
        lines.append("")
    elif extra_parts and primary != _MISSING_SECTION:
        lines.append("## Additional reference\n")
        lines.extend(extra_parts)
        lines.append("")

    return "\n".join(lines) + "\n"


def build_weak_points_seed(course_name: str, source: dict, sections: dict) -> str:
    source_id = source.get("id", "")
    title = source.get("title", source_id)
    lines = [
        "# Weak Points Seed",
        "",
        "Course:",
        course_name,
        "",
        "Source:",
        f"{source_id} - {title}",
        "",
        "Use this file to track concepts you want to strengthen.",
        "",
    ]

    entry_index = 1
    for section_key, section_label in (
        ("missing_concepts", "Missing Concepts"),
        ("corrections", "Corrections That Matter Most"),
        ("remaining_uncertainties", "Remaining Uncertainties"),
        ("exam_traps", "Exam / Homework Traps"),
    ):
        bullets = _bullet_lines(sections.get(section_key, ""))
        if not bullets and sections.get(section_key, "") == _MISSING_SECTION:
            continue
        if not bullets:
            lines.extend(
                [
                    f"## Entry {entry_index}",
                    "",
                    "## Concept",
                    section_label,
                    "",
                    "Chapter/source:",
                    f"{source_id} - {title}",
                    "",
                    "Confidence level:",
                    "1-5:",
                    "",
                    "Why it may be hard:",
                    sections.get(section_key, ""),
                    "",
                    "What to review:",
                    "(fill in)",
                    "",
                    "Practice needed:",
                    "(fill in)",
                    "",
                    "Status:",
                    "New",
                    "",
                ]
            )
            entry_index += 1
            continue

        for bullet in bullets:
            lines.extend(
                [
                    f"## Entry {entry_index}",
                    "",
                    "## Concept",
                    bullet,
                    "",
                    "Chapter/source:",
                    f"{source_id} - {title}",
                    "",
                    "Confidence level:",
                    "1-5:",
                    "",
                    "Why it may be hard:",
                    f"From {section_label}: {bullet}",
                    "",
                    "What to review:",
                    section_label,
                    "",
                    "Practice needed:",
                    "(fill in)",
                    "",
                    "Status:",
                    "New",
                    "",
                ]
            )
            entry_index += 1

    if entry_index == 1:
        lines.append("No weak-point seeds could be parsed from the final audit.\n")

    return "\n".join(lines) + "\n"


def _study_output_paths(course_path: Path, source_id: str) -> dict[str, Path]:
    normalized = _normalize_source_id(source_id)
    base = course_path / STUDY_OUTPUTS_BASE
    flashcard_paths = get_flashcard_output_paths(course_path, normalized)
    return {
        "study_guides": base / "study_guides" / f"{normalized}_final_study_guide.md",
        "flashcards": flashcard_paths["markdown"],
        "flashcards_csv": flashcard_paths["csv"],
        "flashcards_anki_tsv": flashcard_paths["anki_tsv"],
        "formula_sheets": base / "formula_sheets" / f"{normalized}_formula_sheet.md",
        "quizzes": base / "quizzes" / f"{normalized}_practice_quiz.md",
        "active_recall": base / "active_recall" / f"{normalized}_active_recall.md",
        "weak_points": base / "weak_points" / f"{normalized}_weak_points_seed.md",
        "manifest": base / f"{normalized}_study_pack_manifest.json",
    }


def _update_registry_entry(registry: dict, source_id: str, updates: dict) -> None:
    normalized = _normalize_source_id(source_id)
    for entry in registry.get("sources", []):
        if str(entry.get("id", "")).upper() == normalized:
            entry.update(updates)
            return
    raise SourceNotFoundError(f"Source not found in registry: {source_id}")


def generate_study_pack(
    course_name: str,
    source_id: str,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Generate study pack files from the latest final audit (no AI).

    Raises:
        FinalAuditNotFoundError, StudyPackOutputExistsError,
        SourceNotFoundError, CourseNotFoundError.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    final_audit = get_latest_final_audit(course_path, normalized_id)
    audit_entry = final_audit["entry"]
    audit_id = str(audit_entry.get("audit_id", "unknown"))
    sections = extract_sections(final_audit["text"])

    paths = _study_output_paths(course_path, normalized_id)
    output_files = {
        key: path
        for key, path in paths.items()
        if key not in {"manifest", "flashcards", "flashcards_csv", "flashcards_anki_tsv"}
    }

    existing = [str(path.resolve()) for path in output_files.values() if path.is_file()]
    flashcard_paths = [
        paths["flashcards"],
        paths["flashcards_csv"],
        paths["flashcards_anki_tsv"],
    ]
    existing.extend(
        str(path.resolve()) for path in flashcard_paths if path.is_file()
    )
    if existing and not overwrite:
        raise StudyPackOutputExistsError(
            "Study pack output already exists:\n"
            + "\n".join(f"  - {p}" for p in existing)
            + "\nUse --overwrite to replace."
        )

    quality = analyze_study_pack_sections(sections)
    warnings: list[str] = list(quality.get("warnings", []))
    for key in quality.get("missing_sections", []):
        label = _SECTION_HEADINGS.get(key, key)
        line = f"Section missing in final audit: {label}"
        if line not in warnings:
            warnings.append(line)

    for directory in {
        paths["study_guides"].parent,
        paths["flashcards"].parent,
        paths["formula_sheets"].parent,
        paths["quizzes"].parent,
        paths["active_recall"].parent,
        paths["weak_points"].parent,
        paths["manifest"].parent,
    }:
        directory.mkdir(parents=True, exist_ok=True)

    builders = {
        "study_guides": lambda: build_final_study_guide(
            course_path.name, entry, sections, audit_id
        ),
        "formula_sheets": lambda: build_formula_sheet(course_path.name, entry, sections),
        "quizzes": lambda: build_practice_quiz(course_path.name, entry, sections),
        "active_recall": lambda: build_active_recall(course_path.name, entry, sections),
        "weak_points": lambda: build_weak_points_seed(course_path.name, entry, sections),
    }

    written: dict[str, str] = {}
    for key, path in output_files.items():
        content = builders[key]()
        path.write_text(content, encoding="utf-8")
        written[key] = str(path.resolve())

    flashcard_written, flashcard_count = write_flashcard_exports(
        course_path.name, entry, sections, course_path
    )
    written.update(flashcard_written)

    for warning in flashcard_quality_warnings(flashcard_count):
        if warning not in warnings:
            warnings.append(warning)

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    manifest = {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "based_on_final_audit_id": audit_id,
        "date_generated": generated_at,
        "outputs": {
            "final_study_guide": written["study_guides"],
            "flashcards": written["flashcards"],
            "flashcards_csv": written["flashcards_csv"],
            "flashcards_anki_tsv": written["flashcards_anki_tsv"],
            "formula_sheet": written["formula_sheets"],
            "practice_quiz": written["quizzes"],
            "active_recall": written["active_recall"],
            "weak_points_seed": written["weak_points"],
        },
        "flashcard_count": flashcard_count,
        "warnings": warnings,
        "quality": quality,
    }

    with paths["manifest"].open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    registry = load_source_registry(course_path)
    _update_registry_entry(
        registry,
        normalized_id,
        {
            "status": "study_pack_generated",
            "study_pack_manifest_path": str(paths["manifest"].resolve()),
            "final_study_guide_path": written["study_guides"],
            "flashcards_path": written["flashcards"],
            "flashcards_csv_path": written["flashcards_csv"],
            "flashcards_anki_tsv_path": written["flashcards_anki_tsv"],
            "formula_sheet_path": written["formula_sheets"],
            "practice_quiz_path": written["quizzes"],
            "active_recall_path": written["active_recall"],
            "weak_points_seed_path": written["weak_points"],
            "date_study_pack_generated": generated_at,
        },
    )
    save_source_registry(course_path, registry)

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "based_on_final_audit_id": audit_id,
        "manifest_path": str(paths["manifest"].resolve()),
        "outputs": manifest["outputs"],
        "warnings": warnings,
        "flashcard_count": flashcard_count,
        "quality": quality,
        "quality_status": quality["quality_status"],
        "status": "study_pack_generated",
    }
