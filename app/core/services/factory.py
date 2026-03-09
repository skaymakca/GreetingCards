"""Services factory — centralizes dependency wiring."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.card_store import CardStore
from app.core.services.card_service import CardService
from app.core.services.config_service import ConfigService
from app.core.services.processing_service import ProcessingService
from app.core.services.rename_service import RenameService


@dataclass(frozen=True, slots=True)
class Services:
    """Container for all application services."""

    card_store: CardStore
    card_service: CardService
    config_service: ConfigService
    rename_service: RenameService
    processing_service: ProcessingService


def create_services() -> Services:
    """Create and wire all application services.

    A single ``CardStore`` is shared between the services that need it.
    """
    store = CardStore()
    return Services(
        card_store=store,
        card_service=CardService(store),
        config_service=ConfigService(),
        rename_service=RenameService(store),
        processing_service=ProcessingService(store),
    )
