"""Tests for local digest jobs (mocked LM Studio)."""

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

from studyforge.core.digest_jobs import (  # noqa: E402
    DEFAULT_DIGEST_MAX_TOKENS,
    DigestOutputExistsError,
    digest_has_required_sections,
    get_local_digest_dir,
    get_local_digest_log_path,
    run_local_digest_for_source,
)
from studyforge.core.sources import load_source_registry  # noqa: E402
from studyforge.llm.digest_prompts import build_local_digest_messages  # noqa: E402

CHUNK_MD = """# Source Chunk

Chunk ID:
SRC-0001-CHUNK-0001

---

Sample chunk text for digest.
"""


INCOMPLETE_DIGEST = """# Local Digest for SRC-0001-CHUNK-0001

## Big Picture

Overview only.
"""

COMPLETE_DIGEST = """# Local Digest for SRC-0001-CHUNK-0001

## Big Picture

Overview here with enough words to pass minimum length checks easily.

## Key Ideas

Idea one.

## Definitions

Term A.

## Formulas / Rules / Methods

Rule one.

## Worked Examples from the Source

Example.

## Practice Questions

Q1?

## Uncertain Claims

None.

## Source References

Page 1.
"""


class TestDigestJobs(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        courses.mkdir()
        self.course = courses / "ECA1010_Test"
        self.course.mkdir()

        chunk_dir = self.course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True)
        self.chunk_file = chunk_dir / "SRC-0001-CHUNK-0001.md"
        self.chunk_file.write_text(CHUNK_MD, encoding="utf-8")

        manifest = {
            "source_id": "SRC-0001",
            "chunks": [
                {
                    "chunk_id": "SRC-0001-CHUNK-0001",
                    "chunk_number": 1,
                    "file_path": str(self.chunk_file.resolve()),
                    "page_start": 1,
                    "page_end": 1,
                    "pages": [1],
                    "word_count": 10,
                },
                {
                    "chunk_id": "SRC-0001-CHUNK-0002",
                    "chunk_number": 2,
                    "file_path": str((chunk_dir / "SRC-0001-CHUNK-0002.md").resolve()),
                    "page_start": 2,
                    "page_end": 2,
                    "pages": [2],
                    "word_count": 10,
                },
            ],
        }
        (chunk_dir / "chunk_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (chunk_dir / "SRC-0001-CHUNK-0002.md").write_text(CHUNK_MD, encoding="utf-8")

        (self.course / "08_App_Data").mkdir(parents=True)
        registry = {
            "sources": [
                {
                    "id": "SRC-0001",
                    "title": "Test Book",
                    "status": "chunked",
                    "chunk_manifest_path": str((chunk_dir / "chunk_manifest.json").resolve()),
                }
            ]
        }
        from studyforge.core.sources import save_source_registry

        save_source_registry(self.course, registry)

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

    def _complete_digest(self, chunk_id: str) -> str:
        return COMPLETE_DIGEST.replace("SRC-0001-CHUNK-0001", chunk_id)

    @mock.patch("studyforge.core.digest_jobs.chat_completion")
    @mock.patch("studyforge.core.digest_jobs.check_lm_studio_connection")
    def test_registry_status_complete(
        self, mock_check: mock.Mock, mock_chat: mock.Mock
    ) -> None:
        mock_check.return_value = {
            "ok": True,
            "base_url": "http://localhost:1234/v1",
            "models": ["test-model"],
            "error": None,
        }
        mock_chat.side_effect = [
            self._complete_digest("SRC-0001-CHUNK-0001"),
            self._complete_digest("SRC-0001-CHUNK-0002"),
        ]

        summary = run_local_digest_for_source(
            "ECA1010_Test", "SRC-0001", model="test-model", root=self.root
        )
        self.assertEqual(summary["chunk_count_processed"], 2)
        registry = load_source_registry(self.course)
        self.assertEqual(registry["sources"][0]["status"], "local_digest_complete")
        self.assertEqual(registry["sources"][0]["local_digest_model"], "test-model")

        digest_dir = get_local_digest_dir(self.course, "SRC-0001")
        self.assertTrue((digest_dir / "SRC-0001-CHUNK-0001_digest.md").is_file())
        self.assertTrue((digest_dir / "SRC-0001_combined_local_digest.md").is_file())
        self.assertTrue(get_local_digest_log_path(self.course, "SRC-0001").is_file())

    @mock.patch("studyforge.core.digest_jobs.chat_completion")
    @mock.patch("studyforge.core.digest_jobs.check_lm_studio_connection")
    def test_refuse_overwrite(
        self, mock_check: mock.Mock, mock_chat: mock.Mock
    ) -> None:
        mock_check.return_value = {"ok": True, "models": ["m"], "error": None}
        mock_chat.side_effect = [
            self._complete_digest("SRC-0001-CHUNK-0001"),
            self._complete_digest("SRC-0001-CHUNK-0002"),
        ]
        run_local_digest_for_source(
            "ECA1010_Test", "SRC-0001", model="m", root=self.root
        )
        with self.assertRaises(DigestOutputExistsError):
            run_local_digest_for_source(
                "ECA1010_Test", "SRC-0001", model="m", root=self.root
            )

    @mock.patch("studyforge.core.digest_jobs.chat_completion")
    @mock.patch("studyforge.core.digest_jobs.check_lm_studio_connection")
    def test_limit_chunks(
        self, mock_check: mock.Mock, mock_chat: mock.Mock
    ) -> None:
        mock_check.return_value = {"ok": True, "models": ["m"], "error": None}
        mock_chat.return_value = self._complete_digest("SRC-0001-CHUNK-0001")
        summary = run_local_digest_for_source(
            "ECA1010_Test",
            "SRC-0001",
            model="m",
            limit_chunks=1,
            overwrite=True,
            root=self.root,
        )
        self.assertEqual(summary["chunk_count_total"], 1)
        self.assertEqual(mock_chat.call_count, 1)
        registry = load_source_registry(self.course)
        self.assertEqual(registry["sources"][0]["status"], "local_digest_partial")

    @mock.patch("studyforge.core.digest_jobs.chat_completion")
    @mock.patch("studyforge.core.digest_jobs.check_lm_studio_connection")
    def test_resume_full_digest_without_overwrite(
        self, mock_check: mock.Mock, mock_chat: mock.Mock
    ) -> None:
        mock_check.return_value = {"ok": True, "models": ["m"], "error": None}
        mock_chat.return_value = self._complete_digest("SRC-0001-CHUNK-0001")
        run_local_digest_for_source(
            "ECA1010_Test",
            "SRC-0001",
            model="m",
            limit_chunks=1,
            root=self.root,
        )
        mock_chat.reset_mock()
        mock_chat.return_value = self._complete_digest("SRC-0001-CHUNK-0002")
        summary = run_local_digest_for_source(
            "ECA1010_Test", "SRC-0001", model="m", root=self.root
        )
        self.assertEqual(mock_chat.call_count, 1)
        self.assertEqual(summary["chunk_count_processed"], 2)
        registry = load_source_registry(self.course)
        self.assertEqual(registry["sources"][0]["status"], "local_digest_complete")

    @mock.patch("studyforge.core.digest_jobs.chat_completion")
    @mock.patch("studyforge.core.digest_jobs.check_lm_studio_connection")
    def test_exists_error_when_all_chunks_already_digested(
        self, mock_check: mock.Mock, mock_chat: mock.Mock
    ) -> None:
        mock_check.return_value = {"ok": True, "models": ["m"], "error": None}
        mock_chat.side_effect = [
            self._complete_digest("SRC-0001-CHUNK-0001"),
            self._complete_digest("SRC-0001-CHUNK-0002"),
        ]
        run_local_digest_for_source(
            "ECA1010_Test", "SRC-0001", model="m", root=self.root
        )
        with self.assertRaises(DigestOutputExistsError) as ctx:
            run_local_digest_for_source(
                "ECA1010_Test", "SRC-0001", model="m", root=self.root
            )
        self.assertIn("overwrite", str(ctx.exception).lower())

    def test_default_max_tokens_constant(self) -> None:
        self.assertGreaterEqual(DEFAULT_DIGEST_MAX_TOKENS, 6000)

    def test_digest_has_required_sections(self) -> None:
        self.assertFalse(digest_has_required_sections(INCOMPLETE_DIGEST))
        self.assertTrue(digest_has_required_sections(COMPLETE_DIGEST))

    @mock.patch("studyforge.core.digest_jobs.chat_completion")
    @mock.patch("studyforge.core.digest_jobs.check_lm_studio_connection")
    def test_retries_when_sections_missing(
        self, mock_check: mock.Mock, mock_chat: mock.Mock
    ) -> None:
        mock_check.return_value = {"ok": True, "models": ["m"], "error": None}
        mock_chat.side_effect = [INCOMPLETE_DIGEST, COMPLETE_DIGEST]
        summary = run_local_digest_for_source(
            "ECA1010_Test",
            "SRC-0001",
            model="m",
            limit_chunks=1,
            overwrite=True,
            root=self.root,
        )
        self.assertEqual(mock_chat.call_count, 2)
        self.assertEqual(summary["chunk_count_processed"], 1)
        digest_path = get_local_digest_dir(self.course, "SRC-0001") / (
            "SRC-0001-CHUNK-0001_digest.md"
        )
        self.assertTrue(digest_has_required_sections(digest_path.read_text(encoding="utf-8")))

    @mock.patch("studyforge.core.digest_jobs.chat_completion")
    @mock.patch("studyforge.core.digest_jobs.check_lm_studio_connection")
    def test_regenerates_incomplete_existing_digest(
        self, mock_check: mock.Mock, mock_chat: mock.Mock
    ) -> None:
        mock_check.return_value = {"ok": True, "models": ["m"], "error": None}
        digest_path = get_local_digest_dir(self.course, "SRC-0001") / (
            "SRC-0001-CHUNK-0001_digest.md"
        )
        digest_path.write_text(INCOMPLETE_DIGEST, encoding="utf-8")
        mock_chat.return_value = COMPLETE_DIGEST
        run_local_digest_for_source(
            "ECA1010_Test",
            "SRC-0001",
            model="m",
            limit_chunks=1,
            root=self.root,
        )
        self.assertEqual(mock_chat.call_count, 1)
        self.assertTrue(digest_has_required_sections(digest_path.read_text(encoding="utf-8")))

    def test_build_messages_contains_chunk_id(self) -> None:
        messages = build_local_digest_messages(
            "chunk body", "ECA1010_Test", "SRC-0001", "SRC-0001-CHUNK-0001"
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("SRC-0001-CHUNK-0001", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
