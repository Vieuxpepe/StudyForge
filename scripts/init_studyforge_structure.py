#!/usr/bin/env python3
"""
Idempotent StudyForge project scaffold.

Creates folders and placeholder files without deleting or overwriting
existing user content. Safe to run multiple times.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root is one level above scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ensure_dir(path: Path) -> str:
    """Create a directory if missing. Returns 'created' or 'exists'."""
    if path.exists():
        return "exists"
    path.mkdir(parents=True, exist_ok=True)
    return "created"


def ensure_file(path: Path, content: str) -> str:
    """
    Write a file only when it does not exist.
    Returns 'created', 'exists', or 'skipped' (parent could not be ensured).
    """
    if path.exists():
        return "exists"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "created"


def ensure_gitkeep(directory: Path) -> str:
    """Place a .gitkeep in an otherwise empty directory."""
    return ensure_file(directory / ".gitkeep", "")


# ---------------------------------------------------------------------------
# Directory layout (relative to PROJECT_ROOT)
# ---------------------------------------------------------------------------

DIRECTORIES: list[Path] = [
    Path("config"),
    Path("docs"),
    Path("prompts"),
    Path("scripts"),
    Path("src") / "studyforge" / "core",
    Path("src") / "studyforge" / "extraction",
    Path("src") / "studyforge" / "chunking",
    Path("src") / "studyforge" / "llm",
    Path("src") / "studyforge" / "audits",
    Path("src") / "studyforge" / "study",
    Path("src") / "studyforge" / "storage",
    Path("src") / "studyforge" / "ui",
    Path("tests"),
    Path("courses") / "_Course_Template" / "00_Master",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "textbook",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "slides",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "homework",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "notes",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "extra_readings",
    Path("courses") / "_Course_Template" / "02_Extracted_Text" / "source_packets",
    Path("courses") / "_Course_Template" / "02_Extracted_Text" / "chunks",
    Path("courses") / "_Course_Template" / "02_Extracted_Text" / "extraction_logs",
    Path("courses") / "_Course_Template" / "03_Local_Digests",
    Path("courses") / "_Course_Template" / "04_Intermediate_Audits",
    Path("courses") / "_Course_Template" / "05_Final_Audits",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "study_guides",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "flashcards",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "formula_sheets",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "glossaries",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "quizzes",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "mock_tests",
    Path("courses") / "_Course_Template" / "07_My_Work" / "solved_practice",
    Path("courses") / "_Course_Template" / "08_App_Data" / "database",
    Path("courses") / "_Course_Template" / "08_App_Data" / "vector_store",
    Path("courses") / "_Course_Template" / "08_App_Data" / "job_logs",
    Path("courses") / "_Course_Template" / "08_App_Data" / "exports",
]

# Directories that should contain .gitkeep when empty
GITKEEP_DIRS: list[Path] = [
    Path("src") / "studyforge" / "core",
    Path("src") / "studyforge" / "extraction",
    Path("src") / "studyforge" / "chunking",
    Path("src") / "studyforge" / "llm",
    Path("src") / "studyforge" / "audits",
    Path("src") / "studyforge" / "study",
    Path("src") / "studyforge" / "storage",
    Path("src") / "studyforge" / "ui",
    Path("tests"),
    Path("courses") / "_Course_Template" / "01_Source_Material" / "textbook",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "slides",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "homework",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "notes",
    Path("courses") / "_Course_Template" / "01_Source_Material" / "extra_readings",
    Path("courses") / "_Course_Template" / "02_Extracted_Text" / "source_packets",
    Path("courses") / "_Course_Template" / "02_Extracted_Text" / "chunks",
    Path("courses") / "_Course_Template" / "02_Extracted_Text" / "extraction_logs",
    Path("courses") / "_Course_Template" / "03_Local_Digests",
    Path("courses") / "_Course_Template" / "04_Intermediate_Audits",
    Path("courses") / "_Course_Template" / "05_Final_Audits",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "study_guides",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "flashcards",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "formula_sheets",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "glossaries",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "quizzes",
    Path("courses") / "_Course_Template" / "06_Study_Outputs" / "mock_tests",
    Path("courses") / "_Course_Template" / "07_My_Work" / "solved_practice",
    Path("courses") / "_Course_Template" / "08_App_Data" / "database",
    Path("courses") / "_Course_Template" / "08_App_Data" / "vector_store",
    Path("courses") / "_Course_Template" / "08_App_Data" / "job_logs",
    Path("courses") / "_Course_Template" / "08_App_Data" / "exports",
]


def file_contents() -> dict[Path, str]:
    """Return relative path -> default file content for scaffold files."""
    root = PROJECT_ROOT.as_posix()
    courses = (PROJECT_ROOT / "courses").as_posix()

    return {
        Path("README.md"): f"""# StudyForge

StudyForge is a local-first AI study pipeline for digesting source material,
creating study notes, auditing AI-generated outputs, generating study packs,
and tracking mistakes and weak points.

## Quick start

Run the scaffold script (safe to re-run):

```bash
python scripts/init_studyforge_structure.py
```

## Layout

- `config/` — application settings
- `courses/` — per-course data and pipeline outputs
- `docs/` — specifications and planning documents
- `prompts/` — LLM prompt templates
- `scripts/` — setup and utility scripts
- `src/studyforge/` — Python application code (future)
- `tests/` — automated tests (future)

See each folder's README for details.
""",
        Path(".gitignore"): """# Byte-compiled / cache
__pycache__/
*.py[cod]
*$py.class
*.pyo

# Virtual environments
.venv/
venv/
env/
ENV/

# Secrets and local env
.env
.env.*

# Databases (SQLite later)
*.sqlite
*.sqlite3
*.db

# OS
.DS_Store
Thumbs.db
desktop.ini

# Logs and temp
*.log
logs/
tmp/
temp/
*.tmp
*.swp
*~

# Test / tooling caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# IDE
.idea/
.vscode/
*.code-workspace

# Local generated outputs (uncomment per real course as needed)
# courses/MyCourse/02_Extracted_Text/
# courses/MyCourse/03_Local_Digests/
# courses/MyCourse/08_App_Data/
""",
        Path("requirements.txt"): """# StudyForge — Python dependencies (add as features are implemented)
# Example future entries:
# streamlit
# pypdf
# httpx
""",
        Path("config") / "studyforge_config.json": f"""{{
  "app_name": "StudyForge",
  "version": "0.1.0",
  "project_root": "{root}",
  "courses_dir": "{courses}",
  "default_course_template": "_Course_Template",
  "local_first": true,
  "use_sqlite_later": true,
  "use_vector_store_later": true
}}
""",
        Path("docs") / "README.md": """# docs

Planning and specification documents for StudyForge.

- `StudyForge_Master_Sheet.md` — high-level product and pipeline overview
- `MVP_Build_Spec.md` — MVP scope and build order
""",
        Path("docs") / "StudyForge_Master_Sheet.md": """# StudyForge Master Sheet

Placeholder for the master product sheet. Copy or link content from your
canonical planning document here.
""",
        Path("docs") / "MVP_Build_Spec.md": """# MVP Build Spec

Placeholder for MVP scope, milestones, and acceptance criteria.
""",
        Path("prompts") / "README.md": """# prompts

Reusable LLM prompt templates for each pipeline stage. Edit these files
rather than hard-coding prompts in application code.
""",
        Path("prompts") / "local_digest_prompt.md": """# Local Digest Prompt

Placeholder for the local-model digest prompt (source chunks → study digest).
""",
        Path("prompts") / "intermediate_audit_prompt.md": """# Intermediate Audit Prompt

Placeholder for auditing intermediate digests before final packaging.
""",
        Path("prompts") / "final_audit_prompt.md": """# Final Audit Prompt

Placeholder for the final quality audit on study outputs.
""",
        Path("prompts") / "active_recall_prompt.md": """# Active Recall Prompt

Placeholder for generating active-recall questions and drills.
""",
        Path("prompts") / "homework_helper_prompt.md": """# Homework Helper Prompt

Placeholder for guided homework assistance (hints, not full solutions).
""",
        Path("scripts") / "README.md": """# scripts

Utility and setup scripts.

- `init_studyforge_structure.py` — idempotent project scaffold (folders + placeholders)
""",
        Path("src") / "studyforge" / "__init__.py": '''"""StudyForge application package."""

__version__ = "0.1.0"
''',
        Path("src") / "studyforge" / "README.md": """# studyforge (package)

Python source for the StudyForge pipeline and UI.

| Module      | Purpose (planned)                          |
|-------------|--------------------------------------------|
| `core`      | Shared types, config loading, utilities    |
| `extraction`| PDF/text extraction from source material   |
| `chunking`  | Splitting sources into model-sized chunks  |
| `llm`       | Local and cloud LLM clients                |
| `audits`    | Intermediate and final audit runners       |
| `study`     | Study pack generation (guides, cards, etc.) |
| `storage`   | SQLite and file-backed persistence (later) |
| `ui`        | Streamlit or other local UI (later)        |
""",
        Path("courses") / "README.md": """# courses

One folder per course. Copy `_Course_Template` to start a new course
(e.g. `MATH101_Spring2026`) and fill in `00_Master` before adding sources.

Pipeline folders `01`–`08` mirror the study pipeline stages.
""",
        Path("courses") / "_Course_Template" / "00_Master" / "course_profile.md": """# Course Profile

- **Course code:**
- **Title:**
- **Term:**
- **Instructor:**
- **Exam date(s):**
- **Notes:**
""",
        Path("courses") / "_Course_Template" / "00_Master" / "syllabus.md": """# Syllabus

Paste or summarize the official syllabus and learning objectives here.
""",
        Path("courses") / "_Course_Template" / "00_Master" / "exam_targets.md": """# Exam Targets

List topics, weightings, and formats to prioritize in study outputs.
""",
        Path("courses") / "_Course_Template" / "00_Master" / "prompt_templates.md": """# Course Prompt Templates

Optional per-course overrides or additions to global prompts in `prompts/`.
""",
        Path("courses") / "_Course_Template" / "00_Master" / "pipeline_settings.json": """{
  "course_slug": "_Course_Template",
  "chunk_size_tokens": 4000,
  "enable_intermediate_audit": true,
  "enable_final_audit": true
}
""",
        Path("courses") / "_Course_Template" / "07_My_Work" / "mistakes_log.md": """# Mistakes Log

Track errors from practice, homework, and mocks with date, topic, and fix.
""",
        Path("courses") / "_Course_Template" / "07_My_Work" / "weak_points.md": """# Weak Points

Topics or skills that need extra review. Link to relevant study outputs.
""",
    }


def run() -> int:
    """Create scaffold and print a summary."""
    created_dirs: list[str] = []
    existing_dirs: list[str] = []
    created_files: list[str] = []
    existing_files: list[str] = []

    print(f"StudyForge scaffold — project root: {PROJECT_ROOT}\n")

    # 1. Directories
    for rel in DIRECTORIES:
        full = PROJECT_ROOT / rel
        status = ensure_dir(full)
        rel_str = rel.as_posix()
        if status == "created":
            created_dirs.append(rel_str)
        else:
            existing_dirs.append(rel_str)

    # 2. .gitkeep files in empty leaf directories
    for rel in GITKEEP_DIRS:
        full = PROJECT_ROOT / rel
        ensure_dir(full)
        status = ensure_gitkeep(full)
        rel_str = (rel / ".gitkeep").as_posix()
        if status == "created":
            created_files.append(rel_str)
        else:
            existing_files.append(rel_str)

    # 3. Content files
    for rel, content in file_contents().items():
        full = PROJECT_ROOT / rel
        status = ensure_file(full, content)
        rel_str = rel.as_posix()
        if status == "created":
            created_files.append(rel_str)
        else:
            existing_files.append(rel_str)

    # Summary
    print("--- Directories ---")
    print(f"  Created: {len(created_dirs)}")
    for name in sorted(created_dirs):
        print(f"    + {name}")
    print(f"  Already existed: {len(existing_dirs)}")

    print("\n--- Files ---")
    print(f"  Created: {len(created_files)}")
    for name in sorted(created_files):
        print(f"    + {name}")
    print(f"  Already existed (left unchanged): {len(existing_files)}")

    print("\nDone. Re-running this script is safe; existing files are not overwritten.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
