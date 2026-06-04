"""Tests for deterministic final audit normalization."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.final_audit_normalizer import (  # noqa: E402
    EXPECTED_FINAL_AUDIT_HEADINGS,
    NormalizedAuditExistsError,
    RepairPacketExistsError,
    _MISSING_IN_NORMALIZED,
    build_final_audit_repair_packet,
    map_heading_to_expected,
    normalize_final_audit_text,
    normalize_heading_text,
    normalize_latest_final_audit,
    parse_markdown_sections_with_levels,
    parse_top_level_markdown_sections,
)
from studyforge.audits.final_import import import_final_audit  # noqa: E402
from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.study_pack import (  # noqa: E402
    NORMALIZER_SUGGESTION,
    analyze_study_pack_sections,
    extract_markdown_section,
    extract_sections,
)

FULL_AUDIT = """# Final Audit

## Final Verdict

Accuracy is good.

## Corrections That Matter Most

- Fix supply curve label

## Missing Concepts

- Opportunity cost

## Better Explanations

- Elasticity intuition

## Must-Memorize List

- P equals MC

## Must-Understand List

- Why demand slopes down

## Formula / Method Sheet

- Qd = a - bP

## Exam / Homework Traps

- Confusing shift vs movement

## Practice Questions

1. What shifts demand?

## Active Recall Questions

- Define elasticity

## Final Study Checklist

- Review graphs

## Remaining Uncertainties

- Page 42 example unclear
"""

VARIANT_AUDIT = """# Final Audit

## Overall Verdict

Good enough for study.

## Important corrections

- Label axes on every graph

## Missing concepts

- Sunk cost fallacy

## Explanations

- Use coffee price for elasticity

## Must memorize

- Law of demand

## Must understand

- Consumer surplus

## Formula sheet

- Percent change formula

## Exam traps

- Sign errors on elasticity

## Practice problems

- Calculate elasticity from table

## Active recall

- State law of demand without notes

## Study checklist

- Redo chapter 3 problems

## Uncertainties

- Instructor may skip game theory
"""

NESTED_CORRECTIONS_AUDIT = """# Final Audit

## Final Verdict

OK.

## Corrections That Matter Most

Intro line.

### Correction 1

Problem: bad math.

Correct version: good math.

### Correction 2

Problem: wrong sign.

Correct version: right sign.

## Missing Concepts

Gap one.

## Better Explanations

### Real vs. Nominal

Nominal is the shelf price.

### IPC vs GDP Deflator

IPC includes imports.

## Must-Memorize List

Fact A.

## Must-Understand List

Idea B.

## Formula / Method Sheet

F = x.

## Exam / Homework Traps

Trap one.

## Practice Questions

Q1.

## Active Recall Questions

R1.

## Final Study Checklist

Done.

## Remaining Uncertainties

Maybe.
"""

EXTRA_SECTION_AUDIT = """# Final Audit

## Final Verdict

OK.

## Corrections That Matter Most

One fix.

## Missing Concepts

Gap.

## Better Explanations

Tip.

## Must-Memorize List

Fact.

## Must-Understand List

Idea.

## Formula / Method Sheet

F = ma style.

## Exam / Homework Traps

Trap.

## Practice Questions

Q1.

## Active Recall Questions

R1.

## Final Study Checklist

Done.

## Remaining Uncertainties

Maybe.

## Instructor Notes

Keep this unmatched block.
"""


class TestFinalAuditNormalizer(unittest.TestCase):
    def test_normalize_heading_text(self) -> None:
        self.assertEqual(
            normalize_heading_text("  Formula / Method Sheet!  "),
            "formula method sheet",
        )
        self.assertEqual(normalize_heading_text("Must-Memorize List"), "must memorize list")

    def test_map_heading_variants(self) -> None:
        self.assertEqual(map_heading_to_expected("Final verdict"), "Final Verdict")
        self.assertEqual(map_heading_to_expected("Overall verdict"), "Final Verdict")
        self.assertEqual(map_heading_to_expected("Corrections"), "Corrections That Matter Most")
        self.assertEqual(map_heading_to_expected("Memorize"), "Must-Memorize List")
        self.assertEqual(map_heading_to_expected("Practice problems"), "Practice Questions")
        self.assertEqual(map_heading_to_expected("Checklist"), "Final Study Checklist")
        self.assertIsNone(map_heading_to_expected("Random Section Title"))

    def test_parse_markdown_sections_keeps_nested_h3_in_parent(self) -> None:
        sections = parse_markdown_sections_with_levels(
            "## Final Verdict\n\nBody.\n\n### Sub\n\nMore.\n"
        )
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading"], "Final Verdict")
        self.assertEqual(sections[0]["level"], 2)
        self.assertIn("### Sub", sections[0]["content"])
        self.assertIn("More.", sections[0]["content"])

    def test_parse_corrections_with_nested_subsections(self) -> None:
        sections = parse_top_level_markdown_sections(NESTED_CORRECTIONS_AUDIT, level=2)
        by_heading = {s["heading"]: s["content"] for s in sections}
        corrections = by_heading["Corrections That Matter Most"]
        self.assertIn("### Correction 1", corrections)
        self.assertIn("Problem: bad math.", corrections)
        self.assertIn("### Correction 2", corrections)
        self.assertIn("Correct version: right sign.", corrections)
        self.assertNotIn("## Missing Concepts", corrections)

    def test_parse_better_explanations_with_nested_subsections(self) -> None:
        sections = parse_top_level_markdown_sections(NESTED_CORRECTIONS_AUDIT, level=2)
        by_heading = {s["heading"]: s["content"] for s in sections}
        explanations = by_heading["Better Explanations"]
        self.assertIn("### Real vs. Nominal", explanations)
        self.assertIn("### IPC vs GDP Deflator", explanations)
        self.assertIn("IPC includes imports.", explanations)

    def test_normalize_nested_content_not_in_additional_notes(self) -> None:
        normalized, report = normalize_final_audit_text(NESTED_CORRECTIONS_AUDIT)
        self.assertNotIn("Correction 1", report["unmatched_headings"])
        self.assertNotIn("Real vs. Nominal", report["unmatched_headings"])
        self.assertIn("### Correction 1", normalized)
        self.assertIn("### Correction 2", normalized)
        self.assertIn("### Real vs. Nominal", normalized)
        self.assertNotIn("## Additional Notes From Original Audit", normalized)
        better_start = normalized.index("## Better Explanations")
        better_end = normalized.index("## Must-Memorize List")
        explanations_block = normalized[better_start:better_end]
        self.assertNotIn(_MISSING_IN_NORMALIZED, explanations_block)

    def test_normalize_nested_improves_quality(self) -> None:
        _, report = normalize_final_audit_text(NESTED_CORRECTIONS_AUDIT)
        self.assertEqual(report["quality_status"], "ok")
        self.assertNotIn("Better Explanations", report["missing_headings"])

    def test_study_pack_extract_preserves_nested_h3(self) -> None:
        body = extract_markdown_section(NESTED_CORRECTIONS_AUDIT, "Corrections That Matter Most")
        self.assertIn("### Correction 1", body)
        self.assertIn("### Correction 2", body)
        self.assertNotIn("Missing Concepts", body)

    def test_normalize_full_expected_audit(self) -> None:
        normalized, report = normalize_final_audit_text(FULL_AUDIT)
        self.assertEqual(report["quality_status"], "ok")
        self.assertEqual(len(report["missing_headings"]), 0)
        for heading in EXPECTED_FINAL_AUDIT_HEADINGS:
            self.assertIn(f"## {heading}", normalized)

    def test_normalize_variant_headings(self) -> None:
        normalized, report = normalize_final_audit_text(VARIANT_AUDIT)
        self.assertIn("Overall Verdict", report["mapped_headings"])
        self.assertEqual(report["mapped_headings"]["Overall Verdict"], "Final Verdict")
        self.assertIn("## Final Verdict", normalized)
        self.assertIn("Good enough for study.", normalized)
        self.assertEqual(report["quality_status"], "ok")

    def test_missing_headings_placeholder(self) -> None:
        text = "## Final Verdict\n\nOnly verdict.\n"
        normalized, report = normalize_final_audit_text(text)
        self.assertIn(_MISSING_IN_NORMALIZED, normalized)
        self.assertGreater(len(report["missing_headings"]), 0)

    def test_unmatched_preserved_under_additional_notes(self) -> None:
        normalized, report = normalize_final_audit_text(EXTRA_SECTION_AUDIT)
        self.assertIn("## Additional Notes From Original Audit", normalized)
        self.assertIn("Instructor Notes", normalized)
        self.assertIn("Instructor Notes", report["unmatched_headings"])

    def test_quality_failed_fewer_than_three_mapped(self) -> None:
        _, report = normalize_final_audit_text("## Random\n\nx\n")
        self.assertEqual(report["quality_status"], "failed")
        self.assertLess(report["mapped_count"], 3)

    def test_quality_needs_review_important_missing(self) -> None:
        text = """## Final Verdict
ok
## Corrections That Matter Most
fix
## Missing Concepts
gap
"""
        _, report = normalize_final_audit_text(text)
        self.assertEqual(report["quality_status"], "needs_review")
        self.assertIn("Must-Memorize List", report["missing_headings"])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        (self.course / "05_Final_Audits" / "SRC-0001").mkdir(parents=True)
        (self.course / "08_App_Data").mkdir(parents=True)
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Test Book",
                        "status": "final_audit_imported",
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
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=VARIANT_AUDIT, root=self.root
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_normalize_writes_files(self) -> None:
        summary = normalize_latest_final_audit(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        normalized_path = Path(summary["normalized_path"])
        report_path = Path(summary["report_path"])
        self.assertTrue(normalized_path.is_file())
        self.assertTrue(report_path.is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["source_id"], "SRC-0001")
        self.assertIn("quality_status", report)

    def test_overwrite_refusal(self) -> None:
        normalize_latest_final_audit("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(NormalizedAuditExistsError):
            normalize_latest_final_audit("ECA1010_Test", "SRC-0001", root=self.root)

    @patch("studyforge.audits.final_audit_normalizer.import_final_audit")
    def test_import_as_new_version(self, mock_import) -> None:
        mock_import.return_value = {
            "audit_id": "FA-SRC-0001-V002",
            "saved_path": "/tmp/v2.md",
            "warnings": [],
        }
        summary = normalize_latest_final_audit(
            "ECA1010_Test",
            "SRC-0001",
            overwrite=True,
            import_as_new_version=True,
            root=self.root,
        )
        self.assertEqual(summary["imported_audit_id"], "FA-SRC-0001-V002")
        mock_import.assert_called_once()
        kwargs = mock_import.call_args.kwargs
        self.assertEqual(kwargs["auditor_name"], "StudyForge Normalizer")
        self.assertIn("Normalized from", kwargs["notes"])

    def test_repair_packet_contents(self) -> None:
        summary = build_final_audit_repair_packet(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        packet_path = Path(summary["repair_packet_path"])
        text = packet_path.read_text(encoding="utf-8")
        self.assertIn("# Final Audit Repair Packet", text)
        self.assertIn("## Original Final Audit", text)
        self.assertIn("```markdown", text)
        self.assertIn("Overall Verdict", text)
        self.assertIn("## Output Template", text)
        for heading in EXPECTED_FINAL_AUDIT_HEADINGS:
            self.assertIn(f"## {heading}", text)

    def test_repair_packet_overwrite_refusal(self) -> None:
        build_final_audit_repair_packet("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(RepairPacketExistsError):
            build_final_audit_repair_packet("ECA1010_Test", "SRC-0001", root=self.root)

    @patch("scripts.normalize_final_audit.normalize_latest_final_audit")
    def test_cli_normalize(self, mock_normalize) -> None:
        from scripts import normalize_final_audit as cli_module

        mock_normalize.return_value = {
            "source_final_audit_id": "FA-SRC-0001-V001",
            "quality_status": "ok",
            "mapped_count": 12,
            "missing_headings": [],
            "mapped_headings": {},
            "normalized_path": "/tmp/n.md",
            "report_path": "/tmp/r.json",
            "warnings": [],
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--source-id", "SRC-0001"]
        )
        self.assertEqual(code, 0)
        mock_normalize.assert_called_once()

    def test_study_pack_suggests_normalizer_when_weak(self) -> None:
        sections = extract_sections("## Final Verdict\n\nShort.\n")
        quality = analyze_study_pack_sections(sections)
        self.assertIn(quality["quality_status"], {"needs_review", "failed"})
        self.assertTrue(
            any(NORMALIZER_SUGGESTION in w for w in quality["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
