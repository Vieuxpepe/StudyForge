"""Tests for extraction quality diagnostics v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import extract_registered_source  # noqa: E402
from studyforge.extraction.extraction_quality import (  # noqa: E402
    analyze_extracted_markdown,
    analyze_extracted_pages,
    detect_extraction_red_flags,
    get_extraction_logs_dir,
    get_extraction_quality_report_paths,
    run_extraction_quality_check,
)
from studyforge.core.sources import load_source_registry, save_source_registry  # noqa: E402

try:
    import fitz  # noqa: E402

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "01_Source_Material" / "textbook").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "studyforge_config.json").write_text(
        json.dumps(
            {
                "project_root": str(root),
                "courses_dir": str(courses),
                "default_course_template": "_Course_Template",
            }
        ),
        encoding="utf-8",
    )
    return course


def _sample_pages_ok() -> list[dict]:
    return [
        {
            "page_number": index,
            "text": "word " * 150,
            "word_count": 150,
            "char_count": 750,
        }
        for index in range(1, 6)
    ]


class TestAnalyzeExtractedPages(unittest.TestCase):
    def test_ok_quality(self) -> None:
        report = analyze_extracted_pages(_sample_pages_ok())
        self.assertEqual(report["quality_status"], "ok")
        self.assertEqual(report["total_pages"], 5)
        self.assertEqual(report["empty_pages"], [])
        self.assertGreater(report["average_words_per_page"], 100)

    def test_needs_review_empty_pages(self) -> None:
        pages = _sample_pages_ok()
        pages[2] = {
            "page_number": 3,
            "text": "",
            "word_count": 0,
            "char_count": 0,
        }
        report = analyze_extracted_pages(pages)
        self.assertEqual(report["quality_status"], "needs_review")
        self.assertIn(3, report["empty_pages"])

    def test_failed_low_total_words(self) -> None:
        pages = [
            {"page_number": 1, "text": "hi", "word_count": 10, "char_count": 10},
            {"page_number": 2, "text": "bye", "word_count": 12, "char_count": 12},
        ]
        report = analyze_extracted_pages(pages)
        self.assertEqual(report["quality_status"], "failed")
        self.assertLess(report["total_words"], 50)

    def test_failed_majority_empty(self) -> None:
        pages = [
            {"page_number": 1, "text": "word " * 200, "word_count": 200, "char_count": 1000},
            {"page_number": 2, "text": "", "word_count": 0, "char_count": 0},
            {"page_number": 3, "text": "", "word_count": 0, "char_count": 0},
        ]
        report = analyze_extracted_pages(pages)
        self.assertEqual(report["quality_status"], "failed")


class TestDetectRedFlags(unittest.TestCase):
    def test_replacement_characters(self) -> None:
        text = "Intro " + ("\ufffd" * 10) + " more text here"
        flags = detect_extraction_red_flags(text)
        self.assertTrue(any("replacement" in flag.lower() for flag in flags))


class TestAnalyzeMarkdown(unittest.TestCase):
    def test_parse_extracted_markdown_pages(self) -> None:
        long_text = " ".join(["word"] * 120)
        markdown = f"""# Extracted Text

## Page 1

{long_text}

---

## Page 2

{long_text}

---

## Page 3

{long_text}
"""
        report = analyze_extracted_markdown(markdown)
        self.assertEqual(report["total_pages"], 3)
        self.assertGreater(report["total_words"], 50)
        self.assertEqual(report["quality_status"], "ok")


class TestRunExtractionQualityCheck(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.source_id = "SRC-0001"
        extracted_dir = self.course / "02_Extracted_Text" / "extracted_sources"
        extracted_dir.mkdir(parents=True)
        logs_dir = get_extraction_logs_dir(self.course)

        self.extracted_path = extracted_dir / f"{self.source_id}_extracted_text.md"
        self.extracted_path.write_text(
            """## Page 1

word """ + ("sample " * 120) + """

---

## Page 2

word """ + ("sample " * 120),
            encoding="utf-8",
        )
        self.log_path = logs_dir / f"{self.source_id}_extraction_log.json"
        self.log_path.write_text(
            json.dumps(
                {
                    "source_id": self.source_id,
                    "pages": [
                        {"page_number": 1, "word_count": 120, "char_count": 600},
                        {"page_number": 2, "word_count": 120, "char_count": 600},
                    ],
                }
            ),
            encoding="utf-8",
        )
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": self.source_id,
                        "title": "Test Book",
                        "status": "extracted",
                        "extracted_text_path": str(self.extracted_path.resolve()),
                        "extraction_log_path": str(self.log_path.resolve()),
                    }
                ]
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_quality_report_files_written(self) -> None:
        report = run_extraction_quality_check(
            "ECA1010_Test",
            self.source_id,
            root=self.root,
        )
        json_path, md_path = get_extraction_quality_report_paths(
            self.course, self.source_id
        )
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())
        self.assertEqual(report["quality_status"], "ok")
        self.assertEqual(report["report_json_path"], str(json_path.resolve()))

    def test_registry_updated(self) -> None:
        run_extraction_quality_check("ECA1010_Test", self.source_id, root=self.root)
        entry = load_source_registry(self.course)["sources"][0]
        self.assertEqual(entry["extraction_quality_status"], "ok")
        self.assertIn("extraction_quality_report_path", entry)
        self.assertIn("date_extraction_quality_checked", entry)

    def test_missing_backup_info_style_report_needs_review(self) -> None:
        self.log_path.write_text(
            json.dumps(
                {
                    "pages": [
                        {"page_number": 1, "word_count": 0, "char_count": 0},
                        {"page_number": 2, "word_count": 200, "char_count": 1000},
                    ]
                }
            ),
            encoding="utf-8",
        )
        report = run_extraction_quality_check(
            "ECA1010_Test",
            self.source_id,
            root=self.root,
        )
        self.assertEqual(report["quality_status"], "needs_review")
        self.assertIn(1, report["empty_pages"])


class TestPipelineDoctorQualityWarnings(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.pdf = self.course / "01_Source_Material" / "textbook" / "book.pdf"
        self.pdf.write_bytes(b"%PDF")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_needs_review_warning(self) -> None:
        from studyforge.core.pipeline_status import get_pipeline_status

        ext = self.course / "02_Extracted_Text" / "extracted_sources" / "SRC-0001_extracted_text.md"
        ext.parent.mkdir(parents=True)
        ext.write_text("## Page 1\n\nBody", encoding="utf-8")
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Book",
                        "stored_path": str(self.pdf.resolve()),
                        "status": "extracted",
                        "extracted_text_path": str(ext.resolve()),
                        "extraction_quality_status": "needs_review",
                    }
                ]
            },
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(
            any("needs review" in warning.lower() for warning in status["warnings"])
        )

    def test_failed_warning(self) -> None:
        from studyforge.core.pipeline_status import get_pipeline_status

        ext = self.course / "02_Extracted_Text" / "extracted_sources" / "SRC-0001_extracted_text.md"
        ext.parent.mkdir(parents=True)
        ext.write_text("## Page 1\n\nBody", encoding="utf-8")
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Book",
                        "stored_path": str(self.pdf.resolve()),
                        "status": "extracted",
                        "extracted_text_path": str(ext.resolve()),
                        "extraction_quality_status": "failed",
                    }
                ]
            },
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(
            any("quality failed" in warning.lower() for warning in status["warnings"])
        )

    def test_unchecked_warning(self) -> None:
        from studyforge.core.pipeline_status import get_pipeline_status

        ext = self.course / "02_Extracted_Text" / "extracted_sources" / "SRC-0001_extracted_text.md"
        ext.parent.mkdir(parents=True)
        ext.write_text("## Page 1\n\nBody", encoding="utf-8")
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Book",
                        "stored_path": str(self.pdf.resolve()),
                        "status": "extracted",
                        "extracted_text_path": str(ext.resolve()),
                    }
                ]
            },
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(
            any("has not been checked" in warning.lower() for warning in status["warnings"])
        )


@unittest.skipUnless(
    HAS_PYMUPDF,
    "PyMuPDF not installed",
)
class TestExtractionJobAutoQuality(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.pdf = self.root / "sample.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello StudyForge extraction quality test")
        doc.save(self.pdf)
        doc.close()
        from studyforge.core.sources import add_source

        add_source("ECA1010_Test", "textbook", self.pdf, title="Test PDF", root=self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_extraction_auto_runs_quality_check(self) -> None:
        summary = extract_registered_source("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertIn("extraction_quality_status", summary)
        self.assertIn("extraction_quality_report_path", summary)
        entry = load_source_registry(self.course)["sources"][0]
        self.assertIn("extraction_quality_status", entry)
        json_path, md_path = get_extraction_quality_report_paths(
            self.course, "SRC-0001"
        )
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())


class TestCheckExtractionQualityCli(unittest.TestCase):
    @patch("scripts.check_extraction_quality.run_extraction_quality_check")
    def test_cli_smoke(self, mock_run) -> None:
        from scripts import check_extraction_quality as cli_module

        mock_run.return_value = {
            "course": "ECA1010_Test",
            "source_id": "SRC-0001",
            "title": "Book",
            "quality_status": "ok",
            "total_pages": 2,
            "total_words": 240,
            "average_words_per_page": 120,
            "total_characters": 1200,
            "warnings": [],
            "report_json_path": "/tmp/report.json",
            "report_markdown_path": "/tmp/report.md",
        }
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = cli_module.main(
                ["--course", "ECA1010_Test", "--source-id", "SRC-0001"],
            )
        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn("Extraction quality report", output)
        self.assertIn("Quality:", output)


if __name__ == "__main__":
    unittest.main()
