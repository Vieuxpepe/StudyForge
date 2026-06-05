"""
Deterministic extraction quality diagnostics (no OCR, no AI).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from studyforge.chunking.text_chunker import parse_extracted_markdown_pages
from studyforge.core.sources import (
    CourseNotFoundError,
    load_source_registry,
    resolve_course_path,
    save_source_registry,
)

QUALITY_STATUSES = frozenset({"ok", "needs_review", "failed"})

EXTRACTED_TEXT_BASE = Path("02_Extracted_Text")
EXTRACTION_LOGS_DIR = EXTRACTED_TEXT_BASE / "extraction_logs"

_VERY_SHORT_MAX = 20
_LOW_WORD_MAX = 75
_FAILED_TOTAL_WORDS = 50
_FAILED_EMPTY_RATIO = 0.5
_REVIEW_LOW_SHORT_RATIO = 0.25
_REVIEW_AVG_WORDS = 100

_REPLACEMENT_CHAR = "\ufffd"
_REPEATED_SPACE = re.compile(r" {4,}")
_SYMBOL_LINE = re.compile(r"^[\d\s\W]+$")
_FORMULA_SYMBOLS = re.compile(r"[=%$/\u00d7+\u2212]")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def get_extraction_logs_dir(course_path: Path) -> Path:
    """Return 02_Extracted_Text/extraction_logs/ (creates if missing)."""
    path = course_path / EXTRACTION_LOGS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_extraction_quality_report_paths(course_path: Path, source_id: str) -> tuple[Path, Path]:
    """Return JSON and Markdown report paths under extraction_logs/."""
    log_dir = get_extraction_logs_dir(course_path)
    normalized = _normalize_source_id(source_id)
    json_path = log_dir / f"{normalized}_extraction_quality_report.json"
    md_path = log_dir / f"{normalized}_extraction_quality_report.md"
    return json_path, md_path


def detect_extraction_red_flags(text: str) -> list[str]:
    """
    Detect conservative deterministic red flags in extracted text.

    Returns human-readable warning strings (empty if nothing suspicious).
    """
    flags: list[str] = []
    if not text.strip():
        return flags

    replacement_count = text.count(_REPLACEMENT_CHAR)
    if replacement_count >= 5:
        flags.append(
            f"Found {replacement_count} replacement characters ({_REPLACEMENT_CHAR!r}) "
            "— extraction may be corrupted."
        )

    repeated_spaces = len(_REPEATED_SPACE.findall(text))
    if repeated_spaces >= 8:
        flags.append(
            "Repeated unusual spacing detected — layout may not have extracted cleanly."
        )

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return flags

    single_char_lines = sum(1 for line in lines if len(line) == 1)
    if single_char_lines >= max(10, len(lines) // 5):
        flags.append(
            f"Many single-character lines ({single_char_lines}) — "
            "text may be fragmented."
        )

    symbol_only_lines = sum(
        1 for line in lines if len(line) >= 4 and _SYMBOL_LINE.match(line)
    )
    if symbol_only_lines >= max(8, len(lines) // 6):
        flags.append(
            f"Many lines contain only numbers/symbols ({symbol_only_lines}) — "
            "tables or formulas may dominate."
        )

    alnum = sum(1 for ch in text if ch.isalnum())
    if len(text) >= 200:
        non_alnum_ratio = 1 - (alnum / len(text))
        if non_alnum_ratio >= 0.45:
            flags.append(
                "High ratio of non-alphanumeric characters — "
                "extracted text may be noisy."
            )

    formula_lines = sum(1 for line in lines if len(_FORMULA_SYMBOLS.findall(line)) >= 2)
    if formula_lines >= max(10, len(lines) // 4):
        flags.append(
            f"Many lines look like tables/formulas ({formula_lines}) — "
            "review before trusting digest output."
        )

    return flags


def analyze_extracted_pages(pages: list[dict]) -> dict:
    """
    Analyze per-page extraction metrics and assign a quality status.

    Page dicts may include page_number, text, char_count, word_count.
    """
    empty_pages: list[int] = []
    low_word_pages: list[int] = []
    very_short_pages: list[int] = []
    word_counts: list[int] = []
    total_characters = 0
    warnings: list[str] = []

    for page in pages:
        page_number = int(page.get("page_number", 0))
        word_count = int(page.get("word_count", 0))
        char_count = int(page.get("char_count", len(page.get("text", ""))))
        word_counts.append(word_count)
        total_characters += char_count

        if word_count == 0:
            empty_pages.append(page_number)
            warnings.append(f"Page {page_number} is empty.")
        elif word_count <= _VERY_SHORT_MAX:
            very_short_pages.append(page_number)
            warnings.append(f"Page {page_number} is very short ({word_count} words).")
        elif word_count <= _LOW_WORD_MAX:
            low_word_pages.append(page_number)
            warnings.append(f"Page {page_number} has low text ({word_count} words).")

    total_pages = len(pages)
    total_words = sum(word_counts)
    average_words = total_words / total_pages if total_pages else 0.0
    median_words = float(median(word_counts)) if word_counts else 0.0

    quality_status = "ok"
    if total_pages == 0 or total_words < _FAILED_TOTAL_WORDS:
        quality_status = "failed"
        if total_words < _FAILED_TOTAL_WORDS:
            warnings.append(
                f"Total words ({total_words}) is below {_FAILED_TOTAL_WORDS} — "
                "extraction likely failed."
            )
    elif total_pages and len(empty_pages) / total_pages > _FAILED_EMPTY_RATIO:
        quality_status = "failed"
        warnings.append(
            f"More than {int(_FAILED_EMPTY_RATIO * 100)}% of pages are empty."
        )
    elif empty_pages:
        quality_status = "needs_review"
    elif total_pages and (
        (len(low_word_pages) + len(very_short_pages)) / total_pages
        > _REVIEW_LOW_SHORT_RATIO
    ):
        quality_status = "needs_review"
        warnings.append(
            f"More than {int(_REVIEW_LOW_SHORT_RATIO * 100)}% of pages are "
            "low-text or very short."
        )
    elif average_words < _REVIEW_AVG_WORDS:
        quality_status = "needs_review"
        warnings.append(
            f"Average words per page ({average_words:.1f}) is below "
            f"{_REVIEW_AVG_WORDS}."
        )

    return {
        "total_pages": total_pages,
        "empty_pages": empty_pages,
        "low_word_pages": low_word_pages,
        "very_short_pages": very_short_pages,
        "average_words_per_page": round(average_words, 1),
        "median_words_per_page": round(median_words, 1),
        "total_words": total_words,
        "total_characters": total_characters,
        "quality_status": quality_status,
        "warnings": warnings,
    }


def analyze_extracted_markdown(markdown_text: str) -> dict:
    """Parse extracted Markdown and return quality metrics plus red flags."""
    parsed = parse_extracted_markdown_pages(markdown_text)
    pages = [
        {
            "page_number": page["page_number"],
            "text": page.get("text", ""),
            "word_count": page.get("word_count", 0),
            "char_count": len(page.get("text", "")),
        }
        for page in parsed
    ]
    report = analyze_extracted_pages(pages)
    red_flags = detect_extraction_red_flags(markdown_text)
    report["red_flags"] = red_flags
    if red_flags:
        if report["quality_status"] == "ok":
            report["quality_status"] = "needs_review"
        report["warnings"] = list(report.get("warnings", [])) + red_flags
    return report


def _pages_from_extraction_log(log_data: dict) -> list[dict]:
    pages: list[dict] = []
    for page in log_data.get("pages", []):
        pages.append(
            {
                "page_number": int(page.get("page_number", 0)),
                "text": "",
                "word_count": int(page.get("word_count", 0)),
                "char_count": int(page.get("char_count", 0)),
            }
        )
    return pages


def _build_quality_markdown(
    *,
    course_name: str,
    source_id: str,
    title: str,
    report: dict,
) -> str:
    status = report.get("quality_status", "unknown")
    recommendation = {
        "ok": "Safe to chunk/digest.",
        "needs_review": "Inspect flagged pages before trusting digest.",
        "failed": "Re-extract or inspect PDF manually before continuing.",
    }.get(status, "Review the extraction before continuing.")

    lines = [
        "# Extraction Quality Report",
        "",
        f"Course: {course_name}",
        f"Source: {source_id} - {title}",
        f"Quality: {status}",
        "",
        "## Summary",
        "",
        f"- Total pages: {report.get('total_pages', 0)}",
        f"- Total words: {report.get('total_words', 0)}",
        f"- Average words/page: {report.get('average_words_per_page', 0)}",
        f"- Empty pages: {_format_page_list(report.get('empty_pages', []))}",
        f"- Low-word pages: {_format_page_list(report.get('low_word_pages', []))}",
        f"- Very short pages: {_format_page_list(report.get('very_short_pages', []))}",
        "",
        "## Warnings",
        "",
    ]
    warnings = report.get("warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None")

    red_flags = report.get("red_flags") or []
    if red_flags:
        lines.extend(["", "## Red flags", ""])
        for flag in red_flags:
            lines.append(f"- {flag}")

    lines.extend(
        [
            "",
            "## Pages to Inspect",
            "",
        ]
    )
    inspect_pages = sorted(
        set(report.get("empty_pages", []))
        | set(report.get("low_word_pages", []))
        | set(report.get("very_short_pages", []))
    )
    if inspect_pages:
        for page_number in inspect_pages:
            lines.append(f"- Page {page_number}")
    else:
        lines.append("- None flagged")

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- {status}: {recommendation}",
            "",
        ]
    )
    return "\n".join(lines)


def _format_page_list(pages: list[int]) -> str:
    if not pages:
        return "none"
    return ", ".join(str(page) for page in pages)


def run_extraction_quality_check(
    course_name: str,
    source_id: str,
    root: Path | None = None,
) -> dict:
    """
    Analyze extraction quality for a source and write JSON/Markdown reports.

    Raises:
        CourseNotFoundError, SourceNotFoundError, FileNotFoundError, ValueError.
    """
    from studyforge.core.extraction_jobs import SourceNotFoundError, find_source_by_id

    course_path = resolve_course_path(course_name, root)
    entry = find_source_by_id(course_name, source_id, root)
    normalized_id = _normalize_source_id(entry["id"])
    title = entry.get("title", normalized_id)

    extracted_path = Path(entry.get("extracted_text_path", ""))
    log_path = Path(entry.get("extraction_log_path", ""))

    if not extracted_path.is_file() and not log_path.is_file():
        raise FileNotFoundError(
            f"No extracted text or extraction log found for {normalized_id}.\n"
            "Run extract_source.py first."
        )

    pages: list[dict] = []
    markdown_text = ""

    if log_path.is_file():
        with log_path.open(encoding="utf-8") as handle:
            log_data = json.load(handle)
        pages = _pages_from_extraction_log(log_data)

    if extracted_path.is_file():
        markdown_text = extracted_path.read_text(encoding="utf-8")
        if not pages:
            parsed = parse_extracted_markdown_pages(markdown_text)
            pages = [
                {
                    "page_number": page["page_number"],
                    "text": page.get("text", ""),
                    "word_count": page.get("word_count", 0),
                    "char_count": len(page.get("text", "")),
                }
                for page in parsed
            ]

    if not pages and not markdown_text.strip():
        raise ValueError(
            f"Could not load page data for {normalized_id} from extraction outputs."
        )

    report = analyze_extracted_pages(pages)
    red_flags = detect_extraction_red_flags(markdown_text) if markdown_text else []
    report["red_flags"] = red_flags
    if red_flags:
        if report["quality_status"] == "ok":
            report["quality_status"] = "needs_review"
        report["warnings"] = list(report.get("warnings", [])) + red_flags

    checked_at = _now_iso()
    json_path, md_path = get_extraction_quality_report_paths(course_path, normalized_id)

    full_report = {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "date_checked": checked_at,
        "extracted_text_path": str(extracted_path.resolve()) if extracted_path.is_file() else None,
        "extraction_log_path": str(log_path.resolve()) if log_path.is_file() else None,
        **report,
    }

    json_path.write_text(json.dumps(full_report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        _build_quality_markdown(
            course_name=course_path.name,
            source_id=normalized_id,
            title=title,
            report=full_report,
        ),
        encoding="utf-8",
    )

    registry = load_source_registry(course_path)
    for source_entry in registry.get("sources", []):
        if str(source_entry.get("id", "")).upper() == normalized_id:
            source_entry["extraction_quality_status"] = report["quality_status"]
            source_entry["extraction_quality_report_path"] = str(json_path.resolve())
            source_entry["date_extraction_quality_checked"] = checked_at
            break
    else:
        raise SourceNotFoundError(f"Source not found in registry: {normalized_id}")

    save_source_registry(course_path, registry)

    return {
        "course": course_path.name,
        "source_id": normalized_id,
        "title": title,
        "quality_status": report["quality_status"],
        "report_json_path": str(json_path.resolve()),
        "report_markdown_path": str(md_path.resolve()),
        "warnings": report.get("warnings", []),
        **report,
    }
