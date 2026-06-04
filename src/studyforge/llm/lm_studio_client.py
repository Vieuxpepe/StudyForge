"""
HTTP client for LM Studio's OpenAI-compatible local API.
"""

from __future__ import annotations

from typing import Any

import requests

DEFAULT_BASE_URL = "http://localhost:1234/v1"


class LMStudioError(Exception):
    """Base error for LM Studio client failures."""


class LMStudioConnectionError(LMStudioError):
    """Could not reach the LM Studio server."""


class LMStudioAPIError(LMStudioError):
    """LM Studio returned an error or unexpected response."""


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def check_lm_studio_connection(base_url: str = DEFAULT_BASE_URL) -> dict:
    """
    Check whether LM Studio is reachable and list available models.

    Calls GET {base_url}/models

    Returns:
        {
            "ok": bool,
            "base_url": str,
            "models": list[str],
            "error": str | None,
        }
    """
    url = _normalize_base_url(base_url)
    models_url = f"{url}/models"

    try:
        response = requests.get(models_url, timeout=10)
    except requests.exceptions.ConnectionError as exc:
        return {
            "ok": False,
            "base_url": url,
            "models": [],
            "error": f"Connection failed: {exc}",
        }
    except requests.exceptions.Timeout as exc:
        return {
            "ok": False,
            "base_url": url,
            "models": [],
            "error": f"Request timed out: {exc}",
        }
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "base_url": url,
            "models": [],
            "error": str(exc),
        }

    if response.status_code != 200:
        return {
            "ok": False,
            "base_url": url,
            "models": [],
            "error": f"HTTP {response.status_code}: {response.text[:500]}",
        }

    try:
        payload = response.json()
    except ValueError as exc:
        return {
            "ok": False,
            "base_url": url,
            "models": [],
            "error": f"Invalid JSON from /models: {exc}",
        }

    model_ids = _extract_model_ids(payload)
    if not model_ids:
        return {
            "ok": False,
            "base_url": url,
            "models": [],
            "error": "No models returned from /models. Load a model in LM Studio first.",
        }

    return {
        "ok": True,
        "base_url": url,
        "models": model_ids,
        "error": None,
    }


def _extract_model_ids(payload: dict[str, Any]) -> list[str]:
    """Parse model IDs from OpenAI-style or LM Studio /models JSON."""
    ids: list[str] = []

    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))

    if ids:
        return ids

    models = payload.get("models")
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict):
                model_id = item.get("id") or item.get("name")
                if model_id:
                    ids.append(str(model_id))
            elif isinstance(item, str):
                ids.append(item)

    return ids


def choose_default_model(models_response: dict) -> str | None:
    """Pick the first model ID from a check_lm_studio_connection() result."""
    models = models_response.get("models") or []
    if not models:
        return None
    return str(models[0])


def build_chat_completion_body(
    *,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    enable_thinking: bool = False,
) -> dict[str, Any]:
    """
    Build the JSON body for POST /chat/completions.

    When enable_thinking is False (default), request non-thinking mode using
    fields understood by vLLM, LM Studio, and Gemma/Qwen-style chat templates.
    """
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if not enable_thinking:
        template_kwargs = {"enable_thinking": False}
        body["reasoning_effort"] = "none"
        body["chat_template_kwargs"] = template_kwargs
        # OpenAI SDK-style nesting; some LM Studio builds forward this.
        body["extra_body"] = {"chat_template_kwargs": template_kwargs}
    return body


def chat_completion(
    messages: list[dict],
    model: str,
    base_url: str = DEFAULT_BASE_URL,
    temperature: float = 0.2,
    max_tokens: int = 3000,
    timeout: int = 300,
    enable_thinking: bool = False,
) -> str:
    """
    Send a chat completion request and return assistant message content.

    POST {base_url}/chat/completions

    By default, thinking/reasoning mode is disabled so digest tokens go to
    the structured answer (Gemma 4, Qwen3, etc.).

    Raises:
        LMStudioConnectionError: Network or timeout failure.
        LMStudioAPIError: Non-200 response or malformed payload.
    """
    if not model:
        raise LMStudioAPIError("Model name is required for chat completion.")

    url = f"{_normalize_base_url(base_url)}/chat/completions"
    body = build_chat_completion_body(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
    )

    try:
        response = requests.post(url, json=body, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise LMStudioConnectionError(
            f"Could not connect to LM Studio at {base_url}: {exc}"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise LMStudioConnectionError(
            f"LM Studio request timed out after {timeout}s: {exc}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise LMStudioConnectionError(str(exc)) from exc

    if response.status_code != 200:
        raise LMStudioAPIError(
            f"LM Studio returned HTTP {response.status_code}: {response.text[:1000]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise LMStudioAPIError(f"Invalid JSON in chat completion response: {exc}") from exc

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LMStudioAPIError("Chat completion response missing 'choices'.")

    first = choices[0]
    if not isinstance(first, dict):
        raise LMStudioAPIError("Malformed choice in chat completion response.")

    message = first.get("message")
    if not isinstance(message, dict):
        raise LMStudioAPIError("Chat completion choice missing 'message'.")

    content = message.get("content")
    if content is None:
        raise LMStudioAPIError("Chat completion message missing 'content'.")

    return str(content).strip()
