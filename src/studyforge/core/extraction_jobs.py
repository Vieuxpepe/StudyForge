"""
Orchestrate PDF text extraction for registered course sources.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.sources import (
    CourseNotFoundError,
    SourceFileNotFoundError,
    load_source_registry,
    resolve_course_path,
    save_source_registry,
)
from studyforge.extraction.pdf_extractor import extract_pdf_to_markdown

EXTRACTED_TEXT_BASE = Path("02_Extracted_Text")
EXTRACTED_SOURCES_DIR = EXTRACTED_TEXT_BASE / "extracted_sources"
EXTRACTION_LOGS_DIR = EXTRACTED_TEXT_BASE / "extraction_logs"


class SourceNotFoundError(Exception):
    """Raised when source_id is not in the course registry."""


class NotPdfSourceError(ValueError):
    """Raised when the registered source is not a PDF."""


class ExtractionOutputExistsError(Exception):
    """Raised when output files exist and overwrite was not requested."""


def find_source_by_id(
    course_name: str, source_id: str, root: Path | None = None
) -> dict:
    """
    Find a registry entry by source ID (case-insensitive SRC-XXXX).

    Raises:
        CourseNotFoundError: Course folder missing.
        SourceNotFoundError: No matching source ID.
    """
    course_path = resolve_course_path(course_name, root)
    registry = load_source_registry(course_path)
    normalized_id = source_id.strip().upper()

    for entry in registry.get("sources", []):
        if str(entry.get("id", "")).upper() == normalized_id:
            return entry

    raise SourceNotFoundError(
        f"Source not found: {source_id}\n"
        f"Check source_registry.json for course {course_path.name}."
    )


def get_extracted_sources_dir(course_path: Path) -> Path:
    """Return 02_Extracted_Text/extracted_sources/ (creates if missing)."""
    path = course_path / EXTRACTED_SOURCES_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_extraction_logs_dir(course_path: Path) -> Path:
    """Return 02_Extracted_Text/extraction_logs/ (creates if missing)."""
    path = course_path / EXTRACTION_LOGS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extracted_text_path(course_path: Path, source_id: str) -> Path:
    return get_extracted_sources_dir(course_path) / f"{source_id}_extracted_text.md"


def _extraction_log_path(course_path: Path, source_id: str) -> Path:
    return get_extraction_logs_dir(course_path) / f"{source_id}_extraction_log.json"


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _update_registry_entry(
    registry: dict, source_id: str, updates: dict
) -> None:
    """Merge updates into the matching source entry."""
    normalized = _normalize_source_id(source_id)
    for entry in registry.get("sources", []):
        if str(entry.get("id", "")).upper() == normalized:
            entry.update(updates)
            return
    raise SourceNotFoundError(f"Source not found in registry: {source_id}")


def extract_registered_source(
    course_name: str,
    source_id: str,
    root: Path | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Extract text from a registered PDF source and update the registry.

    Steps:
        1. Resolve course and find source by ID
        2. Validate PDF exists on disk
        3. Extract via PyMuPDF
        4. Write Markdown + JSON log
        5. Set registry status to extracted

    Returns:
        Summary dict for CLI display.

    Raises:
        CourseNotFoundError, SourceNotFoundError, NotPdfSourceError,
        SourceFileNotFoundError, ExtractionOutputExistsError,
        FileNotFoundError, ValueError, RuntimeError, ImportError.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])

    stored_path = Path(entry.get("stored_path", ""))
    if not stored_path.exists():
        raise SourceFileNotFoundError(
            f"Stored source file not found: {stored_path}\n"
            "Re-add the source or fix the path in source_registry.json."
        )

    extension = entry.get("file_extension", stored_path.suffix).lower()
    if extension != ".pdf":
        raise NotPdfSourceError(
            f"Source {normalized_id} is not a PDF (extension: {extension!r}). "
            "Only PDF extraction is supported in this version."
        )

    text_out = _extracted_text_path(course_path, normalized_id)
    log_out = _extraction_log_path(course_path, normalized_id)

    if not overwrite and (text_out.exists() or log_out.exists()):
        existing = [str(p) for p in (text_out, log_out) if p.exists()]
        raise ExtractionOutputExistsError(
            "Extraction output already exists:\n"
            + "\n".join(f"  - {p}" for p in existing)
            + "\nUse --overwrite to replace extracted text and log."
        )

    title = entry.get("title", stored_path.stem)
    markdown, metadata = extract_pdf_to_markdown(stored_path, normalized_id, title=title)

    # Enrich log metadata with paths and title
    metadata["title"] = title
    metadata["stored_path"] = str(stored_path.resolve())
    metadata["extracted_text_path"] = str(text_out.resolve())
    metadata["extraction_log_path"] = str(log_out.resolve())

    text_out.write_text(markdown, encoding="utf-8")
    with log_out.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    extracted_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    registry = load_source_registry(course_path)
    _update_registry_entry(
        registry,
        normalized_id,
        {
            "status": "extracted",
            "extracted_text_path": str(text_out.resolve()),
            "extraction_log_path": str(log_out.resolve()),
            "date_extracted": extracted_at,
        },
    )
    save_source_registry(course_path, registry)

    warnings = metadata.get("warnings", [])
    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "total_pages": metadata["total_pages"],
        "total_words": metadata["total_words"],
        "total_characters": metadata["total_characters"],
        "extracted_text_path": str(text_out.resolve()),
        "extraction_log_path": str(log_out.resolve()),
        "warnings": warnings,
    }
