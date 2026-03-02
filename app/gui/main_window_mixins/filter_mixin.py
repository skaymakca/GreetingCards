"""FilterMixin — search and sidebar filter methods for MainWindow (Group D)."""

from __future__ import annotations

import wx

from app.core.services import filter_service
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

        Re-entrancy-free: sidebar count updates may auto-reset internal filter
        state (e.g. when all selected categories go to zero count). We sync
        MainWindow's filter state from sidebar after count updates, then
        recompute display. If display is still empty but search has results,
        auto-reset checkbox filters (keep search text).
        """
        search_cards = self._get_search_filtered_cards()

        # Capture filter state BEFORE sidebar sync / auto-reset may clear them
        had_active_filters = self._has_active_filters()

        # First pass: compute cross-filtered counts
        folder_filtered = self._apply_folder_filters(search_cards)
        category_filtered = self._apply_category_filters(search_cards)
        self._sidebar.update_category_counts(filter_service.count_by_category(folder_filtered))
        self._sidebar.update_folder_counts(
            filter_service.count_by_folder(category_filtered, self._sidebar.folder_filter_keys)
        )

        # Sync filter state back (sidebar may have auto-reset empty categories/folders)
        self._current_category_filters = self._sidebar.get_selected_category_filters()
        self._current_folder_filters = self._sidebar.get_selected_folder_filters()

        # Recompute display with synced filters
        folder_filtered = self._apply_folder_filters(search_cards)
        display_cards = self._apply_category_filters(folder_filtered)

        # Auto-reset checkbox filters when display is empty but cards exist
        if not display_cards and search_cards:
            self._current_category_filters = ["all"]
            self._current_folder_filters = self._sidebar.get_selected_folder_filters()
            self._sidebar.set_category_filters(["all"])
            self._sidebar.set_folder_filters(self._current_folder_filters)
            # Recompute with reset filters
            folder_filtered = self._apply_folder_filters(search_cards)
            display_cards = self._apply_category_filters(folder_filtered)
            # Update counts to reflect reset state
            self._sidebar.update_category_counts(filter_service.count_by_category(folder_filtered))
            self._sidebar.update_folder_counts(
                filter_service.count_by_folder(display_cards, self._sidebar.folder_filter_keys)
            )

        self._review_panel.load_cards(display_cards, preserve_selection=not had_active_filters)

        # Toggle overlay vs content area based on whether any cards exist at all
        self._set_empty_state(self._card_store.is_empty)

    def _has_active_filters(self: MainWindowProtocol) -> bool:
        """Return True if any search or filter is narrowing the view."""
        if self._search_ctrl.GetValue().strip():
            return True
        if "all" not in self._current_category_filters:
            return True
        return "all_folders" not in self._current_folder_filters

    def _get_search_filtered_cards(self: MainWindowProtocol) -> list[CardResult]:
        """Get cards filtered by search query only."""
        cards = self._card_store.get_all_cards()
        query = self._search_ctrl.GetValue()
        return filter_service.search_filter(cards, query)

    def _apply_folder_filters(self: MainWindowProtocol, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar folder filters to a card list."""
        return filter_service.apply_folder_filters(cards, self._current_folder_filters)

    def _apply_category_filters(self: MainWindowProtocol, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar category filters and sort by filename for display."""
        filtered = filter_service.apply_category_filters(cards, self._current_category_filters)
        return sorted(filtered, key=lambda c: c.filename.lower())
