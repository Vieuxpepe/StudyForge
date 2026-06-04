"""
Load API keys from environment or gitignored config/local_secrets.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from studyforge.core.paths import find_project_root

LOCAL_SECRETS_RELATIVE = Path("config") / "local_secrets.json"
_DOTENV_LOADED = False


def load_dotenv_file(root: Path | None = None) -> bool:
    """
    Load project ``.env`` if present (gitignored).

    Does not override variables already set in the process environment.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return False
    _DOTENV_LOADED = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    project_root = root or find_project_root()
    env_path = project_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
        # Windows editors sometimes write UTF-8 BOM; normalize key name.
        bom_key = "\ufeffGOOGLE_API_KEY"
        if bom_key in os.environ and "GOOGLE_API_KEY" not in os.environ:
            os.environ["GOOGLE_API_KEY"] = os.environ.pop(bom_key)
        return True
    return False


def local_secrets_path(root: Path | None = None) -> Path:
    return (root or find_project_root()) / LOCAL_SECRETS_RELATIVE


def load_local_secrets(root: Path | None = None) -> dict[str, Any]:
    path = local_secrets_path(root)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def save_local_secrets(secrets: dict[str, Any], root: Path | None = None) -> Path:
    path = local_secrets_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(secrets, handle, indent=2)
        handle.write("\n")
    return path


def get_google_api_key(root: Path | None = None) -> str | None:
    """Resolve Google AI / Gemini API key from .env, env, or local_secrets.json."""
    load_dotenv_file(root)
    env_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    file_key = load_local_secrets(root).get("google_api_key")
    if isinstance(file_key, str) and file_key.strip():
        return file_key.strip()
    return None


def set_google_api_key(api_key: str, root: Path | None = None) -> Path:
    """Persist Google API key to gitignored local_secrets.json."""
    secrets = load_local_secrets(root)
    secrets["google_api_key"] = api_key.strip()
    return save_local_secrets(secrets, root)
