"""AppleEventsMixin — Apple Events scripting bridge methods for MainWindow (Group A)."""

from __future__ import annotations

from pathlib import Path

from app.core.card_service import CardService
from app.core.rename_service import RenameService
from app.gui.main_window_mixins._protocol import MainWindowProtocol
from app.models.card import CardResult


class AppleEventsMixin:
    """Mixin providing Apple Events scripting bridge methods for MainWindow.

    Methods use ``self: MainWindowProtocol`` to declare the interface they
    depend on.  At runtime ``self`` is always the full ``MainWindow`` instance.
    """

    # ---- Apple Events bridge methods ----------------------------------------
    # Called from app.core.apple_events on the main thread.

    @property
    def is_processing(self: MainWindowProtocol) -> bool:  # type: ignore[misc]
        """True if PDF processing thread is running."""
        return self._is_processing_busy

    @property
    def is_ai_running(self: MainWindowProtocol) -> bool:  # type: ignore[misc]
        """True if AI batch analysis is in progress."""
        return self._ai_batch_running

    def _find_card_by_filename(self: MainWindowProtocol, filename: str) -> CardResult | None:
        """Find a card by filename (case-insensitive match on any file_path)."""
        return self._card_store.find_by_filename(filename)

    def get_status_for_script(self: MainWindowProtocol) -> dict:
        """Return current app status as a dict."""
        return {
            "is_processing": self.is_processing,
            "is_analyzing": self.is_ai_running,
            "loaded_count": self._card_store.count,
            "current_model": self._config_service.get_ai_model(),
            "year": self._get_year(),
        }

    def get_card_info_for_script(self: MainWindowProtocol, filename: str) -> CardResult | None:
        """Find a card by filename for scripting."""
        return self._find_card_by_filename(filename)

    def get_all_cards_for_script(self: MainWindowProtocol) -> list[CardResult]:
        """Return all loaded cards."""
        return self._card_store.get_all_cards()

    def load_paths_for_script(self: MainWindowProtocol, paths: list[str]) -> dict:
        """Load PDFs from file/folder paths. Returns JSON dict with success and count."""
        count = self._load_paths([Path(p) for p in paths])
        return {"success": True, "count": count}

    def rename_card_for_script(self: MainWindowProtocol, filename: str, new_name: str, year: str | None) -> dict:
        """Rename a card on disk. Returns result dict."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return {"success": False, "old_path": "", "new_path": "", "error": f"Card not found: {filename}"}

        year_str = year or self._get_year()
        if not RenameService.validate_year(year_str):
            return {"success": False, "old_path": "", "new_path": "", "error": f"Invalid year: {year_str}"}

        results = self._rename_service.rename_card(card, new_name, year_str)

        self._refresh_display()

        if results:
            r = results[0]
            return {
                "success": r.success,
                "old_path": str(r.old_path),
                "new_path": str(r.new_path),
                "error": "" if r.success else r.message,
            }
        return {"success": False, "old_path": "", "new_path": "", "error": "No rename plan generated"}

    def set_card_name_for_script(self: MainWindowProtocol, filename: str, name: str) -> dict:
        """Set or clear a manual name override."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return {"success": False, "error": f"Card not found: {filename}"}

        updated = self._card_service.set_name(card.id, name)
        if updated:
            self._review_panel.update_card(card.id, updated)
        self._refresh_display()
        return {"success": True}

    def select_candidate_for_script(self: MainWindowProtocol, filename: str, rank: int) -> dict:
        """Select a candidate by 1-based rank order."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return {"success": False, "error": f"Card not found: {filename}"}

        result = self._card_service.select_candidate_by_rank(card.id, rank)
        if isinstance(result, str):
            return {"success": False, "error": result}
        if result:
            self._review_panel.update_card(card.id, result)
        self._refresh_display()
        return {"success": True}

    def set_remove_family_for_script(self: MainWindowProtocol, filename: str, value: bool) -> dict:
        """Toggle the Remove Family flag."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return {"success": False, "error": f"Card not found: {filename}"}

        updated = self._card_service.set_remove_family(card.id, value)
        if updated:
            self._review_panel.update_card(card.id, updated)
        self._refresh_display()
        return {"success": True}

    def analyze_for_script(self: MainWindowProtocol, filename: str | None) -> dict:
        """Start AI analysis. Returns dict with success and count of cards queued."""
        if self._card_store.is_empty:
            return {"success": False, "error": "No cards loaded"}

        if not self._config_service.has_api_key():
            return {"success": False, "error": "No API key configured"}

        if filename:
            card = self._find_card_by_filename(filename)
            if card is None:
                return {"success": False, "error": f"Card not found: {filename}"}
            if not CardService.is_ai_eligible(card):
                return {"success": False, "error": f"Card not eligible for analysis: {filename}"}
            cards = [card]
        else:
            cards = [c for c in self._card_store.get_all_cards() if CardService.is_ai_eligible(c)]

        if not cards:
            return {"success": False, "error": "No eligible cards to analyze"}

        self._start_ai_all(cards=cards, title="AI Analysis (Script)")
        return {"success": True, "count": len(cards)}

    def clear_ai_for_script(self: MainWindowProtocol, filename: str | None) -> dict:
        """Clear AI results. Returns dict with success and count of cards affected."""
        if filename:
            card = self._find_card_by_filename(filename)
            if card is None:
                return {"success": False, "error": f"Card not found: {filename}"}
            cards = [card]
        else:
            cards = self._card_store.get_all_cards()

        if not cards:
            return {"success": True, "count": 0}

        changed = self._card_service.clear_ai_results(cards)

        self._refresh_display()
        return {"success": True, "count": changed}

    def reload_for_script(self: MainWindowProtocol) -> dict:
        """Trigger manual reload. Returns dict with success and changed flag."""
        if not self._card_store.has_paths:
            return {"success": False, "error": "No paths loaded"}

        changed = self._reload_cards(mtime_only=False)
        return {"success": True, "changed": changed}

    def clear_all_for_script(self: MainWindowProtocol) -> dict:
        """Clear all loaded cards and reset UI."""
        self._clear_all()
        return {"success": True}

    def set_ai_model_for_script(self: MainWindowProtocol, model_id: str) -> dict:
        """Set the active AI model. Returns result dict."""
        self._config_service.save_ai_model(model_id)
        return {"success": True}

    def quit_for_script(self: MainWindowProtocol) -> None:
        """Quit the application (AppleScript ``quit`` command)."""
        self._frame.Close()

    # ---- End Apple Events bridge methods ------------------------------------
