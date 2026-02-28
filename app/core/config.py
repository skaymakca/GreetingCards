import logging
import os
import plistlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.paths import get_data_dir, is_bundled

GITHUB_URL = "https://github.com/skaymakca/GreetingCards"

_PLIST_NAME = "preferences.plist"
_KEY_NAME = "ANTHROPIC_API_KEY"
_MODEL_KEY = "AI_MODEL"


@dataclass(frozen=True)
class ModelInfo:
    """Metadata for an available AI model."""

    model_id: str
    label: str
    description: str
    speed: str
    quality: str
    cost_cents: float


AI_MODELS = (
    ModelInfo(
        "claude-haiku-4-5", "Claude Haiku 4.5", "Fast, low cost", speed="Fastest", quality="Good", cost_cents=0.4
    ),
    ModelInfo(
        "claude-sonnet-4-6",
        "Claude Sonnet 4.6",
        "Balanced (default)",
        speed="Fast",
        quality="Excellent",
        cost_cents=1.3,
    ),
    ModelInfo("claude-opus-4-6", "Claude Opus 4.6", "Most capable", speed="Moderate", quality="Best", cost_cents=2.1),
)

DEFAULT_AI_MODEL = "claude-sonnet-4-6"

logger = logging.getLogger(__name__)
_mismatch_warned = False


def _plist_path() -> Path:
    return get_data_dir() / _PLIST_NAME


def _read_plist() -> dict[str, Any]:
    path = _plist_path()
    if path.exists():
        with open(path, "rb") as f:
            return plistlib.load(f)
    return {}


def _write_plist(data: dict[str, Any]) -> None:
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def get_api_key() -> str | None:
    """Return the Anthropic API key, or None if not configured.

    Source mode: env var (ANTHROPIC_API_KEY) takes precedence over plist.
    Bundle mode: plist only (env var ignored).
    """
    global _mismatch_warned

    prefs = _read_plist()
    plist_key = prefs.get(_KEY_NAME) or None  # converts empty string to None

    # Bundle mode: only use plist
    if is_bundled():
        return plist_key

    # Source mode: env var takes precedence
    env_key = os.environ.get(_KEY_NAME)
    if env_key == "your-api-key-here":
        env_key = None

    if env_key and plist_key and env_key != plist_key and not _mismatch_warned:
        logger.warning("ANTHROPIC_API_KEY env var differs from preferences.plist; using env var")
        _mismatch_warned = True

    return env_key or plist_key


def save_api_key(key: str) -> None:
    """Persist the API key to preferences.plist in the data dir."""
    prefs = _read_plist()
    prefs[_KEY_NAME] = key
    _write_plist(prefs)
    # Also set in current process so get_api_key() returns it immediately
    os.environ[_KEY_NAME] = key


def get_ai_model() -> str:
    """Return the configured AI model ID, or DEFAULT_AI_MODEL if not set.

    If the stored model is missing or not in AI_MODELS (e.g. outdated),
    the default is saved back to preferences so it stays corrected.
    """
    prefs = _read_plist()
    model_id = prefs.get(_MODEL_KEY, "")
    valid_ids = {m.model_id for m in AI_MODELS}
    if model_id in valid_ids:
        return model_id
    # Persist the default so stale/missing values are corrected
    prefs[_MODEL_KEY] = DEFAULT_AI_MODEL
    _write_plist(prefs)
    return DEFAULT_AI_MODEL


def save_ai_model(model_id: str) -> None:
    """Persist the AI model choice to preferences.plist."""
    prefs = _read_plist()
    prefs[_MODEL_KEY] = model_id
    _write_plist(prefs)
