"""Tests for rule-based local digest review."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.study.digest_review import (  # noqa: E402
    check_required_sections,
    count_uncertainty_markers,
    review_digest_file,
    review_local_digest_for_source,
)

FULL_DIGEST = """# Local Digest for SRC-0001-CHUNK-0001

## Big Picture

Overview here with enough words to pass minimum length checks easily.

## Key Ideas

Idea one and idea two.

## Definitions

Term A means something.

## Formulas / Rules / Methods

Rule one applies.

## Worked Examples from the Source

Example from page 1.

## Practice Questions

Question 1?

## Uncertain Claims

Not verified in this chunk for one item.

## Source References

Page 1 reference material and additional study notes for completeness.
"""

SHORT_DIGEST = """# Local Digest

## Big Picture

Too short.
"""


class TestUncertaintyAndSections(unittest.TestCase):
    def test_count_uncertainty_markers(self) -> None:
        text = "This is uncertain. Not verified in this chunk. UNCLEAR."
        self.assertEqual(count_uncertainty_markers(text), 2)

    def test_placeholder_not_counted_as_uncertainty(self) -> None:
        text = "Only placeholder: Not verified in this chunk."
        self.assertEqual(count_uncertainty_markers(text), 0)

    def test_detect_required_sections(self) -> None:
        result = check_required_sections(FULL_DIGEST)
        self.assertEqual(result["missing"], [])

    def test_missing_sections(self) -> None:
        result = check_required_sections("# Title\n\n## Big Picture\n\nOnly one.")
        self.assertIn("Key Ideas", result["missing"])


class TestReviewDigestFile(unittest.TestCase):
    def test_very_short_digest_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "short.md"
            path.write_text(SHORT_DIGEST, encoding="utf-8")
            review = review_digest_file(path, min_words=200)
            self.assertEqual(review["status"], "needs_review")
            self.assertTrue(any("very short" in w.lower() for w in review["warnings"]))

    def test_missing_file_review(self) -> None:
        review = review_digest_file(Path("/nonexistent/digest.md"))
        self.assertEqual(review["status"], "failed")
        self.assertFalse(review["exists"])


class TestReviewLocalDigestForSource(unittest.TestCase):
    def _setup_course(self, digests: dict[str, str], log: dict | None, status: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self._tmp = tmp
        root = Path(tmp.name)
        courses = root / "courses"
        course = courses / "ECA1010_Test"
        digest_dir = course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)

        chunk_dir = course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True)
        manifest = {
            "chunks": [
                {"chunk_id": "SRC-0001-CHUNK-0001"},
                {"chunk_id": "SRC-0001-CHUNK-0002"},
            ]
        }
        (chunk_dir / "chunk_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        for name, content in digests.items():
            (digest_dir / name).write_text(content, encoding="utf-8")

        (course / "08_App_Data" / "job_logs").mkdir(parents=True)
        log_path = course / "08_App_Data" / "job_logs" / "SRC-0001_local_digest_log.json"
        if log:
            log_path.write_text(json.dumps(log), encoding="utf-8")

        registry = {
            "sources": [
                {
                    "id": "SRC-0001",
                    "title": "Test Book",
                    "status": status,
                    "local_digest_log_path": str(log_path.resolve()) if log else "",
                    "local_digest_path": str(
                        (digest_dir / "SRC-0001_combined_local_digest.md").resolve()
                    ),
                }
            ]
        }
        (course / "08_App_Data").mkdir(parents=True, exist_ok=True)
        from studyforge.core.sources import save_source_registry

        save_source_registry(course, registry)

        (root / "config").mkdir()
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
        return root

    def tearDown(self) -> None:
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def test_overall_status_ok(self) -> None:
        root = self._setup_course(
            {
                "SRC-0001-CHUNK-0001_digest.md": FULL_DIGEST,
                "SRC-0001-CHUNK-0002_digest.md": FULL_DIGEST.replace(
                    "CHUNK-0001", "CHUNK-0002"
                ),
                "SRC-0001_combined_local_digest.md": FULL_DIGEST,
            },
            log={
                "chunks": [
                    {"chunk_id": "SRC-0001-CHUNK-0001", "status": "complete"},
                    {"chunk_id": "SRC-0001-CHUNK-0002", "status": "complete"},
                ]
            },
            status="local_digest_complete",
        )
        summary = review_local_digest_for_source(
            "ECA1010_Test", "SRC-0001", root=root, min_words=50
        )
        self.assertEqual(summary["overall_status"], "ok")
        self.assertTrue(Path(summary["report_path_md"]).is_file())
        self.assertTrue(Path(summary["report_path_json"]).is_file())

    def test_overall_status_needs_review(self) -> None:
        root = self._setup_course(
            {
                "SRC-0001-CHUNK-0001_digest.md": FULL_DIGEST,
                "SRC-0001-CHUNK-0002_digest.md": SHORT_DIGEST,
                "SRC-0001_combined_local_digest.md": FULL_DIGEST,
            },
            log={"chunks": [{"chunk_id": "SRC-0001-CHUNK-0001", "status": "complete"}]},
            status="local_digest_partial",
        )
        summary = review_local_digest_for_source(
            "ECA1010_Test", "SRC-0001", root=root
        )
        self.assertEqual(summary["overall_status"], "needs_review")
        self.assertGreaterEqual(summary["digests_needing_review"], 1)

    def test_overall_status_failed(self) -> None:
        root = self._setup_course(
            {"SRC-0001-CHUNK-0001_digest.md": FULL_DIGEST},
            log={
                "chunks": [
                    {"chunk_id": "SRC-0001-CHUNK-0001", "status": "failed"},
                ]
            },
            status="local_digest_partial",
        )
        summary = review_local_digest_for_source(
            "ECA1010_Test", "SRC-0001", root=root, min_words=50
        )
        self.assertEqual(summary["overall_status"], "failed")


if __name__ == "__main__":
    unittest.main()
