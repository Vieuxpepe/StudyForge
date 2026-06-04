"""
Small helpers for the Streamlit GUI (no Streamlit imports here).
"""

from __future__ import annotations

from pathlib import Path

_POST_DIGEST_STATUSES = frozenset(
    {
        "local_digest_complete",
        "local_digest_partial",
        "intermediate_audit_imported",
        "final_audit_imported",
        "study_pack_generated",
    }
)


def source_pipeline_flags(entry: dict) -> dict[str, bool]:
    """Derive yes/no pipeline flags from a source_registry entry."""
    status = str(entry.get("status", "added"))
    return {
        "extracted": bool(entry.get("extracted_text_path"))
        or status in {"extracted", "chunked", *_POST_DIGEST_STATUSES},
        "chunked": bool(entry.get("chunk_manifest_path"))
        or status in {"chunked", *_POST_DIGEST_STATUSES},
        "local_digest": bool(entry.get("local_digest_path"))
        or status in {"local_digest_complete", "local_digest_partial"}
        or status.startswith("local_digest"),
        "intermediate_audit": bool(entry.get("latest_intermediate_audit_id"))
        or status
        in {"intermediate_audit_imported", "final_audit_imported", "study_pack_generated"},
        "final_audit": bool(entry.get("latest_final_audit_id"))
        or status in {"final_audit_imported", "study_pack_generated"},
    }


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def read_text_preview(path: Path, max_chars: int = 8000) -> str:
    """Read a text file for preview, or return an error message."""
    if not path.is_file():
        return f"(file not found: {path})"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n... (truncated)"
    return text
