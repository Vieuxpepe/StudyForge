"""Tests for intermediate audit packet export."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.intermediate_packet import (  # noqa: E402
    PacketOutputExistsError,
    build_intermediate_audit_instructions,
    build_intermediate_audit_packet,
    select_chunks_for_audit,
)

CHUNK_SOURCE = """# Source Chunk

Chunk ID:
SRC-0001-CHUNK-0001

---

Source text here for audit.
"""

CHUNK_DIGEST = """# Local Digest for SRC-0001-CHUNK-0001

## Big Picture

Digest content.
"""


def _manifest() -> dict:
    return {
        "source_id": "SRC-0001",
        "max_words": 1200,
        "overlap_words": 150,
        "chunk_count": 2,
        "chunks": [
            {
                "chunk_id": "SRC-0001-CHUNK-0001",
                "file_path": "placeholder1",
            },
            {
                "chunk_id": "SRC-0001-CHUNK-0002",
                "file_path": "placeholder2",
            },
        ],
    }


class TestIntermediatePacket(unittest.TestCase):
    def test_instructions_contain_audit_rules(self) -> None:
        text = build_intermediate_audit_instructions()
        self.assertIn("intermediate auditor", text.lower())
        self.assertIn("hallucinations", text)
        self.assertIn("not verified", text.lower())

    def test_select_first_n_chunks(self) -> None:
        selected = select_chunks_for_audit(_manifest(), limit_chunks=1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["chunk_id"], "SRC-0001-CHUNK-0001")

    def test_select_only_needs_review(self) -> None:
        review = {
            "files": [
                {
                    "path": "/x/SRC-0001-CHUNK-0002_digest.md",
                    "status": "needs_review",
                },
                {
                    "path": "/x/SRC-0001_combined_local_digest.md",
                    "status": "ok",
                },
            ]
        }
        selected = select_chunks_for_audit(
            _manifest(), digest_review=review, only_needs_review=True
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["chunk_id"], "SRC-0001-CHUNK-0002")

    def test_fallback_all_when_no_needs_review(self) -> None:
        review = {"files": [{"path": "/x/SRC-0001-CHUNK-0001_digest.md", "status": "ok"}]}
        selected = select_chunks_for_audit(
            _manifest(), digest_review=review, only_needs_review=True
        )
        self.assertEqual(len(selected), 2)


class TestBuildPacket(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        self.course.mkdir(parents=True)

        chunk_dir = self.course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True)
        self.chunk1 = chunk_dir / "SRC-0001-CHUNK-0001.md"
        self.chunk2 = chunk_dir / "SRC-0001-CHUNK-0002.md"
        self.chunk1.write_text(CHUNK_SOURCE, encoding="utf-8")
        self.chunk2.write_text(CHUNK_SOURCE.replace("0001", "0002"), encoding="utf-8")

        manifest = _manifest()
        manifest["chunks"][0]["file_path"] = str(self.chunk1.resolve())
        manifest["chunks"][1]["file_path"] = str(self.chunk2.resolve())
        (chunk_dir / "chunk_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        (digest_dir / "SRC-0001-CHUNK-0001_digest.md").write_text(
            CHUNK_DIGEST, encoding="utf-8"
        )
        (digest_dir / "SRC-0001-CHUNK-0002_digest.md").write_text(
            CHUNK_DIGEST.replace("0001", "0002"), encoding="utf-8"
        )
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text(
            "# Combined", encoding="utf-8"
        )

        (self.course / "08_App_Data").mkdir(parents=True)
        from studyforge.core.sources import save_source_registry

        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Test Book",
                        "status": "local_digest_complete",
                        "source_type": "textbook",
                        "file_name": "book.pdf",
                        "stored_path": "C:/books/book.pdf",
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

    def test_packet_includes_source_and_digest(self) -> None:
        summary = build_intermediate_audit_packet(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        text = Path(summary["packet_path"]).read_text(encoding="utf-8")
        self.assertIn("### Source Chunk", text)
        self.assertIn("### Local Digest Chunk", text)
        self.assertIn("Source text here for audit", text)
        self.assertIn("Digest content", text)
        self.assertTrue(Path(summary["packet_json_path"]).is_file())

    def test_refuse_overwrite(self) -> None:
        build_intermediate_audit_packet("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(PacketOutputExistsError):
            build_intermediate_audit_packet("ECA1010_Test", "SRC-0001", root=self.root)

    def test_allow_overwrite(self) -> None:
        build_intermediate_audit_packet("ECA1010_Test", "SRC-0001", root=self.root)
        summary = build_intermediate_audit_packet(
            "ECA1010_Test", "SRC-0001", root=self.root, overwrite=True, limit_chunks=1
        )
        self.assertEqual(summary["selected_chunk_count"], 1)
        meta = json.loads(Path(summary["packet_json_path"]).read_text(encoding="utf-8"))
        self.assertEqual(meta["limit_chunks"], 1)


if __name__ == "__main__":
    unittest.main()
