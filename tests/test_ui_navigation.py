"""Tests for Streamlit navigation helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.ui.navigation import (  # noqa: E402
    flatten_navigation_pages,
    get_navigation_pages,
    navigation_keys,
    option_to_page_key,
)


class TestUiNavigation(unittest.TestCase):
    def test_today_is_first(self) -> None:
        pages = get_navigation_pages()
        self.assertEqual(pages[0]["key"], "today")
        self.assertEqual(pages[0]["label"], "Today")

    def test_expected_pages_exist(self) -> None:
        keys = navigation_keys()
        expected = {
            "today",
            "dashboard",
            "sources",
            "pipeline",
            "audits",
            "study_units",
            "study_session",
            "active_recall",
            "flashcards",
            "mock_tests",
            "exam_prep",
            "review_tracker",
            "course_quality",
            "evidence_trace",
            "courses",
            "settings",
        }
        self.assertEqual(set(keys), expected)
        self.assertEqual(len(keys), len(expected))

    def test_no_duplicate_page_keys(self) -> None:
        keys = navigation_keys()
        self.assertEqual(len(keys), len(set(keys)))

    def test_flatten_navigation_pages(self) -> None:
        labels = flatten_navigation_pages()
        self.assertEqual(labels[0], "Today")
        self.assertIn("Build Study Material · Pipeline", labels)
        self.assertIn("Study / Review · Study Session", labels)
        self.assertIn("Quality / Trust · Course Quality", labels)
        self.assertEqual(len(labels), len(get_navigation_pages()))

    def test_option_to_page_key_roundtrip(self) -> None:
        for label in flatten_navigation_pages():
            key = option_to_page_key(label)
            self.assertIsNotNone(key)


if __name__ == "__main__":
    unittest.main()
