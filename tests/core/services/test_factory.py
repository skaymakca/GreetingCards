"""Tests for app/core/services/factory.py — service wiring and Services container."""

from __future__ import annotations

import pytest

from app.core.card_store import CardStore
from app.core.services.card_service import CardService
from app.core.services.config_service import ConfigService
from app.core.services.factory import Services, create_services
from app.core.services.processing_service import ProcessingService
from app.core.services.rename_service import RenameService


class TestCreateServices:
    """Tests for create_services() factory function."""

    def test_returns_services_instance(self) -> None:
        result = create_services()
        assert isinstance(result, Services)

    def test_all_five_services_have_correct_types(self) -> None:
        services = create_services()
        assert isinstance(services.card_store, CardStore)
        assert isinstance(services.card_service, CardService)
        assert isinstance(services.config_service, ConfigService)
        assert isinstance(services.rename_service, RenameService)
        assert isinstance(services.processing_service, ProcessingService)

    def test_services_is_frozen(self) -> None:
        """Services dataclass is frozen — attribute assignment raises."""
        services = create_services()
        with pytest.raises(AttributeError):
            services.card_store = CardStore()  # type: ignore[misc]

    def test_card_store_shared_between_services(self) -> None:
        """CardStore is the same instance across CardService, RenameService, ProcessingService."""
        services = create_services()
        store = services.card_store
        assert services.card_service._store is store
        assert services.rename_service._store is store
        assert services.processing_service._store is store
