"""AppleEventsMixin — Apple Events scripting bridge methods for MainWindow (Group A)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_ai_model, get_api_key
from app.core.database import clear_ai_results, select_candidate, set_manual_name, update_remove_family
from app.core.naming.rename_filter import RESOLVED_MESSAGES
from app.core.naming.renamer import build_rename_plan, execute_rename_plan
from app.core.pipeline.card_processor import load_card_state_from_db, scan_for_pdfs
from app.gui.main_window_mixins._protocol import MainWindowProtocol
from app.models.card import CardResult, Confidence


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
        lower = filename.lower()
        for card in self._cards_by_hash.values():
            for p in card.file_paths:
                if p.name.lower() == lower:
                    return card
        return None

    def get_status_for_script(self: MainWindowProtocol) -> dict:
        """Return current app status as a dict."""
        return {
            "is_processing": self.is_processing,
            "is_analyzing": self.is_ai_running,
            "loaded_count": len(self._cards_by_hash),
            "current_model": get_ai_model(),
            "year": self._year_ctrl.GetValue().strip(),
        }

    def get_card_info_for_script(self: MainWindowProtocol, filename: str) -> CardResult | None:
        """Find a card by filename for scripting."""
        return self._find_card_by_filename(filename)

    def get_all_cards_for_script(self: MainWindowProtocol) -> list[CardResult]:
        """Return all loaded cards."""
        return list(self._cards_by_hash.values())

    def load_paths_for_script(self: MainWindowProtocol, paths: list[str]) -> int:
        """Load PDFs from file/folder paths. Returns count of new PDFs found."""
        path_objects = [Path(p) for p in paths]

        # Scan all paths for PDFs
        all_pdfs: list[Path] = []
        for path in path_objects:
            all_pdfs.extend(scan_for_pdfs(path))

        # Filter already loaded
        new_pdfs = [p for p in all_pdfs if p not in self._hash_by_path]

        if new_pdfs:
            self._pdf_files.update(new_pdfs)
            self._start_processing(new_pdfs)

        return len(new_pdfs)

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
                if result.old_path in self._hash_by_path:
                    file_hash = self._hash_by_path.pop(result.old_path)
                    self._hash_by_path[result.new_path] = file_hash
                if result.old_path in self._mtime_by_path:
                    self._mtime_by_path[result.new_path] = self._mtime_by_path.pop(result.old_path)

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

    def set_card_name_for_script(self: MainWindowProtocol, filename: str, name: str) -> bool:
        """Set or clear a manual name override."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return False

        if name:
            if card.confidence != Confidence.MANUAL:
                card.original_confidence = card.confidence
            card.confidence = Confidence.MANUAL
            card.method = "manual"
            card.family_name = name
            card.manual_override = name
            card.selected_candidate_id = None
            if card.file_hash:
                set_manual_name(card.file_hash, name, card.remove_family)
        else:
            card.manual_override = ""
            if card.file_hash:
                set_manual_name(card.file_hash, "", card.remove_family)
            load_card_state_from_db(card)

        self._review_panel.update_card(card.id, card)
        self._refresh_display()
        return True

    def select_candidate_for_script(self: MainWindowProtocol, filename: str, rank: int) -> bool:
        """Select a candidate by 1-based rank order."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return False

        if rank < 1 or rank > len(card.candidates):
            return False

        cand = card.candidates[rank - 1]
        card.family_name = cand.family_name
        card.manual_override = ""
        card.selected_candidate_id = cand.id
        card.method = cand.method

        try:
            card.confidence = Confidence(cand.confidence)
        except ValueError:
            card.confidence = Confidence.MEDIUM

        if card.file_hash:
            select_candidate(card.file_hash, cand.id, card.remove_family)

        self._review_panel.update_card(card.id, card)
        self._refresh_display()
        return True

    def set_remove_family_for_script(self: MainWindowProtocol, filename: str, value: bool) -> bool:
        """Toggle the Remove Family flag."""
        card = self._find_card_by_filename(filename)
        if card is None:
            return False

        card.remove_family = value
        if card.file_hash:
            update_remove_family(card.file_hash, value)

        self._review_panel.update_card(card.id, card)
        self._refresh_display()
        return True

    def analyze_for_script(self: MainWindowProtocol, filename: str | None) -> int:
        """Start AI analysis. Returns number of cards queued."""
        if not self._cards_by_hash:
            return 0

        if not get_api_key():
            return 0

        if filename:
            card = self._find_card_by_filename(filename)
            if card is None or card.error:
                return 0
            if not card.page_images and not card.preview_image:
                return 0
            cards = [card]
        else:
            cards = [c for c in self._cards_by_hash.values() if not c.error]

        if not cards:
            return 0

        self._start_ai_all(cards=cards, title="AI Analysis (Script)")
        return len(cards)

    def clear_ai_for_script(self: MainWindowProtocol, filename: str | None) -> int:
        """Clear AI results. Returns count of cards affected."""
        if filename:
            card = self._find_card_by_filename(filename)
            if card is None:
                return 0
            cards = [card]
        else:
            cards = list(self._cards_by_hash.values())

        if not cards:
            return 0

        file_hashes = [c.file_hash for c in cards if c.file_hash]
        changed = clear_ai_results(file_hashes)

        for card in cards:
            if card.file_hash:
                load_card_state_from_db(card)

        self._refresh_display()
        return changed

    def reload_for_script(self: MainWindowProtocol) -> bool:
        """Trigger manual reload. Returns True if changes were detected."""
        if not self._hash_by_path:
            return False

        old_count = len(self._cards_by_hash)
        old_hashes = set(self._cards_by_hash.keys())
        self._reload_cards(mtime_only=False)

        # Detect changes by comparing state
        new_hashes = set(self._cards_by_hash.keys())
        return old_hashes != new_hashes or old_count != len(self._cards_by_hash)

    def clear_all_for_script(self: MainWindowProtocol) -> bool:
        """Clear all loaded cards and reset UI."""
        self._clear_all()
        return True

    def quit_for_script(self: MainWindowProtocol) -> None:
        """Quit the application (AppleScript ``quit`` command)."""
        self._frame.Close()

    # ---- End Apple Events bridge methods ------------------------------------
