"""Shared helpers for spec generators."""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def extract_json(text: str) -> Any:
    """Extract and parse the first JSON value from text.

    Handles common Claude response patterns:
    - Clean JSON
    - JSON wrapped in Markdown code fences (```json ... ```)
    - JSON with leading/trailing prose

    Logs any non-JSON text that was stripped at INFO level.
    """
    text = text.strip()

    # Strip Markdown code fences
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        if "```" in text:
            text = text[: text.rindex("```")].strip()

    # Try parsing as-is first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first [ or { and try to parse from there
    for i, ch in enumerate(text):
        if ch in ("[", "{"):
            try:
                result = json.loads(text[i:])
                _log_extra_text(text[:i], text[i:])
                return result
            except json.JSONDecodeError:
                break

    # Last resort: find first [ or { and last } or ] and try that slice
    start = -1
    for i, ch in enumerate(text):
        if ch in ("[", "{"):
            start = i
            break
    if start >= 0:
        end = max(text.rfind("]"), text.rfind("}"))
        if end > start:
            json_slice = text[start : end + 1]
            try:
                result = json.loads(json_slice)
            except json.JSONDecodeError:
                pass
            else:
                _log_extra_text(text[:start], text[end + 1 :])
                return result

    msg = f"No valid JSON found in response: {text[:100]}"
    raise ValueError(msg)


def _log_extra_text(before: str, after: str) -> None:
    """Log non-JSON text that Claude included around the JSON response."""
    extra_parts: list[str] = []
    before = before.strip()
    after = after.strip()
    if before:
        extra_parts.append(f"before: {before!r}")
    if after:
        extra_parts.append(f"after: {after!r}")
    if extra_parts:
        log.info("Claude included extra text around JSON — %s", ", ".join(extra_parts))
