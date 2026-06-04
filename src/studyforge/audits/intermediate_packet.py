"""
Build intermediate audit packets for manual paste into Gemini / Google AI Studio.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.chunking_jobs import get_chunk_manifest_path, get_chunks_dir
from studyforge.core.digest_jobs import get_local_digest_dir
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import resolve_course_path

INTERMEDIATE_AUDIT_BASE = Path("04_Intermediate_Audits")

_DIGEST_STATUSES_OK = frozenset({"local_digest_complete", "local_digest_partial"})


class LocalDigestNotFoundError(Exception):
    """Raised when local digest artifacts are missing for the source."""


class PacketOutputExistsError(Exception):
    """Raised when packet files exist and overwrite was not requested."""


def build_intermediate_audit_instructions() -> str:
    """Return the intermediate auditor prompt for manual AI review."""
    return """You are the intermediate auditor for my StudyForge local AI study pipeline.

I will provide:

1. Source material chunks
2. Local AI digest chunks
3. A rule-based digest review summary

Your job is to audit the local digest against the source chunks.

Check for:

* incorrect claims
* hallucinations
* missing key concepts
* weak explanations
* misleading simplifications
* wrong formulas
* missing assumptions
* skipped examples
* bad practice questions
* unsupported claims
* likely test traps

For every issue, return:

1. Chunk ID
2. Original claim from the local digest
3. Verdict:

   * Correct
   * Incomplete
   * Misleading
   * Wrong
   * Not verified by source
4. Corrected version
5. Source support
6. Why this matters for homework, quizzes, or exams

Rules:

* Do not guess.
* Use the source chunks as the highest authority.
* If the source does not support a claim, say "not verified."
* Preserve chunk IDs.
* Be strict but fair."""


def load_json(path: Path) -> dict:
    """Load a UTF-8 JSON file."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_text(path: Path) -> str:
    """Load a UTF-8 text file."""
    return path.read_text(encoding="utf-8")


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def get_intermediate_audit_dir(course_path: Path, source_id: str) -> Path:
    """Return 04_Intermediate_Audits/<source_id>/ (creates if missing)."""
    normalized = _normalize_source_id(source_id)
    path = course_path / INTERMEDIATE_AUDIT_BASE / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chunk_id_from_digest_review_file(file_review: dict) -> str | None:
    """Extract chunk ID from a digest review file entry (skip combined)."""
    path_str = file_review.get("path", "")
    name = Path(path_str).name
    if "CHUNK" not in name or not name.endswith("_digest.md"):
        return None
    return name.replace("_digest.md", "")


def select_chunks_for_audit(
    chunk_manifest: dict,
    digest_review: dict | None = None,
    limit_chunks: int | None = None,
    only_needs_review: bool = False,
) -> list[dict]:
    """
    Select chunk manifest entries to include in the audit packet.

    Args:
        chunk_manifest: Parsed chunk_manifest.json.
        digest_review: Parsed local digest review JSON, if available.
        limit_chunks: Keep only the first N chunks after selection.
        only_needs_review: Prefer chunks whose digest review status is not ``ok``.

    Returns:
        List of chunk dicts from the manifest (subset).
    """
    all_chunks = list(chunk_manifest.get("chunks", []))
    if not all_chunks:
        return []

    selected = all_chunks

    if only_needs_review and digest_review:
        needs_review_ids: set[str] = set()
        for file_review in digest_review.get("files", []):
            if file_review.get("status") != "ok":
                chunk_id = _chunk_id_from_digest_review_file(file_review)
                if chunk_id:
                    needs_review_ids.add(chunk_id)

        if needs_review_ids:
            selected = [
                c
                for c in all_chunks
                if str(c.get("chunk_id", "")) in needs_review_ids
            ]

    if limit_chunks is not None and limit_chunks > 0:
        selected = selected[:limit_chunks]

    return selected


def _digest_review_path(course_path: Path, source_id: str) -> Path:
    digest_dir = get_local_digest_dir(course_path, source_id)
    return digest_dir / f"{_normalize_source_id(source_id)}_local_digest_review.json"


def _packet_paths(audit_dir: Path, source_id: str) -> tuple[Path, Path]:
    normalized = _normalize_source_id(source_id)
    md_path = audit_dir / f"{normalized}_intermediate_audit_packet.md"
    json_path = audit_dir / f"{normalized}_intermediate_audit_packet.json"
    return md_path, json_path


def _format_review_summary(digest_review: dict | None) -> str:
    if not digest_review:
        return "No rule-based local digest review found."

    lines = [
        f"Overall status: {digest_review.get('overall_status', 'unknown')}",
        f"Digests OK: {digest_review.get('digests_ok', 0)}",
        f"Digests needing review: {digest_review.get('digests_needing_review', 0)}",
        f"Digests failed: {digest_review.get('digests_failed', 0)}",
        f"Total uncertainty markers: {digest_review.get('total_uncertainty_markers', 0)}",
        "Warnings:",
    ]
    warnings = digest_review.get("warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"* {warning}")
    else:
        lines.append("* None")
    return "\n".join(lines)


def _build_packet_markdown(
    course_name: str,
    source_id: str,
    title: str,
    entry: dict,
    digest_review: dict | None,
    chunk_manifest: dict,
    audit_items: list[dict],
    generated_at: str,
) -> str:
    """Assemble the full intermediate audit packet Markdown."""
    instructions = build_intermediate_audit_instructions()
    review_block = _format_review_summary(digest_review)

    lines = [
        "# Intermediate Audit Packet",
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
        "## Audit Instructions",
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
        "## Chunk Manifest Summary",
        "",
        f"Chunk count: {chunk_manifest.get('chunk_count', len(chunk_manifest.get('chunks', [])))}",
        f"Max words: {chunk_manifest.get('max_words', 'unknown')}",
        f"Overlap words: {chunk_manifest.get('overlap_words', 'unknown')}",
        "",
        "---",
        "",
        "# Audit Materials",
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
            "## Questions for Intermediate Auditor",
            "",
            "1. Which claims are unsupported by the source chunk?",
            "2. Which explanations are incomplete or misleading?",
            "3. Are any formulas, definitions, or examples incorrect?",
            "4. What key concepts did the local digest miss?",
            "5. Which chunks need final auditor attention most?",
            "",
        ]
    )

    return "\n".join(lines)


def collect_intermediate_audit_items(
    course_name: str,
    source_id: str,
    limit_chunks: int | None = None,
    only_needs_review: bool = False,
    root: Path | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Load source chunks and local digests selected for intermediate audit.

    Returns:
        (audit_items, warnings) — each item has chunk_id, source/digest text, paths.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])

    status = entry.get("status", "")
    combined_path = Path(entry.get("local_digest_path", ""))
    if status not in _DIGEST_STATUSES_OK and not combined_path.is_file():
        raise LocalDigestNotFoundError(
            f"Local digest not found for {normalized_id} (status: {status!r}).\n"
            "Run run_local_digest.py first."
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
        raise ValueError("No chunks selected for intermediate audit.")

    digest_dir = get_local_digest_dir(course_path, normalized_id)
    warnings: list[str] = []
    audit_items: list[dict] = []

    for chunk in selected_chunks:
        chunk_id = str(chunk.get("chunk_id", ""))
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
                "source_chunk_path": str(source_path.resolve())
                if source_path.is_file()
                else str(source_path),
                "digest_chunk_path": str(digest_path.resolve())
                if digest_path.is_file()
                else str(digest_path),
            }
        )

    if not digest_review:
        warnings.append("No rule-based local digest review JSON found.")

    return audit_items, warnings


def build_intermediate_audit_packet(
    course_name: str,
    source_id: str,
    limit_chunks: int | None = None,
    only_needs_review: bool = False,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Build and save an intermediate audit packet for manual cloud audit.

    Does not modify source_registry.json or call any AI API.

    Returns:
        Summary dict including packet paths and selected chunk IDs.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    manifest_path = get_chunk_manifest_path(course_path, normalized_id)
    chunk_manifest = load_json(manifest_path)
    review_path = _digest_review_path(course_path, normalized_id)
    digest_review = load_json(review_path) if review_path.is_file() else None

    audit_items, warnings = collect_intermediate_audit_items(
        course_name,
        source_id,
        limit_chunks=limit_chunks,
        only_needs_review=only_needs_review,
        root=root,
    )

    audit_dir = get_intermediate_audit_dir(course_path, normalized_id)
    md_path, json_path = _packet_paths(audit_dir, normalized_id)

    if not overwrite and (md_path.exists() or json_path.exists()):
        raise PacketOutputExistsError(
            "Intermediate audit packet already exists:\n"
            f"  - {md_path}\n"
            f"  - {json_path}\n"
            "Use --overwrite to replace the packet files."
        )

    selected_ids = [item["chunk_id"] for item in audit_items]

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    packet_md = _build_packet_markdown(
        course_name=course_path.name,
        source_id=normalized_id,
        title=title,
        entry=entry,
        digest_review=digest_review,
        chunk_manifest=chunk_manifest,
        audit_items=audit_items,
        generated_at=generated_at,
    )

    md_path.write_text(packet_md, encoding="utf-8")

    metadata = {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "packet_path": str(md_path.resolve()),
        "packet_json_path": str(json_path.resolve()),
        "selected_chunk_count": len(selected_ids),
        "selected_chunks": selected_ids,
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
        "warnings": warnings,
    }
