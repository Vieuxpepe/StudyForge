"""
Run local LM Studio digests for chunked course sources.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.chunking_jobs import get_chunk_manifest_path
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import (
    load_source_registry,
    resolve_course_path,
    save_source_registry,
)
from studyforge.llm.digest_prompts import build_local_digest_messages
from studyforge.study.digest_review import check_required_sections
from studyforge.llm.lm_studio_client import (
    DEFAULT_BASE_URL,
    LMStudioAPIError,
    LMStudioConnectionError,
    chat_completion,
    check_lm_studio_connection,
    choose_default_model,
)

LOCAL_DIGEST_BASE = Path("03_Local_Digests")
JOB_LOGS_DIR = Path("08_App_Data") / "job_logs"

DEFAULT_DIGEST_MAX_TOKENS = 6000
DIGEST_RETRY_MAX_TOKENS_BONUS = 2000
MAX_DIGEST_COMPLETION_ATTEMPTS = 2

# Statuses that mean chunking is done and digest may run
_CHUNKED_STATUSES = frozenset(
    {"chunked", "local_digest_complete", "local_digest_partial"}
)


class SourceNotChunkedError(Exception):
    """Raised when the source has not been chunked yet."""


class DigestOutputExistsError(Exception):
    """Raised when digest output exists and overwrite was not requested."""


class LMStudioNotAvailableError(Exception):
    """Raised when LM Studio is not reachable or has no models."""


def get_local_digest_dir(course_path: Path, source_id: str) -> Path:
    """Return 03_Local_Digests/<source_id>/ (creates if missing)."""
    normalized = source_id.strip().upper()
    path = course_path / LOCAL_DIGEST_BASE / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_local_digest_log_path(course_path: Path, source_id: str) -> Path:
    """Return 08_App_Data/job_logs/<source_id>_local_digest_log.json."""
    normalized = source_id.strip().upper()
    path = course_path / JOB_LOGS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{normalized}_local_digest_log.json"


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def _update_registry_entry(registry: dict, source_id: str, updates: dict) -> None:
    normalized = _normalize_source_id(source_id)
    for entry in registry.get("sources", []):
        if str(entry.get("id", "")).upper() == normalized:
            entry.update(updates)
            return
    raise SourceNotFoundError(f"Source not found in registry: {source_id}")


def _chunk_digest_path(digest_dir: Path, chunk_id: str) -> Path:
    return digest_dir / f"{chunk_id}_digest.md"


def _existing_chunk_digest_ids(digest_dir: Path) -> set[str]:
    """Return chunk IDs that already have per-chunk digest markdown on disk."""
    if not digest_dir.is_dir():
        return set()
    ids: set[str] = set()
    for path in digest_dir.glob("*_digest.md"):
        if "combined" in path.name.lower():
            continue
        ids.add(path.stem.removesuffix("_digest"))
    return ids


def _digest_has_output(digest_dir: Path) -> bool:
    if not digest_dir.is_dir():
        return False
    return bool(_existing_chunk_digest_ids(digest_dir)) or any(
        digest_dir.glob("*_combined_local_digest.md")
    )


def _manifest_chunk_ids(manifest: dict) -> list[str]:
    return [str(c.get("chunk_id", "")) for c in manifest.get("chunks", []) if c.get("chunk_id")]


def _clear_digest_outputs(digest_dir: Path) -> None:
    """Remove generated digest markdown for one source (not the folder)."""
    if not digest_dir.is_dir():
        return
    for path in digest_dir.iterdir():
        if path.is_file() and path.suffix.lower() == ".md":
            path.unlink()


def digest_has_required_sections(text: str) -> bool:
    """True when all required ## sections appear in a chunk digest."""
    return not check_required_sections(text)["missing"]


def _read_chunk_digest_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _complete_chunk_digest_ids(digest_dir: Path) -> set[str]:
    """Chunk IDs whose on-disk digest includes every required section."""
    complete: set[str] = set()
    for chunk_id in _existing_chunk_digest_ids(digest_dir):
        path = _chunk_digest_path(digest_dir, chunk_id)
        if digest_has_required_sections(_read_chunk_digest_text(path)):
            complete.add(chunk_id)
    return complete


def _generate_chunk_digest(
    *,
    messages: list[dict],
    chunk_id: str,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> tuple[str, list[str]]:
    """
    Call LM Studio up to MAX_DIGEST_COMPLETION_ATTEMPTS times until required
    sections are present, or return the last attempt with warnings.
    """
    warnings: list[str] = []
    digest_text = ""
    prior_text = ""

    for attempt in range(MAX_DIGEST_COMPLETION_ATTEMPTS):
        attempt_tokens = max_tokens + (attempt * DIGEST_RETRY_MAX_TOKENS_BONUS)
        if attempt == 0:
            attempt_messages = messages
        else:
            missing = check_required_sections(prior_text)["missing"]
            attempt_messages = messages + [
                {"role": "assistant", "content": prior_text},
                {
                    "role": "user",
                    "content": (
                        f"Your previous digest for {chunk_id} was incomplete. "
                        f"Missing sections: {', '.join(missing)}.\n\n"
                        "Reply with the COMPLETE markdown digest again. Include "
                        "every required ## heading from Big Picture through "
                        "Source References. Do not stop until ## Source References "
                        "is finished."
                    ),
                },
            ]

        digest_text = chat_completion(
            messages=attempt_messages,
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=attempt_tokens,
            timeout=timeout,
        )
        prior_text = digest_text
        missing = check_required_sections(digest_text)["missing"]
        if not missing:
            return digest_text, warnings

        if attempt < MAX_DIGEST_COMPLETION_ATTEMPTS - 1:
            warnings.append(
                f"{chunk_id}: incomplete digest (missing: {', '.join(missing)}); retrying."
            )

    missing = check_required_sections(digest_text)["missing"]
    if missing:
        warnings.append(
            f"{chunk_id}: still incomplete after {MAX_DIGEST_COMPLETION_ATTEMPTS} "
            f"attempt(s); missing: {', '.join(missing)}."
        )
    return digest_text, warnings


def _load_chunk_manifest(manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Chunk manifest not found: {manifest_path}")
    with manifest_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def run_local_digest_for_source(
    course_name: str,
    source_id: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = DEFAULT_DIGEST_MAX_TOKENS,
    timeout: int = 300,
    limit_chunks: int | None = None,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Run LM Studio digests for each chunk in a source's chunk manifest.

    Returns:
        Summary dict for CLI display.

    Raises:
        SourceNotFoundError, SourceNotChunkedError, FileNotFoundError,
        DigestOutputExistsError, LMStudioNotAvailableError,
        LMStudioConnectionError, LMStudioAPIError.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    status = entry.get("status", "added")
    if status not in _CHUNKED_STATUSES:
        raise SourceNotChunkedError(
            f"Source {normalized_id} is not ready for digest (status: {status!r}).\n"
            "Run chunk_source.py first."
        )

    manifest_path = get_chunk_manifest_path(course_path, normalized_id)
    manifest = _load_chunk_manifest(manifest_path)
    chunk_entries = list(manifest.get("chunks", []))
    if not chunk_entries:
        raise ValueError(f"No chunks listed in manifest: {manifest_path}")

    if limit_chunks is not None and limit_chunks > 0:
        chunk_entries = chunk_entries[:limit_chunks]

    digest_dir = get_local_digest_dir(course_path, normalized_id)
    log_path = get_local_digest_log_path(course_path, normalized_id)

    manifest_total = len(manifest.get("chunks", []))
    all_chunk_ids = _manifest_chunk_ids(manifest)
    complete_digest_ids = _complete_chunk_digest_ids(digest_dir)
    run_chunk_ids = {str(c.get("chunk_id", "")) for c in chunk_entries}

    if _digest_has_output(digest_dir) and not overwrite:
        if limit_chunks is not None and limit_chunks > 0:
            already_done = run_chunk_ids <= complete_digest_ids
        else:
            already_done = set(all_chunk_ids) <= complete_digest_ids
        if already_done:
            raise DigestOutputExistsError(
                f"Local digest output already exists for {normalized_id}:\n"
                f"  - {digest_dir}\n"
                "Use --overwrite (or the Overwrite checkbox in the GUI) to "
                "replace existing digest files for this source."
            )

    if overwrite:
        _clear_digest_outputs(digest_dir)
        complete_digest_ids = set()

    connection = check_lm_studio_connection(base_url)
    if not connection.get("ok"):
        raise LMStudioNotAvailableError(
            connection.get("error") or "LM Studio is not available."
        )

    selected_model = model or choose_default_model(connection)
    if not selected_model:
        raise LMStudioNotAvailableError("No model available from LM Studio.")

    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    warnings: list[str] = []
    log_chunks: list[dict] = []
    digest_bodies: list[tuple[str, str]] = []  # (chunk_id, digest markdown)

    for chunk_info in chunk_entries:
        chunk_id = str(chunk_info.get("chunk_id", ""))
        input_path = Path(chunk_info.get("file_path", ""))
        output_path = _chunk_digest_path(digest_dir, chunk_id)

        record = {
            "chunk_id": chunk_id,
            "input_path": str(input_path.resolve()) if input_path.exists() else str(input_path),
            "output_path": str(output_path.resolve()),
            "status": "pending",
            "error": None,
        }

        if not input_path.is_file():
            record["status"] = "failed"
            record["error"] = f"Chunk file not found: {input_path}"
            warnings.append(record["error"])
            log_chunks.append(record)
            continue

        if not overwrite and output_path.is_file():
            existing_text = _read_chunk_digest_text(output_path)
            if digest_has_required_sections(existing_text):
                record["status"] = "skipped"
                record["error"] = None
                digest_bodies.append((chunk_id, existing_text))
                log_chunks.append(record)
                continue

        chunk_markdown = input_path.read_text(encoding="utf-8")
        messages = build_local_digest_messages(
            chunk_markdown=chunk_markdown,
            course_name=course_path.name,
            source_id=normalized_id,
            chunk_id=chunk_id,
        )

        try:
            digest_text, chunk_warnings = _generate_chunk_digest(
                messages=messages,
                chunk_id=chunk_id,
                model=selected_model,
                base_url=base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            warnings.extend(chunk_warnings)
            output_path.write_text(digest_text, encoding="utf-8")
            if digest_has_required_sections(digest_text):
                record["status"] = "complete"
            else:
                record["status"] = "incomplete"
                missing = check_required_sections(digest_text)["missing"]
                record["error"] = f"Missing sections: {', '.join(missing)}"
            digest_bodies.append((chunk_id, digest_text))
        except (LMStudioConnectionError, LMStudioAPIError) as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            warnings.append(f"{chunk_id}: {exc}")

        log_chunks.append(record)

    combined_path = digest_dir / f"{normalized_id}_combined_local_digest.md"
    combined_sections: list[tuple[str, str]] = []
    for chunk_id in all_chunk_ids:
        chunk_digest_path = _chunk_digest_path(digest_dir, chunk_id)
        if chunk_digest_path.is_file():
            combined_sections.append(
                (chunk_id, chunk_digest_path.read_text(encoding="utf-8"))
            )
        else:
            warnings.append(f"Missing digest on disk after run: {chunk_id}")

    combined_lines = [
        "# Combined Local Digest",
        "",
        "Course:",
        course_path.name,
        "",
        "Source ID:",
        normalized_id,
        "",
        "Model:",
        selected_model,
        "",
        "Chunk count:",
        str(len(combined_sections)),
        "",
        "---",
        "",
    ]

    for chunk_id, digest_text in combined_sections:
        combined_lines.append(f"## {chunk_id}")
        combined_lines.append("")
        combined_lines.append(digest_text)
        combined_lines.append("")
        combined_lines.append("---")
        combined_lines.append("")

    combined_path.write_text("\n".join(combined_lines), encoding="utf-8")

    completed_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    digested_count = len(_existing_chunk_digest_ids(digest_dir))
    processed = sum(
        1 for c in log_chunks if c["status"] in ("complete", "skipped")
    )
    failed = sum(1 for c in log_chunks if c["status"] == "failed")
    total = len(log_chunks)

    incomplete = sum(1 for c in log_chunks if c["status"] == "incomplete")

    if (
        digested_count >= manifest_total
        and failed == 0
        and incomplete == 0
        and manifest_total > 0
    ):
        final_status = "local_digest_complete"
    elif processed > 0:
        final_status = "local_digest_partial"
    else:
        final_status = "local_digest_partial"
        warnings.append("No chunks were digested successfully.")

    job_log = {
        "job_type": "local_digest",
        "course": course_path.name,
        "source_id": normalized_id,
        "model": selected_model,
        "base_url": base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "chunk_count_total": total,
        "chunk_count_processed": processed,
        "chunk_count_failed": failed,
        "date_started": started_at,
        "date_completed": completed_at,
        "chunks": log_chunks,
        "warnings": warnings,
    }

    with log_path.open("w", encoding="utf-8") as handle:
        json.dump(job_log, handle, indent=2)
        handle.write("\n")

    registry = load_source_registry(course_path)
    _update_registry_entry(
        registry,
        normalized_id,
        {
            "status": final_status,
            "local_digest_path": str(combined_path.resolve()),
            "local_digest_log_path": str(log_path.resolve()),
            "date_local_digest": completed_at,
            "local_digest_model": selected_model,
        },
    )
    save_source_registry(course_path, registry)

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "model": selected_model,
        "chunk_count_processed": processed,
        "chunk_count_total": total,
        "chunk_count_failed": failed,
        "combined_digest_path": str(combined_path.resolve()),
        "log_path": str(log_path.resolve()),
        "status": final_status,
        "warnings": warnings,
    }
