"""ConfigService — thin facade for configuration persistence.

Routes all config read/write operations through a single service so
callers never import ``app.core.config`` persistence functions directly.
"""

from app.core.config import (
    AI_MODELS,
    GITHUB_URL,
    ModelInfo,
    get_ai_model,
    has_prompted_auto_update,
    save_ai_model,
    set_prompted_auto_update,
)
from app.core.constants import RELOAD_COOLDOWN, default_year
from app.core.keychain import (
    get_api_key,
    save_api_key,
)


class ConfigService:
    """Facade for configuration and application constants."""

    @staticmethod
    def get_api_key() -> str | None:
        return get_api_key()

    @staticmethod
    def save_api_key(key: str) -> None:
        save_api_key(key)

    @staticmethod
    def has_api_key() -> bool:
        return get_api_key() is not None

    @staticmethod
    def get_ai_model() -> str:
        return get_ai_model()

    @staticmethod
    def save_ai_model(model_id: str) -> None:
        save_ai_model(model_id)

    @staticmethod
    def get_available_models() -> tuple[ModelInfo, ...]:
        """Return all available AI models."""
        return AI_MODELS

    @staticmethod
    def validate_model_id(model_id: str) -> bool:
        """Return True if model_id is a known AI model."""
        return any(m.model_id == model_id for m in AI_MODELS)

    @staticmethod
    def get_github_url() -> str:
        """Return the project GitHub URL."""
        return GITHUB_URL

    @staticmethod
    def get_default_year() -> str:
        """Return the default year for card naming."""
        return default_year()

    @staticmethod
    def has_prompted_auto_update() -> bool:  # pragma: no cover — Sparkle UI only
        """Return True if the auto-update opt-in dialog has been shown."""
        return has_prompted_auto_update()

    @staticmethod
    def set_prompted_auto_update() -> None:  # pragma: no cover — Sparkle UI only
        """Record that the auto-update opt-in dialog has been shown."""
        set_prompted_auto_update()

    @staticmethod
    def get_reload_cooldown() -> float:
        """Return the reload cooldown period in seconds."""
        return RELOAD_COOLDOWN
