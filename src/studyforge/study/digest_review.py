"""
Rule-based quality review for local LM Studio digests (no AI).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.chunking_jobs import get_chunk_manifest_path
from studyforge.core.digest_jobs import get_local_digest_dir
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import load_source_registry, resolve_course_path

# Expected placeholder when a section has no chunk support (not counted as uncertainty)
_EXPECTED_PLACEHOLDER_PHRASE = "not verified in this chunk"

# Phrases that suggest genuine uncertainty (matched case-insensitively)
_UNCERTAINTY_PHRASES = [
    "uncertain",
    "unclear",
    "missing source",
    "source does not say",
    "cannot determine",
]

DEFAULT_REQUIRED_SECTIONS = [
    "Big Picture",
    "Key Ideas",
    "Definitions",
    "Formulas / Rules / Methods",
    "Worked Examples from the Source",
    "Practice Questions",
    "Uncertain Claims",
    "Source References",
]

# Per-file and overall thresholds
_HIGH_UNCERTAINTY_PER_FILE = 5
_HIGH_UNCERTAINTY_TOTAL = 15

_DIGEST_COMPLETE_STATUSES = frozenset(
    {"local_digest_complete", "local_digest_partial"}
)


def count_uncertainty_markers(text: str) -> int:
    """
    Count uncertainty-related phrases in ``text`` (case-insensitive).

    Ignores the standard empty-section placeholder ("Not verified in this chunk.")
    so conservative digests are not flagged for following the template.
    """
    lowered = text.lower()
    scrubbed = lowered.replace(_EXPECTED_PLACEHOLDER_PHRASE, "")
    total = 0
    for phrase in _UNCERTAINTY_PHRASES:
        total += len(re.findall(re.escape(phrase), scrubbed))
    return total


def _word_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


def check_required_sections(
    text: str, required_sections: list[str] | None = None
) -> dict:
    """
    Check which required Markdown sections appear in ``text``.

    Looks for headings like ``## Big Picture`` or ``# Big Picture``.

    Returns:
        {
            "required_sections": [...],
            "present": [...],
            "missing": [...],
        }
    """
    sections = required_sections or DEFAULT_REQUIRED_SECTIONS
    present: list[str] = []
    missing: list[str] = []

    for section in sections:
        # Match ## Section or # Section (allow flexible spacing)
        pattern = re.compile(
            rf"^#{{1,2}}\s+{re.escape(section)}\s*$",
            re.MULTILINE | re.IGNORECASE,
        )
        if pattern.search(text):
            present.append(section)
        else:
            missing.append(section)

    return {
        "required_sections": list(sections),
        "present": present,
        "missing": missing,
    }


def review_digest_file(path: Path, min_words: int = 200) -> dict:
    """
    Review a single digest Markdown file with deterministic rules.

    Returns a dict with path, exists, word_count, uncertainty_markers,
    missing_sections, warnings, and status (ok | needs_review | failed).
    """
    warnings: list[str] = []
    result: dict = {
        "path": str(path.resolve()) if path else str(path),
        "exists": False,
        "word_count": 0,
        "uncertainty_markers": 0,
        "missing_sections": [],
        "warnings": warnings,
        "status": "failed",
    }

    if not path.is_file():
        warnings.append("Digest file is missing.")
        return result

    result["exists"] = True
    text = path.read_text(encoding="utf-8")
    result["word_count"] = _word_count(text)

    if not text.strip():
        warnings.append("Digest file is empty.")
        result["status"] = "failed"
        return result

    result["uncertainty_markers"] = count_uncertainty_markers(text)
    section_check = check_required_sections(text)
    result["missing_sections"] = section_check["missing"]

    if result["word_count"] < min_words:
        warnings.append(
            f"Digest is very short ({result['word_count']} words, minimum {min_words})."
        )

    if result["missing_sections"]:
        warnings.append(
            "Missing required sections: " + ", ".join(result["missing_sections"])
        )

    if result["uncertainty_markers"] >= _HIGH_UNCERTAINTY_PER_FILE:
        warnings.append(
            f"High uncertainty marker count ({result['uncertainty_markers']})."
        )

    result["status"] = "needs_review" if warnings else "ok"
    return result


def _load_json_if_exists(path: Path) -> dict | None:
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    return None


def _chunk_digest_paths(digest_dir: Path, source_id: str) -> list[Path]:
    """List per-chunk digest files (not combined or review artifacts)."""
    if not digest_dir.is_dir():
        return []
    suffix = "_digest.md"
    combined_name = f"{source_id}_combined_local_digest.md"
    review_prefix = f"{source_id}_local_digest_review"
    files = []
    for path in sorted(digest_dir.glob("*.md")):
        name = path.name
        if name == combined_name:
            continue
        if name.startswith(review_prefix):
            continue
        if name.endswith(suffix) and "CHUNK" in name:
            files.append(path)
    return files


def _build_markdown_report(summary: dict) -> str:
    """Render the review summary as readable Markdown."""
    lines = [
        "# Local Digest Review",
        "",
        "Course:",
        summary["course"],
        "",
        "Source:",
        f"{summary['source_id']} - {summary['title']}",
        "",
        "Overall status:",
        summary["overall_status"],
        "",
        "## Summary",
        "",
        f"* Expected chunks: {summary['chunk_count_expected']}",
        f"* Found chunk digests: {summary['chunk_count_found']}",
        f"* Failed chunks from log: {summary['failed_chunks_from_log']}",
        f"* Digests OK: {summary['digests_ok']}",
        f"* Digests needing review: {summary['digests_needing_review']}",
        f"* Digests failed: {summary['digests_failed']}",
        f"* Total uncertainty markers: {summary['total_uncertainty_markers']}",
        "",
        "## Warnings",
        "",
    ]

    if summary["warnings"]:
        for warning in summary["warnings"]:
            lines.append(f"* {warning}")
    else:
        lines.append("* None")

    lines.extend(["", "## Files Reviewed", ""])

    for file_review in summary.get("files", []):
        name = Path(file_review["path"]).name
        lines.extend(
            [
                f"### {name}",
                "",
                f"Status: {file_review['status']}",
                f"Word count: {file_review['word_count']}",
                f"Uncertainty markers: {file_review['uncertainty_markers']}",
            ]
        )
        missing = file_review.get("missing_sections") or []
        lines.append(
            "Missing sections: "
            + (", ".join(missing) if missing else "None")
        )
        file_warnings = file_review.get("warnings") or []
        if file_warnings:
            lines.append("Warnings:")
            for w in file_warnings:
                lines.append(f"* {w}")
        else:
            lines.append("Warnings: None")
        lines.append("")

    return "\n".join(lines) + "\n"


def review_local_digest_for_source(
    course_name: str,
    source_id: str,
    root: Path | None = None,
    min_words: int = 200,
) -> dict:
    """
    Review all local digest artifacts for a source and write JSON + Markdown reports.

    Does not modify source_registry.json or digest files.

    Returns:
        Summary dict (also written to review JSON/MD paths).
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = entry["id"].strip().upper()
    title = entry.get("title", normalized_id)
    registry_status = entry.get("status", "unknown")

    digest_dir = get_local_digest_dir(course_path, normalized_id)
    combined_path = digest_dir / f"{normalized_id}_combined_local_digest.md"

    log_path_str = entry.get("local_digest_log_path", "")
    log_path = Path(log_path_str) if log_path_str else None
    digest_log = _load_json_if_exists(log_path) if log_path else None

    # Expected chunks from manifest
    chunk_count_expected = 0
    expected_chunk_ids: list[str] = []
    manifest_path = get_chunk_manifest_path(course_path, normalized_id)
    manifest = _load_json_if_exists(manifest_path)
    if manifest:
        for chunk in manifest.get("chunks", []):
            cid = chunk.get("chunk_id")
            if cid:
                expected_chunk_ids.append(str(cid))
        chunk_count_expected = len(expected_chunk_ids)

    # Failed chunks from job log
    failed_chunks_from_log = 0
    log_chunk_ids: set[str] = set()
    if digest_log:
        for chunk_record in digest_log.get("chunks", []):
            cid = str(chunk_record.get("chunk_id", ""))
            if cid:
                log_chunk_ids.add(cid)
            if chunk_record.get("status") == "failed":
                failed_chunks_from_log += 1

    chunk_digest_paths = _chunk_digest_paths(digest_dir, normalized_id)
    chunk_count_found = len(chunk_digest_paths)

    file_reviews: list[dict] = []
    for digest_path in chunk_digest_paths:
        file_reviews.append(review_digest_file(digest_path, min_words=min_words))

    combined_review = review_digest_file(combined_path, min_words=min_words)
    combined_review["path"] = str(combined_path.resolve())
    file_reviews.append(combined_review)

    digests_ok = sum(1 for f in file_reviews if f["status"] == "ok")
    digests_needing_review = sum(1 for f in file_reviews if f["status"] == "needs_review")
    digests_failed = sum(1 for f in file_reviews if f["status"] == "failed")

    # Exclude combined from chunk-only counts for summary fields that say "chunk digests"
    chunk_only_reviews = [f for f in file_reviews if "combined" not in Path(f["path"]).name]
    digests_ok_chunks = sum(1 for f in chunk_only_reviews if f["status"] == "ok")
    digests_needing_review_chunks = sum(
        1 for f in chunk_only_reviews if f["status"] == "needs_review"
    )
    digests_failed_chunks = sum(1 for f in chunk_only_reviews if f["status"] == "failed")

    total_uncertainty = sum(
        f["uncertainty_markers"]
        for f in file_reviews
        if "combined" not in Path(f["path"]).name.lower()
    )

    warnings: list[str] = []

    if registry_status in _DIGEST_COMPLETE_STATUSES and failed_chunks_from_log:
        warnings.append(
            f"Registry status is {registry_status!r} but the digest log reports "
            f"{failed_chunks_from_log} failed chunk(s)."
        )
    elif registry_status == "local_digest_complete" and digests_failed_chunks:
        warnings.append(
            "Registry status is local_digest_complete but some chunk digest files failed review."
        )
    elif registry_status not in _DIGEST_COMPLETE_STATUSES:
        warnings.append(
            f"Registry status is {registry_status!r}; expected local_digest_complete or "
            "local_digest_partial after running local digest."
        )

    if chunk_count_expected and chunk_count_found < chunk_count_expected:
        warnings.append(
            f"Expected {chunk_count_expected} chunk digests but found {chunk_count_found}."
        )

    for expected_id in expected_chunk_ids:
        expected_file = digest_dir / f"{expected_id}_digest.md"
        if not expected_file.is_file():
            warnings.append(f"Missing digest file for {expected_id}.")

    if not combined_path.is_file():
        warnings.append("Combined local digest file is missing.")

    if chunk_count_found == 0:
        warnings.append("No chunk digest files found.")

    for file_review in file_reviews:
        warnings.extend(file_review["warnings"])

    # Deduplicate warnings while preserving order
    seen: set[str] = set()
    unique_warnings: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique_warnings.append(w)
    warnings = unique_warnings

    overall_status = "ok"

    if (
        failed_chunks_from_log > 0
        or not combined_path.is_file()
        or chunk_count_found == 0
        or digests_failed > 0
        or "Combined local digest file is missing." in warnings
    ):
        overall_status = "failed"
    elif (
        digests_needing_review > 0
        or total_uncertainty >= _HIGH_UNCERTAINTY_TOTAL
        or digests_needing_review_chunks > 0
    ):
        overall_status = "needs_review"

    summary = {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "registry_status": registry_status,
        "chunk_count_expected": chunk_count_expected,
        "chunk_count_found": chunk_count_found,
        "failed_chunks_from_log": failed_chunks_from_log,
        "digests_ok": digests_ok_chunks,
        "digests_needing_review": digests_needing_review_chunks,
        "digests_failed": digests_failed_chunks,
        "total_uncertainty_markers": total_uncertainty,
        "overall_status": overall_status,
        "warnings": warnings,
        "files": file_reviews,
        "date_reviewed": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"
        ),
        "min_words_threshold": min_words,
    }

    json_path = digest_dir / f"{normalized_id}_local_digest_review.json"
    md_path = digest_dir / f"{normalized_id}_local_digest_review.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    md_path.write_text(_build_markdown_report(summary), encoding="utf-8")

    summary["report_path_md"] = str(md_path.resolve())
    summary["report_path_json"] = str(json_path.resolve())

    return summary
