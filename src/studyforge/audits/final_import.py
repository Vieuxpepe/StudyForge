"""
Import and version manual final audits (ChatGPT, etc.) — storage only.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.audits.final_packet import FINAL_AUDIT_BASE
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import (
    load_source_registry,
    resolve_course_path,
    save_source_registry,
)

_REGISTRY_SUFFIX = "_final_audit_registry.json"
_AUDIT_FILE_PATTERN = re.compile(
    r"^(?P<source_id>.+)_final_audit_v(?P<version>\d{3})\.md$",
    re.IGNORECASE,
)

_ALLOWED_STATUSES = frozenset(
    {"intermediate_audit_imported", "final_audit_imported"}
)


class FinalAuditNotReadyError(Exception):
    """Raised when intermediate audit has not been imported yet."""


class EmptyAuditError(ValueError):
    """Raised when audit content is empty."""


class AuditInputError(ValueError):
    """Raised when --file and --text are both or neither provided."""


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def get_final_audit_dir(course_path: Path, source_id: str) -> Path:
    """Return 05_Final_Audits/<source_id>/ (creates if missing)."""
    normalized = _normalize_source_id(source_id)
    path = course_path / FINAL_AUDIT_BASE / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_final_audit_registry_path(course_path: Path, source_id: str) -> Path:
    """Return path to the final audit registry JSON for a source."""
    normalized = _normalize_source_id(source_id)
    return get_final_audit_dir(course_path, normalized) / f"{normalized}{_REGISTRY_SUFFIX}"


def load_final_audit_registry(path: Path, source_id: str) -> dict:
    """Load final audit registry JSON, or return an empty registry if missing."""
    normalized = _normalize_source_id(source_id)
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if "audits" not in data or not isinstance(data["audits"], list):
            data["audits"] = []
        data["source_id"] = normalized
        return data
    return {"source_id": normalized, "audits": []}


def save_final_audit_registry(path: Path, registry: dict) -> None:
    """Write final audit registry JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2)
        handle.write("\n")


def _word_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


def _scan_versions_on_disk(audit_dir: Path, source_id: str) -> list[int]:
    """Find version numbers from existing final audit Markdown files."""
    versions: list[int] = []
    if not audit_dir.is_dir():
        return versions
    for path in audit_dir.glob("*.md"):
        if "packet" in path.name:
            continue
        match = _AUDIT_FILE_PATTERN.match(path.name)
        if match and match.group("source_id").upper() == source_id.upper():
            versions.append(int(match.group("version")))
    return versions


def get_next_final_audit_version(
    registry: dict,
    audit_dir: Path | None = None,
    source_id: str | None = None,
) -> int:
    """Determine the next final audit version (starts at 1)."""
    versions: list[int] = []
    for entry in registry.get("audits", []):
        try:
            versions.append(int(entry.get("version", 0)))
        except (TypeError, ValueError):
            continue

    sid = source_id or str(registry.get("source_id", ""))
    if audit_dir and sid:
        versions.extend(_scan_versions_on_disk(audit_dir, sid))

    if not versions:
        return 1
    return max(versions) + 1


def build_final_audit_file_name(source_id: str, version: int) -> str:
    """Build versioned filename, e.g. SRC-0001_final_audit_v001.md."""
    normalized = _normalize_source_id(source_id)
    return f"{normalized}_final_audit_v{version:03d}.md"


def build_final_audit_id(source_id: str, version: int) -> str:
    """Build audit ID, e.g. FA-SRC-0001-V001."""
    normalized = _normalize_source_id(source_id)
    return f"FA-{normalized}-V{version:03d}"


def _update_source_registry_entry(
    registry: dict, source_id: str, updates: dict
) -> None:
    normalized = _normalize_source_id(source_id)
    for entry in registry.get("sources", []):
        if str(entry.get("id", "")).upper() == normalized:
            entry.update(updates)
            return
    raise SourceNotFoundError(f"Source not found in registry: {source_id}")


def _read_audit_content(
    audit_text: str | None, audit_file: Path | None
) -> str:
    """Read audit body from inline text or a file (mutually exclusive)."""
    if audit_file is not None and audit_text is not None:
        raise AuditInputError("Provide only one of audit_text or audit_file, not both.")
    if audit_file is None and audit_text is None:
        raise AuditInputError("Provide audit_text or audit_file.")

    if audit_file is not None:
        path = Path(audit_file)
        if not path.is_file():
            raise FileNotFoundError(f"Audit file not found: {path}")
        return path.read_text(encoding="utf-8")

    return audit_text if audit_text is not None else ""


def import_final_audit(
    course_name: str,
    source_id: str,
    audit_text: str | None = None,
    audit_file: Path | None = None,
    auditor_name: str = "ChatGPT",
    notes: str | None = None,
    root: Path | None = None,
) -> dict:
    """
    Import a manual final audit as a new versioned Markdown file.

    Appends to the final audit registry and updates source_registry.json.
    Never overwrites previous audit versions.

    Returns:
        Summary dict for CLI output.
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    status = entry.get("status", "")
    if status not in _ALLOWED_STATUSES:
        raise FinalAuditNotReadyError(
            f"Source {normalized_id} is not ready for final audit import "
            f"(status: {status!r}). Import an intermediate audit first."
        )

    content = _read_audit_content(audit_text, audit_file)
    if not content.strip():
        raise EmptyAuditError("Audit content is empty.")

    audit_dir = get_final_audit_dir(course_path, normalized_id)
    registry_path = get_final_audit_registry_path(course_path, normalized_id)

    warnings: list[str] = []
    registry = load_final_audit_registry(registry_path, normalized_id)

    if not registry_path.is_file() and _scan_versions_on_disk(audit_dir, normalized_id):
        warnings.append(
            "Final audit registry was missing; next version was chosen from existing "
            "audit files on disk."
        )

    version = get_next_final_audit_version(registry, audit_dir, normalized_id)
    file_name = build_final_audit_file_name(normalized_id, version)
    audit_path = audit_dir / file_name

    if audit_path.exists():
        while audit_path.exists():
            version += 1
            file_name = build_final_audit_file_name(normalized_id, version)
            audit_path = audit_dir / file_name
        warnings.append(
            f"Expected new file was taken; using version {version:03d} instead."
        )

    audit_path.write_text(content, encoding="utf-8")
    imported_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    audit_id = build_final_audit_id(normalized_id, version)

    registry_entry = {
        "version": version,
        "audit_id": audit_id,
        "auditor_name": auditor_name,
        "file_path": str(audit_path.resolve()),
        "date_imported": imported_at,
        "notes": notes or "",
        "word_count": _word_count(content),
        "status": "imported",
    }
    registry.setdefault("audits", []).append(registry_entry)
    save_final_audit_registry(registry_path, registry)

    source_registry = load_source_registry(course_path)
    _update_source_registry_entry(
        source_registry,
        normalized_id,
        {
            "status": "final_audit_imported",
            "latest_final_audit_path": str(audit_path.resolve()),
            "latest_final_audit_id": audit_id,
            "date_final_audit_imported": imported_at,
        },
    )
    save_source_registry(course_path, source_registry)

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "audit_id": audit_id,
        "auditor_name": auditor_name,
        "version": version,
        "saved_path": str(audit_path.resolve()),
        "registry_path": str(registry_path.resolve()),
        "word_count": registry_entry["word_count"],
        "warnings": warnings,
    }
