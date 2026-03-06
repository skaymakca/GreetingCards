import logging
import plistlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.paths import get_data_dir

GITHUB_URL = "https://github.com/skaymakca/GreetingCards"

_PLIST_NAME = "preferences.plist"
_MODEL_KEY = "AI_MODEL"
_AUTO_UPDATE_PROMPTED_KEY = "AUTO_UPDATE_PROMPTED"


@dataclass(frozen=True)
class ModelInfo:
    """Metadata for an available AI model.

    Contains both technical (model_id, cost_cents) and presentation
    (label, description, speed, quality) fields. These are consumed by
    both the Settings GUI and the Apple Events scripting layer — splitting
    into separate types would require a mapping table with no clear benefit.
    """

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


def has_prompted_auto_update() -> bool:
    """Return True if the user has already been shown the auto-update opt-in dialog."""
    return bool(_read_plist().get(_AUTO_UPDATE_PROMPTED_KEY, False))


def set_prompted_auto_update() -> None:
    """Record that the auto-update opt-in dialog has been shown."""
    prefs = _read_plist()
    prefs[_AUTO_UPDATE_PROMPTED_KEY] = True
    _write_plist(prefs)
