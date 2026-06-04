"""
HTTP client for Google AI (Gemini API) — Gemma 4 and related models.
"""

from __future__ import annotations

from typing import Any

import requests

DEFAULT_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Gemma 4 on Google AI Studio (see ai.google.dev)
DEFAULT_GEMMA_4_26B_MODEL = "gemma-4-26b-a4b-it"
DEFAULT_GEMMA_4_31B_MODEL = "gemma-4-31b-it"

# Free tier is often ~15 RPM — pause between chunk audits if needed
DEFAULT_REQUEST_INTERVAL_SECONDS = 4.0


class GoogleGenAIError(Exception):
    """Base error for Google Generative Language API failures."""


class GoogleGenAIConfigError(GoogleGenAIError):
    """Missing API key or model configuration."""


class GoogleGenAIConnectionError(GoogleGenAIError):
    """Network or timeout failure."""


class GoogleGenAIAPIError(GoogleGenAIError):
    """Non-success HTTP response or malformed payload."""


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def build_generate_content_body(
    *,
    user_text: str,
    system_instruction: str | None = None,
    temperature: float = 0.2,
    max_output_tokens: int = 8192,
    disable_thinking: bool = True,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_text}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    # Gemma 4 on the Gemini API rejects thinkingBudget; thinking is off by default.
    # Only attach thinkingConfig when explicitly enabling it (future use).
    if not disable_thinking:
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 1024}
    return body


def generate_content(
    *,
    api_key: str,
    model: str,
    user_text: str,
    system_instruction: str | None = None,
    base_url: str = DEFAULT_GOOGLE_BASE_URL,
    temperature: float = 0.2,
    max_output_tokens: int = 8192,
    timeout: int = 300,
    disable_thinking: bool = True,
) -> str:
    """
    Call ``models/{model}:generateContent`` and return response text.

    Raises:
        GoogleGenAIConfigError, GoogleGenAIConnectionError, GoogleGenAIAPIError.
    """
    if not api_key.strip():
        raise GoogleGenAIConfigError(
            "Google API key is missing. Set GOOGLE_API_KEY or add "
            "google_api_key to config/local_secrets.json (see local_secrets.example.json)."
        )
    if not model.strip():
        raise GoogleGenAIConfigError("Model name is required.")

    url = (
        f"{_normalize_base_url(base_url)}/models/{model}:generateContent"
        f"?key={api_key.strip()}"
    )
    body = build_generate_content_body(
        user_text=user_text,
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        disable_thinking=disable_thinking,
    )

    try:
        response = requests.post(url, json=body, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise GoogleGenAIConnectionError(f"Could not reach Google AI API: {exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise GoogleGenAIConnectionError(
            f"Google AI request timed out after {timeout}s: {exc}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise GoogleGenAIConnectionError(str(exc)) from exc

    if response.status_code != 200:
        raise GoogleGenAIAPIError(
            f"Google AI returned HTTP {response.status_code}: {response.text[:1500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise GoogleGenAIAPIError(f"Invalid JSON in response: {exc}") from exc

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        block_reason = payload.get("promptFeedback") or payload
        raise GoogleGenAIAPIError(
            f"Response missing candidates: {block_reason!s}"[:1000]
        )

    first = candidates[0]
    if not isinstance(first, dict):
        raise GoogleGenAIAPIError("Malformed candidate in response.")

    content = first.get("content")
    if not isinstance(content, dict):
        raise GoogleGenAIAPIError("Candidate missing content.")

    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise GoogleGenAIAPIError("Content missing text parts.")

    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            texts.append(str(part["text"]))

    if not texts:
        raise GoogleGenAIAPIError("No text in response parts.")

    return "\n".join(texts).strip()


def list_models(api_key: str, base_url: str = DEFAULT_GOOGLE_BASE_URL, timeout: int = 30) -> list[str]:
    """Return model names from GET /models (best-effort)."""
    url = f"{_normalize_base_url(base_url)}/models?key={api_key.strip()}"
    try:
        response = requests.get(url, timeout=timeout)
    except requests.exceptions.RequestException:
        return []
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    names: list[str] = []
    for item in payload.get("models", []):
        if isinstance(item, dict) and item.get("name"):
            name = str(item["name"])
            if name.startswith("models/"):
                name = name.split("/", 1)[1]
            names.append(name)
    return names
