"""
Page-aware chunking of extracted StudyForge Markdown.
"""

from __future__ import annotations

import re

# Matches "## Page 12" headings in extracted Markdown
_PAGE_HEADING = re.compile(r"^## Page (\d+)\s*$", re.MULTILINE)

# Placeholder used when a PDF page had no extractable text
_EMPTY_PAGE_PLACEHOLDER = "_(no text)_"


def split_words(text: str) -> list[str]:
    """Split text into words on whitespace."""
    return text.split()


def count_words(text: str) -> int:
    """Return the number of words in ``text``."""
    return len(split_words(text))


def parse_extracted_markdown_pages(markdown_text: str) -> list[dict]:
    """
    Parse page sections from extracted Markdown.

    Expects headings like ``## Page 1`` followed by page text (optional ``---`` separators).

    Returns:
        List of dicts with page_number, text, word_count.
    """
    pages: list[dict] = []
    matches = list(_PAGE_HEADING.finditer(markdown_text))
    if not matches:
        return pages

    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        block = markdown_text[start:end].strip()

        # Drop trailing horizontal rule separators between pages
        block = re.sub(r"\n---\s*$", "", block).strip()
        if block == _EMPTY_PAGE_PLACEHOLDER:
            block = ""

        word_count = count_words(block) if block else 0
        pages.append(
            {
                "page_number": page_number,
                "text": block,
                "word_count": word_count,
            }
        )

    return pages


def _segments_to_text(segments: list[dict]) -> str:
    """Turn internal segments into chunk body text with page headings."""
    parts: list[str] = []
    for segment in segments:
        page = segment["pages"][0]
        parts.append(f"## Page {page}")
        parts.append("")
        parts.append(" ".join(segment["words"]))
        parts.append("")
    return "\n".join(parts).strip()


def _split_long_page_words(
    words: list[str], page_number: int, max_words: int, overlap_words: int
) -> list[dict]:
    """Split a single page's word list into units of at most ``max_words``."""
    units: list[dict] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        units.append({"pages": [page_number], "words": words[start:end]})
        if end >= len(words):
            break
        start = max(start + 1, end - overlap_words)
    return units


def create_chunks_from_pages(
    pages: list[dict],
    max_words: int = 1200,
    overlap_words: int = 150,
    source_id: str | None = None,
) -> list[dict]:
    """
    Build chunks from parsed pages using word limits and optional overlap.

    Short consecutive pages are merged; long pages are split. Overlap repeats
    the last ``overlap_words`` of the previous chunk when starting the next one.

    Raises:
        ValueError: If overlap_words >= max_words or parameters are invalid.
    """
    if max_words < 1:
        raise ValueError("max_words must be at least 1.")
    if overlap_words < 0:
        raise ValueError("overlap_words cannot be negative.")
    if overlap_words >= max_words:
        raise ValueError("overlap_words must be less than max_words.")

    sid = source_id or "SRC-0000"

    # Step 1: expand pages into units (whole page or page splits)
    units: list[dict] = []
    for page in pages:
        text = page["text"].strip()
        if text == _EMPTY_PAGE_PLACEHOLDER:
            text = ""
        words = split_words(text) if text else []
        if not words:
            continue

        page_number = page["page_number"]
        if len(words) <= max_words:
            units.append({"pages": [page_number], "words": words})
        else:
            units.extend(
                _split_long_page_words(words, page_number, max_words, overlap_words)
            )

    if not units:
        return []

    # Step 2: merge units into chunks
    chunk_segments: list[list[dict]] = []
    current_segments: list[dict] = []

    def segment_word_count(segments: list[dict]) -> int:
        return sum(len(s["words"]) for s in segments)

    def finalize_segments(segments: list[dict]) -> None:
        if segments:
            chunk_segments.append(list(segments))

    for unit in units:
        unit_word_len = len(unit["words"])

        if not current_segments:
            current_segments.append(
                {"pages": list(unit["pages"]), "words": list(unit["words"])}
            )
            continue

        if segment_word_count(current_segments) + unit_word_len <= max_words:
            current_segments.append(
                {"pages": list(unit["pages"]), "words": list(unit["words"])}
            )
            continue

        # Save words/pages from the chunk we are closing
        prev_words: list[str] = []
        prev_pages: list[int] = []
        for seg in current_segments:
            prev_words.extend(seg["words"])
            prev_pages.extend(seg["pages"])

        finalize_segments(current_segments)
        current_segments = []

        overlap = prev_words[-overlap_words:] if overlap_words else []
        if overlap:
            merged_pages = sorted(set(prev_pages + unit["pages"]))
            current_segments.append(
                {
                    "pages": merged_pages,
                    "words": overlap + list(unit["words"]),
                }
            )
        else:
            current_segments.append(
                {"pages": list(unit["pages"]), "words": list(unit["words"])}
            )

    finalize_segments(current_segments)

    # Step 3: build chunk dicts with IDs
    chunks: list[dict] = []
    for index, segments in enumerate(chunk_segments, start=1):
        all_pages = sorted(
            {page for segment in segments for page in segment["pages"]}
        )
        text = _segments_to_text(segments)
        chunks.append(
            {
                "chunk_id": f"{sid}-CHUNK-{index:04d}",
                "source_id": sid,
                "chunk_number": index,
                "page_start": min(all_pages),
                "page_end": max(all_pages),
                "pages": all_pages,
                "word_count": count_words(text),
                "text": text,
            }
        )

    return chunks


def chunk_to_markdown(chunk: dict) -> str:
    """Format a chunk dict as Markdown for saving to disk."""
    pages = chunk.get("pages", [])
    if len(pages) == 1:
        pages_label = str(pages[0])
    elif pages:
        pages_label = f"{pages[0]}-{pages[-1]}"
    else:
        pages_label = "unknown"

    lines = [
        "# Source Chunk",
        "",
        "Chunk ID:",
        str(chunk.get("chunk_id", "")),
        "",
        "Source ID:",
        str(chunk.get("source_id", "")),
        "",
        "Pages:",
        pages_label,
        "",
        "Word count:",
        str(chunk.get("word_count", 0)),
        "",
        "---",
        "",
        str(chunk.get("text", "")),
    ]
    return "\n".join(lines) + "\n"


def collect_chunking_warnings(
    pages: list[dict],
    chunks: list[dict],
    max_words: int,
    overlap_words: int,
    extracted_path: str | None = None,
    extracted_exists: bool = True,
) -> list[str]:
    """Build warning messages for chunking jobs and manifests."""
    warnings: list[str] = []

    if extracted_path and not extracted_exists:
        warnings.append(f"Extracted text file missing: {extracted_path}")

    if overlap_words >= max_words:
        warnings.append("overlap_words must be less than max_words.")

    if not pages:
        warnings.append("No pages parsed from extracted Markdown.")

    if not chunks:
        warnings.append("No chunks were created from the parsed pages.")

    for chunk in chunks:
        if chunk.get("word_count", 0) < 50:
            warnings.append(
                f"Chunk {chunk.get('chunk_id')} has only "
                f"{chunk.get('word_count', 0)} words (below 50)."
            )

    return warnings
