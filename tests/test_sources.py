"""Tests for source material management."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import (  # noqa: E402
    CourseNotFoundError,
    SourceFileNotFoundError,
    SourceTypeError,
    add_source,
    list_sources,
    sanitize_file_name,
    validate_source_type,
)


class TestSourceValidation(unittest.TestCase):
    def test_valid_type(self) -> None:
        self.assertEqual(validate_source_type("Textbook"), "textbook")

    def test_invalid_type_lists_allowed(self) -> None:
        with self.assertRaises(SourceTypeError) as ctx:
            validate_source_type("video")
        self.assertIn("textbook", str(ctx.exception))


class TestSanitizeFileName(unittest.TestCase):
    def test_keeps_extension(self) -> None:
        self.assertEqual(sanitize_file_name("chapter book.pdf"), "chapter_book.pdf")

    def test_removes_invalid_chars(self) -> None:
        self.assertEqual(sanitize_file_name('bad<>:".pdf'), "bad.pdf")


class TestAddSource(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

        courses = self.root / "courses"
        courses.mkdir()
        self.course = courses / "ECA1010_Micro"
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

        self.source_pdf = self.root / "incoming.pdf"
        self.source_pdf.write_bytes(b"%PDF-1.4 test")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_add_source_copies_and_registers(self) -> None:
        stored = add_source(
            "ECA1010_Micro",
            "textbook",
            self.source_pdf,
            title="Main Textbook",
            root=self.root,
        )
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.name, "incoming.pdf")

        entries = list_sources("ECA1010_Micro", root=self.root)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "SRC-0001")
        self.assertEqual(entries[0]["title"], "Main Textbook")
        self.assertEqual(entries[0]["source_type"], "textbook")

    def test_unique_name_when_file_exists(self) -> None:
        add_source("ECA1010_Micro", "textbook", self.source_pdf, root=self.root)
        second = add_source("ECA1010_Micro", "textbook", self.source_pdf, root=self.root)
        self.assertEqual(second.name, "incoming_002.pdf")
        self.assertEqual(len(list_sources("ECA1010_Micro", root=self.root)), 2)

    def test_course_not_found(self) -> None:
        with self.assertRaises(CourseNotFoundError):
            add_source("MISSING", "textbook", self.source_pdf, root=self.root)

    def test_file_not_found(self) -> None:
        with self.assertRaises(SourceFileNotFoundError):
            add_source(
                "ECA1010_Micro",
                "textbook",
                self.root / "nope.pdf",
                root=self.root,
            )


if __name__ == "__main__":
    unittest.main()
