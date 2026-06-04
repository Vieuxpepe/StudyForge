#!/usr/bin/env python3
"""
Launch the StudyForge Streamlit GUI.

Example:
    python scripts/launch_gui.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    app_path = project_root / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    print("Launching StudyForge GUI:")
    print(" ", " ".join(cmd))
    print(f"\nProject root: {project_root}\n")
    return subprocess.call(cmd, cwd=str(project_root))


if __name__ == "__main__":
    raise SystemExit(main())
