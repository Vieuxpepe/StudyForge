"""Tests for text chunking."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.chunking.text_chunker import (  # noqa: E402
    count_words,
    create_chunks_from_pages,
    parse_extracted_markdown_pages,
    split_words,
)
from studyforge.core.chunking_jobs import (  # noqa: E402
    ChunkOutputExistsError,
    chunk_registered_source,
)
from studyforge.core.sources import load_source_registry, save_source_registry  # noqa: E402

SAMPLE_MARKDOWN = """# Extracted Text

Source ID:
SRC-0001

---

## Page 1

Alpha beta gamma delta.

---

## Page 2

Epsilon zeta eta theta iota kappa.

---

## Page 3

Lambda mu nu xi omicron pi.

---
"""

LONG_PAGE_MARKDOWN = """## Page 1

""" + " ".join(f"word{i}" for i in range(1, 1501)) + """

---
"""


class TestTextChunker(unittest.TestCase):
    def test_split_and_count_words(self) -> None:
        self.assertEqual(split_words("one two  three"), ["one", "two", "three"])
        self.assertEqual(count_words("one two three"), 3)

    def test_parse_extracted_markdown_pages(self) -> None:
        pages = parse_extracted_markdown_pages(SAMPLE_MARKDOWN)
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertGreater(pages[0]["word_count"], 0)

    def test_create_chunks_from_short_pages(self) -> None:
        pages = parse_extracted_markdown_pages(SAMPLE_MARKDOWN)
        chunks = create_chunks_from_pages(
            pages, max_words=1200, overlap_words=150, source_id="SRC-0001"
        )
        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_id"], "SRC-0001-CHUNK-0001")
        self.assertEqual(chunks[0]["page_start"], 1)
        self.assertEqual(chunks[0]["page_end"], 3)

    def test_split_long_page(self) -> None:
        pages = parse_extracted_markdown_pages(LONG_PAGE_MARKDOWN)
        chunks = create_chunks_from_pages(
            pages, max_words=500, overlap_words=50, source_id="SRC-0001"
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c["page_start"] == 1 for c in chunks))

    def test_preserve_page_ranges(self) -> None:
        pages = parse_extracted_markdown_pages(SAMPLE_MARKDOWN)
        chunks = create_chunks_from_pages(
            pages, max_words=5, overlap_words=2, source_id="SRC-0001"
        )
        for chunk in chunks:
            self.assertIn(chunk["page_start"], chunk["pages"])
            self.assertIn(chunk["page_end"], chunk["pages"])

    def test_reject_overlap_ge_max_words(self) -> None:
        pages = parse_extracted_markdown_pages(SAMPLE_MARKDOWN)
        with self.assertRaises(ValueError):
            create_chunks_from_pages(pages, max_words=100, overlap_words=100)


class TestChunkingJobs(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        courses.mkdir()
        self.course = courses / "ECA1010_Test"
        self.course.mkdir()

        extracted_dir = self.course / "02_Extracted_Text" / "extracted_sources"
        extracted_dir.mkdir(parents=True)
        self.extracted = extracted_dir / "SRC-0001_extracted_text.md"
        self.extracted.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

        (self.course / "08_App_Data").mkdir(parents=True)
        registry = {
            "sources": [
                {
                    "id": "SRC-0001",
                    "title": "Test Book",
                    "status": "extracted",
                    "extracted_text_path": str(self.extracted.resolve()),
                }
            ]
        }
        save_source_registry(self.course, registry)

        (self.root / "config").mkdir()
        config = {
            "project_root": str(self.root),
            "courses_dir": str(courses),
            "default_course_template": "_Course_Template",
        }
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_refuse_overwrite_without_flag(self) -> None:
        chunk_registered_source("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(ChunkOutputExistsError):
            chunk_registered_source("ECA1010_Test", "SRC-0001", root=self.root)

    def test_allow_overwrite(self) -> None:
        chunk_registered_source("ECA1010_Test", "SRC-0001", root=self.root)
        summary = chunk_registered_source(
            "ECA1010_Test", "SRC-0001", root=self.root, overwrite=True
        )
        self.assertGreater(summary["chunk_count"], 0)

    def test_registry_status_chunked(self) -> None:
        chunk_registered_source("ECA1010_Test", "SRC-0001", root=self.root)
        registry = load_source_registry(self.course)
        entry = registry["sources"][0]
        self.assertEqual(entry["status"], "chunked")
        self.assertIn("chunk_manifest_path", entry)
        self.assertIn("chunk_count", entry)
        self.assertIn("date_chunked", entry)


if __name__ == "__main__":
    unittest.main()
