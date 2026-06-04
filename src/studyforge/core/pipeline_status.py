"""
Inspect pipeline progress for a course source and recommend the next step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from studyforge.audits.final_packet import FINAL_AUDIT_BASE
from studyforge.audits.intermediate_packet import INTERMEDIATE_AUDIT_BASE
from studyforge.core.chunking_jobs import get_chunk_manifest_path
from studyforge.core.digest_jobs import get_local_digest_dir, get_local_digest_log_path
from studyforge.core.extraction_jobs import find_source_by_id
from studyforge.core.secrets import get_google_api_key
from studyforge.core.sources import resolve_course_path

STUDY_OUTPUTS_BASE = Path("06_Study_Outputs")

STEP_ORDER: tuple[tuple[str, str], ...] = (
    ("source_registered", "Source registered"),
    ("extracted", "PDF extracted"),
    ("chunked", "Text chunked"),
    ("local_digest", "Local digest (LM Studio)"),
    ("local_digest_review", "Local digest review"),
    ("intermediate_audit", "Intermediate audit"),
    ("final_audit", "Final audit"),
    ("study_pack_generated", "Study pack generated"),
)

_NEXT_ACTIONS: dict[str, dict[str, str]] = {
    "source_missing": {
        "label": "Fix or re-register source file",
        "reason": "The stored source file path is missing on disk.",
        "gui_hint": "Sources page — upload or re-add the PDF.",
    },
    "extract_pdf": {
        "label": "Extract PDF",
        "reason": "Source is registered but extracted text is not available yet.",
        "gui_hint": "Pipeline — step 1: Extract PDF.",
    },
    "chunk_source": {
        "label": "Chunk source",
        "reason": "Extraction is done but chunks have not been created.",
        "gui_hint": "Pipeline — step 2: Chunk source.",
    },
    "run_local_digest": {
        "label": "Run local digest",
        "reason": "Source is chunked but no local LM Studio digest exists yet.",
        "gui_hint": "Pipeline — step 4: Run full local digest.",
    },
    "review_local_digest": {
        "label": "Review local digest",
        "reason": "Local digest exists but rule-based review has not been run.",
        "gui_hint": "Pipeline — step 5: Review local digest.",
    },
    "export_or_run_intermediate_audit": {
        "label": "Run or import intermediate audit",
        "reason": "Local digest is ready but no intermediate audit has been imported.",
        "gui_hint": "Audits — Run intermediate audit (Google AI) or export/import packet.",
    },
    "export_final_audit_packet": {
        "label": "Export or import final audit",
        "reason": "Intermediate audit is done but final audit has not been imported.",
        "gui_hint": "Audits — export final audit packet, then import ChatGPT result.",
    },
    "generate_study_pack": {
        "label": "Generate study pack",
        "reason": "Final audit exists, but no study pack has been generated yet.",
        "gui_hint": "Pipeline — Study Pack section: Generate study pack.",
    },
    "study_pack_ready": {
        "label": "Study pack ready",
        "reason": "You can study with the guide, flashcards, quiz, and active recall files.",
        "gui_hint": "Open files under 06_Study_Outputs/ for this source.",
    },
}


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _file_exists(path_str: str | None) -> bool:
    if not path_str:
        return False
    return Path(path_str).is_file()


def _load_chunk_count(manifest_path: Path) -> int | None:
    if not manifest_path.is_file():
        return None
    try:
        with manifest_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    chunks = data.get("chunks")
    if isinstance(chunks, list):
        return len(chunks)
    return data.get("chunk_count")


def _count_chunk_digests(digest_dir: Path, source_id: str) -> int:
    if not digest_dir.is_dir():
        return 0
    suffix = "_digest.md"
    combined = f"{source_id}_combined_local_digest.md"
    count = 0
    for path in digest_dir.glob(f"*{suffix}"):
        if path.name == combined or "review" in path.name.lower():
            continue
        if "CHUNK" in path.name:
            count += 1
    return count


def _packet_paths(course_path: Path, source_id: str) -> dict[str, Path | None]:
    normalized = _normalize_source_id(source_id)
    ia_dir = course_path / INTERMEDIATE_AUDIT_BASE / normalized
    fa_dir = course_path / FINAL_AUDIT_BASE / normalized
    ia_md = ia_dir / f"{normalized}_intermediate_audit_packet.md"
    ia_json = ia_dir / f"{normalized}_intermediate_audit_packet.json"
    fa_md = fa_dir / f"{normalized}_final_audit_packet.md"
    fa_json = fa_dir / f"{normalized}_final_audit_packet.json"
    return {
        "intermediate_packet_md": ia_md if ia_md.is_file() else None,
        "intermediate_packet_json": ia_json if ia_json.is_file() else None,
        "final_packet_md": fa_md if fa_md.is_file() else None,
        "final_packet_json": fa_json if fa_json.is_file() else None,
    }


def _build_next_action(key: str, extra_reason: str | None = None) -> dict[str, str]:
    base = dict(_NEXT_ACTIONS[key])
    base["key"] = key
    if extra_reason:
        base["reason"] = f"{base['reason']} {extra_reason}".strip()
    return base


def _determine_next_action(
    steps: dict[str, dict[str, Any]],
    warnings: list[str],
) -> dict[str, str]:
    if not steps["source_registered"]["done"]:
        return _build_next_action("source_missing")
    if not steps["extracted"]["done"]:
        return _build_next_action("extract_pdf")
    if not steps["chunked"]["done"]:
        return _build_next_action("chunk_source")
    if not steps["local_digest"]["done"]:
        return _build_next_action("run_local_digest")
    if not steps["local_digest_review"]["done"]:
        return _build_next_action("review_local_digest")
    if not steps["intermediate_audit"]["done"]:
        hint = ""
        if get_google_api_key():
            hint = "Google API key is configured — you can use automated audit on Audits."
        return _build_next_action("export_or_run_intermediate_audit", hint or None)
    if not steps["final_audit"]["done"]:
        return _build_next_action("export_final_audit_packet")
    if not steps["study_pack_generated"]["done"]:
        return _build_next_action("generate_study_pack")
    return _build_next_action("study_pack_ready")


def get_pipeline_status(
    course_name: str,
    source_id: str,
    root: Path | None = None,
) -> dict:
    """
    Inspect registry entries and on-disk artifacts for one source.

    Returns course/source metadata, per-step checklist, warnings, and next_action.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)
    registry_status = str(entry.get("status", "added"))
    warnings: list[str] = []

    stored_path = Path(entry.get("stored_path", ""))
    source_registered = stored_path.is_file()
    if entry.get("stored_path") and not source_registered:
        warnings.append(f"Stored source file missing: {stored_path}")

    extracted_path = entry.get("extracted_text_path", "")
    extraction_log = entry.get("extraction_log_path", "")
    extracted = _file_exists(extracted_path)
    if entry.get("extracted_text_path") and not extracted:
        warnings.append(f"Extracted text file missing: {extracted_path}")
    if extracted and not _file_exists(extraction_log):
        warnings.append(f"Extraction log missing: {extraction_log}")

    manifest_path = get_chunk_manifest_path(course_path, normalized_id)
    chunk_count = _load_chunk_count(manifest_path)
    chunked = manifest_path.is_file() and chunk_count is not None and chunk_count > 0
    if entry.get("chunk_manifest_path") and not manifest_path.is_file():
        warnings.append(f"Chunk manifest missing: {manifest_path}")
    chunk_detail = f"{chunk_count} chunks" if chunk_count else ""

    digest_dir = get_local_digest_dir(course_path, normalized_id)
    combined_path = Path(entry.get("local_digest_path", ""))
    if not combined_path.is_file():
        combined_path = digest_dir / f"{normalized_id}_combined_local_digest.md"
    digest_log_path = Path(entry.get("local_digest_log_path", ""))
    if not digest_log_path.is_file():
        digest_log_path = get_local_digest_log_path(course_path, normalized_id)

    digest_count = _count_chunk_digests(digest_dir, normalized_id)
    local_digest = combined_path.is_file()
    if local_digest:
        digest_detail = f"combined digest on disk"
        if chunk_count:
            digest_detail += f"; {digest_count}/{chunk_count} chunk digests"
        if registry_status == "local_digest_partial":
            digest_detail += " (registry: partial)"
            if chunk_count and digest_count < chunk_count:
                warnings.append(
                    f"Local digest incomplete: {digest_count}/{chunk_count} chunk files."
                )
        elif registry_status == "local_digest_complete":
            digest_detail += " (complete)"
    else:
        digest_detail = ""
        if registry_status.startswith("local_digest"):
            warnings.append("Registry claims local digest but combined digest file is missing.")

    review_json = digest_dir / f"{normalized_id}_local_digest_review.json"
    review_md = digest_dir / f"{normalized_id}_local_digest_review.md"
    local_digest_review = review_json.is_file() or review_md.is_file()
    review_detail = ""
    if local_digest_review:
        parts = []
        if review_json.is_file():
            parts.append("JSON review")
        if review_md.is_file():
            parts.append("Markdown report")
        review_detail = ", ".join(parts)

    ia_path = entry.get("latest_intermediate_audit_path", "")
    intermediate_audit = _file_exists(ia_path)
    ia_detail = ""
    if intermediate_audit:
        ia_detail = Path(ia_path).name
        if entry.get("latest_intermediate_audit_id"):
            ia_detail = f"{entry['latest_intermediate_audit_id']} — {ia_detail}"

    fa_path = entry.get("latest_final_audit_path", "")
    final_audit = _file_exists(fa_path)
    fa_detail = ""
    if final_audit:
        fa_detail = Path(fa_path).name
        if entry.get("latest_final_audit_id"):
            fa_detail = f"{entry['latest_final_audit_id']} — {fa_detail}"

    packets = _packet_paths(course_path, normalized_id)
    packet_notes: list[str] = []
    if packets["intermediate_packet_md"]:
        packet_notes.append("intermediate packet exported")
    if packets["final_packet_md"]:
        packet_notes.append("final packet exported")

    study_manifest_path = course_path / STUDY_OUTPUTS_BASE / f"{normalized_id}_study_pack_manifest.json"
    registry_study_manifest = entry.get("study_pack_manifest_path", "")
    if registry_study_manifest and not study_manifest_path.is_file():
        study_manifest_path = Path(registry_study_manifest)
    study_pack_done = study_manifest_path.is_file()
    pack_detail = study_manifest_path.name if study_pack_done else ""
    if entry.get("study_pack_manifest_path") and not study_pack_done:
        warnings.append(
            f"Registry lists study pack manifest but file is missing: {study_manifest_path}"
        )

    steps: dict[str, dict[str, Any]] = {
        "source_registered": {
            "done": source_registered,
            "details": str(stored_path) if source_registered else "",
        },
        "extracted": {
            "done": extracted,
            "details": str(extracted_path) if extracted else "",
        },
        "chunked": {
            "done": chunked,
            "details": chunk_detail,
        },
        "local_digest": {
            "done": local_digest,
            "details": digest_detail,
        },
        "local_digest_review": {
            "done": local_digest_review,
            "details": review_detail,
        },
        "intermediate_audit": {
            "done": intermediate_audit,
            "details": ia_detail,
        },
        "final_audit": {
            "done": final_audit,
            "details": fa_detail,
        },
        "study_pack_generated": {
            "done": study_pack_done,
            "details": pack_detail,
        },
    }

    if packet_notes:
        warnings.append("Optional packets on disk: " + "; ".join(packet_notes))

    completed_steps = [label for key, label in STEP_ORDER if steps[key]["done"]]
    missing_steps = [label for key, label in STEP_ORDER if not steps[key]["done"]]

    next_action = _determine_next_action(steps, warnings)

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "registry_status": registry_status,
        "steps": steps,
        "completed_steps": completed_steps,
        "missing_steps": missing_steps,
        "warnings": warnings,
        "next_action": next_action,
        "artifacts": {
            "stored_path": str(stored_path) if source_registered else None,
            "extracted_text_path": extracted_path or None,
            "chunk_manifest_path": str(manifest_path) if manifest_path.is_file() else None,
            "chunk_count": chunk_count,
            "local_digest_path": str(combined_path) if local_digest else None,
            "local_digest_review_json": str(review_json) if review_json.is_file() else None,
            "latest_intermediate_audit_path": ia_path or None,
            "latest_final_audit_path": fa_path or None,
            "study_pack_manifest_path": str(study_manifest_path)
            if study_manifest_path.is_file()
            else None,
        },
    }
