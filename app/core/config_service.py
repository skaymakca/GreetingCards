"""ConfigService — thin facade for configuration persistence.

Routes all config read/write operations through a single service so
GUI callers never import ``app.core.config`` persistence functions directly.
"""

from app.core.config import get_ai_model, get_api_key, save_ai_model, save_api_key


class ConfigService:
    """Facade for configuration persistence (API key, AI model)."""

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
