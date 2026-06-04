"""Tests for final audit packet export."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.final_packet import (  # noqa: E402
    FinalPacketOutputExistsError,
    NoIntermediateAuditError,
    build_final_audit_packet,
    build_final_auditor_instructions,
    get_latest_intermediate_audit,
)

CHUNK_SOURCE = "# Source Chunk\n\nSource body.\n"
CHUNK_DIGEST = "# Digest\n\nDigest body.\n"
INTERMEDIATE_AUDIT = "# Intermediate Audit\n\nGemini found one issue.\n"
COMBINED_DIGEST = "# Combined Local Digest\n\nAll chunks combined.\n"


class TestFinalPacket(unittest.TestCase):
    def test_instructions_contain_anti_slop_rules(self) -> None:
        text = build_final_auditor_instructions()
        self.assertIn("do not blindly trust", text.lower())
        self.assertIn("not verified", text.lower())
        self.assertIn("source chunks", text.lower())

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        self.course.mkdir(parents=True)

        chunk_dir = self.course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True)
        self.chunk1 = chunk_dir / "SRC-0001-CHUNK-0001.md"
        self.chunk1.write_text(CHUNK_SOURCE, encoding="utf-8")
        manifest = {
            "chunks": [
                {
                    "chunk_id": "SRC-0001-CHUNK-0001",
                    "file_path": str(self.chunk1.resolve()),
                }
            ]
        }
        (chunk_dir / "chunk_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        (digest_dir / "SRC-0001-CHUNK-0001_digest.md").write_text(
            CHUNK_DIGEST, encoding="utf-8"
        )
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text(
            COMBINED_DIGEST, encoding="utf-8"
        )

        inter_dir = self.course / "04_Intermediate_Audits" / "SRC-0001"
        inter_dir.mkdir(parents=True)
        audit_path = inter_dir / "SRC-0001_intermediate_audit_v001.md"
        audit_path.write_text(INTERMEDIATE_AUDIT, encoding="utf-8")
        registry = {
            "source_id": "SRC-0001",
            "audits": [
                {
                    "version": 1,
                    "audit_id": "IA-SRC-0001-V001",
                    "auditor_name": "Gemini",
                    "file_path": str(audit_path.resolve()),
                    "date_imported": "2026-01-01T00:00:00",
                    "notes": "test",
                    "word_count": 10,
                    "status": "imported",
                }
            ],
        }
        (inter_dir / "SRC-0001_intermediate_audit_registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

        from studyforge.core.sources import save_source_registry

        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Test Book",
                        "status": "intermediate_audit_imported",
                        "source_type": "textbook",
                        "file_name": "book.pdf",
                        "stored_path": "C:/book.pdf",
                        "latest_intermediate_audit_id": "IA-SRC-0001-V001",
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

    def test_latest_intermediate_audit_selection(self) -> None:
        result = get_latest_intermediate_audit(self.course, "SRC-0001")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["entry"]["audit_id"], "IA-SRC-0001-V001")
        self.assertIn("Gemini", result["text"])

    def test_refuse_without_intermediate_audit(self) -> None:
        empty_course = self.root / "courses" / "EMPTY"
        empty_course.mkdir(parents=True)
        from studyforge.core.sources import save_source_registry

        save_source_registry(
            empty_course,
            {"sources": [{"id": "SRC-0001", "title": "X", "status": "chunked"}]},
        )
        with self.assertRaises(NoIntermediateAuditError):
            build_final_audit_packet("EMPTY", "SRC-0001", root=self.root)

    def test_build_packet_with_combined_and_chunks(self) -> None:
        summary = build_final_audit_packet(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        text = Path(summary["packet_path"]).read_text(encoding="utf-8")
        self.assertIn("## Combined Local Digest", text)
        self.assertIn("Combined Local Digest", text)
        self.assertIn("### Source Chunk", text)
        self.assertIn("Gemini found one issue", text)
        self.assertTrue(Path(summary["packet_json_path"]).is_file())

    def test_refuse_overwrite(self) -> None:
        build_final_audit_packet("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(FinalPacketOutputExistsError):
            build_final_audit_packet("ECA1010_Test", "SRC-0001", root=self.root)

    def test_allow_overwrite_and_limit_chunks(self) -> None:
        build_final_audit_packet("ECA1010_Test", "SRC-0001", root=self.root)
        summary = build_final_audit_packet(
            "ECA1010_Test",
            "SRC-0001",
            root=self.root,
            overwrite=True,
            limit_chunks=1,
        )
        self.assertEqual(summary["selected_chunk_count"], 1)


if __name__ == "__main__":
    unittest.main()
