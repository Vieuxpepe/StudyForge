"""Tests for PDF extraction jobs."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import (  # noqa: E402
    ExtractionOutputExistsError,
    NotPdfSourceError,
    SourceNotFoundError,
    extract_registered_source,
    find_source_by_id,
    get_extracted_sources_dir,
    get_extraction_logs_dir,
)
from studyforge.core.sources import add_source, load_source_registry  # noqa: E402

try:
    import fitz  # noqa: E402

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


def _make_minimal_pdf(path: Path, text: str = "Hello StudyForge") -> None:
    """Create a one-page PDF for tests."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


@unittest.skipUnless(
    HAS_PYMUPDF,
    "PyMuPDF not installed — run: python -m pip install -r requirements.txt",
)
class TestExtractionJobs(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

        courses = self.root / "courses"
        courses.mkdir()
        self.course = courses / "ECA1010_Test"
        (self.course / "01_Source_Material" / "textbook").mkdir(parents=True)
        (self.course / "08_App_Data").mkdir(parents=True)

        (self.root / "config").mkdir()
        config = {
            "project_root": str(self.root),
            "courses_dir": str(courses),
            "default_course_template": "_Course_Template",
        }
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

        self.pdf = self.root / "sample.pdf"
        _make_minimal_pdf(self.pdf)
        add_source("ECA1010_Test", "textbook", self.pdf, title="Test PDF", root=self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_find_source_by_id(self) -> None:
        entry = find_source_by_id("ECA1010_Test", "src-0001", root=self.root)
        self.assertEqual(entry["id"], "SRC-0001")
        self.assertEqual(entry["title"], "Test PDF")

    def test_missing_source_id(self) -> None:
        with self.assertRaises(SourceNotFoundError):
            find_source_by_id("ECA1010_Test", "SRC-9999", root=self.root)

    def test_reject_non_pdf(self) -> None:
        registry = load_source_registry(self.course)
        registry["sources"][0]["file_extension"] = ".docx"
        from studyforge.core.sources import save_source_registry

        save_source_registry(self.course, registry)
        with self.assertRaises(NotPdfSourceError):
            extract_registered_source("ECA1010_Test", "SRC-0001", root=self.root)

    def test_output_paths_created(self) -> None:
        summary = extract_registered_source(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        text_path = Path(summary["extracted_text_path"])
        log_path = Path(summary["extraction_log_path"])
        self.assertTrue(text_path.is_file())
        self.assertTrue(log_path.is_file())
        self.assertIn("SRC-0001", text_path.name)
        self.assertTrue(get_extracted_sources_dir(self.course).is_dir())
        self.assertTrue(get_extraction_logs_dir(self.course).is_dir())

    def test_refuse_overwrite_without_flag(self) -> None:
        extract_registered_source("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(ExtractionOutputExistsError):
            extract_registered_source("ECA1010_Test", "SRC-0001", root=self.root)

    def test_allow_overwrite(self) -> None:
        extract_registered_source("ECA1010_Test", "SRC-0001", root=self.root)
        summary = extract_registered_source(
            "ECA1010_Test", "SRC-0001", root=self.root, overwrite=True
        )
        self.assertGreater(summary["total_words"], 0)

    def test_registry_status_updated(self) -> None:
        extract_registered_source("ECA1010_Test", "SRC-0001", root=self.root)
        registry = load_source_registry(self.course)
        entry = registry["sources"][0]
        self.assertEqual(entry["status"], "extracted")
        self.assertIn("extracted_text_path", entry)
        self.assertIn("extraction_log_path", entry)
        self.assertIn("date_extracted", entry)


class TestPdfExtractorValidation(unittest.TestCase):
    def test_non_pdf_raises(self) -> None:
        from studyforge.extraction.pdf_extractor import extract_pdf_pages

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"not pdf")
            tmp_path = Path(tmp.name)
        try:
            with self.assertRaises(ValueError):
                extract_pdf_pages(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
