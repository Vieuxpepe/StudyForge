"""
Run intermediate audits via Google AI (Gemma 4 on Gemini API).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from studyforge.audits.intermediate_import import import_intermediate_audit
from studyforge.audits.intermediate_packet import (
    LocalDigestNotFoundError,
    build_intermediate_audit_instructions,
    collect_intermediate_audit_items,
)
from studyforge.core.extraction_jobs import find_source_by_id
from studyforge.core.secrets import get_google_api_key
from studyforge.core.sources import resolve_course_path
from studyforge.llm.google_genai_client import (
    DEFAULT_GEMMA_4_26B_MODEL,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    GoogleGenAIAPIError,
    GoogleGenAIConfigError,
    GoogleGenAIConnectionError,
    generate_content,
)


def build_chunk_audit_user_message(
    chunk_id: str,
    source_chunk_text: str,
    digest_chunk_text: str,
) -> str:
    return f"""Audit item — Chunk ID: {chunk_id}

## Source chunk (authority)

{source_chunk_text}

---

## Local digest (to verify)

{digest_chunk_text}

---

Apply the audit instructions. Report findings for this chunk only.
Use the chunk ID {chunk_id} in every issue entry.
"""


def _assemble_audit_markdown(
    *,
    course_name: str,
    source_id: str,
    title: str,
    model: str,
    chunk_sections: list[tuple[str, str]],
    warnings: list[str],
) -> str:
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "# Intermediate Audit (Google AI)",
        "",
        "Course:",
        course_name,
        "",
        "Source:",
        f"{source_id} - {title}",
        "",
        "Model:",
        model,
        "",
        "Generated:",
        generated_at,
        "",
        "Auditor:",
        "Google AI (automated)",
        "",
    ]
    if warnings:
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"* {warning}")
        lines.append("")

    lines.extend(["---", ""])

    for chunk_id, section_text in chunk_sections:
        lines.extend(
            [
                f"## Audit — {chunk_id}",
                "",
                section_text,
                "",
                "---",
                "",
            ]
        )

    return "\n".join(lines)


def run_intermediate_audit_for_source(
    course_name: str,
    source_id: str,
    *,
    model: str = DEFAULT_GEMMA_4_26B_MODEL,
    api_key: str | None = None,
    limit_chunks: int | None = None,
    only_needs_review: bool = False,
    max_output_tokens: int = 8192,
    request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    root: Path | None = None,
    notes: str | None = None,
) -> dict:
    """
    Run an automated intermediate audit with Google AI and import the result.

    Calls the API once per selected chunk (respecting rate limits), then saves
    a versioned audit file via ``import_intermediate_audit``.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = entry["id"].strip().upper()
    title = entry.get("title", normalized_id)

    resolved_key = api_key or get_google_api_key(root)
    if not resolved_key:
        raise GoogleGenAIConfigError(
            "Google API key not configured. Set GOOGLE_API_KEY, add "
            "google_api_key to config/local_secrets.json, or pass api_key=."
        )

    try:
        items, warnings = collect_intermediate_audit_items(
            course_name,
            source_id,
            limit_chunks=limit_chunks,
            only_needs_review=only_needs_review,
            root=root,
        )
    except LocalDigestNotFoundError:
        raise

    if not items:
        raise ValueError("No chunks selected for intermediate audit.")

    instructions = build_intermediate_audit_instructions()
    chunk_sections: list[tuple[str, str]] = []
    api_errors: list[str] = []

    for index, item in enumerate(items):
        chunk_id = item["chunk_id"]
        user_message = build_chunk_audit_user_message(
            chunk_id,
            item["source_chunk_text"],
            item["digest_chunk_text"],
        )

        try:
            section_text = generate_content(
                api_key=resolved_key,
                model=model,
                system_instruction=instructions,
                user_text=user_message,
                max_output_tokens=max_output_tokens,
                disable_thinking=True,
            )
            chunk_sections.append((chunk_id, section_text))
        except (GoogleGenAIConnectionError, GoogleGenAIAPIError) as exc:
            api_errors.append(f"{chunk_id}: {exc}")
            chunk_sections.append((chunk_id, f"_Audit API error: {exc}_"))

        if index < len(items) - 1 and request_interval_seconds > 0:
            time.sleep(request_interval_seconds)

    if api_errors:
        warnings.extend(api_errors)

    audit_markdown = _assemble_audit_markdown(
        course_name=course_path.name,
        source_id=normalized_id,
        title=title,
        model=model,
        chunk_sections=chunk_sections,
        warnings=warnings,
    )

    import_notes = notes or f"Automated run; model={model}; chunks={len(items)}"
    import_summary = import_intermediate_audit(
        course_name,
        source_id,
        audit_text=audit_markdown,
        auditor_name=f"Google AI ({model})",
        notes=import_notes,
        root=root,
    )

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "model": model,
        "chunk_count": len(items),
        "selected_chunks": [item["chunk_id"] for item in items],
        "audit_id": import_summary.get("audit_id"),
        "saved_path": import_summary.get("saved_path"),
        "warnings": warnings,
        "api_errors": api_errors,
        "status": "failed" if api_errors and len(api_errors) == len(items) else "imported",
    }
