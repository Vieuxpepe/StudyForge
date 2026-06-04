"""Tests for course folder naming and creation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# src on path for unittest discovery from project root
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.courses import (  # noqa: E402
    CourseAlreadyExistsError,
    CourseValidationError,
    build_course_folder_name,
    create_course,
    list_courses,
    sanitize_folder_name,
    validate_course_code,
)
class TestSanitizeFolderName(unittest.TestCase):
    def test_spaces_become_underscores(self) -> None:
        self.assertEqual(sanitize_folder_name("Droit des affaires"), "Droit_des_affaires")

    def test_removes_invalid_windows_chars(self) -> None:
        self.assertEqual(sanitize_folder_name('bad<>:"|?*name'), "badname")

    def test_collapses_underscores(self) -> None:
        self.assertEqual(sanitize_folder_name("a   b"), "a_b")

    def test_keeps_accents(self) -> None:
        self.assertEqual(sanitize_folder_name("Calcul différentiel"), "Calcul_différentiel")


class TestBuildCourseFolderName(unittest.TestCase):
    def test_example_names(self) -> None:
        self.assertEqual(
            build_course_folder_name("eca1010", "Microeconomics"),
            "ECA1010_Microeconomics",
        )
        self.assertEqual(
            build_course_folder_name("DRA1001", "Droit des affaires"),
            "DRA1001_Droit_des_affaires",
        )


class TestValidation(unittest.TestCase):
    def test_rejects_empty_code(self) -> None:
        with self.assertRaises(CourseValidationError):
            validate_course_code("  ")

    def test_rejects_invalid_code_chars(self) -> None:
        with self.assertRaises(CourseValidationError):
            validate_course_code("ECA 1010")


class TestCreateCourse(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

        (self.root / "config").mkdir()
        courses = self.root / "courses"
        courses.mkdir()
        template = courses / "_Course_Template" / "00_Master"
        template.mkdir(parents=True)
        (template / "course_profile.md").write_text("template", encoding="utf-8")
        (template / "pipeline_settings.json").write_text("{}", encoding="utf-8")

        config = {
            "project_root": str(self.root),
            "courses_dir": str(courses),
            "default_course_template": "_Course_Template",
        }
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_course_writes_master_files(self) -> None:
        path = create_course("MAT1001", "Calcul différentiel", root=self.root)
        self.assertTrue(path.is_dir())
        profile = (path / "00_Master" / "course_profile.md").read_text(encoding="utf-8")
        self.assertIn("MAT1001", profile)
        self.assertIn("Calcul différentiel", profile)

        settings = json.loads(
            (path / "00_Master" / "pipeline_settings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(settings["course_code"], "MAT1001")
        self.assertEqual(settings["course_folder"], "MAT1001_Calcul_différentiel")

    def test_does_not_overwrite_existing(self) -> None:
        create_course("ECA1010", "Micro", root=self.root)
        with self.assertRaises(CourseAlreadyExistsError):
            create_course("ECA1010", "Micro", root=self.root)

    def test_list_excludes_template(self) -> None:
        create_course("ECA1010", "Micro", root=self.root)
        names = [p.name for p in list_courses(self.root)]
        self.assertEqual(names, ["ECA1010_Micro"])
        self.assertNotIn("_Course_Template", names)


if __name__ == "__main__":
    unittest.main()
