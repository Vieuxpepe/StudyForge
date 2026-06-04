"""
Deterministic final audit normalizer — map messy audits to StudyForge template headings.
No AI calls.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from studyforge.audits.final_import import import_final_audit, load_final_audit_registry
from studyforge.audits.final_packet import FINAL_AUDIT_BASE
from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id
from studyforge.core.sources import resolve_course_path
from studyforge.study.study_pack import FinalAuditNotFoundError, get_latest_final_audit

EXPECTED_FINAL_AUDIT_HEADINGS: tuple[str, ...] = (
    "Final Verdict",
    "Corrections That Matter Most",
    "Missing Concepts",
    "Better Explanations",
    "Must-Memorize List",
    "Must-Understand List",
    "Formula / Method Sheet",
    "Exam / Homework Traps",
    "Practice Questions",
    "Active Recall Questions",
    "Final Study Checklist",
    "Remaining Uncertainties",
)

IMPORTANT_HEADINGS: frozenset[str] = frozenset(
    {
        "Must-Memorize List",
        "Must-Understand List",
        "Formula / Method Sheet",
        "Practice Questions",
        "Active Recall Questions",
    }
)

_MISSING_IN_NORMALIZED = "Not found in original final audit."

_NORMALIZED_MD_SUFFIX = "_final_audit_normalized.md"
_REPORT_JSON_SUFFIX = "_final_audit_normalization_report.json"
_REPAIR_MD_SUFFIX = "_final_audit_repair_packet.md"
_REPAIR_JSON_SUFFIX = "_final_audit_repair_packet.json"


class NormalizedAuditExistsError(Exception):
    """Raised when normalized output exists and overwrite was not requested."""


class RepairPacketExistsError(Exception):
    """Raised when repair packet exists and overwrite was not requested."""


def normalize_heading_text(heading: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\s/]", " ", text)
    text = text.replace("/", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_heading_aliases() -> dict[str, str]:
    """Normalized key -> expected heading (conservative aliases)."""
    aliases: dict[str, str] = {
        "final verdict": "Final Verdict",
        "overall verdict": "Final Verdict",
        "corrections that matter most": "Corrections That Matter Most",
        "important corrections": "Corrections That Matter Most",
        "missing concepts": "Missing Concepts",
        "better explanations": "Better Explanations",
        "must memorize list": "Must-Memorize List",
        "must memorize": "Must-Memorize List",
        "must understand list": "Must-Understand List",
        "must understand": "Must-Understand List",
        "formula method sheet": "Formula / Method Sheet",
        "formula sheet": "Formula / Method Sheet",
        "exam homework traps": "Exam / Homework Traps",
        "exam traps": "Exam / Homework Traps",
        "homework traps": "Exam / Homework Traps",
        "practice questions": "Practice Questions",
        "practice problems": "Practice Questions",
        "active recall questions": "Active Recall Questions",
        "active recall": "Active Recall Questions",
        "recall questions": "Active Recall Questions",
        "final study checklist": "Final Study Checklist",
        "study checklist": "Final Study Checklist",
        "remaining uncertainties": "Remaining Uncertainties",
    }
    # Shorter aliases only when unambiguous in our template set.
    short_aliases = {
        "corrections": "Corrections That Matter Most",
        "explanations": "Better Explanations",
        "memorize": "Must-Memorize List",
        "understand": "Must-Understand List",
        "formulas": "Formula / Method Sheet",
        "methods": "Formula / Method Sheet",
        "checklist": "Final Study Checklist",
        "uncertainties": "Remaining Uncertainties",
    }
    for key, expected in short_aliases.items():
        if key not in aliases:
            aliases[key] = expected
    for heading in EXPECTED_FINAL_AUDIT_HEADINGS:
        aliases[normalize_heading_text(heading)] = heading
    return aliases


_HEADING_ALIASES = _build_heading_aliases()


def map_heading_to_expected(heading: str) -> str | None:
    """Map a heading string to an expected template heading, or None."""
    key = normalize_heading_text(heading)
    if not key:
        return None
    return _HEADING_ALIASES.get(key)


def _heading_level(line: str) -> int | None:
    match = re.match(r"^(#+)\s+", line.strip())
    if match:
        return len(match.group(1))
    return None


def _heading_title(line: str) -> str:
    return re.sub(r"^#+\s+", "", line.strip()).strip()


def parse_top_level_markdown_sections(text: str, level: int = 2) -> list[dict]:
    """
    Parse Markdown into sections at the given heading level (default ``##``).

    Section content includes all text and lower-level headings (e.g. ``###``)
    until the next heading of the same or higher level.
    """
    lines = text.splitlines()
    sections: list[dict] = []
    current: dict | None = None

    for index, line in enumerate(lines):
        heading_level = _heading_level(line)
        if heading_level is None:
            if current is not None:
                current["content_lines"].append(line)
            continue

        title = _heading_title(line)
        if heading_level == 1 and title.lower() in {"final audit", "audit"}:
            continue

        if heading_level < level:
            continue

        if heading_level > level:
            if current is not None:
                current["content_lines"].append(line)
            continue

        if current is not None:
            current["content"] = "\n".join(current.pop("content_lines", [])).strip()
            sections.append(current)

        current = {
            "level": level,
            "heading": title,
            "normalized_heading": normalize_heading_text(title),
            "content_lines": [],
            "start_line": index + 1,
        }

    if current is not None:
        current["content"] = "\n".join(current.pop("content_lines", [])).strip()
        sections.append(current)

    return sections


def parse_markdown_sections_with_levels(text: str, level: int = 2) -> list[dict]:
    """
    Parse top-level ``##`` sections; nested ``###``+ headings stay in parent content.
    """
    return parse_top_level_markdown_sections(text, level=level)


def _merge_content(existing: str, new: str) -> str:
    if not existing:
        return new
    if not new:
        return existing
    return existing + "\n\n" + new


def _build_normalization_report(
    mapped_headings: dict[str, str],
    missing_headings: list[str],
    unmatched_headings: list[str],
    found_headings: list[str],
    warnings: list[str],
) -> dict:
    mapped_count = len({v for v in mapped_headings.values()})
    quality_status = "ok"

    if mapped_count < 3:
        quality_status = "failed"
        warnings.append(
            f"Only {mapped_count} expected headings could be mapped from the original audit."
        )

    important_missing = [h for h in IMPORTANT_HEADINGS if h in missing_headings]
    if important_missing:
        for heading in important_missing:
            warnings.append(f"Important section missing after normalization: {heading}")
        if quality_status != "failed":
            quality_status = "needs_review"

    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)

    return {
        "expected_headings": list(EXPECTED_FINAL_AUDIT_HEADINGS),
        "found_headings": found_headings,
        "mapped_headings": mapped_headings,
        "missing_headings": missing_headings,
        "unmatched_headings": unmatched_headings,
        "mapped_count": mapped_count,
        "quality_status": quality_status,
        "warnings": deduped,
    }


def normalize_final_audit_text(text: str) -> tuple[str, dict]:
    """
    Build normalized final audit Markdown and a normalization report.
    """
    parsed = parse_top_level_markdown_sections(text, level=2)
    content_by_expected: dict[str, str] = {h: "" for h in EXPECTED_FINAL_AUDIT_HEADINGS}
    mapped_headings: dict[str, str] = {}
    found_headings: list[str] = []
    unmatched_sections: list[dict] = []
    warnings: list[str] = []

    for section in parsed:
        raw_heading = section["heading"]
        found_headings.append(raw_heading)
        expected = map_heading_to_expected(raw_heading)
        body = section.get("content", "").strip()

        if expected:
            mapped_headings[raw_heading] = expected
            content_by_expected[expected] = _merge_content(
                content_by_expected[expected], body
            )
        else:
            unmatched_sections.append(section)

    missing_headings: list[str] = []
    for heading in EXPECTED_FINAL_AUDIT_HEADINGS:
        if not content_by_expected[heading].strip():
            content_by_expected[heading] = _MISSING_IN_NORMALIZED
            missing_headings.append(heading)

    lines = ["# Final Audit", ""]
    for heading in EXPECTED_FINAL_AUDIT_HEADINGS:
        lines.extend([f"## {heading}", "", content_by_expected[heading], ""])

    unmatched_headings = [s["heading"] for s in unmatched_sections]
    if unmatched_sections:
        lines.extend(["## Additional Notes From Original Audit", ""])
        for section in unmatched_sections:
            lines.extend([f"### {section['heading']}", ""])
            body = section.get("content", "").strip()
            lines.append(body if body else "_(empty)_")
            lines.append("")

    report = _build_normalization_report(
        mapped_headings, missing_headings, unmatched_headings, found_headings, warnings
    )
    return "\n".join(lines).rstrip() + "\n", report


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def get_final_audit_dir(course_path: Path, source_id: str) -> Path:
    return course_path / FINAL_AUDIT_BASE / _normalize_source_id(source_id)


def get_normalized_audit_path(course_path: Path, source_id: str) -> Path:
    normalized = _normalize_source_id(source_id)
    return get_final_audit_dir(course_path, normalized) / f"{normalized}{_NORMALIZED_MD_SUFFIX}"


def get_normalization_report_path(course_path: Path, source_id: str) -> Path:
    normalized = _normalize_source_id(source_id)
    return get_final_audit_dir(course_path, normalized) / f"{normalized}{_REPORT_JSON_SUFFIX}"


def get_repair_packet_path(course_path: Path, source_id: str) -> Path:
    normalized = _normalize_source_id(source_id)
    return get_final_audit_dir(course_path, normalized) / f"{normalized}{_REPAIR_MD_SUFFIX}"


def get_final_audit_registry_path(course_path: Path, source_id: str) -> Path:
    from studyforge.study.study_pack import get_final_audit_registry_path as _path

    return _path(course_path, _normalize_source_id(source_id))


def load_final_audit_by_version(
    course_path: Path, source_id: str, version: int
) -> dict:
    """Load a specific final audit version (same shape as get_latest_final_audit)."""
    normalized = _normalize_source_id(source_id)
    registry_path = get_final_audit_registry_path(course_path, normalized)
    registry = load_final_audit_registry(registry_path, normalized)

    for entry in registry.get("audits", []):
        if int(entry.get("version", 0)) == version:
            file_path = Path(entry.get("file_path", ""))
            if not file_path.is_file():
                break
            return {
                "entry": entry,
                "file_path": str(file_path.resolve()),
                "text": file_path.read_text(encoding="utf-8"),
            }

    audit_dir = get_final_audit_dir(course_path, normalized)
    fallback = audit_dir / f"{normalized}_final_audit_v{version:03d}.md"
    if fallback.is_file():
        return {
            "entry": {"audit_id": f"FA-{normalized}-V{version:03d}", "version": version},
            "file_path": str(fallback.resolve()),
            "text": fallback.read_text(encoding="utf-8"),
        }

    raise FinalAuditNotFoundError(
        f"No final audit version {version} found for {normalized}."
    )


def get_repair_packet_json_path(course_path: Path, source_id: str) -> Path:
    normalized = _normalize_source_id(source_id)
    return get_final_audit_dir(course_path, normalized) / f"{normalized}{_REPAIR_JSON_SUFFIX}"


def normalize_latest_final_audit(
    course_name: str,
    source_id: str,
    overwrite: bool = False,
    import_as_new_version: bool = False,
    audit_version: int | None = None,
    root: Path | None = None,
) -> dict:
    """
    Normalize the latest final audit and save artifacts (optional new version import).
    """
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    if audit_version is not None:
        final_audit = load_final_audit_by_version(
            course_path, normalized_id, audit_version
        )
    else:
        final_audit = get_latest_final_audit(course_path, normalized_id)
    source_audit_id = str(final_audit["entry"].get("audit_id", "unknown"))
    source_path = final_audit["file_path"]

    normalized_path = get_normalized_audit_path(course_path, normalized_id)
    report_path = get_normalization_report_path(course_path, normalized_id)

    if (normalized_path.is_file() or report_path.is_file()) and not overwrite:
        raise NormalizedAuditExistsError(
            f"Normalized final audit already exists:\n"
            f"  - {normalized_path}\n"
            f"  - {report_path}\n"
            "Use --overwrite to replace."
        )

    normalized_text, report = normalize_final_audit_text(final_audit["text"])

    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.write_text(normalized_text, encoding="utf-8")

    report_payload = {
        "course": course_path.name,
        "source_id": normalized_id,
        "source_final_audit_id": source_audit_id,
        "source_final_audit_path": source_path,
        "normalized_path": str(normalized_path.resolve()),
        **report,
    }
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report_payload, handle, indent=2)
        handle.write("\n")

    result: dict = {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "source_final_audit_id": source_audit_id,
        "normalized_path": str(normalized_path.resolve()),
        "report_path": str(report_path.resolve()),
        "quality_status": report["quality_status"],
        "mapped_count": report["mapped_count"],
        "missing_headings": report["missing_headings"],
        "mapped_headings": report["mapped_headings"],
        "warnings": report["warnings"],
        "imported_audit_id": None,
        "imported_path": None,
    }

    if import_as_new_version:
        notes = f"Normalized from {source_audit_id} for Study Pack generation"
        import_summary = import_final_audit(
            course_name,
            source_id,
            audit_text=normalized_text,
            auditor_name="StudyForge Normalizer",
            notes=notes,
            root=root,
        )
        result["imported_audit_id"] = import_summary["audit_id"]
        result["imported_path"] = import_summary["saved_path"]
        result["import_warnings"] = import_summary.get("warnings", [])

    return result


def build_final_audit_repair_packet(
    course_name: str,
    source_id: str,
    root: Path | None = None,
    overwrite: bool = False,
    audit_version: int | None = None,
) -> dict:
    """Export a manual repair packet for ChatGPT (no AI in StudyForge)."""
    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    if audit_version is not None:
        final_audit = load_final_audit_by_version(
            course_path, normalized_id, audit_version
        )
    else:
        final_audit = get_latest_final_audit(course_path, normalized_id)
    source_audit_id = str(final_audit["entry"].get("audit_id", "unknown"))
    original_text = final_audit["text"]

    repair_path = get_repair_packet_path(course_path, normalized_id)
    repair_json_path = get_repair_packet_json_path(course_path, normalized_id)

    if (repair_path.is_file() or repair_json_path.is_file()) and not overwrite:
        raise RepairPacketExistsError(
            f"Repair packet already exists:\n"
            f"  - {repair_path}\n"
            "Use --overwrite to replace."
        )

    headings_list = "\n".join(f"- ## {h}" for h in EXPECTED_FINAL_AUDIT_HEADINGS)
    template_blocks = "\n\n".join(f"## {h}\n" for h in EXPECTED_FINAL_AUDIT_HEADINGS)

    lines = [
        "# Final Audit Repair Packet",
        "",
        "Purpose:",
        "",
        "Rewrite the final audit below into the exact StudyForge final audit template.",
        "",
        "Rules:",
        "",
        "- Preserve source-supported corrections.",
        "- Do not invent new facts.",
        "- Do not invent page references.",
        "- Keep uncertainty if the original audit is uncertain.",
        "- Use the exact headings listed below.",
        f"- If a section cannot be filled from the audit, write:\n  {_MISSING_IN_NORMALIZED}",
        "- Do not include scratchpad, reasoning process, or drafting notes.",
        "- Output only the repaired final audit.",
        "",
        "Required headings:",
        "",
        headings_list,
        "",
        "---",
        "",
        "## Original Final Audit",
        "",
        "```markdown",
        original_text.rstrip(),
        "```",
        "",
        "---",
        "",
        "## Output Template",
        "",
        "# Final Audit",
        "",
        template_blocks,
        "",
    ]

    repair_path.parent.mkdir(parents=True, exist_ok=True)
    repair_path.write_text("\n".join(lines), encoding="utf-8")

    metadata = {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "source_final_audit_id": source_audit_id,
        "repair_packet_path": str(repair_path.resolve()),
        "purpose": "manual_chatgpt_repair",
    }
    with repair_json_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "source_final_audit_id": source_audit_id,
        "repair_packet_path": str(repair_path.resolve()),
        "repair_packet_json_path": str(repair_json_path.resolve()),
    }
