"""
Evidence Trace Viewer v1 — inspect source → digest → audit → study pack chain (no AI).
"""

from __future__ import annotations

import json
from pathlib import Path

from studyforge.core.chunking_jobs import get_chunk_manifest_path, get_chunks_dir
from studyforge.core.digest_jobs import get_local_digest_dir
from studyforge.core.extraction_jobs import find_source_by_id
from studyforge.core.sources import resolve_course_path
from studyforge.study.flashcards import get_flashcard_output_paths
from studyforge.study.study_pack import STUDY_OUTPUTS_BASE

APP_DATA_DIR = Path("08_App_Data")
EVIDENCE_TRACES_DIR = APP_DATA_DIR / "reports" / "evidence_traces"


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _file_exists(path: Path | None) -> bool:
    return path is not None and path.is_file()


def _resolve_path(registry_path: str | None, default_path: Path) -> Path:
    if registry_path:
        candidate = Path(registry_path)
        if candidate.is_file():
            return candidate
    return default_path


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def get_evidence_trace_dir(course_path: Path) -> Path:
    """Return ``08_App_Data/reports/evidence_traces/``."""
    path = course_path / EVIDENCE_TRACES_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_mentions_in_markdown(
    text: str,
    query: str,
    context_lines: int = 4,
) -> list[dict]:
    """Return snippets around lines containing ``query`` (case-insensitive)."""
    if not text.strip() or not query.strip():
        return []

    lines = text.splitlines()
    needle = query.lower()
    mentions: list[dict] = []
    seen_snippets: set[str] = set()

    for index, line in enumerate(lines):
        if needle not in line.lower():
            continue
        start = max(0, index - context_lines)
        end = min(len(lines), index + context_lines + 1)
        snippet = "\n".join(lines[start:end])
        if snippet in seen_snippets:
            continue
        seen_snippets.add(snippet)
        mentions.append(
            {
                "line_number": index + 1,
                "match_line": line.strip(),
                "snippet": snippet,
            }
        )

    return mentions


def get_source_trace_summary(
    course_name: str,
    source_id: str,
    root: Path | None = None,
) -> dict:
    """Summarize available evidence artifacts and paths for a source."""
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized)
    warnings: list[str] = []

    outputs_base = course_path / STUDY_OUTPUTS_BASE
    flashcard_paths = get_flashcard_output_paths(course_path, normalized)
    digest_dir = get_local_digest_dir(course_path, normalized)

    source_pdf = _resolve_path(
        entry.get("stored_path"),
        Path(entry.get("stored_path", "")),
    )
    extracted_text = _resolve_path(
        entry.get("extracted_text_path"),
        course_path
        / "02_Extracted_Text"
        / "extracted_sources"
        / f"{normalized}_extracted_text.md",
    )
    chunk_manifest = _resolve_path(
        entry.get("chunk_manifest_path"),
        get_chunk_manifest_path(course_path, normalized),
    )
    combined_digest = _resolve_path(
        entry.get("local_digest_path"),
        digest_dir / f"{normalized}_combined_local_digest.md",
    )
    digest_review_md = digest_dir / f"{normalized}_local_digest_review.md"
    digest_review_json = digest_dir / f"{normalized}_local_digest_review.json"

    intermediate_audit = _resolve_path(
        entry.get("latest_intermediate_audit_path"),
        Path(entry.get("latest_intermediate_audit_path", "")),
    )
    final_audit = _resolve_path(
        entry.get("latest_final_audit_path"),
        Path(entry.get("latest_final_audit_path", "")),
    )
    study_guide = _resolve_path(
        entry.get("final_study_guide_path"),
        outputs_base / "study_guides" / f"{normalized}_final_study_guide.md",
    )
    flashcards = _resolve_path(
        entry.get("flashcards_path"),
        flashcard_paths["markdown"],
    )
    practice_quiz = _resolve_path(
        entry.get("practice_quiz_path"),
        outputs_base / "quizzes" / f"{normalized}_practice_quiz.md",
    )
    active_recall = _resolve_path(
        entry.get("active_recall_path"),
        outputs_base / "active_recall" / f"{normalized}_active_recall.md",
    )
    study_manifest = _resolve_path(
        entry.get("study_pack_manifest_path"),
        outputs_base / f"{normalized}_study_pack_manifest.json",
    )

    available = {
        "source_pdf": _file_exists(source_pdf),
        "extracted_text": _file_exists(extracted_text),
        "chunk_manifest": _file_exists(chunk_manifest),
        "local_digest": _file_exists(combined_digest),
        "digest_review": _file_exists(digest_review_md) or _file_exists(digest_review_json),
        "intermediate_audit": _file_exists(intermediate_audit),
        "final_audit": _file_exists(final_audit),
        "study_pack": _file_exists(study_manifest) or _file_exists(study_guide),
        "flashcards": _file_exists(flashcards),
        "active_recall": _file_exists(active_recall),
    }

    if entry.get("stored_path") and not available["source_pdf"]:
        warnings.append(f"Source PDF missing: {entry.get('stored_path')}")
    if entry.get("extracted_text_path") and not available["extracted_text"]:
        warnings.append(f"Extracted text missing: {entry.get('extracted_text_path')}")
    if entry.get("chunk_manifest_path") and not available["chunk_manifest"]:
        warnings.append(f"Chunk manifest missing: {entry.get('chunk_manifest_path')}")
    if not available["chunk_manifest"]:
        warnings.append("No chunk manifest — chunk-level trace unavailable.")

    paths = {
        "source_pdf": str(source_pdf.resolve()) if _file_exists(source_pdf) else "",
        "extracted_text": str(extracted_text.resolve()) if _file_exists(extracted_text) else "",
        "chunk_manifest": str(chunk_manifest.resolve()) if _file_exists(chunk_manifest) else "",
        "combined_local_digest": str(combined_digest.resolve()) if _file_exists(combined_digest) else "",
        "digest_review_md": str(digest_review_md.resolve()) if _file_exists(digest_review_md) else "",
        "latest_intermediate_audit": str(intermediate_audit.resolve())
        if _file_exists(intermediate_audit)
        else "",
        "latest_final_audit": str(final_audit.resolve()) if _file_exists(final_audit) else "",
        "final_study_guide": str(study_guide.resolve()) if _file_exists(study_guide) else "",
        "flashcards": str(flashcards.resolve()) if _file_exists(flashcards) else "",
        "practice_quiz": str(practice_quiz.resolve()) if _file_exists(practice_quiz) else "",
        "active_recall": str(active_recall.resolve()) if _file_exists(active_recall) else "",
    }

    return {
        "course": course_path.name,
        "source_id": normalized,
        "title": title,
        "registry_status": str(entry.get("status", "added")),
        "available_artifacts": available,
        "paths": paths,
        "warnings": warnings,
    }


def list_source_chunks(
    course_name: str,
    source_id: str,
    root: Path | None = None,
) -> list[dict]:
    """Load chunk manifest entries for a source."""
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized = _normalize_source_id(entry["id"])
    manifest_path = _resolve_path(
        entry.get("chunk_manifest_path"),
        get_chunk_manifest_path(course_path, normalized),
    )
    if not manifest_path.is_file():
        return []

    try:
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []

    chunks: list[dict] = []
    for item in manifest.get("chunks", []):
        chunk_id = str(item.get("chunk_id", "")).strip()
        if not chunk_id:
            continue
        file_path = item.get("file_path", "")
        if not file_path:
            file_path = str((get_chunks_dir(course_path, normalized) / f"{chunk_id}.md").resolve())
        chunks.append(
            {
                "chunk_id": chunk_id,
                "chunk_number": int(item.get("chunk_number", 0)),
                "page_start": item.get("page_start"),
                "page_end": item.get("page_end"),
                "word_count": int(item.get("word_count", 0)),
                "file_path": file_path,
            }
        )

    chunks.sort(key=lambda chunk: chunk.get("chunk_number", 0))
    return chunks


def _chunk_info_for_id(chunks: list[dict], chunk_id: str) -> dict | None:
    normalized = chunk_id.strip().upper()
    for chunk in chunks:
        if str(chunk.get("chunk_id", "")).upper() == normalized:
            return chunk
    return None


def _load_artifact_mentions(path: Path, chunk_id: str) -> list[dict]:
    if not path.is_file():
        return []
    return find_mentions_in_markdown(_read_text(path), chunk_id)


def get_chunk_trace(
    course_name: str,
    source_id: str,
    chunk_id: str,
    root: Path | None = None,
) -> dict:
    """Build an evidence trace for one chunk across digest and audits."""
    summary = get_source_trace_summary(course_name, source_id, root=root)
    normalized = summary["source_id"]
    course_path = resolve_course_path(course_name, root)
    chunks = list_source_chunks(course_name, source_id, root=root)
    chunk_info = _chunk_info_for_id(chunks, chunk_id)
    warnings = list(summary.get("warnings") or [])

    if chunk_info is None:
        warnings.append(f"Chunk not found in manifest: {chunk_id}")
        chunk_info = {"chunk_id": chunk_id.strip().upper()}

    resolved_chunk_id = str(chunk_info.get("chunk_id", chunk_id)).strip().upper()
    chunk_path = Path(chunk_info.get("file_path", ""))
    if not chunk_path.is_file():
        chunk_path = get_chunks_dir(course_path, normalized) / f"{resolved_chunk_id}.md"

    source_chunk_text = _read_text(chunk_path) if chunk_path.is_file() else ""
    if not chunk_path.is_file():
        warnings.append(f"Source chunk file missing: {chunk_path}")

    digest_path = get_local_digest_dir(course_path, normalized) / f"{resolved_chunk_id}_digest.md"
    digest_text = _read_text(digest_path) if digest_path.is_file() else ""
    if not digest_path.is_file():
        warnings.append(f"Local digest chunk missing: {digest_path}")

    digest_review_path = Path(summary["paths"].get("digest_review_md", ""))
    intermediate_path = Path(summary["paths"].get("latest_intermediate_audit", ""))
    final_path = Path(summary["paths"].get("latest_final_audit", ""))

    digest_review_mentions = _load_artifact_mentions(digest_review_path, resolved_chunk_id)
    intermediate_mentions = _load_artifact_mentions(intermediate_path, resolved_chunk_id)
    final_mentions = _load_artifact_mentions(final_path, resolved_chunk_id)

    if digest_review_path.is_file() and not digest_review_mentions:
        warnings.append(f"No digest review mentions found for {resolved_chunk_id}.")
    if intermediate_path.is_file() and not intermediate_mentions:
        warnings.append(f"No intermediate audit mentions found for {resolved_chunk_id}.")
    if final_path.is_file() and not final_mentions:
        warnings.append(f"No final audit mentions found for {resolved_chunk_id}.")

    return {
        "course": summary["course"],
        "source_id": normalized,
        "chunk_id": resolved_chunk_id,
        "chunk_info": chunk_info,
        "source_chunk": {
            "path": str(chunk_path.resolve()) if chunk_path.is_file() else str(chunk_path),
            "exists": chunk_path.is_file(),
            "text": source_chunk_text,
        },
        "local_digest_chunk": {
            "path": str(digest_path.resolve()) if digest_path.is_file() else str(digest_path),
            "exists": digest_path.is_file(),
            "text": digest_text,
        },
        "digest_review_mentions": digest_review_mentions,
        "intermediate_audit_mentions": intermediate_mentions,
        "final_audit_mentions": final_mentions,
        "warnings": warnings,
    }


def _format_mentions(mentions: list[dict], empty_label: str) -> str:
    if not mentions:
        return empty_label
    parts: list[str] = []
    for mention in mentions:
        parts.append(f"Line {mention.get('line_number', '?')}:")
        parts.append(str(mention.get("snippet", "")))
        parts.append("")
    return "\n".join(parts).strip()


def build_chunk_trace_markdown(trace: dict) -> str:
    """Render a chunk evidence trace as Markdown."""
    chunk_info = trace.get("chunk_info") or {}
    page_start = chunk_info.get("page_start", "?")
    page_end = chunk_info.get("page_end", "?")
    word_count = chunk_info.get("word_count", "?")

    source_chunk = trace.get("source_chunk") or {}
    digest_chunk = trace.get("local_digest_chunk") or {}

    lines = [
        f"# Evidence Trace — {trace.get('chunk_id', '')}",
        "",
        f"Course: {trace.get('course', '')}",
        f"Source: {trace.get('source_id', '')}",
        f"Pages: {page_start}–{page_end}",
        f"Words: {word_count}",
        "",
        "## Source Chunk",
        "",
        source_chunk.get("text") or "_(missing)_",
        "",
        "## Local Digest Chunk",
        "",
        digest_chunk.get("text") or "_(missing)_",
        "",
        "## Digest Review Mentions",
        "",
        _format_mentions(
            trace.get("digest_review_mentions") or [],
            "_(no mentions found)_",
        ),
        "",
        "## Intermediate Audit Mentions",
        "",
        _format_mentions(
            trace.get("intermediate_audit_mentions") or [],
            "_(no mentions found)_",
        ),
        "",
        "## Final Audit Mentions",
        "",
        _format_mentions(
            trace.get("final_audit_mentions") or [],
            "_(no mentions found)_",
        ),
        "",
        "## Warnings",
        "",
    ]
    warnings = trace.get("warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def export_chunk_trace(
    course_name: str,
    source_id: str,
    chunk_id: str,
    root: Path | None = None,
) -> Path:
    """Write chunk evidence trace Markdown under 08_App_Data/reports/evidence_traces/."""
    course_path = resolve_course_path(course_name, root)
    trace = get_chunk_trace(course_name, source_id, chunk_id, root=root)
    output_dir = get_evidence_trace_dir(course_path)
    output_path = output_dir / f"{trace['chunk_id']}_evidence_trace.md"
    output_path.write_text(build_chunk_trace_markdown(trace), encoding="utf-8")
    return output_path
