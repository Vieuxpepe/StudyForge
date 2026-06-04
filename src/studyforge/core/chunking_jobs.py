"""
Orchestrate chunking of extracted source text for StudyForge courses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.chunking.text_chunker import (
    chunk_to_markdown,
    collect_chunking_warnings,
    create_chunks_from_pages,
    parse_extracted_markdown_pages,
)
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import (
    CourseNotFoundError,
    load_source_registry,
    resolve_course_path,
    save_source_registry,
)

CHUNKS_BASE = Path("02_Extracted_Text") / "chunks"
MANIFEST_NAME = "chunk_manifest.json"


class SourceNotExtractedError(Exception):
    """Raised when the source has not been extracted yet."""


class ChunkOutputExistsError(Exception):
    """Raised when chunk output exists and overwrite was not requested."""


def get_chunks_dir(course_path: Path, source_id: str) -> Path:
    """Return 02_Extracted_Text/chunks/<source_id>/ (creates if missing)."""
    normalized = source_id.strip().upper()
    path = course_path / CHUNKS_BASE / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_chunk_manifest_path(course_path: Path, source_id: str) -> Path:
    """Return path to chunk_manifest.json for a source."""
    return get_chunks_dir(course_path, source_id) / MANIFEST_NAME


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _update_registry_entry(registry: dict, source_id: str, updates: dict) -> None:
    normalized = _normalize_source_id(source_id)
    for entry in registry.get("sources", []):
        if str(entry.get("id", "")).upper() == normalized:
            entry.update(updates)
            return
    raise SourceNotFoundError(f"Source not found in registry: {source_id}")


def _chunk_has_output(chunk_dir: Path) -> bool:
    """True if chunk folder already has a manifest or chunk files."""
    if not chunk_dir.is_dir():
        return False
    if (chunk_dir / MANIFEST_NAME).is_file():
        return True
    return any(chunk_dir.glob("*.md"))


def _clear_chunk_outputs(chunk_dir: Path) -> None:
    """Remove generated chunk files in a source chunk folder (not the folder itself)."""
    if not chunk_dir.is_dir():
        return
    for path in chunk_dir.iterdir():
        if path.is_file():
            path.unlink()


def chunk_registered_source(
    course_name: str,
    source_id: str,
    max_words: int = 1200,
    overlap_words: int = 150,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Chunk extracted Markdown for a registered source and update the registry.

    Returns:
        Summary dict for CLI output.

    Raises:
        CourseNotFoundError, SourceNotFoundError, SourceNotExtractedError,
        ChunkOutputExistsError, FileNotFoundError, ValueError.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    status = entry.get("status", "added")
    if status == "added":
        raise SourceNotExtractedError(
            f"Source {normalized_id} has not been extracted yet.\n"
            "Run: python scripts/extract_source.py "
            f"--course {course_path.name} --source-id {normalized_id}"
        )

    extracted_path = Path(entry.get("extracted_text_path", ""))
    if not extracted_path.is_file():
        raise FileNotFoundError(
            f"Extracted text file not found: {extracted_path}\n"
            "Re-run extract_source.py or fix extracted_text_path in the registry."
        )

    chunk_dir = get_chunks_dir(course_path, normalized_id)
    manifest_path = get_chunk_manifest_path(course_path, normalized_id)

    if _chunk_has_output(chunk_dir) and not overwrite:
        raise ChunkOutputExistsError(
            f"Chunk output already exists for {normalized_id}:\n"
            f"  - {chunk_dir}\n"
            "Use --overwrite to replace chunk files and manifest for this source."
        )

    if overwrite:
        _clear_chunk_outputs(chunk_dir)

    markdown_text = extracted_path.read_text(encoding="utf-8")
    pages = parse_extracted_markdown_pages(markdown_text)
    chunks = create_chunks_from_pages(
        pages,
        max_words=max_words,
        overlap_words=overlap_words,
        source_id=normalized_id,
    )

    warnings = collect_chunking_warnings(
        pages,
        chunks,
        max_words,
        overlap_words,
        extracted_path=str(extracted_path),
        extracted_exists=extracted_path.is_file(),
    )

    if not chunks:
        raise ValueError(
            "No chunks could be created. Check extracted text and page headings."
        )

    manifest_chunks: list[dict] = []
    for chunk in chunks:
        chunk_file = chunk_dir / f"{chunk['chunk_id']}.md"
        chunk_file.write_text(chunk_to_markdown(chunk), encoding="utf-8")
        manifest_chunks.append(
            {
                "chunk_id": chunk["chunk_id"],
                "chunk_number": chunk["chunk_number"],
                "file_path": str(chunk_file.resolve()),
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "pages": chunk["pages"],
                "word_count": chunk["word_count"],
            }
        )

    chunked_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    manifest = {
        "source_id": normalized_id,
        "title": title,
        "max_words": max_words,
        "overlap_words": overlap_words,
        "chunk_count": len(chunks),
        "date_chunked": chunked_at,
        "chunks": manifest_chunks,
        "warnings": warnings,
    }

    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    registry = load_source_registry(course_path)
    _update_registry_entry(
        registry,
        normalized_id,
        {
            "status": "chunked",
            "chunk_manifest_path": str(manifest_path.resolve()),
            "chunk_count": len(chunks),
            "date_chunked": chunked_at,
        },
    )
    save_source_registry(course_path, registry)

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "chunk_count": len(chunks),
        "chunk_manifest_path": str(manifest_path.resolve()),
        "chunk_folder": str(chunk_dir.resolve()),
        "warnings": warnings,
    }
