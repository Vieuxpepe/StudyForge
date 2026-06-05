"""Tests for Evidence Trace Viewer v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.evidence_trace import (  # noqa: E402
    build_chunk_trace_markdown,
    export_chunk_trace,
    find_mentions_in_markdown,
    get_chunk_trace,
    get_source_trace_summary,
    list_source_chunks,
)


def _setup_course(root: Path, entry: dict) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(course, {"sources": [entry]})
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


class TestEvidenceTrace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.pdf = self.root / "book.pdf"
        self.pdf.write_bytes(b"%PDF")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _build_fixture(self) -> Path:
        course = _setup_course(
            self.root,
            {
                "id": "SRC-0001",
                "title": "Main Textbook",
                "source_type": "textbook",
                "status": "study_pack_generated",
                "stored_path": str(self.pdf.resolve()),
            },
        )

        chunk_dir = course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True)
        chunk_path = chunk_dir / "SRC-0001-CHUNK-0001.md"
        chunk_path.write_text("## Page 1\n\nSource chunk text.", encoding="utf-8")
        manifest = chunk_dir / "chunk_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "chunks": [
                        {
                            "chunk_id": "SRC-0001-CHUNK-0001",
                            "chunk_number": 1,
                            "page_start": 1,
                            "page_end": 3,
                            "word_count": 1100,
                            "file_path": str(chunk_path.resolve()),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        digest_dir = course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        (digest_dir / "SRC-0001-CHUNK-0001_digest.md").write_text(
            "Digest for SRC-0001-CHUNK-0001",
            encoding="utf-8",
        )
        (digest_dir / "SRC-0001_local_digest_review.md").write_text(
            "Review notes for SRC-0001-CHUNK-0001 chunk.",
            encoding="utf-8",
        )

        ia_dir = course / "04_Intermediate_Audits" / "SRC-0001"
        ia_dir.mkdir(parents=True)
        ia_path = ia_dir / "SRC-0001_intermediate_audit_v001.md"
        ia_path.write_text("Intermediate audit mentions SRC-0001-CHUNK-0001.", encoding="utf-8")

        fa_dir = course / "05_Final_Audits" / "SRC-0001"
        fa_dir.mkdir(parents=True)
        fa_path = fa_dir / "SRC-0001_final_audit_v001.md"
        fa_path.write_text("Final audit references SRC-0001-CHUNK-0001.", encoding="utf-8")

        outputs = course / "06_Study_Outputs"
        (outputs / "study_guides").mkdir(parents=True)
        (outputs / "flashcards").mkdir(parents=True)
        (outputs / "active_recall").mkdir(parents=True)
        (outputs / "study_guides" / "SRC-0001_final_study_guide.md").write_text(
            "# Guide", encoding="utf-8"
        )
        (outputs / "flashcards" / "SRC-0001_flashcards.md").write_text(
            "# Cards", encoding="utf-8"
        )
        (outputs / "active_recall" / "SRC-0001_active_recall.md").write_text(
            "# Recall", encoding="utf-8"
        )
        (outputs / "SRC-0001_study_pack_manifest.json").write_text("{}", encoding="utf-8")

        save_source_registry(
            course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Main Textbook",
                        "source_type": "textbook",
                        "status": "study_pack_generated",
                        "stored_path": str(self.pdf.resolve()),
                        "extracted_text_path": str(
                            (course / "02_Extracted_Text" / "extracted_sources" / "SRC-0001_extracted_text.md")
                        ),
                        "chunk_manifest_path": str(manifest.resolve()),
                        "local_digest_path": str(
                            (digest_dir / "SRC-0001_combined_local_digest.md").resolve()
                        ),
                        "latest_intermediate_audit_path": str(ia_path.resolve()),
                        "latest_final_audit_path": str(fa_path.resolve()),
                        "study_pack_manifest_path": str(
                            (outputs / "SRC-0001_study_pack_manifest.json").resolve()
                        ),
                        "final_study_guide_path": str(
                            (outputs / "study_guides" / "SRC-0001_final_study_guide.md").resolve()
                        ),
                        "flashcards_path": str(
                            (outputs / "flashcards" / "SRC-0001_flashcards.md").resolve()
                        ),
                        "active_recall_path": str(
                            (outputs / "active_recall" / "SRC-0001_active_recall.md").resolve()
                        ),
                    }
                ]
            },
        )
        (course / "02_Extracted_Text" / "extracted_sources").mkdir(parents=True, exist_ok=True)
        return course

    def test_source_trace_summary_detects_artifacts(self) -> None:
        self._build_fixture()
        summary = get_source_trace_summary("ECA1010_Test", "SRC-0001", root=self.root)
        artifacts = summary["available_artifacts"]
        self.assertTrue(artifacts["source_pdf"])
        self.assertTrue(artifacts["chunk_manifest"])
        self.assertTrue(artifacts["intermediate_audit"])
        self.assertTrue(artifacts["final_audit"])
        self.assertTrue(artifacts["study_pack"])
        self.assertTrue(artifacts["flashcards"])
        self.assertTrue(artifacts["active_recall"])

    def test_list_source_chunks(self) -> None:
        self._build_fixture()
        chunks = list_source_chunks("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_id"], "SRC-0001-CHUNK-0001")
        self.assertEqual(chunks[0]["word_count"], 1100)

    def test_get_chunk_trace_loads_chunks(self) -> None:
        self._build_fixture()
        trace = get_chunk_trace(
            "ECA1010_Test",
            "SRC-0001",
            "SRC-0001-CHUNK-0001",
            root=self.root,
        )
        self.assertTrue(trace["source_chunk"]["exists"])
        self.assertIn("Source chunk text", trace["source_chunk"]["text"])
        self.assertTrue(trace["local_digest_chunk"]["exists"])
        self.assertIn("Digest for", trace["local_digest_chunk"]["text"])
        self.assertEqual(len(trace["digest_review_mentions"]), 1)

    def test_missing_digest_chunk_warning(self) -> None:
        course = self._build_fixture()
        missing_digest = (
            course / "03_Local_Digests" / "SRC-0001" / "SRC-0001-CHUNK-0001_digest.md"
        )
        missing_digest.unlink()
        trace = get_chunk_trace(
            "ECA1010_Test",
            "SRC-0001",
            "SRC-0001-CHUNK-0001",
            root=self.root,
        )
        self.assertFalse(trace["local_digest_chunk"]["exists"])
        self.assertTrue(any("digest chunk missing" in w.lower() for w in trace["warnings"]))

    def test_find_mentions_in_markdown(self) -> None:
        text = "Intro\nLine about SRC-0001-CHUNK-0001 here\nMore text\n"
        mentions = find_mentions_in_markdown(text, "SRC-0001-CHUNK-0001", context_lines=1)
        self.assertEqual(len(mentions), 1)
        self.assertIn("SRC-0001-CHUNK-0001", mentions[0]["snippet"])

    def test_build_chunk_trace_markdown(self) -> None:
        self._build_fixture()
        trace = get_chunk_trace(
            "ECA1010_Test",
            "SRC-0001",
            "SRC-0001-CHUNK-0001",
            root=self.root,
        )
        markdown = build_chunk_trace_markdown(trace)
        self.assertIn("# Evidence Trace — SRC-0001-CHUNK-0001", markdown)
        self.assertIn("## Source Chunk", markdown)
        self.assertIn("## Local Digest Chunk", markdown)
        self.assertIn("Source chunk text", markdown)

    def test_export_chunk_trace_writes_file(self) -> None:
        course = self._build_fixture()
        path = export_chunk_trace(
            "ECA1010_Test",
            "SRC-0001",
            "SRC-0001-CHUNK-0001",
            root=self.root,
        )
        self.assertTrue(path.is_file())
        self.assertIn("evidence_traces", str(path))
        self.assertIn("SRC-0001-CHUNK-0001", path.name)


class TestEvidenceTraceCli(unittest.TestCase):
    @patch("scripts.evidence_trace.get_source_trace_summary")
    def test_cli_summary_smoke(self, mock_summary) -> None:
        from scripts import evidence_trace as cli_module

        mock_summary.return_value = {
            "course": "ECA1010_Test",
            "source_id": "SRC-0001",
            "title": "Book",
            "registry_status": "chunked",
            "available_artifacts": {"chunk_manifest": True},
            "paths": {},
            "warnings": [],
        }
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = cli_module.main(
                ["--course", "ECA1010_Test", "--source-id", "SRC-0001", "--summary"]
            )
        self.assertEqual(code, 0)
        self.assertIn("Evidence trace summary", buffer.getvalue())

    @patch("scripts.evidence_trace.list_source_chunks")
    def test_cli_chunks_smoke(self, mock_chunks) -> None:
        from scripts import evidence_trace as cli_module

        mock_chunks.return_value = [
            {
                "chunk_id": "SRC-0001-CHUNK-0001",
                "page_start": 1,
                "page_end": 3,
                "word_count": 1100,
                "file_path": "/tmp/chunk.md",
            }
        ]
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = cli_module.main(
                ["--course", "ECA1010_Test", "--source-id", "SRC-0001", "--chunks"]
            )
        self.assertEqual(code, 0)
        self.assertIn("Chunks (1)", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
