import os
import plistlib
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import is_bundled, get_data_dir

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
    ModelInfo("claude-haiku-4-5-20251001", "Claude Haiku 4.5", "Fast, low cost",
              speed="Fastest", quality="Good", cost_cents=0.4),
    ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6", "Balanced (default)",
              speed="Fast", quality="Excellent", cost_cents=1.3),
    ModelInfo("claude-opus-4-6", "Claude Opus 4.6", "Most capable",
              speed="Moderate", quality="Best", cost_cents=2.1),
)

DEFAULT_AI_MODEL = "claude-sonnet-4-6"


def _plist_path() -> Path:
    return get_data_dir() / _PLIST_NAME


def _read_plist() -> dict:
    path = _plist_path()
    if path.exists():
        with open(path, "rb") as f:
            return plistlib.load(f)
    return {}


def _write_plist(data: dict) -> None:
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def get_api_key() -> str | None:
    """Return the Anthropic API key, or None if not configured.

    Resolution order:
      1. ANTHROPIC_API_KEY environment variable (always checked)
      2. Dev mode: .env file via dotenv
      3. Bundled mode: preferences.plist in data dir
    """
    # 1. Check environment (may already be set externally)
    key = os.environ.get(_KEY_NAME)
    if key and key != "your-api-key-here":
        return key

    if not is_bundled():
        # 2. Dev mode — load .env then re-check
        from dotenv import load_dotenv
        load_dotenv()
        key = os.environ.get(_KEY_NAME)
        if key and key != "your-api-key-here":
            return key
    else:
        # 3. Bundled mode — read from plist
        prefs = _read_plist()
        key = prefs.get(_KEY_NAME)
        if key:
            return key

    return None


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
