"""Tests for intermediate audit import."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.intermediate_import import (  # noqa: E402
    AuditInputError,
    EmptyAuditError,
    build_audit_file_name,
    get_next_audit_version,
    import_intermediate_audit,
    load_audit_registry,
)
from studyforge.core.sources import load_source_registry  # noqa: E402

AUDIT_BODY = "# Intermediate Audit\n\nChunk SRC-0001-CHUNK-0001 is mostly correct.\n"


class TestIntermediateImport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        (self.course / "03_Local_Digests" / "SRC-0001").mkdir(parents=True)
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

    def test_import_from_text(self) -> None:
        summary = import_intermediate_audit(
            "ECA1010_Test",
            "SRC-0001",
            audit_text=AUDIT_BODY,
            root=self.root,
        )
        self.assertEqual(summary["audit_id"], "IA-SRC-0001-V001")
        self.assertTrue(Path(summary["saved_path"]).is_file())
        registry = load_audit_registry(Path(summary["registry_path"]))
        self.assertEqual(len(registry["audits"]), 1)

    def test_import_from_file(self) -> None:
        audit_file = self.root / "external_audit.md"
        audit_file.write_text(AUDIT_BODY, encoding="utf-8")
        summary = import_intermediate_audit(
            "ECA1010_Test",
            "SRC-0001",
            audit_file=audit_file,
            root=self.root,
        )
        self.assertEqual(Path(summary["saved_path"]).read_text(encoding="utf-8"), AUDIT_BODY)

    def test_reject_both_file_and_text(self) -> None:
        with self.assertRaises(AuditInputError):
            import_intermediate_audit(
                "ECA1010_Test",
                "SRC-0001",
                audit_text="x",
                audit_file=Path("y.md"),
                root=self.root,
            )

    def test_reject_empty_audit(self) -> None:
        with self.assertRaises(EmptyAuditError):
            import_intermediate_audit(
                "ECA1010_Test",
                "SRC-0001",
                audit_text="   ",
                root=self.root,
            )

    def test_version_increments(self) -> None:
        import_intermediate_audit(
            "ECA1010_Test", "SRC-0001", audit_text=AUDIT_BODY, root=self.root
        )
        summary2 = import_intermediate_audit(
            "ECA1010_Test", "SRC-0001", audit_text=AUDIT_BODY + "\n\nv2", root=self.root
        )
        self.assertEqual(summary2["audit_id"], "IA-SRC-0001-V002")
        self.assertEqual(
            summary2["saved_path"],
            str(
                (
                    self.course
                    / "04_Intermediate_Audits"
                    / "SRC-0001"
                    / build_audit_file_name("SRC-0001", 2)
                ).resolve()
            ),
        )

    def test_source_registry_updated(self) -> None:
        import_intermediate_audit(
            "ECA1010_Test", "SRC-0001", audit_text=AUDIT_BODY, root=self.root
        )
        reg = load_source_registry(self.course)
        entry = reg["sources"][0]
        self.assertEqual(entry["status"], "intermediate_audit_imported")
        self.assertEqual(entry["latest_intermediate_audit_id"], "IA-SRC-0001-V001")

    def test_existing_audit_not_overwritten(self) -> None:
        summary1 = import_intermediate_audit(
            "ECA1010_Test", "SRC-0001", audit_text="version one", root=self.root
        )
        import_intermediate_audit(
            "ECA1010_Test", "SRC-0001", audit_text="version two", root=self.root
        )
        self.assertEqual(
            Path(summary1["saved_path"]).read_text(encoding="utf-8"),
            "version one",
        )

    def test_registry_from_disk_when_missing(self) -> None:
        audit_dir = self.course / "04_Intermediate_Audits" / "SRC-0001"
        audit_dir.mkdir(parents=True)
        (audit_dir / build_audit_file_name("SRC-0001", 1)).write_text(
            "old audit", encoding="utf-8"
        )
        summary = import_intermediate_audit(
            "ECA1010_Test", "SRC-0001", audit_text=AUDIT_BODY, root=self.root
        )
        self.assertEqual(summary["version"], 2)
        self.assertTrue(summary["warnings"])


if __name__ == "__main__":
    unittest.main()
