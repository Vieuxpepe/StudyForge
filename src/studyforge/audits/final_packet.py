"""
Build final audit packets for manual paste into ChatGPT / strong reasoning models.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.audits.intermediate_import import (
    get_intermediate_audit_dir,
    get_intermediate_audit_registry_path,
    load_audit_registry,
)
from studyforge.audits.intermediate_packet import (
    _format_review_summary,
    load_json,
    load_text,
    select_chunks_for_audit,
)
from studyforge.core.chunking_jobs import get_chunk_manifest_path
from studyforge.core.digest_jobs import get_local_digest_dir
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import resolve_course_path

FINAL_AUDIT_BASE = Path("05_Final_Audits")

_INTERMEDIATE_AUDIT_FILE_SUFFIX = "_intermediate_audit_v"


class NoIntermediateAuditError(Exception):
    """Raised when no intermediate audit has been imported for this source."""


class FinalPacketOutputExistsError(Exception):
    """Raised when final packet files exist and overwrite was not requested."""


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def get_final_audit_dir(course_path: Path, source_id: str) -> Path:
    """Return 05_Final_Audits/<source_id>/ (creates if missing)."""
    normalized = _normalize_source_id(source_id)
    path = course_path / FINAL_AUDIT_BASE / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def _final_packet_paths(audit_dir: Path, source_id: str) -> tuple[Path, Path]:
    normalized = _normalize_source_id(source_id)
    md_path = audit_dir / f"{normalized}_final_audit_packet.md"
    json_path = audit_dir / f"{normalized}_final_audit_packet.json"
    return md_path, json_path


def build_final_auditor_instructions() -> str:
    """Return the final auditor prompt for manual AI review."""
    return """You are the final auditor and tutor for my StudyForge local AI study pipeline.

I will provide:

1. Source material chunks
2. Local AI digest
3. Rule-based local digest review
4. Intermediate audit from Gemini or another model

Your job:

* verify whether the intermediate audit is correct
* catch remaining errors
* identify missing concepts
* correct weak or misleading explanations
* explain difficult ideas clearly
* decide what matters most for homework/tests
* produce a final corrected study guide
* create active recall questions
* preserve uncertainty where needed

Rules:

* Do not blindly trust the local digest.
* Do not blindly trust the intermediate audit.
* Use the source chunks as the highest authority.
* If something is not supported by the source chunks, say "not verified."
* Do not invent page references.
* Preserve source IDs and chunk IDs.
* Separate source-supported facts from your interpretation.
* Prefer incomplete but verified material over complete but unreliable material.
* Do not give final homework answers unless this is clearly study/practice material.

Output format:

# Final Audit

## Final Verdict

Accuracy:
Completeness:
Study usefulness:
Biggest risks:

## Corrections That Matter Most

For each correction:

* Problem:
* Correct version:
* Source support:
* Why it matters:

## Missing Concepts

## Better Explanations

## Must-Memorize List

## Must-Understand List

## Formula / Method Sheet

## Exam / Homework Traps

## Practice Questions

## Active Recall Questions

## Final Study Checklist

## Remaining Uncertainties"""


def _find_latest_audit_on_disk(intermediate_dir: Path, source_id: str) -> dict | None:
    """Pick the highest-version intermediate audit file if registry is empty."""
    normalized = _normalize_source_id(source_id)
    prefix = f"{normalized}{_INTERMEDIATE_AUDIT_FILE_SUFFIX}"
    candidates = sorted(
        [
            p
            for p in intermediate_dir.glob("*.md")
            if p.name.startswith(prefix) and "packet" not in p.name
        ],
        key=lambda p: p.name,
    )
    if not candidates:
        return None
    latest_path = candidates[-1]
    return {
        "version": 0,
        "audit_id": "unknown",
        "auditor_name": "unknown",
        "file_path": str(latest_path.resolve()),
        "date_imported": "",
        "notes": "",
        "status": "imported",
    }


def get_latest_intermediate_audit(
    course_path: Path, source_id: str
) -> dict | None:
    """
    Load the latest intermediate audit entry and its Markdown text.

    Reads 04_Intermediate_Audits/<source_id>/ registry JSON, or scans disk
    for versioned audit files if the registry is empty.

    Returns:
        None if no audit exists, else
        {
            "entry": {...},
            "text": "...",
            "registry_path": "...",
        }
    """
    normalized = _normalize_source_id(source_id)
    intermediate_dir = get_intermediate_audit_dir(course_path, normalized)
    registry_path = get_intermediate_audit_registry_path(course_path, normalized)
    registry = load_audit_registry(registry_path)

    audits = list(registry.get("audits", []))
    entry: dict | None = None

    if audits:
        entry = max(audits, key=lambda item: int(item.get("version", 0)))
    else:
        entry = _find_latest_audit_on_disk(intermediate_dir, normalized)

    if not entry:
        return None

    file_path = Path(entry.get("file_path", ""))
    if not file_path.is_file():
        # Try rebuild path from version
        version = int(entry.get("version", 1))
        if version > 0:
            file_path = intermediate_dir / (
                f"{normalized}_intermediate_audit_v{version:03d}.md"
            )
        if not file_path.is_file() and entry.get("audit_id") == "unknown":
            scanned = _find_latest_audit_on_disk(intermediate_dir, normalized)
            if scanned:
                file_path = Path(scanned["file_path"])

    if not file_path.is_file():
        return None

    return {
        "entry": entry,
        "text": load_text(file_path),
        "registry_path": str(registry_path.resolve()) if registry_path.is_file() else "",
    }


def _digest_review_path(course_path: Path, source_id: str) -> Path:
    digest_dir = get_local_digest_dir(course_path, source_id)
    return digest_dir / f"{_normalize_source_id(source_id)}_local_digest_review.json"


def _build_packet_markdown(
    course_name: str,
    source_id: str,
    title: str,
    entry: dict,
    digest_review: dict | None,
    intermediate_audit: dict,
    combined_digest_text: str,
    audit_items: list[dict],
    generated_at: str,
) -> str:
    """Assemble the full final audit packet Markdown."""
    instructions = build_final_auditor_instructions()
    review_block = _format_review_summary(digest_review)
    ia_entry = intermediate_audit["entry"]

    lines = [
        "# Final Audit Packet",
        "",
        "Course:",
        course_name,
        "",
        "Source:",
        f"{source_id} - {title}",
        "",
        "Generated:",
        generated_at,
        "",
        "---",
        "",
        "## Final Auditor Instructions",
        "",
        instructions,
        "",
        "---",
        "",
        "## Source Metadata",
        "",
        "Source ID:",
        source_id,
        "",
        "Title:",
        title,
        "",
        "Source type:",
        str(entry.get("source_type", "unknown")),
        "",
        "Original file:",
        str(entry.get("file_name", entry.get("original_path", "unknown"))),
        "",
        "Stored path:",
        str(entry.get("stored_path", "unknown")),
        "",
        "Registry status:",
        str(entry.get("status", "unknown")),
        "",
        "---",
        "",
        "## Local Digest Review Summary",
        "",
        review_block,
        "",
        "---",
        "",
        "## Latest Intermediate Audit",
        "",
        "Audit ID:",
        str(ia_entry.get("audit_id", "unknown")),
        "",
        "Auditor:",
        str(ia_entry.get("auditor_name", "unknown")),
        "",
        "Version:",
        str(ia_entry.get("version", "unknown")),
        "",
        "Date imported:",
        str(ia_entry.get("date_imported", "unknown")),
        "",
        "Notes:",
        str(ia_entry.get("notes", "")) or "(none)",
        "",
        "```markdown",
        intermediate_audit["text"].strip(),
        "```",
        "",
        "---",
        "",
        "## Combined Local Digest",
        "",
        "```markdown",
        combined_digest_text.strip()
        if combined_digest_text.strip()
        else "_(combined local digest not found)_",
        "```",
        "",
        "---",
        "",
        "# Source and Digest Materials",
        "",
    ]

    for index, item in enumerate(audit_items, start=1):
        chunk_id = item["chunk_id"]
        lines.extend(
            [
                f"## Audit Item {index} — {chunk_id}",
                "",
                "### Source Chunk",
                "",
                "```markdown",
                item["source_chunk_text"],
                "```",
                "",
                "### Local Digest Chunk",
                "",
                "```markdown",
                item["digest_chunk_text"],
                "```",
                "",
                "---",
                "",
            ]
        )

    lines.extend(
        [
            "## Questions for Final Auditor",
            "",
            "1. Was the intermediate audit correct?",
            "2. What remaining errors or unsupported claims exist?",
            "3. What concepts are still missing or weak?",
            "4. What should be in the final corrected study guide?",
            "5. What should I memorize?",
            "6. What should I understand deeply?",
            "7. What are the likely exam or homework traps?",
            "8. What active recall questions should I answer?",
            "",
        ]
    )

    return "\n".join(lines)


def build_final_audit_packet(
    course_name: str,
    source_id: str,
    limit_chunks: int | None = None,
    only_needs_review: bool = False,
    root: Path | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Build and save a final audit packet for manual cloud audit.

    Does not modify source_registry.json or call any AI API.

    Returns:
        Summary dict including packet paths and selected chunk IDs.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    intermediate_audit = get_latest_intermediate_audit(course_path, normalized_id)
    if not intermediate_audit:
        raise NoIntermediateAuditError(
            f"No intermediate audit found for {normalized_id}.\n"
            "Import one with: python scripts/import_intermediate_audit.py"
        )

    manifest_path = get_chunk_manifest_path(course_path, normalized_id)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Chunk manifest not found: {manifest_path}")

    chunk_manifest = load_json(manifest_path)
    review_path = _digest_review_path(course_path, normalized_id)
    digest_review = load_json(review_path) if review_path.is_file() else None

    selected_chunks = select_chunks_for_audit(
        chunk_manifest,
        digest_review=digest_review,
        limit_chunks=limit_chunks,
        only_needs_review=only_needs_review,
    )
    if not selected_chunks:
        raise ValueError("No chunks selected for final audit packet.")

    final_dir = get_final_audit_dir(course_path, normalized_id)
    md_path, json_path = _final_packet_paths(final_dir, normalized_id)

    if not overwrite and (md_path.exists() or json_path.exists()):
        raise FinalPacketOutputExistsError(
            "Final audit packet already exists:\n"
            f"  - {md_path}\n"
            f"  - {json_path}\n"
            "Use --overwrite to replace the packet files."
        )

    digest_dir = get_local_digest_dir(course_path, normalized_id)
    combined_path = digest_dir / f"{normalized_id}_combined_local_digest.md"
    if not combined_path.is_file():
        alt = Path(entry.get("local_digest_path", ""))
        combined_path = alt if alt.is_file() else combined_path

    combined_text = load_text(combined_path) if combined_path.is_file() else ""

    warnings: list[str] = []
    if not combined_text.strip():
        warnings.append("Combined local digest file not found or empty.")
    if not digest_review:
        warnings.append("No rule-based local digest review JSON found.")

    audit_items: list[dict] = []
    selected_ids: list[str] = []

    for chunk in selected_chunks:
        chunk_id = str(chunk.get("chunk_id", ""))
        selected_ids.append(chunk_id)

        source_path = Path(chunk.get("file_path", ""))
        digest_path = digest_dir / f"{chunk_id}_digest.md"

        if not source_path.is_file():
            warnings.append(f"Source chunk file missing: {source_path}")
            source_text = f"_(missing source chunk: {source_path})_"
        else:
            source_text = load_text(source_path)

        if not digest_path.is_file():
            warnings.append(f"Local digest chunk missing: {digest_path}")
            digest_text = f"_(missing digest: {digest_path})_"
        else:
            digest_text = load_text(digest_path)

        audit_items.append(
            {
                "chunk_id": chunk_id,
                "source_chunk_text": source_text,
                "digest_chunk_text": digest_text,
            }
        )

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    packet_md = _build_packet_markdown(
        course_name=course_path.name,
        source_id=normalized_id,
        title=title,
        entry=entry,
        digest_review=digest_review,
        intermediate_audit=intermediate_audit,
        combined_digest_text=combined_text,
        audit_items=audit_items,
        generated_at=generated_at,
    )

    md_path.write_text(packet_md, encoding="utf-8")

    ia_entry = intermediate_audit["entry"]
    metadata = {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "packet_path": str(md_path.resolve()),
        "packet_json_path": str(json_path.resolve()),
        "selected_chunk_count": len(selected_ids),
        "selected_chunks": selected_ids,
        "intermediate_audit_id": str(ia_entry.get("audit_id", "unknown")),
        "only_needs_review": only_needs_review,
        "limit_chunks": limit_chunks,
        "date_created": generated_at,
        "warnings": warnings,
    }

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "packet_path": str(md_path.resolve()),
        "packet_json_path": str(json_path.resolve()),
        "selected_chunk_count": len(selected_ids),
        "selected_chunks": selected_ids,
        "intermediate_audit_id": metadata["intermediate_audit_id"],
        "warnings": warnings,
    }
