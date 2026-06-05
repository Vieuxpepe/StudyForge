"""Tests for Course Backup / Export v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.backup import (  # noqa: E402
    BACKUP_INFO_FILENAME,
    build_backup_name,
    create_course_backup,
    get_course_backup_dir,
    list_course_backups,
    should_exclude_from_backup,
)
from studyforge.core.sources import save_source_registry  # noqa: E402


def _setup_course(root: Path, course_name: str = "ECA1010_Test") -> Path:
    courses = root / "courses"
    course = courses / course_name
    (course / "00_Master").mkdir(parents=True)
    (course / "01_Source_Material" / "textbook").mkdir(parents=True)
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    (course / "00_Master" / "notes.txt").write_text("master notes", encoding="utf-8")
    (course / "01_Source_Material" / "textbook" / "book.pdf").write_bytes(b"%PDF-fake")
    (course / "07_My_Work" / "log.json").write_text("{}", encoding="utf-8")
    save_source_registry(
        course,
        {"sources": [{"id": "SRC-0001", "title": "Book", "status": "added"}]},
    )
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


class TestBackupHelpers(unittest.TestCase):
    def test_build_backup_name_safe_filename(self) -> None:
        name = build_backup_name("ECA1010 Micro/economics!", "2026-06-04_153000")
        self.assertEqual(name, "ECA1010_Micro_economics_backup_2026-06-04_153000.zip")
        self.assertNotIn("/", name)
        self.assertNotIn("\\", name)

    def test_should_exclude_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "ECA1010_Test"
            course.mkdir()
            cache_dir = course / "__pycache__"
            cache_dir.mkdir()
            cache_file = cache_dir / "mod.pyc"
            cache_file.write_bytes(b"x")
            self.assertTrue(
                should_exclude_from_backup(cache_file, include_sources=True)
            )

            tmp_file = course / "07_My_Work"
            tmp_file.mkdir()
            draft = tmp_file / "draft.tmp"
            draft.write_text("x", encoding="utf-8")
            self.assertTrue(should_exclude_from_backup(draft))

            source_dir = course / "01_Source_Material" / "textbook"
            source_dir.mkdir(parents=True)
            source_file = source_dir / "book.pdf"
            source_file.write_bytes(b"pdf")
            self.assertFalse(should_exclude_from_backup(source_file))
            self.assertTrue(
                should_exclude_from_backup(source_file, include_sources=False)
            )


class TestCreateCourseBackup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_backup_includes_expected_files(self) -> None:
        with patch(
            "studyforge.core.backup.build_backup_name",
            return_value="ECA1010_Test_backup_2026-06-04_153000.zip",
        ):
            summary = create_course_backup("ECA1010_Test", root=self.root)

        backup_path = Path(summary["backup_path"])
        self.assertTrue(backup_path.is_file())
        names = set(zipfile.ZipFile(backup_path).namelist())
        self.assertIn("ECA1010_Test/00_Master/notes.txt", names)
        self.assertIn("ECA1010_Test/07_My_Work/log.json", names)
        self.assertIn("ECA1010_Test/08_App_Data/source_registry.json", names)
        self.assertIn(f"ECA1010_Test/{BACKUP_INFO_FILENAME}", names)

    def test_backup_excludes_existing_backup_zip(self) -> None:
        backup_dir = get_course_backup_dir(self.course)
        backup_dir.mkdir(parents=True, exist_ok=True)
        old_zip = backup_dir / "ECA1010_Test_backup_2020-01-01_120000.zip"
        old_zip.write_bytes(b"old")

        with patch(
            "studyforge.core.backup.build_backup_name",
            return_value="ECA1010_Test_backup_2026-06-04_153000.zip",
        ):
            summary = create_course_backup("ECA1010_Test", root=self.root)

        names = set(zipfile.ZipFile(summary["backup_path"]).namelist())
        self.assertFalse(any(name.endswith("2020-01-01_120000.zip") for name in names))

    def test_no_sources_excludes_source_material(self) -> None:
        with patch(
            "studyforge.core.backup.build_backup_name",
            return_value="ECA1010_Test_backup_2026-06-04_153000.zip",
        ):
            summary = create_course_backup(
                "ECA1010_Test",
                include_sources=False,
                root=self.root,
            )

        names = set(zipfile.ZipFile(summary["backup_path"]).namelist())
        self.assertFalse(any("01_Source_Material" in name for name in names))
        self.assertTrue(summary["include_sources"] is False)
        self.assertTrue(summary["warnings"])

    def test_backup_info_file_content(self) -> None:
        with patch(
            "studyforge.core.backup.build_backup_name",
            return_value="ECA1010_Test_backup_2026-06-04_153000.zip",
        ):
            summary = create_course_backup("ECA1010_Test", root=self.root)

        with zipfile.ZipFile(summary["backup_path"]) as archive:
            info = archive.read(f"ECA1010_Test/{BACKUP_INFO_FILENAME}").decode("utf-8")

        self.assertIn("ECA1010_Test", info)
        self.assertIn("Include source materials: true", info)
        self.assertIn("Restore (manual", info)
        self.assertIn("courses/", info)

    def test_summary_counts(self) -> None:
        with patch(
            "studyforge.core.backup.build_backup_name",
            return_value="ECA1010_Test_backup_2026-06-04_153000.zip",
        ):
            summary = create_course_backup("ECA1010_Test", root=self.root)

        self.assertGreater(summary["file_count"], 0)
        self.assertGreater(summary["total_bytes"], 0)
        self.assertIn("date_created", summary)


class TestListCourseBackups(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.backup_dir = get_course_backup_dir(self.course)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_backups_newest_first(self) -> None:
        older = self.backup_dir / "ECA1010_Test_backup_2020-01-01_120000.zip"
        newer = self.backup_dir / "ECA1010_Test_backup_2026-06-04_153000.zip"
        older.write_bytes(b"old")
        newer.write_bytes(b"newer-content")

        import os

        os.utime(older, (1_600_000_000, 1_600_000_000))
        os.utime(newer, (1_700_000_000, 1_700_000_000))

        backups = list_course_backups("ECA1010_Test", root=self.root)
        self.assertEqual(len(backups), 2)
        self.assertEqual(backups[0]["file_name"], newer.name)
        self.assertGreater(backups[0]["size_bytes"], backups[1]["size_bytes"])


class TestBackupCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @patch("scripts.backup_course.create_course_backup")
    def test_cli_create_output(self, mock_create) -> None:
        from scripts import backup_course as cli_module

        mock_create.return_value = {
            "course": "ECA1010_Test",
            "backup_path": str(self.course / "backup.zip"),
            "file_count": 12,
            "total_bytes": 12_400_000,
            "include_sources": True,
            "date_created": "2026-06-04T15:30:00",
            "warnings": [],
        }
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = cli_module.main(["--course", "ECA1010_Test"])
        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn("Backup created.", output)
        self.assertIn("Files:", output)
        self.assertIn("MB", output)

    @patch("scripts.backup_course.list_course_backups")
    def test_cli_list(self, mock_list) -> None:
        from scripts import backup_course as cli_module

        mock_list.return_value = [
            {
                "path": "/tmp/a.zip",
                "file_name": "a.zip",
                "size_bytes": 100,
                "modified": "2026-06-04T15:30:00",
            }
        ]
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = cli_module.main(["--course", "ECA1010_Test", "--list"])
        self.assertEqual(code, 0)
        self.assertIn("Backups (1)", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
