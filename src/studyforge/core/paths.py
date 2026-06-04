"""
Project paths and configuration loading.

Locates the StudyForge root by looking for config/studyforge_config.json,
then exposes common directories used by scripts and library code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Relative to project root
CONFIG_RELATIVE = Path("config") / "studyforge_config.json"


def find_project_root(start: Path | None = None) -> Path:
    """
    Walk upward from ``start`` (or this file) until studyforge_config.json exists.

    Raises:
        FileNotFoundError: No project root found in the parent chain.
    """
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / CONFIG_RELATIVE).is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not find StudyForge project root (missing {CONFIG_RELATIVE})."
    )


def load_config(root: Path | None = None) -> dict[str, Any]:
    """
    Load config/studyforge_config.json as a dictionary.

    Raises:
        FileNotFoundError: Config file missing.
        json.JSONDecodeError: Config file is not valid JSON.
    """
    project_root = root or find_project_root()
    config_path = project_root / CONFIG_RELATIVE
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_courses_dir(root: Path | None = None, config: dict[str, Any] | None = None) -> Path:
    """Return the courses directory (from config or project_root/courses)."""
    project_root = root or find_project_root()
    cfg = config or load_config(project_root)

    if "courses_dir" in cfg and cfg["courses_dir"]:
        return Path(cfg["courses_dir"])

    return project_root / "courses"


def get_course_template_dir(
    root: Path | None = None, config: dict[str, Any] | None = None
) -> Path:
    """Return the path to the default course template folder."""
    project_root = root or find_project_root()
    cfg = config or load_config(project_root)
    template_name = cfg.get("default_course_template", "_Course_Template")
    return get_courses_dir(project_root, cfg) / template_name
