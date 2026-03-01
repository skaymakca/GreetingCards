"""AppleEventsMixin — Apple Events scripting bridge methods for MainWindow (Group A)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_ai_model, get_api_key
from app.core.naming.rename_filter import RESOLVED_MESSAGES
from app.core.naming.renamer import build_rename_plan, execute_rename_plan
from app.core.pipeline.card_processor import scan_for_pdfs
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
        return bool(self._processing_files) and not self._toolbar.GetToolEnabled(self._reload_id)

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
            "current_model": get_ai_model(),
            "year": self._year_ctrl.GetValue().strip(),
        }

    def get_card_info_for_script(self: MainWindowProtocol, filename: str) -> CardResult | None:
        """Find a card by filename for scripting."""
        return self._find_card_by_filename(filename)

    def get_all_cards_for_script(self: MainWindowProtocol) -> list[CardResult]:
        """Return all loaded cards."""
        return self._card_store.get_all_cards()

    def load_paths_for_script(self: MainWindowProtocol, paths: list[str]) -> dict:
        """Load PDFs from file/folder paths. Returns JSON dict with success and count."""
        path_objects = [Path(p) for p in paths]

        # Scan all paths for PDFs
        all_pdfs: list[Path] = []
        for path in path_objects:
            all_pdfs.extend(scan_for_pdfs(path))

        # Filter already loaded
        new_pdfs = [p for p in all_pdfs if not self._card_store.has_path(p)]

        if new_pdfs:
            self._card_store.register_new_pdfs(new_pdfs)
            self._start_processing(new_pdfs)

        return {"success": True, "count": len(new_pdfs)}

    def rename_card_for_script(self: MainWindowProtocol, filename: str, new_name: str, year: str | None) -> dict:
        """Rename a card on disk. Returns result dict."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return {"success": False, "old_path": "", "new_path": "", "error": f"Card not found: {filename}"}

        year_str = year or self._year_ctrl.GetValue().strip()
        if not year_str or not year_str.isdigit() or len(year_str) != 4:
            return {"success": False, "old_path": "", "new_path": "", "error": f"Invalid year: {year_str}"}

        # Temporarily set the card's display name for rename
        old_override = card.manual_override
        old_family = card.family_name
        old_method = card.method
        old_confidence = card.confidence

        card.manual_override = new_name

        plan = build_rename_plan([card], year_str)
        results = execute_rename_plan(plan)

        # Update tracking dicts for successful renames
        for result in results:
            if result.success and result.message in RESOLVED_MESSAGES:
                self._card_store.update_path_mapping(result.old_path, result.new_path)

        # Restore override if rename didn't use it (e.g. skip)
        if not any(r.success for r in results):
            card.manual_override = old_override
            card.family_name = old_family
            card.method = old_method
            card.confidence = old_confidence

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

        if rank < 1 or rank > len(card.candidates):
            return {"success": False, "error": f"Invalid rank {rank}: card has {len(card.candidates)} candidates"}

        updated = self._card_service.select_candidate_by_rank(card.id, rank)
        if updated:
            self._review_panel.update_card(card.id, updated)
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

        if not get_api_key():
            return {"success": False, "error": "No API key configured"}

        if filename:
            card = self._find_card_by_filename(filename)
            if card is None or card.error:
                return {"success": False, "error": f"Card not found: {filename}"}
            if not card.page_images and not card.preview_image:
                return {"success": False, "error": f"No images available for: {filename}"}
            cards = [card]
        else:
            cards = [c for c in self._card_store.get_all_cards() if not c.error]

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

        old_count = self._card_store.count
        old_hashes = {c.file_hash for c in self._card_store.get_all_cards() if c.file_hash}
        self._reload_cards(mtime_only=False)

        # Detect changes by comparing state
        new_hashes = {c.file_hash for c in self._card_store.get_all_cards() if c.file_hash}
        changed = old_hashes != new_hashes or old_count != self._card_store.count
        return {"success": True, "changed": changed}

    def clear_all_for_script(self: MainWindowProtocol) -> dict:
        """Clear all loaded cards and reset UI."""
        self._clear_all()
        return {"success": True}

    def quit_for_script(self: MainWindowProtocol) -> None:
        """Quit the application (AppleScript ``quit`` command)."""
        self._frame.Close()

    # ---- End Apple Events bridge methods ------------------------------------
