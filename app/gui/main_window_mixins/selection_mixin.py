"""SelectionMixin — card selection and editing methods for MainWindow (Group F)."""

from __future__ import annotations

import wx

from app.gui.main_window_mixins._protocol import MainWindowProtocol
from app.gui.styles import Layout


class SelectionMixin:
    """Mixin providing card selection and edit-debounce functionality for MainWindow.

    Methods use ``self: MainWindowProtocol`` to declare the interface they
    depend on.  At runtime ``self`` is always the full ``MainWindow`` instance.
    """

    def _on_card_select(self: MainWindowProtocol, card_id: int | None) -> None:
        """Handle card selection - update preview panel."""
        if card_id is None:
            self._preview_panel.clear()
            return

        card = self._get_card_by_id(card_id)
        if not card:
            return

        if card.error:
            self._preview_panel.show_error(card.error, card.filename)
        elif images := card.best_preview_images:
            self._preview_panel.show_images(images, card.filename)
        else:
            self._preview_panel.clear()

    def _on_name_change(self: MainWindowProtocol, card_id: int, new_name: str) -> None:
        """Handle manual name edit in review panel."""
        card = self._card_service.set_name(card_id, new_name)
        if card is None:
            return

        # Update review panel
        self._review_panel.update_card(card_id, card)

        # Debounce: restart 1-second timer on each keystroke
        self._edit_debounce_timer.Stop()
        self._edit_debounce_timer.StartOnce(Layout.DEBOUNCE_MS)

    def _on_checkbox_toggle(self: MainWindowProtocol, card_id: int, value: bool) -> None:
        """Handle Remove Family checkbox toggle from review panel."""
        card = self._card_service.set_remove_family(card_id, value)
        if card:
            self._review_panel.update_card(card_id, card)
        self._refresh_display()

    def _on_candidate_select(self: MainWindowProtocol, card_id: int, candidate_id: int) -> None:
        """Handle candidate selection from review panel."""
        card = self._card_service.select_candidate(card_id, candidate_id)
        if card:
            self._review_panel.update_card(card_id, card)
        self._refresh_display()

    def _on_card_edited(self: MainWindowProtocol, card_id: int) -> None:
        """Handle discrete card edits (e.g. candidate selection) that change confidence."""
        self._refresh_display()

    def _on_remove_card(self: MainWindowProtocol, file_hash: str) -> None:
        """Remove a card from the in-memory table (non-destructive — does not delete files).

        Args:
            file_hash: The content hash of the card to remove
        """
        card = self._card_service.get_by_hash(file_hash)
        if not card:
            return

        # Remove all path → hash mappings for this card, then the card itself
        for path in list(card.file_paths):
            self._unlink_path(path)

        # Refresh display (handles filter counts, list reload, empty state)
        self._refresh_display()

    def _on_remove_menu(self: MainWindowProtocol, event: wx.CommandEvent) -> None:
        """Handle Edit > Remove — remove all selected cards."""
        for card_id in list(self._review_panel.selected_card_ids):
            card = self._get_card_by_id(card_id)
            if card:
                for path in list(card.file_paths):
                    self._unlink_path(path)
        self._refresh_display()

    def _on_update_remove_menu(self: MainWindowProtocol, event: wx.UpdateUIEvent) -> None:
        """Enable Remove menu item only when cards are selected."""
        event.Enable(bool(self._review_panel.selected_card_ids))

    def _on_edit_debounce_fire(self: MainWindowProtocol, event: wx.TimerEvent) -> None:
        """Fire after user stops typing for 1 second — refresh filters."""
        self._refresh_display()
