"""Tests for pipeline status / Pipeline Doctor."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.extraction_jobs import SourceNotFoundError  # noqa: E402
from studyforge.core.pipeline_status import get_pipeline_status  # noqa: E402
from studyforge.core.sources import save_source_registry  # noqa: E402


class TestPipelineStatus(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        self.course.mkdir(parents=True)
        (self.course / "08_App_Data").mkdir(parents=True)
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
        self.source_dir = self.course / "01_Source_Material" / "textbook"
        self.source_dir.mkdir(parents=True)
        self.pdf = self.source_dir / "book.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 minimal")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _save_entry(self, entry: dict) -> None:
        save_source_registry(self.course, {"sources": [entry]})

    def _write_extraction_artifacts(self) -> Path:
        extracted = self.course / "02_Extracted_Text" / "extracted_sources"
        extracted.mkdir(parents=True)
        ext_file = extracted / "SRC-0001_extracted_text.md"
        ext_file.write_text("# Extracted\n\nPage 1\n\nBody", encoding="utf-8")
        return ext_file

    def _write_chunk_manifest(self) -> Path:
        chunk_dir = self.course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True)
        manifest = chunk_dir / "chunk_manifest.json"
        manifest.write_text(
            json.dumps({"chunks": [{"chunk_id": "SRC-0001-CHUNK-0001"}]}),
            encoding="utf-8",
        )
        return manifest

    def _base_entry(self) -> dict:
        return {
            "id": "SRC-0001",
            "title": "Main Textbook",
            "source_type": "textbook",
            "stored_path": str(self.pdf.resolve()),
            "status": "added",
        }

    def test_source_missing(self) -> None:
        entry = self._base_entry()
        entry["stored_path"] = str(self.course / "missing.pdf")
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "source_missing")
        self.assertFalse(status["steps"]["source_registered"]["done"])
        self.assertTrue(any("missing" in w.lower() for w in status["warnings"]))

    def test_extract_pdf_next(self) -> None:
        self._save_entry(self._base_entry())
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "extract_pdf")
        self.assertTrue(status["steps"]["source_registered"]["done"])
        self.assertFalse(status["steps"]["extracted"]["done"])

    def test_chunk_source_next(self) -> None:
        extracted = self.course / "02_Extracted_Text" / "extracted_sources"
        extracted.mkdir(parents=True)
        ext_file = extracted / "SRC-0001_extracted_text.md"
        ext_file.write_text("# Extracted\n\nPage 1\n\nBody", encoding="utf-8")
        entry = self._base_entry()
        entry["status"] = "extracted"
        entry["extracted_text_path"] = str(ext_file.resolve())
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "chunk_source")

    def test_run_local_digest_next(self) -> None:
        ext_file = self._write_extraction_artifacts()
        manifest = self._write_chunk_manifest()
        entry = self._base_entry()
        entry["status"] = "chunked"
        entry["extracted_text_path"] = str(ext_file.resolve())
        entry["chunk_manifest_path"] = str(manifest.resolve())
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "run_local_digest")
        self.assertTrue(status["steps"]["chunked"]["done"])

    def test_review_local_digest_next(self) -> None:
        ext_file = self._write_extraction_artifacts()
        manifest = self._write_chunk_manifest()
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        combined = digest_dir / "SRC-0001_combined_local_digest.md"
        combined.write_text("# Combined", encoding="utf-8")
        entry = self._base_entry()
        entry["status"] = "local_digest_complete"
        entry["extracted_text_path"] = str(ext_file.resolve())
        entry["chunk_manifest_path"] = str(manifest.resolve())
        entry["local_digest_path"] = str(combined.resolve())
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "review_local_digest")
        self.assertTrue(status["steps"]["local_digest"]["done"])

    def test_intermediate_audit_next(self) -> None:
        ext_file = self._write_extraction_artifacts()
        manifest = self._write_chunk_manifest()
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        combined = digest_dir / "SRC-0001_combined_local_digest.md"
        combined.write_text("# Combined", encoding="utf-8")
        review = digest_dir / "SRC-0001_local_digest_review.json"
        review.write_text("{}", encoding="utf-8")
        entry = self._base_entry()
        entry["status"] = "local_digest_complete"
        entry["extracted_text_path"] = str(ext_file.resolve())
        entry["chunk_manifest_path"] = str(manifest.resolve())
        entry["local_digest_path"] = str(combined.resolve())
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "export_or_run_intermediate_audit")

    def test_final_audit_next(self) -> None:
        ext_file = self._write_extraction_artifacts()
        manifest = self._write_chunk_manifest()
        ia_dir = self.course / "04_Intermediate_Audits" / "SRC-0001"
        ia_dir.mkdir(parents=True)
        ia_file = ia_dir / "SRC-0001_intermediate_audit_v001.md"
        ia_file.write_text("# IA", encoding="utf-8")
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text("# c", encoding="utf-8")
        (digest_dir / "SRC-0001_local_digest_review.json").write_text("{}", encoding="utf-8")
        entry = self._base_entry()
        entry["status"] = "intermediate_audit_imported"
        entry["extracted_text_path"] = str(ext_file.resolve())
        entry["chunk_manifest_path"] = str(manifest.resolve())
        entry["latest_intermediate_audit_path"] = str(ia_file.resolve())
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "export_final_audit_packet")

    def test_generate_study_pack_next(self) -> None:
        ext_file = self._write_extraction_artifacts()
        manifest = self._write_chunk_manifest()
        ia_dir = self.course / "04_Intermediate_Audits" / "SRC-0001"
        fa_dir = self.course / "05_Final_Audits" / "SRC-0001"
        ia_dir.mkdir(parents=True)
        fa_dir.mkdir(parents=True)
        ia_file = ia_dir / "SRC-0001_intermediate_audit_v001.md"
        fa_file = fa_dir / "SRC-0001_final_audit_v001.md"
        ia_file.write_text("# IA", encoding="utf-8")
        fa_file.write_text("# FA", encoding="utf-8")
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text("# c", encoding="utf-8")
        (digest_dir / "SRC-0001_local_digest_review.json").write_text("{}", encoding="utf-8")
        entry = self._base_entry()
        entry["status"] = "final_audit_imported"
        entry["extracted_text_path"] = str(ext_file.resolve())
        entry["chunk_manifest_path"] = str(manifest.resolve())
        entry["latest_intermediate_audit_path"] = str(ia_file.resolve())
        entry["latest_final_audit_path"] = str(fa_file.resolve())
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "generate_study_pack")
        self.assertIn("Study pack generated", status["missing_steps"])

    def test_study_pack_ready(self) -> None:
        ext_file = self._write_extraction_artifacts()
        manifest = self._write_chunk_manifest()
        ia_dir = self.course / "04_Intermediate_Audits" / "SRC-0001"
        fa_dir = self.course / "05_Final_Audits" / "SRC-0001"
        ia_dir.mkdir(parents=True)
        fa_dir.mkdir(parents=True)
        ia_file = ia_dir / "SRC-0001_intermediate_audit_v001.md"
        fa_file = fa_dir / "SRC-0001_final_audit_v001.md"
        ia_file.write_text("# IA", encoding="utf-8")
        fa_file.write_text("# FA", encoding="utf-8")
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text("# c", encoding="utf-8")
        (digest_dir / "SRC-0001_local_digest_review.json").write_text("{}", encoding="utf-8")
        pack_manifest = self.course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
        pack_manifest.parent.mkdir(parents=True)
        pack_manifest.write_text("{}", encoding="utf-8")
        entry = self._base_entry()
        entry["status"] = "study_pack_generated"
        entry["extracted_text_path"] = str(ext_file.resolve())
        entry["chunk_manifest_path"] = str(manifest.resolve())
        entry["latest_intermediate_audit_path"] = str(ia_file.resolve())
        entry["latest_final_audit_path"] = str(fa_file.resolve())
        entry["study_pack_manifest_path"] = str(pack_manifest.resolve())
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "study_pack_ready")
        self.assertTrue(status["steps"]["study_pack_generated"]["done"])

    def test_missing_files_warn(self) -> None:
        entry = self._base_entry()
        entry["status"] = "chunked"
        entry["extracted_text_path"] = str(self.course / "nope.md")
        entry["chunk_manifest_path"] = str(self.course / "nope_manifest.json")
        self._save_entry(entry)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertGreaterEqual(len(status["warnings"]), 2)
        self.assertEqual(status["next_action"]["key"], "extract_pdf")

    def test_unknown_source(self) -> None:
        self._save_entry(self._base_entry())
        with self.assertRaises(SourceNotFoundError):
            get_pipeline_status("ECA1010_Test", "SRC-9999", root=self.root)


if __name__ == "__main__":
    unittest.main()
