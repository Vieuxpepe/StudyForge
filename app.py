#!/usr/bin/env python3
"""
StudyForge Streamlit GUI — entry point for Streamlit only.

Start the GUI with (from project root):
    python -m streamlit run app.py

Or:
    python scripts/launch_gui.py

Do not start with ``python app.py`` — that skips Streamlit's server.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on the path when Streamlit runs this file
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.ui.streamlit_app import run  # noqa: E402

run()
