"""Tests for automated intermediate audit jobs."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.intermediate_audit_jobs import (  # noqa: E402
    run_intermediate_audit_for_source,
)


class TestIntermediateAuditJobs(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        course = courses / "ECA1010_Test"
        chunk_dir = course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True)
        chunk_file = chunk_dir / "SRC-0001-CHUNK-0001.md"
        chunk_file.write_text("# chunk\n\nSource text.", encoding="utf-8")
        digest_dir = course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        (digest_dir / "SRC-0001-CHUNK-0001_digest.md").write_text(
            "# digest\n\n## Big Picture\n\nx\n\n## Key Ideas\n\ny\n\n"
            "## Definitions\n\nz\n\n## Formulas / Rules / Methods\n\na\n\n"
            "## Worked Examples from the Source\n\nb\n\n## Practice Questions\n\nc\n\n"
            "## Uncertain Claims\n\nd\n\n## Source References\n\ne\n",
            encoding="utf-8",
        )
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text(
            "# combined", encoding="utf-8"
        )
        (chunk_dir / "chunk_manifest.json").write_text(
            json.dumps(
                {
                    "chunks": [
                        {
                            "chunk_id": "SRC-0001-CHUNK-0001",
                            "file_path": str(chunk_file.resolve()),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (course / "08_App_Data").mkdir(parents=True)
        from studyforge.core.sources import save_source_registry

        save_source_registry(
            course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "T",
                        "status": "local_digest_complete",
                        "local_digest_path": str(
                            (digest_dir / "SRC-0001_combined_local_digest.md").resolve()
                        ),
                    }
                ]
            },
        )
        (self.root / "config").mkdir()
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps(
                {
                    "project_root": str(self.root),
                    "courses_dir": str(courses),
                    "default_course_template": "_Course_Template",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @mock.patch("studyforge.core.intermediate_audit_jobs.generate_content")
    @mock.patch("studyforge.core.intermediate_audit_jobs.time.sleep")
    def test_run_imports_audit(
        self, _sleep: mock.Mock, mock_gen: mock.Mock
    ) -> None:
        mock_gen.return_value = (
            "Wait, let me check.\n\n"
            "## Audit — SRC-0001-CHUNK-0001\n\n"
            "No major issues found.\n"
        )
        summary = run_intermediate_audit_for_source(
            "ECA1010_Test",
            "SRC-0001",
            api_key="fake-key",
            request_interval_seconds=0,
            root=self.root,
        )
        self.assertEqual(summary["status"], "imported")
        saved = Path(summary["saved_path"])
        self.assertTrue(saved.is_file())
        content = saved.read_text(encoding="utf-8")
        self.assertNotIn("Wait, let me check", content)
        self.assertIn("No major issues found", content)
        self.assertGreater(summary["sanitization"]["sanitizer_removed_words"], 0)
        self.assertEqual(mock_gen.call_count, 1)

    @mock.patch("studyforge.core.intermediate_audit_jobs.generate_content")
    @mock.patch("studyforge.core.intermediate_audit_jobs.time.sleep")
    def test_keep_raw_saves_debug_files(
        self, _sleep: mock.Mock, mock_gen: mock.Mock
    ) -> None:
        mock_gen.return_value = "Wait.\n\n## Audit — SRC-0001-CHUNK-0001\n\nOK\n"
        summary = run_intermediate_audit_for_source(
            "ECA1010_Test",
            "SRC-0001",
            api_key="fake-key",
            request_interval_seconds=0,
            keep_raw=True,
            root=self.root,
        )
        raw_path = (
            Path(summary["raw_debug_dir"]) / "SRC-0001-CHUNK-0001_raw.md"
        )
        self.assertTrue(raw_path.is_file())
        self.assertIn("Wait.", raw_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
