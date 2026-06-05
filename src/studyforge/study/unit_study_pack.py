"""
Unit Study Pack Generator v1 — deterministic outputs from imported unit synthesis (no AI).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import resolve_course_path
from studyforge.study.flashcards import (
    build_flashcards_from_sections,
    flashcards_to_anki_tsv,
    flashcards_to_csv,
    flashcards_to_markdown,
)
from studyforge.study.study_pack import extract_markdown_section
from studyforge.study.study_units import (
    StudyUnitNotFoundError,
    _find_unit,
    _normalize_unit_id,
    get_study_unit_summary,
    load_study_units,
    save_study_units,
)
from studyforge.study.unit_synthesis_import import (
    _SYNTHESIS_FILE_PATTERN,
    get_unit_synthesis_dir,
    get_unit_synthesis_registry_path,
    load_unit_synthesis_registry,
)

_MISSING_SECTION = "Not found in unit synthesis."

_UNIT_SECTION_HEADINGS: dict[str, str] = {
    "unit_overview": "Unit Overview",
    "core_concepts": "Core Concepts",
    "formula_sheet": "Merged Formula / Method Sheet",
    "cross_source_connections": "Cross-Source Connections",
    "conflicts_uncertainties": "Conflicts or Uncertainties",
    "must_memorize": "Must-Memorize List",
    "must_understand": "Must-Understand List",
    "exam_traps": "Exam / Homework Traps",
    "practice_questions": "Practice Questions",
    "active_recall": "Active Recall Questions",
    "weak_points": "Weak Points to Review",
    "final_checklist": "Final Unit Checklist",
}

IMPORTANT_SECTION_KEYS = (
    "core_concepts",
    "formula_sheet",
    "practice_questions",
    "active_recall",
)

_MIN_TOTAL_WORDS_FAILED = 100
_MIN_MISSING_SECTIONS_FAILED = 6
_MIN_MISSING_SECTIONS_NEEDS_REVIEW = 3


class UnitSynthesisNotFoundError(Exception):
    """Raised when no unit synthesis has been imported."""


class UnitStudyPackOutputExistsError(Exception):
    """Raised when unit study pack outputs exist and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _title_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.strip().lower())
    return slug.strip("_")


def _section_word_count(body: str) -> int:
    if not body or body == _MISSING_SECTION:
        return 0
    return len(body.split())


def _is_section_missing(body: str) -> bool:
    return not body.strip() or body.strip() == _MISSING_SECTION


def get_unit_study_pack_output_paths(course_path: Path, unit_id: str) -> dict[str, Path]:
    """Return paths for unit study pack outputs under the unit synthesis directory."""
    normalized = _normalize_unit_id(unit_id)
    base = get_unit_synthesis_dir(course_path, unit_id)
    return {
        "unit_study_guide": base / f"{normalized}_unit_study_guide.md",
        "unit_flashcards": base / f"{normalized}_unit_flashcards.md",
        "unit_flashcards_csv": base / f"{normalized}_unit_flashcards.csv",
        "unit_flashcards_anki_tsv": base / f"{normalized}_unit_flashcards_anki.tsv",
        "unit_practice_quiz": base / f"{normalized}_unit_practice_quiz.md",
        "unit_active_recall": base / f"{normalized}_unit_active_recall.md",
        "unit_formula_sheet": base / f"{normalized}_unit_formula_sheet.md",
        "manifest": base / f"{normalized}_unit_study_pack_manifest.json",
    }


def _find_latest_synthesis_on_disk(synthesis_dir: Path, unit_id: str) -> dict | None:
    normalized = _normalize_unit_id(unit_id)
    candidates: list[tuple[int, Path]] = []
    if not synthesis_dir.is_dir():
        return None
    for path in synthesis_dir.glob("*.md"):
        if "unit_study" in path.name or "unit_flashcards" in path.name:
            continue
        match = _SYNTHESIS_FILE_PATTERN.match(path.name)
        if match and match.group("unit_id").upper() == normalized:
            candidates.append((int(match.group("version")), path))
    if not candidates:
        return None
    _, latest_path = max(candidates, key=lambda item: item[0])
    version = max(v for v, _ in candidates)
    return {
        "version": version,
        "synthesis_id": f"US-{normalized}-V{version:03d}",
        "file_path": str(latest_path.resolve()),
        "date_imported": "",
        "synthesizer_name": "unknown",
        "notes": "",
        "status": "imported",
    }


def get_latest_unit_synthesis(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Load the latest unit synthesis registry entry and Markdown text."""
    course_path = resolve_course_path(course_name, root)
    normalized = _normalize_unit_id(unit_id)
    synthesis_dir = get_unit_synthesis_dir(course_path, normalized)
    registry_path = get_unit_synthesis_registry_path(course_path, normalized)
    registry = load_unit_synthesis_registry(registry_path, normalized)

    syntheses = list(registry.get("syntheses", []))
    entry: dict | None = None

    if syntheses:
        entry = max(syntheses, key=lambda item: int(item.get("version", 0)))
    else:
        entry = _find_latest_synthesis_on_disk(synthesis_dir, normalized)

    if not entry:
        raise UnitSynthesisNotFoundError(
            f"No unit synthesis found for {normalized}. Import a unit synthesis first."
        )

    file_path = Path(str(entry.get("file_path", "")))
    if not file_path.is_file():
        version = int(entry.get("version", 1))
        file_path = synthesis_dir / f"{normalized}_synthesis_v{version:03d}.md"
    if not file_path.is_file():
        raise UnitSynthesisNotFoundError(
            f"Unit synthesis file missing for {normalized}: {file_path}"
        )

    text = file_path.read_text(encoding="utf-8")
    return {
        "entry": entry,
        "text": text,
        "registry_path": str(registry_path.resolve()) if registry_path.is_file() else "",
        "file_path": str(file_path.resolve()),
        "synthesis_id": str(entry.get("synthesis_id", "")),
    }


def extract_unit_synthesis_sections(text: str) -> dict[str, str]:
    """Parse standard unit synthesis sections into a dict."""
    sections: dict[str, str] = {}
    for key, heading in _UNIT_SECTION_HEADINGS.items():
        body = extract_markdown_section(text, heading)
        sections[key] = body if body else _MISSING_SECTION
    return sections


def analyze_unit_study_pack_sections(sections: dict[str, str]) -> dict:
    """Score extracted unit synthesis sections for unit study pack usefulness."""
    found_sections: list[str] = []
    missing_sections: list[str] = []
    section_word_counts: dict[str, int] = {}
    warnings: list[str] = []

    for key in _UNIT_SECTION_HEADINGS:
        body = sections.get(key, _MISSING_SECTION)
        count = _section_word_count(body)
        section_word_counts[key] = count

        if _is_section_missing(body):
            missing_sections.append(key)
            continue

        found_sections.append(key)

    total_extracted_words = sum(section_word_counts.values())
    missing_count = len(missing_sections)
    important_missing = [
        key for key in IMPORTANT_SECTION_KEYS if key in missing_sections
    ]

    for key in important_missing:
        warnings.append(
            f"Missing important section: {key} ({_UNIT_SECTION_HEADINGS[key]})"
        )

    if total_extracted_words < _MIN_TOTAL_WORDS_FAILED:
        warnings.append(
            f"Only {total_extracted_words} words extracted from unit synthesis "
            f"(under {_MIN_TOTAL_WORDS_FAILED})."
        )

    if missing_count >= _MIN_MISSING_SECTIONS_FAILED:
        warnings.append(
            f"{missing_count} of {len(_UNIT_SECTION_HEADINGS)} expected sections are missing."
        )

    quality_status = "ok"
    if (
        total_extracted_words < _MIN_TOTAL_WORDS_FAILED
        or missing_count >= _MIN_MISSING_SECTIONS_FAILED
    ):
        quality_status = "failed"
        warnings.insert(
            0,
            "Unit study pack quality is poor — re-import or fix the unit synthesis.",
        )
    elif (
        missing_count >= _MIN_MISSING_SECTIONS_NEEDS_REVIEW
        or important_missing
    ):
        quality_status = "needs_review"
        warnings.append(
            "Unit study pack generated from limited unit synthesis content."
        )

    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)

    return {
        "found_sections": found_sections,
        "missing_sections": missing_sections,
        "section_word_counts": section_word_counts,
        "total_extracted_words": total_extracted_words,
        "quality_status": quality_status,
        "warnings": deduped,
    }


def _section_block(title: str, body: str) -> str:
    content = body if body and body != _MISSING_SECTION else _MISSING_SECTION
    return f"## {title}\n\n{content}\n"


def build_unit_study_guide(
    course_name: str,
    unit: dict,
    synthesis: dict,
    sections: dict,
) -> str:
    """Build the main unit study guide Markdown."""
    unit_id = unit.get("unit_id", "")
    title = unit.get("title", unit_id)
    synthesis_id = synthesis.get("synthesis_id", synthesis.get("entry", {}).get("synthesis_id", ""))

    lines = [
        "# Unit Study Guide",
        "",
        "Course:",
        course_name,
        "",
        "Unit:",
        f"{unit_id} — {title}",
        "",
        "Based on:",
        synthesis_id,
        "",
        "---",
        "",
        _section_block("Unit Overview", sections["unit_overview"]),
        _section_block("Core Concepts", sections["core_concepts"]),
        _section_block("Merged Formula / Method Sheet", sections["formula_sheet"]),
        _section_block("Cross-Source Connections", sections["cross_source_connections"]),
        _section_block("Conflicts or Uncertainties", sections["conflicts_uncertainties"]),
        _section_block("Must-Memorize List", sections["must_memorize"]),
        _section_block("Must-Understand List", sections["must_understand"]),
        _section_block("Exam / Homework Traps", sections["exam_traps"]),
        _section_block("Final Unit Checklist", sections["final_checklist"]),
    ]
    return "\n".join(lines) + "\n"


def build_unit_practice_quiz(
    course_name: str, unit: dict, sections: dict
) -> str:
    unit_id = unit.get("unit_id", "")
    title = unit.get("title", unit_id)
    body = sections.get("practice_questions", _MISSING_SECTION)
    return (
        f"# Unit Practice Quiz\n\n"
        f"Course:\n{course_name}\n\n"
        f"Unit:\n{unit_id} — {title}\n\n"
        f"Instructions:\n"
        f"Answer these without looking at the unit study guide first. "
        f"Then check against the unit synthesis or unit study guide.\n\n"
        f"---\n\n"
        f"{body}\n"
    )


def build_unit_active_recall(
    course_name: str, unit: dict, sections: dict
) -> str:
    unit_id = unit.get("unit_id", "")
    title = unit.get("title", unit_id)
    body = sections.get("active_recall", _MISSING_SECTION)
    return (
        f"# Unit Active Recall\n\n"
        f"Course:\n{course_name}\n\n"
        f"Unit:\n{unit_id} — {title}\n\n"
        f"Instructions:\n"
        f"Ask one question at a time. Mark each answer correct, partial, or wrong.\n\n"
        f"---\n\n"
        f"{body}\n"
    )


def build_unit_formula_sheet(
    course_name: str, unit: dict, sections: dict
) -> str:
    unit_id = unit.get("unit_id", "")
    title = unit.get("title", unit_id)
    primary = sections.get("formula_sheet", _MISSING_SECTION)
    return (
        f"# Unit Formula Sheet\n\n"
        f"Course:\n{course_name}\n\n"
        f"Unit:\n{unit_id} — {title}\n\n"
        f"---\n\n"
        f"## Merged Formula / Method Sheet\n\n"
        f"{primary}\n"
    )


def build_unit_flashcards(
    course_name: str,
    unit: dict,
    sections: dict,
) -> tuple[list[dict], str]:
    """Build unit flashcards and Markdown export text."""
    unit_id = str(unit.get("unit_id", ""))
    title = str(unit.get("title", unit_id))
    slug = _title_slug(title)

    flash_sections = {
        "must_memorize": sections.get("must_memorize", _MISSING_SECTION),
        "formula_sheet": sections.get("formula_sheet", _MISSING_SECTION),
        "exam_traps": sections.get("exam_traps", _MISSING_SECTION),
        "must_understand": sections.get("must_understand", _MISSING_SECTION),
        "active_recall": sections.get("active_recall", _MISSING_SECTION),
    }

    cards = build_flashcards_from_sections(unit_id, title, flash_sections)
    for card in cards:
        tags = list(card.get("tags", []))
        if unit_id.upper() not in {t.upper() for t in tags}:
            tags.insert(0, unit_id.upper())
        if slug and slug not in tags:
            tags.append(slug)
        card["tags"] = tags
        card["source_id"] = unit_id.upper()

    markdown = flashcards_to_markdown(cards, course_name, unit_id, title)
    return cards, markdown


def load_unit_study_pack_quality(manifest_path: str | Path) -> str:
    """Return quality_status from a unit study pack manifest, or empty string."""
    path = Path(manifest_path)
    if not path.is_file():
        return ""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    quality = manifest.get("quality") or {}
    return str(quality.get("quality_status", ""))


def unit_has_study_pack(unit: dict) -> bool:
    """Return True when the unit has a generated study pack manifest on disk."""
    manifest_path = str(unit.get("latest_unit_study_pack_manifest_path", "")).strip()
    return bool(manifest_path and Path(manifest_path).is_file())


def diagnose_unit_study_pack(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Load latest synthesis, extract sections, return quality analysis only."""
    course_path = resolve_course_path(course_name, root)
    get_study_unit_summary(course_name, unit_id, root)
    synthesis = get_latest_unit_synthesis(course_name, unit_id, root)
    sections = extract_unit_synthesis_sections(synthesis["text"])
    quality = analyze_unit_study_pack_sections(sections)

    return {
        "course": course_path.name,
        "unit_id": _normalize_unit_id(unit_id),
        "based_on_unit_synthesis_id": synthesis.get("synthesis_id", ""),
        "synthesis_path": synthesis.get("file_path", ""),
        "quality": quality,
        "warnings": list(quality.get("warnings", [])),
    }


def _update_study_unit_pack_fields(
    course_name: str,
    unit_id: str,
    *,
    manifest_path: str,
    study_guide_path: str,
    flashcards_path: str,
    active_recall_path: str,
    root: Path | None,
) -> None:
    data = load_study_units(course_name, root)
    unit = _find_unit(data.get("units", []), unit_id)
    unit["latest_unit_study_pack_manifest_path"] = manifest_path
    unit["latest_unit_study_guide_path"] = study_guide_path
    unit["latest_unit_flashcards_path"] = flashcards_path
    unit["latest_unit_active_recall_path"] = active_recall_path
    unit["date_unit_study_pack_generated"] = _now_iso()
    unit["date_updated"] = _now_iso()
    save_study_units(course_name, data, root)


def generate_unit_study_pack(
    course_name: str,
    unit_id: str,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Generate unit study pack files from the latest imported unit synthesis.

    Never modifies source-level study packs or unit synthesis files.
    """
    course_path = resolve_course_path(course_name, root)
    summary = get_study_unit_summary(course_name, unit_id, root)
    normalized = _normalize_unit_id(unit_id)
    unit = {
        "unit_id": summary.get("unit_id", normalized),
        "title": summary.get("title", normalized),
        "description": summary.get("description", ""),
    }

    synthesis = get_latest_unit_synthesis(course_name, unit_id, root)
    synthesis_id = str(
        synthesis.get("synthesis_id")
        or synthesis.get("entry", {}).get("synthesis_id", "")
    )
    sections = extract_unit_synthesis_sections(synthesis["text"])
    quality = analyze_unit_study_pack_sections(sections)
    warnings: list[str] = list(quality.get("warnings", []))

    paths = get_unit_study_pack_output_paths(course_path, normalized)
    output_files = [paths[key] for key in paths if key != "manifest"]
    existing = [str(path.resolve()) for path in output_files if path.is_file()]
    if paths["manifest"].is_file():
        existing.append(str(paths["manifest"].resolve()))

    if existing and not overwrite:
        raise UnitStudyPackOutputExistsError(
            "Unit study pack output already exists:\n"
            + "\n".join(f"  - {p}" for p in existing)
            + "\nUse --overwrite to replace."
        )

    paths["unit_study_guide"].parent.mkdir(parents=True, exist_ok=True)

    guide_text = build_unit_study_guide(
        course_path.name, unit, synthesis, sections
    )
    paths["unit_study_guide"].write_text(guide_text, encoding="utf-8")

    cards, flash_md = build_unit_flashcards(course_path.name, unit, sections)
    paths["unit_flashcards"].write_text(flash_md, encoding="utf-8")
    paths["unit_flashcards_csv"].write_text(flashcards_to_csv(cards), encoding="utf-8")
    paths["unit_flashcards_anki_tsv"].write_text(
        flashcards_to_anki_tsv(cards), encoding="utf-8"
    )

    paths["unit_practice_quiz"].write_text(
        build_unit_practice_quiz(course_path.name, unit, sections),
        encoding="utf-8",
    )
    paths["unit_active_recall"].write_text(
        build_unit_active_recall(course_path.name, unit, sections),
        encoding="utf-8",
    )
    paths["unit_formula_sheet"].write_text(
        build_unit_formula_sheet(course_path.name, unit, sections),
        encoding="utf-8",
    )

    generated_at = _now_iso()
    outputs = {
        "unit_study_guide": str(paths["unit_study_guide"].resolve()),
        "unit_flashcards": str(paths["unit_flashcards"].resolve()),
        "unit_flashcards_csv": str(paths["unit_flashcards_csv"].resolve()),
        "unit_flashcards_anki_tsv": str(paths["unit_flashcards_anki_tsv"].resolve()),
        "unit_practice_quiz": str(paths["unit_practice_quiz"].resolve()),
        "unit_active_recall": str(paths["unit_active_recall"].resolve()),
        "unit_formula_sheet": str(paths["unit_formula_sheet"].resolve()),
    }

    manifest = {
        "course": course_path.name,
        "unit_id": normalized,
        "title": unit.get("title", ""),
        "based_on_unit_synthesis_id": synthesis_id,
        "date_generated": generated_at,
        "quality": quality,
        "flashcard_count": len(cards),
        "outputs": outputs,
    }
    with paths["manifest"].open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    _update_study_unit_pack_fields(
        course_name,
        normalized,
        manifest_path=str(paths["manifest"].resolve()),
        study_guide_path=outputs["unit_study_guide"],
        flashcards_path=outputs["unit_flashcards"],
        active_recall_path=outputs["unit_active_recall"],
        root=root,
    )

    return {
        "course": course_path.name,
        "unit_id": normalized,
        "title": unit.get("title", ""),
        "based_on_unit_synthesis_id": synthesis_id,
        "quality_status": quality.get("quality_status", ""),
        "quality": quality,
        "flashcard_count": len(cards),
        "manifest_path": str(paths["manifest"].resolve()),
        "outputs": outputs,
        "warnings": warnings,
    }
