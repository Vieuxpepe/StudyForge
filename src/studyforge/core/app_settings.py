"""
Local app preferences (LM Studio, chunking, digest, GUI).

Stored in gitignored ``config/local_app_settings.json``. Never store API keys here.
"""

from __future__ import annotations

import copy
import json
import warnings
from pathlib import Path
from typing import Any

from studyforge.core.paths import find_project_root

LOCAL_APP_SETTINGS_RELATIVE = Path("config") / "local_app_settings.json"

_SECRET_KEY_FRAGMENTS = ("api_key", "apikey", "secret", "password", "credential")
_ALLOWED_TOKEN_KEYS = frozenset({"max_tokens"})


def get_default_app_settings() -> dict[str, Any]:
    """Return a fresh copy of default app settings."""
    return copy.deepcopy(
        {
            "lm_studio": {
                "base_url": "http://localhost:1234/v1",
                "default_model": "",
                "temperature": 0.2,
                "max_tokens": 6000,
                "timeout": 300,
            },
            "chunking": {
                "max_words": 1200,
                "overlap_words": 150,
            },
            "digest": {
                "limit_chunks_default": 1,
                "full_digest_default": False,
                "overwrite_default": False,
            },
            "gui": {
                "default_page": "today",
                "show_advanced_options": True,
            },
        }
    )


def get_app_settings_path(root: Path | None = None) -> Path:
    """Return the path to ``config/local_app_settings.json``."""
    project_root = root or find_project_root()
    return project_root / LOCAL_APP_SETTINGS_RELATIVE


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` into a copy of ``base``."""
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _is_secret_key(key: str) -> bool:
    lower = key.lower()
    if lower in _ALLOWED_TOKEN_KEYS:
        return False
    if any(fragment in lower for fragment in _SECRET_KEY_FRAGMENTS):
        return True
    return "token" in lower


def _strip_secret_keys(data: Any) -> Any:
    """Remove secret-like keys before loading or saving settings."""
    if not isinstance(data, dict):
        return data
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if _is_secret_key(str(key)):
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_secret_keys(value)
        else:
            cleaned[key] = value
    return cleaned


def load_app_settings(root: Path | None = None) -> dict[str, Any]:
    """
    Load settings from disk, merged with defaults.

    Malformed JSON falls back to defaults with a warning.
    """
    defaults = get_default_app_settings()
    path = get_app_settings_path(root)
    if not path.is_file():
        return defaults

    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        warnings.warn(
            f"Could not parse {path}; using default app settings. ({exc})",
            stacklevel=2,
        )
        return defaults

    if not isinstance(data, dict):
        warnings.warn(
            f"Expected JSON object in {path}; using default app settings.",
            stacklevel=2,
        )
        return defaults

    return _deep_merge(defaults, _strip_secret_keys(data))


def save_app_settings(settings: dict[str, Any], root: Path | None = None) -> Path:
    """Save settings to disk (merged with defaults, secrets stripped)."""
    path = get_app_settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _deep_merge(get_default_app_settings(), _strip_secret_keys(settings))
    with path.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def update_app_settings(
    updates: dict[str, Any], root: Path | None = None
) -> dict[str, Any]:
    """Merge updates into existing settings and save."""
    current = load_app_settings(root)
    merged = _deep_merge(current, _strip_secret_keys(updates))
    save_app_settings(merged, root)
    return merged


def validate_app_settings(settings: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty if valid)."""
    errors: list[str] = []

    lm = settings.get("lm_studio", {})
    base_url = str(lm.get("base_url", "")).strip()
    if not base_url.startswith(("http://", "https://")):
        errors.append("LM Studio base URL must start with http:// or https://.")

    temperature = lm.get("temperature")
    if not isinstance(temperature, (int, float)) or not 0 <= float(temperature) <= 2:
        errors.append("LM Studio temperature must be between 0 and 2.")

    max_tokens = lm.get("max_tokens")
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        errors.append("LM Studio max tokens must be greater than 0.")

    timeout = lm.get("timeout")
    if not isinstance(timeout, int) or timeout <= 0:
        errors.append("LM Studio timeout must be greater than 0.")

    chunking = settings.get("chunking", {})
    max_words = chunking.get("max_words")
    overlap_words = chunking.get("overlap_words")
    if not isinstance(max_words, int) or max_words <= 0:
        errors.append("Chunking max words must be greater than 0.")
    if not isinstance(overlap_words, int) or overlap_words < 0:
        errors.append("Chunking overlap words must be 0 or greater.")
    elif isinstance(max_words, int) and isinstance(overlap_words, int):
        if overlap_words >= max_words:
            errors.append("Chunking overlap words must be less than max words.")

    gui = settings.get("gui", {})
    default_page = str(gui.get("default_page", "")).strip().lower()
    if not default_page:
        errors.append("GUI default page must not be empty.")

    return errors
