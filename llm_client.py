"""Ollama LLM client with JSON response extraction."""

from __future__ import annotations

import json
import re
import time
import requests

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_FALLBACK_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_MAX_RETRIES,
    MAX_OUTPUT_TOKENS,
    PHASE_MODELS,
)


def get_model(phase: str | None = None) -> str:
    """Resolve the Ollama model name for a given phase.

    Falls back to OLLAMA_FALLBACK_MODEL if the phase model is not set
    or if phase is None.
    """
    if phase and phase in PHASE_MODELS:
        return PHASE_MODELS[phase]
    return OLLAMA_FALLBACK_MODEL


def generate(prompt: str, model: str | None = None, max_tokens: int | None = None) -> str:
    """Send a prompt to Ollama and return the raw text response."""
    model = model or OLLAMA_FALLBACK_MODEL
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens or MAX_OUTPUT_TOKENS,
            "temperature": 0.3,
        },
    }

    last_error = None
    for attempt in range(1, OLLAMA_MAX_RETRIES + 2):
        try:
            resp = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
            if resp.status_code == 404:
                raise ConnectionError(
                    f"Model '{model}' not found. Pull it first: ollama pull {model}"
                )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt <= OLLAMA_MAX_RETRIES:
                time.sleep(2 * attempt)

    raise ConnectionError(f"Ollama request failed after {OLLAMA_MAX_RETRIES + 1} attempts: {last_error}")


def generate_json(prompt: str, model: str | None = None, max_tokens: int | None = None) -> list[dict] | dict:
    """Call Ollama and extract JSON from the response.

    Handles common SLM quirks: markdown fences, preamble text, trailing commas.
    Returns parsed JSON (dict or list).
    """
    raw = generate(prompt, model, max_tokens=max_tokens)
    return parse_json_response(raw)


def _find_json_span(s: str, start: int) -> str | None:
    """Find the full extent of a JSON array or object starting at start.
    Respects brackets inside double-quoted strings. Returns None if truncated.
    """
    if start >= len(s) or s[start] not in "[{":
        return None
    open_b, close_b = ("[", "]") if s[start] == "[" else ("{", "}")
    depth = 1
    i = start + 1
    in_string = False
    escape_next = False
    while i < len(s):
        c = s[i]
        if escape_next:
            escape_next = False
            i += 1
            continue
        if in_string:
            if c == "\\":
                escape_next = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == open_b:
            depth += 1
            i += 1
            continue
        if c == close_b:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
            i += 1
            continue
        i += 1
    return None


def _try_parse(candidate: str) -> list[dict] | dict | None:
    """Try to parse JSON, optionally fix trailing commas. Returns None on failure."""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


def parse_json_response(raw: str) -> list[dict] | dict:
    """Extract and parse JSON from a raw LLM text response.

    Handles preamble text (e.g. "Output only valid JSON", "BEGIN EXTRACT"),
    markdown fences, trailing commas, and bracket-aware extraction so that
    brackets inside string values do not break the match. If the response
    appears truncated, tries to recover by closing the array and parsing
    complete objects only.
    """
    # Try direct parse first
    result = _try_parse(raw)
    if result is not None:
        return result

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    # Find first start of JSON (array or object) to skip preamble
    start_array = cleaned.find("[")
    start_object = cleaned.find("{")
    start = -1
    if start_array >= 0 and (start_object < 0 or start_array < start_object):
        start = start_array
    elif start_object >= 0:
        start = start_object

    if start >= 0:
        span = _find_json_span(cleaned, start)
        if span is not None:
            result = _try_parse(span)
            if result is not None:
                return result
        # Truncation fallback: response may be cut off before closing ]
        if start_array >= 0 and start == start_array:
            # Try to close the array and parse up to last complete object
            tail = cleaned[start_array:]
            # Find last occurrence of "}\s*" that could be end of an object
            last_brace = tail.rfind("}")
            if last_brace >= 0:
                candidate = tail[: last_brace + 1]
                # Ensure we have [ ... ] with at least one object
                if not candidate.strip().startswith("["):
                    candidate = "[" + candidate
                if not candidate.rstrip().endswith("]"):
                    candidate = candidate.rstrip()
                    if candidate.endswith(","):
                        candidate = candidate[:-1]
                    candidate += "]"
                result = _try_parse(candidate)
                if result is not None:
                    return result

    raise ValueError(f"Could not extract valid JSON from LLM response. Raw output:\n{raw[:500]}")


def unload_model(model: str):
    """Tell Ollama to unload a model from VRAM immediately."""
    url = f"{OLLAMA_BASE_URL}/api/generate"
    try:
        requests.post(
            url,
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=10,
        )
    except requests.exceptions.RequestException:
        pass


def preload_model(model: str):
    """Tell Ollama to load a model into VRAM without generating anything."""
    url = f"{OLLAMA_BASE_URL}/api/generate"
    try:
        requests.post(
            url,
            json={"model": model, "prompt": "", "keep_alive": "10m"},
            timeout=60,
        )
    except requests.exceptions.RequestException:
        pass


def swap_model(current_phase: str, next_phase: str):
    """Unload the current phase model and preload the next one."""
    current_model = get_model(current_phase)
    next_model = get_model(next_phase)
    if current_model != next_model:
        unload_model(current_model)
        preload_model(next_model)
