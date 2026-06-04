"""
Extract readable text from PDF files using PyMuPDF (fitz).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

EXTRACTION_METHOD = "PyMuPDF"

# If total words across the document is below this, warn about low extraction
_LOW_TEXT_WORD_THRESHOLD = 10


def ensure_pymupdf() -> None:
    """
    Verify PyMuPDF is installed (import fitz).

    Raises:
        ImportError: With install/verify instructions if missing.
    """
    try:
        import fitz  # PyMuPDF — do not use pymupdf import name
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is not installed. From the project root run:\n"
            "  python -m pip install -r requirements.txt\n"
            "Then verify:\n"
            '  python -c "import fitz; print(\'PyMuPDF OK\')"'
        ) from exc


def _word_count(text: str) -> int:
    """Count words in a text block (whitespace-separated)."""
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


def extract_pdf_pages(pdf_path: Path) -> list[dict]:
    """
    Extract text from each page of a PDF.

    Returns a list of dicts with page_number, text, char_count, word_count.

    Raises:
        FileNotFoundError: PDF path does not exist.
        ValueError: Path is not a file or not a .pdf extension.
        RuntimeError: PyMuPDF failed to open or read the document.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {path}")

    ensure_pymupdf()
    import fitz  # PyMuPDF (available after ensure_pymupdf)

    pages: list[dict] = []
    try:
        with fitz.open(path) as document:
            for index, page in enumerate(document):
                text = page.get_text() or ""
                pages.append(
                    {
                        "page_number": index + 1,
                        "text": text,
                        "char_count": len(text),
                        "word_count": _word_count(text),
                    }
                )
    except Exception as exc:
        raise RuntimeError(f"PDF extraction failed for {path}: {exc}") from exc

    if not pages:
        raise RuntimeError(f"PDF has no pages: {path}")

    return pages


def _build_warnings(pages: list[dict], total_words: int) -> list[str]:
    """Collect human-readable warnings from extraction results."""
    warnings: list[str] = []

    for page in pages:
        if page["word_count"] == 0:
            warnings.append(f"Page {page['page_number']} is empty (no text extracted).")

    if total_words < _LOW_TEXT_WORD_THRESHOLD:
        warnings.append(
            f"Very low text extraction overall ({total_words} words). "
            "The PDF may be scanned images or protected."
        )

    return warnings


def extract_pdf_to_markdown(
    pdf_path: Path, source_id: str, title: str | None = None
) -> tuple[str, dict]:
    """
    Extract PDF text and format as Markdown with metadata.

    Returns:
        (markdown_text, metadata_dict) suitable for saving to disk and logs.
    """
    pages = extract_pdf_pages(pdf_path)
    path = Path(pdf_path)
    display_title = (title or path.stem).strip() or path.name

    total_characters = sum(p["char_count"] for p in pages)
    total_words = sum(p["word_count"] for p in pages)
    warnings = _build_warnings(pages, total_words)

    page_meta = [
        {
            "page_number": p["page_number"],
            "char_count": p["char_count"],
            "word_count": p["word_count"],
            "empty": p["word_count"] == 0,
        }
        for p in pages
    ]

    metadata = {
        "source_id": source_id,
        "file_name": path.name,
        "extraction_method": EXTRACTION_METHOD,
        "total_pages": len(pages),
        "total_words": total_words,
        "total_characters": total_characters,
        "pages": page_meta,
        "warnings": warnings,
        "date_extracted": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"
        ),
    }

    header_lines = [
        "# Extracted Text",
        "",
        "Source ID:",
        source_id,
        "",
        "Title:",
        display_title,
        "",
        "Original file:",
        path.name,
        "",
        "Extraction method:",
        EXTRACTION_METHOD,
        "",
        "Total pages:",
        str(len(pages)),
        "",
        "Total words:",
        str(total_words),
        "",
        "Total characters:",
        str(total_characters),
        "",
        "---",
        "",
    ]

    body_parts: list[str] = []
    for page in pages:
        body_parts.append(f"## Page {page['page_number']}")
        body_parts.append("")
        body_parts.append(page["text"].strip() if page["text"].strip() else "_(no text)_")
        body_parts.append("")
        body_parts.append("---")
        body_parts.append("")

    markdown = "\n".join(header_lines + body_parts)
    return markdown, metadata
