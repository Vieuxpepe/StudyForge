"""
Unit Synthesis Packet v1 — export multi-source study material for manual AI synthesis (no API).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import list_sources, resolve_course_path
from studyforge.study.flashcard_review import collect_due_flashcards
from studyforge.study.flashcards import get_flashcard_output_paths
from studyforge.study.review_planner import (
    collect_active_recall_needs_review,
    collect_open_mistakes,
    collect_open_weak_points,
)
from studyforge.study.review_schedule import today_date_str
from studyforge.study.study_unit_dashboard import (
    _filter_by_source_ids,
    get_unit_reports_dir,
    get_unit_source_ids,
)
from studyforge.study.study_units import (
    StudyUnitNotFoundError,
    _normalize_source_id,
    get_study_unit_summary,
    load_study_units,
)

STUDY_OUTPUTS_BASE = Path("06_Study_Outputs")


class UnitSynthesisPacketExistsError(Exception):
    """Raised when synthesis packet files exist and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_unit_id(unit_id: str) -> str:
    return unit_id.strip().upper()


def _read_text_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _load_manifest_quality(manifest_path: Path) -> str:
    if not manifest_path.is_file():
        return "missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "needs_review"
    quality = manifest.get("quality") or {}
    status = str(quality.get("quality_status", "")).lower()
    if status in {"ok", "needs_review", "failed"}:
        return status
    return "ok"


def _resolve_source_paths(course_path: Path, entry: dict, source_id: str) -> dict[str, Path | None]:
    """Return study output paths (registry override, then defaults)."""
    normalized = _normalize_source_id(source_id)
    base = course_path / STUDY_OUTPUTS_BASE
    flashcard_paths = get_flashcard_output_paths(course_path, normalized)

    def _path_from_registry(key: str, default: Path) -> Path | None:
        registry_path = str(entry.get(key, "")).strip()
        if registry_path:
            candidate = Path(registry_path)
            if candidate.is_file():
                return candidate
        return default if default.is_file() else None

    guide_default = base / "study_guides" / f"{normalized}_final_study_guide.md"
    formula_default = base / "formula_sheets" / f"{normalized}_formula_sheet.md"
    quiz_default = base / "quizzes" / f"{normalized}_practice_quiz.md"
    recall_default = base / "active_recall" / f"{normalized}_active_recall.md"
    manifest_default = base / f"{normalized}_study_pack_manifest.json"
    audit_default = Path(str(entry.get("latest_final_audit_path", "")).strip())

    return {
        "final_study_guide": _path_from_registry("final_study_guide_path", guide_default),
        "formula_sheet": _path_from_registry("formula_sheet_path", formula_default),
        "practice_quiz": _path_from_registry("practice_quiz_path", quiz_default),
        "active_recall": _path_from_registry("active_recall_path", recall_default),
        "flashcards_md": flashcard_paths["markdown"]
        if flashcard_paths["markdown"].is_file()
        else None,
        "flashcards_csv": flashcard_paths["csv"]
        if flashcard_paths["csv"].is_file()
        else None,
        "manifest": _path_from_registry("study_pack_manifest_path", manifest_default),
        "final_audit": audit_default if audit_default.is_file() else None,
    }


def _flashcards_summary(paths: dict[str, Path | None]) -> tuple[str, list[str]]:
    """Return flashcard text and warnings."""
    warnings: list[str] = []
    md_path = paths.get("flashcards_md")
    if md_path is not None:
        return _read_text_file(md_path), warnings

    csv_path = paths.get("flashcards_csv")
    if csv_path is None:
        return "", warnings

    lines = ["# Flashcards (CSV summary)", ""]
    try:
        with csv_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                front = str(row.get("front", "")).strip()
                back = str(row.get("back", "")).strip()
                card_id = str(row.get("card_id", "")).strip() or f"card-{index}"
                lines.append(f"- **{card_id}** — {front}")
                if back:
                    lines.append(f"  - Back: {back}")
    except OSError as exc:
        warnings.append(f"Could not read flashcards CSV: {exc}")
        return "", warnings

    if len(lines) <= 2:
        warnings.append("Flashcards CSV has no rows.")
        return "", warnings

    return "\n".join(lines) + "\n", warnings


def build_unit_synthesis_instructions() -> str:
    """Return manual synthesis instructions for pasting into an external AI."""
    return """You are the unit synthesis tutor for StudyForge.

I will provide:
1. A study unit description
2. Source-level final study guides
3. Source-level formula sheets
4. Practice questions / active recall questions
5. Mistakes and weak points related to this unit

Your job:
- Create a unified study guide for the unit.
- Merge overlapping concepts.
- Preserve source IDs.
- Do not invent facts.
- Mark unsupported or uncertain claims.
- Keep formulas precise.
- Identify what matters most for quizzes/exams.
- Create active recall questions and practice questions.
- Create a final unit checklist.

Rules:
- Do not blindly trust any one source.
- Preserve source IDs when discussing concepts.
- If sources conflict, flag the conflict.
- Do not invent page references.
- Output only the final structured unit synthesis.
- Do not include scratchpad or reasoning process.

Output format:

# Unit Synthesis

## Unit Overview

## Core Concepts

## Merged Formula / Method Sheet

## Cross-Source Connections

## Conflicts or Uncertainties

## Must-Memorize List

## Must-Understand List

## Exam / Homework Traps

## Practice Questions

## Active Recall Questions

## Weak Points to Review

## Final Unit Checklist
"""


def collect_unit_source_outputs(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Collect per-source study pack outputs and warnings for a unit."""
    course_path = resolve_course_path(course_name, root)
    summary = get_study_unit_summary(course_name, unit_id, root)
    source_ids = get_unit_source_ids(course_name, unit_id, root)

    registry = {
        _normalize_source_id(str(entry.get("id", ""))): entry
        for entry in list_sources(course_name, root)
        if entry.get("id")
    }

    unit_warnings: list[str] = []
    sources_out: list[dict] = []

    for sid in source_ids:
        entry = registry.get(sid)
        source_warnings: list[str] = []
        if entry is None:
            unit_warnings.append(f"{sid} is no longer in the source registry.")
            sources_out.append(
                {
                    "source_id": sid,
                    "title": sid,
                    "status": "missing",
                    "final_study_guide_text": "",
                    "formula_sheet_text": "",
                    "practice_quiz_text": "",
                    "active_recall_text": "",
                    "flashcards_text": "",
                    "final_audit_path": "",
                    "study_pack_quality": "missing",
                    "warnings": ["Source not found in registry."],
                }
            )
            continue

        paths = _resolve_source_paths(course_path, entry, sid)
        guide_text = _read_text_file(paths.get("final_study_guide"))
        formula_text = _read_text_file(paths.get("formula_sheet"))
        quiz_text = _read_text_file(paths.get("practice_quiz"))
        recall_text = _read_text_file(paths.get("active_recall"))
        flashcards_text, flash_warnings = _flashcards_summary(paths)
        source_warnings.extend(flash_warnings)

        manifest_path = paths.get("manifest")
        quality = _load_manifest_quality(manifest_path) if manifest_path else "missing"

        audit_path = paths.get("final_audit")
        audit_str = str(audit_path.resolve()) if audit_path else ""

        if not guide_text:
            source_warnings.append("Final study guide not found.")
        if not formula_text:
            source_warnings.append("Formula sheet not found.")
        if not quiz_text:
            source_warnings.append("Practice quiz not found.")
        if not recall_text:
            source_warnings.append("Active recall file not found.")
        if not flashcards_text:
            source_warnings.append("Flashcards markdown/CSV not found.")
        if not audit_str:
            source_warnings.append("Final audit file not found.")

        sources_out.append(
            {
                "source_id": sid,
                "title": str(entry.get("title", sid)),
                "status": str(entry.get("status", "")),
                "final_study_guide_text": guide_text,
                "formula_sheet_text": formula_text,
                "practice_quiz_text": quiz_text,
                "active_recall_text": recall_text,
                "flashcards_text": flashcards_text,
                "final_audit_path": audit_str,
                "study_pack_quality": quality,
                "warnings": source_warnings,
            }
        )

    if not source_ids:
        unit_warnings.append("Study unit has no sources.")

    return {
        "unit": summary,
        "sources": sources_out,
        "warnings": unit_warnings,
    }


def collect_unit_learning_state(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Collect open mistakes, weak points, due flashcards, and recall gaps for the unit."""
    source_ids = get_unit_source_ids(course_name, unit_id, root)
    source_id_set = set(source_ids)
    day = today_date_str()

    mistakes = _filter_by_source_ids(
        collect_open_mistakes(course_name, root), source_id_set
    )
    weak_points = _filter_by_source_ids(
        collect_open_weak_points(course_name, root), source_id_set
    )
    due_flashcards = _filter_by_source_ids(
        collect_due_flashcards(course_name, root, today=day), source_id_set
    )
    recall_items = _filter_by_source_ids(
        collect_active_recall_needs_review(course_name, root), source_id_set
    )

    return {
        "open_mistakes": mistakes,
        "open_weak_points": weak_points,
        "due_flashcards": due_flashcards,
        "active_recall_needs_review": recall_items,
    }


def get_unit_synthesis_packet_paths(
    course_path: Path, unit_id: str
) -> tuple[Path, Path]:
    """Return Markdown and JSON paths for a unit synthesis packet."""
    normalized = _normalize_unit_id(unit_id)
    report_dir = get_unit_reports_dir(course_path)
    return (
        report_dir / f"{normalized}_synthesis_packet.md",
        report_dir / f"{normalized}_synthesis_packet.json",
    )


def _format_learning_entry_lines(entries: list[dict], *, kind: str) -> list[str]:
    lines: list[str] = []
    if not entries:
        lines.append(f"No {kind} for this unit.")
        lines.append("")
        return lines

    for entry in entries:
        if kind == "mistakes":
            lines.extend(
                [
                    f"### {entry.get('mistake_id', 'MISTAKE')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Question:** {entry.get('question', '')}",
                    f"- **Your answer:** {entry.get('user_answer', '')}",
                    f"- **Status:** {entry.get('status', 'new')}",
                    "",
                ]
            )
        elif kind == "weak points":
            lines.extend(
                [
                    f"### {entry.get('weak_point_id', 'WEAK')} — {entry.get('concept', '')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Confidence:** {entry.get('confidence_level', '')}",
                    f"- **Status:** {entry.get('status', 'new')}",
                    "",
                ]
            )
        elif kind == "flashcards":
            lines.extend(
                [
                    f"### {entry.get('card_id', 'card')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Front:** {entry.get('front', '')}",
                    f"- **Due date:** {entry.get('due_date', '')}",
                    "",
                ]
            )
        elif kind == "active recall":
            lines.extend(
                [
                    f"### {entry.get('question_id', 'question')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Question:** {entry.get('question', '')}",
                    f"- **Last grade:** {entry.get('grade', '')}",
                    "",
                ]
            )
    return lines


def _fenced_markdown_block(title: str, text: str) -> list[str]:
    lines = [f"### {title}", ""]
    if text.strip():
        lines.extend(["```markdown", text.rstrip(), "```", ""])
    else:
        lines.append("(not available)")
        lines.append("")
    return lines


def build_unit_synthesis_packet_markdown(
    *,
    course_name: str,
    unit_summary: dict,
    sources: list[dict],
    learning_state: dict | None,
    generated_at: str,
    unit_warnings: list[str],
) -> str:
    """Build the full synthesis packet Markdown."""
    unit_id = unit_summary.get("unit_id", "")
    unit_title = unit_summary.get("title", "")
    instructions = build_unit_synthesis_instructions()

    lines = [
        "# Unit Synthesis Packet",
        "",
        "Course:",
        course_name,
        "",
        "Unit:",
        f"{unit_id} — {unit_title}",
        "",
        "Description:",
        unit_summary.get("description") or "—",
        "",
        "Generated:",
        generated_at,
        "",
        "---",
        "",
        "## Instructions",
        "",
        instructions,
        "",
        "---",
        "",
        "## Unit Sources",
        "",
    ]

    if not sources:
        lines.append("No sources in this unit.")
        lines.append("")
    else:
        for source in sources:
            warning_text = "; ".join(source.get("warnings") or []) or "none"
            lines.extend(
                [
                    f"- **{source.get('source_id', '')}** — {source.get('title', '')}",
                    f"  - Status: {source.get('status', '')}",
                    f"  - Study pack quality: {source.get('study_pack_quality', 'missing')}",
                    f"  - Warnings: {warning_text}",
                ]
            )
        lines.append("")

    for warning in unit_warnings:
        lines.append(f"- Unit warning: {warning}")
    if unit_warnings:
        lines.append("")

    lines.extend(["---", "", "# Source Study Materials", ""])

    for source in sources:
        sid = source.get("source_id", "")
        title = source.get("title", "")
        lines.extend([f"## Source {sid} — {title}", ""])
        lines.extend(
            _fenced_markdown_block(
                "Final Study Guide", source.get("final_study_guide_text", "")
            )
        )
        lines.extend(
            _fenced_markdown_block(
                "Formula Sheet", source.get("formula_sheet_text", "")
            )
        )
        lines.extend(
            _fenced_markdown_block(
                "Practice Quiz", source.get("practice_quiz_text", "")
            )
        )
        lines.extend(
            _fenced_markdown_block(
                "Active Recall", source.get("active_recall_text", "")
            )
        )
        lines.extend(
            _fenced_markdown_block(
                "Flashcards", source.get("flashcards_text", "")
            )
        )
        audit_path = source.get("final_audit_path", "")
        if audit_path:
            lines.extend(["### Final Audit Path", "", audit_path, ""])
        lines.append("")

    if learning_state is not None:
        lines.extend(["---", "", "## Unit Learning State", ""])
        lines.extend(["### Open Mistakes", ""])
        lines.extend(
            _format_learning_entry_lines(
                learning_state.get("open_mistakes", []), kind="mistakes"
            )
        )
        lines.extend(["### Open Weak Points", ""])
        lines.extend(
            _format_learning_entry_lines(
                learning_state.get("open_weak_points", []), kind="weak points"
            )
        )
        lines.extend(["### Due Flashcards", ""])
        lines.extend(
            _format_learning_entry_lines(
                learning_state.get("due_flashcards", []), kind="flashcards"
            )
        )
        lines.extend(["### Active Recall Needing Review", ""])
        lines.extend(
            _format_learning_entry_lines(
                learning_state.get("active_recall_needs_review", []),
                kind="active recall",
            )
        )

    lines.extend(
        [
            "---",
            "",
            "## Questions for the Synthesizer",
            "",
            "- What concepts appear across multiple sources?",
            "- What formulas/methods should be unified?",
            "- What concepts are emphasized by mistakes or weak points?",
            "- What should be memorized?",
            "- What should be understood deeply?",
            "- What practice questions best cover the unit?",
            "",
        ]
    )

    return "\n".join(lines)


def build_unit_synthesis_packet(
    course_name: str,
    unit_id: str,
    root: Path | None = None,
    include_learning_state: bool = True,
    overwrite: bool = False,
) -> dict:
    """
    Build and save unit synthesis packet Markdown + metadata JSON.

    Raises ``UnitSynthesisPacketExistsError`` if files exist and overwrite is False.
    Raises ``StudyUnitNotFoundError`` for invalid unit_id.
    """
    course_path = resolve_course_path(course_name, root)
    normalized_unit = _normalize_unit_id(unit_id)
    load_study_units(course_name, root)

    outputs = collect_unit_source_outputs(course_name, unit_id, root)
    unit_summary = outputs["unit"]
    sources = outputs["sources"]
    unit_warnings = list(outputs.get("warnings", []))

    learning_state: dict | None = None
    if include_learning_state:
        learning_state = collect_unit_learning_state(course_name, unit_id, root)

    md_path, json_path = get_unit_synthesis_packet_paths(course_path, unit_id)
    if (md_path.is_file() or json_path.is_file()) and not overwrite:
        raise UnitSynthesisPacketExistsError(
            f"Unit synthesis packet already exists for {normalized_unit}:\n"
            f"  - {md_path}\n"
            f"  - {json_path}\n"
            "Use --overwrite to replace."
        )

    generated_at = _now_iso()
    markdown = build_unit_synthesis_packet_markdown(
        course_name=course_path.name,
        unit_summary=unit_summary,
        sources=sources,
        learning_state=learning_state,
        generated_at=generated_at,
        unit_warnings=unit_warnings,
    )

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")

    included_sources = [s["source_id"] for s in sources]
    all_warnings = list(unit_warnings)
    for source in sources:
        all_warnings.extend(source.get("warnings", []))

    metadata = {
        "course": course_path.name,
        "unit_id": normalized_unit,
        "unit_title": unit_summary.get("title", ""),
        "source_count": len(sources),
        "included_sources": included_sources,
        "include_learning_state": include_learning_state,
        "packet_path": str(md_path.resolve()),
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
        "date_created": generated_at,
        "warnings": all_warnings,
    }

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return {
        "course": course_path.name,
        "unit_id": normalized_unit,
        "unit_title": unit_summary.get("title", ""),
        "source_count": len(sources),
        "included_sources": included_sources,
        "include_learning_state": include_learning_state,
        "packet_path": str(md_path.resolve()),
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
        "warnings": all_warnings,
        "metadata": metadata,
    }
