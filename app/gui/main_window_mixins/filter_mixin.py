"""FilterMixin — search and sidebar filter methods for MainWindow (Group D)."""

from __future__ import annotations

import wx

from app.core.services import filter_service
from app.core.services.filter_service import FilterCategory
from app.gui.main_window_mixins._protocol import MainWindowProtocol
from app.models.card import CardResult


class FilterMixin:
    """Mixin providing search/filter functionality for MainWindow.

    Methods use ``self: MainWindowProtocol`` to declare the interface they
    depend on.  At runtime ``self`` is always the full ``MainWindow`` instance.
    """

    def _on_search_text(self: MainWindowProtocol, event: wx.CommandEvent) -> None:
        """Filter cards as user types in search field."""
        self._refresh_display()

    def _on_search_cancel(self: MainWindowProtocol, event: wx.CommandEvent) -> None:
        """Clear filter when cancel button clicked."""
        self._search_ctrl.ChangeValue("")
        self._refresh_display()

    def _on_category_filter_change(self: MainWindowProtocol, filter_keys: list[str]) -> None:
        """Handle sidebar category filter change.

        Args:
            filter_keys: List of selected category filters (e.g., ["high", "manual"])
        """
        self._current_category_filters = filter_keys
        self._refresh_display()

    def _on_folder_filter_change(self: MainWindowProtocol, filter_keys: list[str]) -> None:
        """Handle sidebar folder filter change.

        Args:
            filter_keys: List of selected folder filters (e.g., ["all_folders"] or ["/path/to/dir"])
        """
        self._current_folder_filters = filter_keys
        self._refresh_display()

    def _refresh_display(self: MainWindowProtocol) -> None:
        """Refresh sidebar counts and cards table using cross-filtered pipeline.

        Delegates the two-pass cross-filter algorithm to
        ``filter_service.compute_filtered_view()`` so business logic stays in
        the service layer.  The view reads the result and updates widgets.
        """
        # Capture filter state BEFORE compute may trigger auto-reset
        had_active_filters = self._has_active_filters()

        view = filter_service.compute_filtered_view(
            all_cards=self._card_service.get_all_cards(),
            search_query=self._search_ctrl.GetValue(),
            category_filters=self._current_category_filters,
            folder_filters=self._current_folder_filters,
            folder_keys=self._sidebar.folder_filter_keys,
        )

        # Update sidebar counts (may auto-disable zero-count checkboxes)
        self._sidebar.update_category_counts(view.category_counts)
        self._sidebar.update_folder_counts(view.folder_counts)

        # Sync filter state: if compute_filtered_view auto-reset categories,
        # push the reset into the sidebar and our local state.
        if view.filters_were_reset:
            self._current_category_filters = [FilterCategory.ALL.value]
            self._sidebar.set_category_filters([FilterCategory.ALL.value])
            self._current_folder_filters = self._sidebar.get_selected_folder_filters()
        else:
            self._current_category_filters = self._sidebar.get_selected_category_filters()
            self._current_folder_filters = self._sidebar.get_selected_folder_filters()

        self._review_panel.load_cards(view.display_cards, preserve_selection=not had_active_filters)

        # Toggle overlay vs content area based on whether any cards exist at all
        self._set_empty_state(self._card_service.is_empty)

    def _has_active_filters(self: MainWindowProtocol) -> bool:
        """Return True if any search or filter is narrowing the view."""
        if self._search_ctrl.GetValue().strip():
            return True
        if FilterCategory.ALL.value not in self._current_category_filters:
            return True
        return "all_folders" not in self._current_folder_filters

    def _get_search_filtered_cards(self: MainWindowProtocol) -> list[CardResult]:
        """Get cards filtered by search query only."""
        cards = self._card_service.get_all_cards()
        query = self._search_ctrl.GetValue()
        return filter_service.search_filter(cards, query)

    def _apply_folder_filters(self: MainWindowProtocol, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar folder filters to a card list."""
        return filter_service.apply_folder_filters(cards, self._current_folder_filters)

    def _apply_category_filters(self: MainWindowProtocol, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar category filters to a card list."""
        return filter_service.apply_category_filters(cards, self._current_category_filters)
