"""Tests for deterministic study pack generation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.final_import import import_final_audit  # noqa: E402
from studyforge.core.pipeline_status import get_pipeline_status  # noqa: E402
from studyforge.core.sources import load_source_registry, save_source_registry  # noqa: E402
from studyforge.study.study_pack import (  # noqa: E402
    FinalAuditNotFoundError,
    StudyPackOutputExistsError,
    extract_markdown_section,
    extract_sections,
    generate_study_pack,
    get_latest_final_audit,
)

FULL_AUDIT = """# Final Audit

## Final Verdict

Accuracy is good.

## Corrections That Matter Most

- Fix supply/demand confusion

## Missing Concepts

- Opportunity cost edge cases

## Better Explanations

- Elasticity intuition

## Must-Memorize List

- P = MC in perfect competition

## Must-Understand List

- Why deadweight loss happens

## Formula / Method Sheet

- Elasticity = (% change Q) / (% change P)

## Exam / Homework Traps

- Mixing up shifts vs movements along a curve

## Practice Questions

1. Define price elasticity.

## Active Recall Questions

- What is consumer surplus?

## Final Study Checklist

- Review chapter 2

## Remaining Uncertainties

- Monopsony edge cases
"""


class TestStudyPack(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        (self.course / "04_Intermediate_Audits" / "SRC-0001").mkdir(parents=True)
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
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Main Textbook",
                        "status": "intermediate_audit_imported",
                    }
                ]
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _import_final(self, text: str = FULL_AUDIT) -> dict:
        return import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=text, root=self.root
        )

    def _pipeline_ready_entry(self, final_summary: dict) -> None:
        """Registry + on-disk flags so Pipeline Doctor reaches study-pack steps."""
        source_dir = self.course / "01_Source_Material" / "textbook"
        source_dir.mkdir(parents=True, exist_ok=True)
        pdf = source_dir / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4 minimal")
        extracted = self.course / "02_Extracted_Text" / "extracted_sources"
        extracted.mkdir(parents=True, exist_ok=True)
        ext_file = extracted / "SRC-0001_extracted_text.md"
        ext_file.write_text("# Extracted\n", encoding="utf-8")
        chunk_dir = self.course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        manifest = chunk_dir / "chunk_manifest.json"
        manifest.write_text(
            json.dumps({"chunks": [{"chunk_id": "SRC-0001-CHUNK-0001"}]}),
            encoding="utf-8",
        )
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True, exist_ok=True)
        combined = digest_dir / "SRC-0001_combined_local_digest.md"
        combined.write_text("# Combined", encoding="utf-8")
        (digest_dir / "SRC-0001_local_digest_review.json").write_text("{}", encoding="utf-8")
        ia_dir = self.course / "04_Intermediate_Audits" / "SRC-0001"
        ia_dir.mkdir(parents=True, exist_ok=True)
        ia_file = ia_dir / "SRC-0001_intermediate_audit_v001.md"
        ia_file.write_text("# IA", encoding="utf-8")
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Main Textbook",
                        "status": "final_audit_imported",
                        "stored_path": str(pdf.resolve()),
                        "extracted_text_path": str(ext_file.resolve()),
                        "chunk_manifest_path": str(manifest.resolve()),
                        "local_digest_path": str(combined.resolve()),
                        "latest_intermediate_audit_path": str(ia_file.resolve()),
                        "latest_final_audit_path": final_summary["saved_path"],
                        "latest_final_audit_id": final_summary["audit_id"],
                    }
                ]
            },
        )

    def test_extract_markdown_section(self) -> None:
        body = extract_markdown_section(FULL_AUDIT, "Must-Memorize List")
        self.assertIn("P = MC", body)
        self.assertNotIn("Must-Understand", body)

    def test_missing_section_fallback(self) -> None:
        minimal = "# Audit\n\n## Final Verdict\n\nOK\n"
        sections = extract_sections(minimal)
        self.assertEqual(sections["final_verdict"], "OK")
        self.assertEqual(sections["must_memorize"], "Not found in final audit.")

    def test_latest_final_audit_highest_version(self) -> None:
        self._import_final("## Final Verdict\n\nversion one\n")
        import_final_audit(
            "ECA1010_Test",
            "SRC-0001",
            audit_text="## Final Verdict\n\nversion two\n",
            root=self.root,
        )
        latest = get_latest_final_audit(self.course, "SRC-0001")
        self.assertEqual(latest["entry"]["audit_id"], "FA-SRC-0001-V002")
        self.assertIn("version two", latest["text"])

    def test_generate_refuses_without_final_audit(self) -> None:
        with self.assertRaises(FinalAuditNotFoundError):
            generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)

    def test_generate_writes_all_files(self) -> None:
        self._import_final()
        summary = generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        outputs = summary["outputs"]
        for path_str in outputs.values():
            self.assertTrue(Path(path_str).is_file(), path_str)
        self.assertIn("flashcards_csv", outputs)
        self.assertIn("flashcards_anki_tsv", outputs)
        self.assertGreater(summary.get("flashcard_count", 0), 0)
        manifest = Path(summary["manifest_path"])
        self.assertTrue(manifest.is_file())
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["source_id"], "SRC-0001")
        self.assertEqual(data["based_on_final_audit_id"], "FA-SRC-0001-V001")

    def test_overwrite_refusal(self) -> None:
        self._import_final()
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(StudyPackOutputExistsError):
            generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)

    def test_overwrite_allowed(self) -> None:
        self._import_final()
        first = generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        second = generate_study_pack(
            "ECA1010_Test", "SRC-0001", overwrite=True, root=self.root
        )
        self.assertEqual(first["manifest_path"], second["manifest_path"])

    def test_source_registry_updated(self) -> None:
        self._import_final()
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        registry = load_source_registry(self.course)
        entry = registry["sources"][0]
        self.assertEqual(entry["status"], "study_pack_generated")
        self.assertTrue(entry.get("study_pack_manifest_path"))
        self.assertTrue(entry.get("final_study_guide_path"))
        self.assertTrue(entry.get("date_study_pack_generated"))

    def test_pipeline_generate_study_pack_next(self) -> None:
        summary = self._import_final()
        self._pipeline_ready_entry(summary)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "generate_study_pack")
        self.assertFalse(status["steps"]["study_pack_generated"]["done"])

    def test_pipeline_study_pack_ready(self) -> None:
        summary = self._import_final()
        self._pipeline_ready_entry(summary)
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "study_pack_ready")
        self.assertTrue(status["steps"]["study_pack_generated"]["done"])


if __name__ == "__main__":
    unittest.main()
