"""AIMixin — AI batch analysis methods for MainWindow (Group B)."""

from __future__ import annotations

import logging
import threading

import wx

from app.core.pipeline.ai_analyzer import AIError, AIErrorKind
from app.core.services.ai_service import AIService
from app.core.services.card_service import CardService
from app.gui.dialogs import ErrorListDialog
from app.gui.dialogs.api_key import show_api_key_dialog
from app.gui.main_window_mixins._protocol import MainWindowProtocol
from app.gui.utils import plural as _plural
from app.models.card import CardResult

logger = logging.getLogger(__name__)

_ELIGIBILITY_MESSAGES: dict[str, str] = {
    "card_has_error": "Cannot analyze card with errors.",
    "no_image": "No preview image available for AI analysis.",
}


class AIMixin:
    """Mixin providing AI batch analysis functionality for MainWindow.

    Methods use ``self: MainWindowProtocol`` to declare the interface they
    depend on.  At runtime ``self`` is always the full ``MainWindow`` instance.
    """

    def _get_action_menu_label(self: MainWindowProtocol, base: str, shortcut: str) -> str:
        """Build dynamic menu label like 'AI Analyze Selected (3)\\tCtrl+Shift+I'."""
        if self._card_service.is_empty:
            return f"{base}{shortcut}"
        cards, scope = self._get_target_cards()
        scope_label = "Selected" if scope == "selected" else "Visible"
        return f"{base} {scope_label} ({len(cards)}){shortcut}"

    # noinspection PyUnusedLocal
    def _on_clear_ai_results(self: MainWindowProtocol, event: wx.CommandEvent) -> None:
        """Clear AI results for selected or visible cards."""
        if self._card_service.is_empty:
            return

        cards, scope = self._get_target_cards()
        if not cards:
            return

        n = len(cards)
        scope_word = "selected" if scope == "selected" else "visible"
        result = wx.MessageBox(
            f"This will clear AI results for {n} {scope_word} card(s).\n\n"
            "OCR results, manual entries, and preferences preserved.\n"
            "Cards can be re-analyzed afterwards.\n\n"
            "Continue?",
            "Clear AI Results",
            wx.YES_NO | wx.ICON_QUESTION,
            self._frame,
        )
        if result != wx.YES:
            return

        changed = self._card_service.clear_ai_results(cards)

        self._refresh_display()
        self._show_info_message(
            f"AI results cleared for {n} card(s). {changed} reverted to OCR names.", wx.ICON_INFORMATION
        )

    def _ensure_api_key(self: MainWindowProtocol) -> bool:
        """Check for an API key; prompt the user if missing. Returns True if a key is available."""
        if self._config_service.has_api_key():
            return True

        # Show info bar with warning (no auto-dismiss for important warnings)
        self._show_info_message(
            "API key not configured\nUse Settings to add your Anthropic API key",
            wx.ICON_WARNING,
            duration_ms=0,  # Don't auto-dismiss warnings
        )

        # Also show dialog for immediate action
        api_key = show_api_key_dialog(self._frame)
        if api_key is not None:
            self._config_service.save_api_key(api_key)
            self._sidebar.dismiss_notification()
            return True

        return False

    def _get_target_cards(self: MainWindowProtocol) -> tuple[list[CardResult], str]:
        """Return (cards, scope) based on selection state.

        UI-policy: 2+ selected cards -> scoped batch; otherwise all visible cards.
        This is a presentation-layer decision about what the user intends to target.
        """
        selected_ids = self._review_panel.selected_card_ids
        if len(selected_ids) >= 2:
            cards = self._review_panel.get_cards_by_ids(selected_ids)
            return cards, "selected"
        return self._review_panel.get_cards(), "visible"

    def _on_ai_request(self: MainWindowProtocol, card_id: int) -> None:
        """Handle AI button click for single card — delegates to batch path."""
        if self._ai_batch_running:
            return
        card = self._get_card_by_id(card_id)
        if not card:
            return

        reason = CardService.check_ai_eligibility(card)
        if reason is not None:
            wx.MessageBox(
                _ELIGIBILITY_MESSAGES.get(reason, "Card is not eligible for AI analysis."),
                "Not Eligible",
                wx.OK | wx.ICON_WARNING,
                self._frame,
            )
            return

        if not self._ensure_api_key():
            return

        # Disable AI button before delegating (after API key check so
        # cancelling the key dialog doesn't leave the button stuck disabled)
        self._review_panel.set_ai_button_state(card_id, False)

        self._start_ai_all(cards=[card], title="AI Analysis")

    def _start_ai_all(
        self: MainWindowProtocol, cards: list[CardResult] | None = None, title: str | None = None
    ) -> None:
        """Start AI analysis for given cards, selected cards, or all visible cards.

        Args:
            cards: Explicit card list (e.g. single card from detail button).
                   If None, determines scope from selection state.
            title: Progress dialog title. If None, auto-generated from scope.
        """
        if self._card_service.is_empty:
            return

        if not self._ensure_api_key():
            return

        # Determine target cards and title
        if cards is None:
            cards, scope = self._get_target_cards()
            n = len(cards)
            if scope == "selected":
                title = f"AI Analysis \u2014 {n} Selected"
            else:
                title = f"AI Analysis \u2014 {n} Cards"
        elif title is None:
            title = "AI Analysis"

        if not cards:
            return

        self._ai_target_cards = cards
        self._ai_batch_running = True

        # Disable toolbar tools and lock AI buttons in review panel
        self._enable_action_tools(reload=False, ai=False, rename=False, clear=False)
        self._review_panel.set_ai_buttons_locked(True)

        # Show progress strip
        total = len(cards)
        self._show_progress_strip(total, title)

        # Start background thread
        thread = threading.Thread(target=self._run_ai_all, daemon=True)
        thread.start()

    def _run_ai_all(self: MainWindowProtocol) -> None:
        """Run async AI batch processing in background thread."""
        try:
            AIService.run_batch(
                self._ai_target_cards,
                on_progress=lambda c, t, f, i, card: wx.CallAfter(self._update_ai_all_progress, c, t, f, i, card),
                on_complete=lambda errors, aborted: wx.CallAfter(self._ai_all_complete, errors, aborted),
            )
        except Exception as e:
            error_msg = str(e)
            logger.error("AI batch processing failed: %s", error_msg)
            wx.CallAfter(self._ai_all_complete, [AIError(kind=AIErrorKind.UNKNOWN, detail=error_msg)])
        except BaseException:
            # Ensure flag is always cleared (e.g. KeyboardInterrupt, SystemExit)
            wx.CallAfter(self._ai_all_complete, [])
            raise

    # noinspection PyUnusedLocal
    def _update_ai_all_progress(
        self: MainWindowProtocol,
        completed: int,
        total: int,
        filename: str,
        card_id: int,
        card: CardResult | None,
    ) -> None:
        """Update progress during batch AI processing."""
        self._update_progress_strip(completed, f"AI analyzing: {filename}")

        if card is not None:
            self._review_panel.update_card(card_id, card)

    def _ai_all_complete(self: MainWindowProtocol, errors: list[AIError], auth_aborted: bool = False) -> None:
        """Called when batch AI processing completes."""
        self._ai_batch_running = False
        self._hide_progress_strip()

        # Unlock AI buttons in review panel and re-enable toolbar tools
        self._review_panel.set_ai_buttons_locked(False)
        self._enable_action_tools(reload=True, ai=True, rename=True, clear=True)

        # Update sidebar counts and cards table (confidence levels may have changed)
        self._refresh_display()

        if errors:
            suffix = " (auth error)" if auth_aborted else " (with errors)"
            dialog = ErrorListDialog(self._frame, f"AI Analysis{suffix}", errors, auth_aborted)
            dialog.ShowModal()
            dialog.Destroy()
        else:
            # Show success message with auto-dismiss
            count = len(self._ai_target_cards) or self._card_service.count
            self._show_info_message(f"Analysis complete\n{_plural(count, 'card')} analyzed", wx.ICON_INFORMATION)
