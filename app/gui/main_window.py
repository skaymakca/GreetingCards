"""wxPython Main Window for Greeting Cards application."""

import asyncio
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import wx
import wx.adv

logger = logging.getLogger(__name__)

from app.core.ai_batch import run_ai_batch_async
from app.core.card_processor import derive_folders, load_card_state_from_db, scan_for_pdfs, worker_result_to_card
from app.core.config import get_api_key
from app.core.constants import OCR_WORKERS
from app.core.database import (
    clear_ai_results,
    set_manual_name,
)
from app.core.pdf_worker import process_pdf_worker
from app.core.rename_executor import RESOLVED_MESSAGES, filter_completed_renames
from app.core.renamer import build_rename_plan, execute_rename_plan
from app.gui.components.drop_target import DropOverlay as _DropOverlay
from app.gui.components.drop_target import FileDropTarget
from app.gui.components.filter_sidebar import FilterSidebar
from app.gui.components.preview_panel import PreviewPanel
from app.gui.components.review_panel import ReviewPanelMasterDetail
from app.gui.components.toolbar import ToolbarManager
from app.gui.dialogs import CompletionDialog, ErrorListDialog, RenameConfirmDialog
from app.gui.dialogs.api_key import show_api_key_dialog
from app.gui.dialogs.settings import create_preferences_editor, get_commit_hash
from app.gui.styles import Color, Font, Layout
from app.gui.utils import plural as _plural
from app.models.card import CardResult, Confidence, RenameResult

# Alias for backward compatibility with tests that import from main_window
_RESOLVED_MESSAGES = RESOLVED_MESSAGES


# noinspection PyMethodMayBeStatic,PyUnusedLocal,PyTypeChecker
class MainWindow:
    """Main application window with toolbar and content panels."""

    def __init__(self) -> None:
        # Create frame
        self._frame = wx.Frame(None, title="Greeting Cards", size=(Layout.WINDOW_WIDTH, Layout.WINDOW_HEIGHT))
        self._frame.SetMinSize(Layout.MIN_FRAME_SIZE)

        # State - Content-based deduplication (multi-load architecture)
        self._next_card_id = 0  # Monotonically increasing ID counter
        self._cards_by_hash: dict[str, CardResult] = {}  # hash → Card (1:1)
        self._hash_by_path: dict[Path, str] = {}  # path → hash (many:1)
        self._mtime_by_path: dict[Path, float] = {}  # path → st_mtime (for fast pre-filter)
        self._pdf_files: list[Path] = []
        self._year = datetime.now().year - 1
        self._current_category_filters = ["all"]  # Current sidebar category filters
        self._current_folder_filters = ["all_folders"]  # Current sidebar folder filters
        self._ai_target_cards: list[CardResult] = []  # Cards for current AI batch
        self._processing_files: list[Path] = []  # Files currently being processed
        self._state_lock = threading.Lock()  # Protects _cards_by_hash, _hash_by_path, _next_card_id

        # Preferences editor (lazy-init)
        self._prefs_editor: wx.PreferencesEditor | None = None
        self._ai_batch_running = False
        self._last_reload_time: float = 0.0  # monotonic timestamp for reload cooldown

        # Debounce timer for name edits (fires _refresh_display after user stops typing)
        self._edit_debounce_timer = wx.Timer(self._frame)
        self._frame.Bind(wx.EVT_TIMER, self._on_edit_debounce_fire, self._edit_debounce_timer)

        # Toolbar/menu widget + ID attributes — set by ToolbarManager.build_*()
        self._toolbar: wx.ToolBar
        self._search_ctrl: wx.SearchCtrl
        self._year_ctrl: wx.TextCtrl
        self._browse_id: int
        self._reload_id: int
        self._ai_all_id: int
        self._rename_id: int
        self._clear_id: int
        self._reload_menu_id: wx.WindowIDRef
        self._ai_menu_id: wx.WindowIDRef
        self._clear_ai_menu_id: wx.WindowIDRef
        self._rename_menu_id: wx.WindowIDRef
        self._clear_menu_id: wx.WindowIDRef
        self._find_menu_id: wx.WindowIDRef
        self._select_none_id: wx.WindowIDRef
        self._remove_menu_id: wx.WindowIDRef

        # Build UI
        self._toolbar_mgr = ToolbarManager(self)
        self._toolbar_mgr.build_menu_bar()
        self._build_ui()
        self._setup_drop_target()
        self._setup_keyboard_shortcuts()

        # Dark mode detection + initial color refresh
        from app.gui import appearance

        Color.refresh()
        appearance.start_observer(self._on_appearance_changed)

        # Center and bind close/activate events
        self._frame.Centre()
        self._frame.Bind(wx.EVT_CLOSE, self._on_close)
        self._frame.Bind(wx.EVT_ACTIVATE, self._on_frame_activate)

    def _get_card_by_id(self, card_id: int) -> CardResult | None:
        """Get card by ID (searches through hash-based storage).

        Args:
            card_id: Card ID to find

        Returns:
            CardResult if found, None otherwise
        """
        for card in self._cards_by_hash.values():
            if card.id == card_id:
                return card
        return None

    def _on_select_all(self, event: wx.CommandEvent) -> None:
        """Handle Select All — route to text field if focused, else select all cards."""
        focus = self._frame.FindFocus()
        if isinstance(focus, wx.TextCtrl):
            focus.SelectAll()
        else:
            self._review_panel.select_all()

    def _show_preferences(self) -> None:
        """Show the native macOS Preferences editor."""
        if self._prefs_editor is None:
            self._prefs_editor = create_preferences_editor(
                on_db_reset=self._clear_all,
                is_ai_running=lambda: self._ai_batch_running,
            )
        self._prefs_editor.Show(self._frame)

    def _show_about(self) -> None:
        """Show the native macOS About dialog."""
        info = wx.adv.AboutDialogInfo()
        info.SetName("Greeting Cards")
        info.SetCopyright(f"(c) {datetime.now().year}")
        # Do not call SetIcon() — it forces the generic About box on macOS.
        # The native About panel automatically uses the app bundle icon
        # from Contents/Resources/icon.icns via CFBundleIconFile in Info.plist.
        # Only set the commit hash as the version — the native About panel
        # already shows CFBundleShortVersionString from Info.plist as the main version.
        info.SetDescription("Open-source licenses: Help > Licenses")
        commit = get_commit_hash()
        if commit:
            info.SetVersion(commit)
        wx.adv.AboutBox(info)

    def _build_ui(self) -> None:
        """Assemble main UI layout with toolbar and three-column layout."""
        # Main panel for content
        self._panel = wx.Panel(self._frame)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Toolbar (wx.ToolBar for proper tool semantics)
        self._toolbar_mgr.build_toolbar()
        main_sizer.Add(self._toolbar, 0, wx.EXPAND)

        # Three-column content splitter
        self._content_splitter = self._build_content_area()
        main_sizer.Add(self._content_splitter, 1, wx.EXPAND)

        # Drop overlay (shown when no cards loaded — covers entire content area)
        self._drop_overlay = _DropOverlay(self._panel)
        main_sizer.Add(self._drop_overlay, 1, wx.EXPAND)

        # Inline progress strip at the bottom (hidden by default)
        self._build_progress_strip()
        main_sizer.Add(self._progress_strip, 0, wx.EXPAND)

        # Initially show overlay, hide content
        self._content_splitter.Hide()

        self._panel.SetSizer(main_sizer)

    def _build_progress_strip(self) -> None:
        """Build inline progress strip (hidden by default)."""
        strip = wx.Panel(self._panel)

        outer = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)

        self._progress_label = wx.StaticText(strip, label="")
        self._progress_label.SetFont(Font.SMALL())
        self._progress_label.SetForegroundColour(Color.TEXT_PRIMARY)
        row.Add(self._progress_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)

        row.AddStretchSpacer()

        self._progress_gauge = wx.Gauge(strip, range=100, size=(200, -1))
        row.Add(self._progress_gauge, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._progress_count = wx.StaticText(strip, label="")
        self._progress_count.SetFont(Font.SMALL())
        self._progress_count.SetForegroundColour(Color.TEXT_SECONDARY)
        row.Add(self._progress_count, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)

        outer.Add(row, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)

        strip.SetSizer(outer)
        strip.Hide()
        self._progress_strip = strip

    def _show_progress_strip(self, total: int, title: str) -> None:
        """Show progress strip with given total and title."""
        self._progress_gauge.SetRange(total)
        self._progress_gauge.SetValue(0)
        self._progress_label.SetLabel(title)
        self._progress_count.SetLabel(f"0 / {total}")
        # Refresh colors for current appearance mode
        self._progress_label.SetForegroundColour(Color.TEXT_PRIMARY)
        self._progress_count.SetForegroundColour(Color.TEXT_SECONDARY)
        self._progress_strip.Show()
        self._panel.Layout()

    def _update_progress_strip(self, current: int, message: str) -> None:
        """Update progress strip gauge and labels."""
        if not self._progress_strip.IsShown():
            return
        self._progress_gauge.SetValue(current)
        self._progress_label.SetLabel(message)
        total = self._progress_gauge.GetRange()
        self._progress_count.SetLabel(f"{current} / {total}")

    def _hide_progress_strip(self) -> None:
        """Hide progress strip."""
        self._progress_strip.Hide()
        self._panel.Layout()

    def _enable_action_tools(
        self,
        *,
        reload: bool | None = None,
        ai: bool | None = None,
        rename: bool | None = None,
        clear: bool | None = None,
    ) -> None:
        """Enable or disable action toolbar tools. Pass None to leave unchanged."""
        self._toolbar_mgr.enable_action_tools(reload=reload, ai=ai, rename=rename, clear=clear)

    def _on_search_text(self, event: wx.CommandEvent) -> None:
        """Filter cards as user types in search field."""
        self._refresh_display()

    def _on_search_cancel(self, event: wx.CommandEvent) -> None:
        """Clear filter when cancel button clicked."""
        self._search_ctrl.ChangeValue("")
        self._refresh_display()

    def _on_category_filter_change(self, filter_keys: list[str]) -> None:
        """Handle sidebar category filter change.

        Args:
            filter_keys: List of selected category filters (e.g., ["high", "manual"])
        """
        self._current_category_filters = filter_keys
        self._refresh_display()

    def _on_folder_filter_change(self, filter_keys: list[str]) -> None:
        """Handle sidebar folder filter change.

        Args:
            filter_keys: List of selected folder filters (e.g., ["all_folders"] or ["/path/to/dir"])
        """
        self._current_folder_filters = filter_keys
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh sidebar counts and cards table using cross-filtered pipeline.

        Re-entrancy-free: sidebar count updates may auto-reset internal filter
        state (e.g. when all selected categories go to zero count). We sync
        MainWindow's filter state from sidebar after count updates, then
        recompute display. If display is still empty but search has results,
        auto-reset checkbox filters (keep search text).
        """
        search_cards = self._get_search_filtered_cards()

        # First pass: compute cross-filtered counts
        folder_filtered = self._apply_folder_filters(search_cards)
        category_filtered = self._apply_category_filters(search_cards)
        self._sidebar.update_category_counts(folder_filtered)
        self._sidebar.update_folder_counts(category_filtered)

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
            self._sidebar.update_category_counts(folder_filtered)
            self._sidebar.update_folder_counts(display_cards)

        self._review_panel.load_cards(display_cards, preserve_selection=not self._has_active_filters())

        # Toggle overlay vs content area based on whether any cards exist at all
        self._set_empty_state(not self._cards_by_hash)

    def _has_active_filters(self) -> bool:
        """Return True if any search or filter is narrowing the view."""
        if self._search_ctrl.GetValue().strip():
            return True
        if "all" not in self._current_category_filters:
            return True
        return "all_folders" not in self._current_folder_filters

    def _get_search_filtered_cards(self) -> list[CardResult]:
        """Get cards filtered by search query only."""
        cards = list(self._cards_by_hash.values())
        query = self._search_ctrl.GetValue().lower().strip()
        if query:
            cards = [c for c in cards if query in c.filename.lower() or query in c.family_name.lower()]
        return cards

    def _apply_folder_filters(self, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar folder filters to a card list."""
        if "all_folders" in self._current_folder_filters:
            return cards
        folder_set = set(self._current_folder_filters)
        return [c for c in cards if any(str(p.parent) in folder_set for p in c.file_paths)]

    def _apply_category_filters(self, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar category filters to a card list."""
        if "all" not in self._current_category_filters:
            filtered: list[CardResult] = []
            for filter_key in self._current_category_filters:
                if filter_key == "manual":
                    filtered.extend(c for c in cards if c.confidence == Confidence.MANUAL)
                elif filter_key == "high":
                    filtered.extend(c for c in cards if c.confidence == Confidence.HIGH)
                elif filter_key == "needs_review":
                    filtered.extend(c for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW))
                elif filter_key == "errors":
                    filtered.extend(c for c in cards if c.error or c.confidence == Confidence.NONE)
            cards = list({c.id: c for c in filtered}.values())
        return sorted(cards, key=lambda c: c.filename.lower())

    def _build_content_area(self) -> wx.SplitterWindow:
        """Build three-column Mail.app style layout: [sidebar | review | preview]."""
        # Main splitter: [sidebar | content]
        main_splitter = wx.SplitterWindow(self._panel, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)

        # Left: Filter sidebar
        self._sidebar = FilterSidebar(
            main_splitter,
            on_category_filter=self._on_category_filter_change,
            on_folder_filter=self._on_folder_filter_change,
        )

        # Right: Nested splitter for [review | preview]
        content_splitter = wx.SplitterWindow(main_splitter, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)

        # Review panel with callbacks
        self._review_panel = ReviewPanelMasterDetail(
            content_splitter,
            on_select=self._on_card_select,
            on_ai_request=self._on_ai_request,
            on_name_change=self._on_name_change,
            on_card_edited=self._on_card_edited,
            on_remove=self._on_remove_card,
            on_ai_analyze=lambda cards: self._start_ai_all(cards=cards),
        )

        # Preview panel
        self._preview_panel = PreviewPanel(content_splitter)

        # Split nested content splitter vertically
        content_splitter.SplitVertically(self._review_panel, self._preview_panel)
        content_splitter.SetSashGravity(Layout.CONTENT_SASH_GRAVITY)  # Cards panel gets slightly more space
        content_splitter.SetMinimumPaneSize(Layout.CONTENT_MIN_PANE)
        self._inner_splitter = content_splitter

        # Split main splitter vertically (sidebar | content)
        main_splitter.SplitVertically(self._sidebar, content_splitter)
        main_splitter.SetMinimumPaneSize(Layout.SIDEBAR_WIDTH)

        # Set initial sash positions after layout
        wx.CallAfter(lambda: main_splitter.SetSashPosition(Layout.SIDEBAR_WIDTH))

        return main_splitter

    def _apply_content_sash_position(self) -> None:
        """Set the content splitter sash to split review/preview equally."""

        def _apply() -> None:
            w = self._inner_splitter.GetSize().GetWidth()
            if w > 0:
                self._inner_splitter.SetSashPosition(int(w * Layout.CONTENT_SASH_GRAVITY))

        wx.CallAfter(_apply)

    def _set_empty_state(self, is_empty: bool) -> None:
        """Toggle between drop overlay (empty) and content splitter (has cards)."""
        self._drop_overlay.Show(is_empty)
        self._content_splitter.Show(not is_empty)
        self._panel.Layout()
        if not is_empty:
            # Re-apply sash position after showing — hiding resets it
            self._apply_content_sash_position()

    def _setup_drop_target(self) -> None:
        """Enable drag-and-drop on the frame."""
        drop_target = FileDropTarget(
            on_drop=self._on_drop,
            on_drag_over=self._on_drag_over,
            on_drag_leave=self._on_drag_leave,
        )
        self._frame.SetDropTarget(drop_target)

    def _on_drag_over(self) -> None:
        """Show drag highlight on overlay or review panel."""
        if self._drop_overlay.IsShown():
            self._drop_overlay.set_drag_active(True)
        else:
            self._review_panel.set_drag_highlight(True)

    def _on_drag_leave(self) -> None:
        """Hide drag highlight."""
        self._drop_overlay.set_drag_active(False)
        self._review_panel.set_drag_highlight(False)

    def _on_drop(self, paths: list[Path]) -> None:
        """Handle dropped files and/or folders (multi-select).

        Args:
            paths: List of dropped paths (files or folders)
        """
        # Clear drag highlights
        self._on_drag_leave()
        # Add to existing cards (don't replace)
        self._load_paths(paths, auto_process=True)

    def _setup_keyboard_shortcuts(self) -> None:
        """Set up keyboard accelerators."""
        # Menu shortcuts (Cmd+O, Cmd+W, Cmd+Q, Cmd+F, Cmd+A, Cmd+Shift+A) handled by menu bar

        # Navigation shortcuts
        self._frame.Bind(wx.EVT_CHAR_HOOK, self._on_key_press)

    def _on_key_press(self, event: wx.KeyEvent) -> None:
        """Handle key presses for navigation."""
        key = event.GetKeyCode()
        focus = self._frame.FindFocus()

        # Handle Escape key - clear search if search has focus
        if key == wx.WXK_ESCAPE:
            if focus == self._search_ctrl:
                self._search_ctrl.SetValue("")
                self._frame.SetFocus()
            else:
                self._frame.SetFocus()  # Defocus text entry
            return

        # Skip if focus is in text entry (except search handled above)
        if isinstance(focus, (wx.TextCtrl, wx.ComboBox, wx.Choice)):
            event.Skip()
            return

        if key == wx.WXK_UP:
            self._review_panel.select_prev_card()
        elif key == wx.WXK_DOWN:
            self._review_panel.select_next_card()
        elif key == wx.WXK_LEFT:
            self._preview_panel.prev_page()
        elif key == wx.WXK_RIGHT:
            self._preview_panel.next_page()
        else:
            event.Skip()

    def _add_files_folders(self) -> None:
        """Add PDF files or folders (unified picker - multi-load architecture)."""
        from app.gui.utils import open_files_and_folders

        paths = open_files_and_folders("Add PDF Files or Folders", ["pdf"])
        if paths:
            self._load_paths(paths, auto_process=True)

    def _load_paths(self, paths: list[Path], auto_process: bool = True) -> None:
        """Load PDFs from multiple files/folders (accumulating, not replacing).

        Args:
            paths: List of file or folder paths
            auto_process: Whether to start processing immediately
        """
        # 1. Scan all paths for PDFs (recursive for folders)
        all_pdfs = []
        for path in paths:
            all_pdfs.extend(scan_for_pdfs(path))

        # 2. Filter out already-loaded paths (same path won't load twice)
        new_pdfs = []
        skipped_pdfs = []

        for pdf_path in all_pdfs:
            if pdf_path in self._hash_by_path:
                # This exact path is already loaded (regardless of content)
                skipped_pdfs.append(pdf_path)
            else:
                # New path - will process and check hash later
                new_pdfs.append(pdf_path)

        # 3. Update state (accumulate, don't replace)
        self._pdf_files.extend(new_pdfs)

        # 4. Show feedback
        if new_pdfs or skipped_pdfs:
            msg = f"Found {_plural(len(new_pdfs), 'new PDF')}"
            if skipped_pdfs:
                msg += f"\nSkipped {len(skipped_pdfs)} already loaded"
            self._show_info_message(msg, wx.ICON_INFORMATION)
        elif not all_pdfs:
            self._show_info_message("No PDF files found", wx.ICON_WARNING, duration_ms=0)

        # 5. Process new PDFs
        if new_pdfs and auto_process:
            self._start_processing(new_pdfs)

    def _clear_all(self) -> None:
        """Clear all loaded cards (from all sources) and reset UI."""
        # Clear all state (multi-load architecture)
        self._cards_by_hash.clear()
        self._hash_by_path.clear()
        self._mtime_by_path.clear()
        self._pdf_files = []
        self._next_card_id = 0

        self._review_panel.load_cards([])
        self._preview_panel.clear()
        self._sidebar.update_category_counts([])
        self._sidebar.update_folders([])
        self._set_empty_state(True)

        # Disable toolbar tools
        self._enable_action_tools(reload=False, ai=False, rename=False, clear=False)

        # Clear search filter
        self._search_ctrl.SetValue("")

        # Reset sidebar filters
        self._current_category_filters = ["all"]
        self._current_folder_filters = ["all_folders"]
        self._sidebar.set_category_filters(["all"])

        # Show confirmation
        self._show_info_message("All cards cleared", wx.ICON_INFORMATION)

    # noinspection DuplicatedCode
    def _reload_cards(self, *, mtime_only: bool = False) -> None:
        """Re-check all loaded paths for modifications and deletions.

        Diff-based reload: iterates over currently loaded paths only.
        Does not scan folders for new files.

        Args:
            mtime_only: When True (auto-reload path), use mtime as a fast
                pre-filter — files whose mtime hasn't changed are skipped
                entirely without computing a hash. Files with changed mtime
                still fall through to hash comparison.
                When False (manual reload), every file is hash-checked.
        """
        from app.core.database import compute_file_hash

        if not self._hash_by_path:
            return

        # Update cooldown timestamp (prevents rapid re-triggers from EVT_ACTIVATE)
        self._last_reload_time = time.monotonic()

        # Snapshot current paths (dict may mutate during iteration)
        loaded_paths = set(self._hash_by_path.keys())
        deleted_paths: list[Path] = []
        needs_processing: list[Path] = []

        for path in loaded_paths:
            if not path.exists():
                # File was deleted externally
                old_hash = self._hash_by_path.pop(path, None)
                self._mtime_by_path.pop(path, None)
                if path in self._pdf_files:
                    self._pdf_files.remove(path)
                if old_hash and old_hash in self._cards_by_hash:
                    card = self._cards_by_hash[old_hash]
                    if path in card.file_paths:
                        card.file_paths.remove(path)
                    if not card.file_paths:
                        del self._cards_by_hash[old_hash]
                deleted_paths.append(path)
            else:
                # mtime pre-filter: skip files whose mtime hasn't changed
                if mtime_only:
                    try:
                        current_mtime = path.stat().st_mtime
                    except OSError:
                        continue
                    if current_mtime == self._mtime_by_path.get(path):
                        continue  # mtime unchanged → skip hash check

                # File exists — check if content changed
                old_hash = self._hash_by_path[path]
                try:
                    new_hash = compute_file_hash(path)
                except OSError:
                    continue  # Can't read file, skip
                if new_hash != old_hash:
                    # Content changed — remove from old card
                    self._hash_by_path.pop(path, None)
                    self._mtime_by_path.pop(path, None)
                    if path in self._pdf_files:
                        self._pdf_files.remove(path)
                    if old_hash in self._cards_by_hash:
                        card = self._cards_by_hash[old_hash]
                        if path in card.file_paths:
                            card.file_paths.remove(path)
                        if not card.file_paths:
                            del self._cards_by_hash[old_hash]
                    needs_processing.append(path)

        if needs_processing:
            # Re-add to _pdf_files and process (dedup handled by _process_cards)
            self._pdf_files.extend(needs_processing)
            self._start_processing(needs_processing)
            n_del = len(deleted_paths)
            n_mod = len(needs_processing)
            parts = []
            if n_del:
                parts.append(f"{_plural(n_del, 'file')} removed")
            if n_mod:
                parts.append(f"{_plural(n_mod, 'file')} reprocessing")
            self._show_info_message("Reload: " + ", ".join(parts), wx.ICON_INFORMATION)
        elif deleted_paths:
            # Only deletions — update UI
            self._sidebar.update_folders(derive_folders(self._cards_by_hash.values()))
            self._current_folder_filters = self._sidebar.get_selected_folder_filters()
            self._refresh_display()
            if not self._cards_by_hash:
                self._enable_action_tools(reload=False, ai=False, rename=False, clear=False)
            self._show_info_message(
                f"Reload: {_plural(len(deleted_paths), 'file')} removed",
                wx.ICON_INFORMATION,
            )
        else:
            self._show_info_message("All files up to date", wx.ICON_INFORMATION)

    def _on_clear_ai_results(self, event: wx.CommandEvent) -> None:
        """Clear AI results for selected or visible cards."""
        if not self._cards_by_hash:
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

        file_hashes = [card.file_hash for card in cards if card.file_hash]
        changed = clear_ai_results(file_hashes)

        # Reload card state from DB
        for card in cards:
            if card.file_hash:
                load_card_state_from_db(card)

        self._refresh_display()
        self._show_info_message(
            f"AI results cleared for {n} card(s). {changed} reverted to OCR names.", wx.ICON_INFORMATION
        )

    def _start_processing(self, files: list[Path] | None = None) -> None:
        """Start processing PDFs in background.

        Args:
            files: Specific files to process. If None, processes self._pdf_files.
        """
        files_to_process = files or self._pdf_files
        if not files_to_process:
            return

        # Snapshot the file list for the background thread
        self._processing_files = list(files_to_process)

        # Show busy cursor
        wx.BeginBusyCursor()

        # Disable toolbar tools
        self._enable_action_tools(reload=False, ai=False, rename=False)

        # Don't clear existing cards (multi-load architecture - accumulate!)
        # Note: Card deduplication happens in _process_cards during processing

        # Show progress strip
        total = len(self._processing_files)
        self._show_progress_strip(total, "Processing Cards...")

        # Start background thread
        thread = threading.Thread(target=self._process_cards, daemon=True)
        thread.start()

    def _process_cards(self) -> None:
        """Process PDFs using ProcessPoolExecutor (runs in background thread)."""
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed

        # Set spawn method for PyInstaller
        try:
            multiprocessing.set_start_method("spawn", force=True)
        except RuntimeError as exc:
            if "context has already been set" not in str(exc):
                raise

        total = len(self._processing_files)
        pdf_paths_str = [str(p) for p in self._processing_files]
        completed = 0

        with ProcessPoolExecutor(max_workers=min(total, OCR_WORKERS)) as executor:
            futures = {executor.submit(process_pdf_worker, path_str): path_str for path_str in pdf_paths_str}
            for future in as_completed(futures):
                worker_result = future.result()
                pdf_path = Path(worker_result.pdf_path)
                file_hash = worker_result.file_hash

                # Content-based deduplication: check if we already have this content
                with self._state_lock:
                    if file_hash and file_hash in self._cards_by_hash:
                        # Duplicate content - add path to existing card
                        existing_card = self._cards_by_hash[file_hash]
                        if pdf_path not in existing_card.file_paths:
                            existing_card.file_paths.append(pdf_path)
                        card = existing_card
                    else:
                        # New content - create new card
                        card_id = self._next_card_id
                        self._next_card_id += 1

                        card = worker_result_to_card(worker_result, card_id)
                        if file_hash is not None:
                            self._cards_by_hash[file_hash] = card

                    # Always update path → hash mapping
                    if file_hash is not None:
                        self._hash_by_path[pdf_path] = file_hash
                        try:
                            self._mtime_by_path[pdf_path] = pdf_path.stat().st_mtime
                        except OSError:
                            pass  # File vanished; reload will re-check

                # Update UI (thread-safe with wx.CallAfter)
                completed += 1
                wx.CallAfter(self._update_processing_progress, completed, total, card.filename)

        wx.CallAfter(self._processing_complete)

    def _update_processing_progress(self, current: int, total: int, name: str) -> None:
        """Update progress strip from background thread."""
        self._update_progress_strip(current, f"Processing: {name}")

    def _processing_complete(self) -> None:
        """Called when processing finishes."""
        # End busy cursor
        if wx.IsBusy():
            wx.EndBusyCursor()

        self._hide_progress_strip()

        # Update folder section FIRST (creates checkboxes before _refresh_display populates counts)
        self._sidebar.update_folders(derive_folders(self._cards_by_hash.values()))
        # Sync main window state — update_folders resets sidebar to "all_folders"
        # but doesn't fire callback, so we must sync manually
        self._current_folder_filters = self._sidebar.get_selected_folder_filters()

        # Now refresh display (folder checkboxes exist, counts will populate)
        self._refresh_display()

        # Enable toolbar tools
        self._enable_action_tools(reload=True, ai=True, rename=True, clear=True)

        # Show success message
        count = len(self._cards_by_hash)
        self._show_info_message(
            f"Processing complete\n{_plural(count, 'card')} loaded",
            wx.ICON_INFORMATION,
        )

    def _on_card_select(self, card_id: int | None) -> None:
        """Handle card selection - update preview panel."""
        if card_id is None:
            self._preview_panel.clear()
            return

        card = self._get_card_by_id(card_id)
        if not card:
            return

        if card.error:
            self._preview_panel.show_error(card.error, card.filename)
        elif card.page_images:
            self._preview_panel.show_images(card.page_images, card.filename)
        elif card.preview_image:
            self._preview_panel.show_images([card.preview_image], card.filename)
        else:
            self._preview_panel.clear()

    def _on_name_change(self, card_id: int, new_name: str) -> None:
        """Handle manual name edit in review panel."""
        card = self._get_card_by_id(card_id)
        if not card:
            return

        # Update card object
        if new_name:
            # Save original confidence before marking as manual
            if card.confidence != Confidence.MANUAL:
                card.original_confidence = card.confidence
            card.confidence = Confidence.MANUAL
            card.method = "manual"
            card.family_name = new_name
            card.manual_override = new_name
            card.selected_candidate_id = None

            # Save to database
            if card.file_hash:
                set_manual_name(card.file_hash, new_name, card.remove_family)
        else:
            # User cleared the name — revert to pre-manual state
            card.manual_override = ""

            # Clear manual name in database
            if card.file_hash:
                set_manual_name(card.file_hash, "", card.remove_family)

            # Reload state from DB to get the best candidate name
            load_card_state_from_db(card)

        # Update review panel
        self._review_panel.update_card(card_id, card)

        # Debounce: restart 1-second timer on each keystroke
        self._edit_debounce_timer.Stop()
        self._edit_debounce_timer.StartOnce(Layout.DEBOUNCE_MS)

    def _on_card_edited(self, card_id: int) -> None:
        """Handle discrete card edits (e.g. candidate selection) that change confidence."""
        self._refresh_display()

    def _on_remove_card(self, file_hash: str) -> None:
        """Remove a card from the in-memory table (non-destructive — does not delete files).

        Args:
            file_hash: The content hash of the card to remove
        """
        card = self._cards_by_hash.get(file_hash)
        if not card:
            return

        # Remove all path → hash mappings for this card
        for path in card.file_paths:
            self._hash_by_path.pop(path, None)
            self._mtime_by_path.pop(path, None)
            if path in self._pdf_files:
                self._pdf_files.remove(path)

        # Remove the card itself
        del self._cards_by_hash[file_hash]

        # Refresh display (handles filter counts, list reload, empty state)
        self._refresh_display()

    def _on_remove_menu(self, event: wx.CommandEvent) -> None:
        """Handle Edit > Remove — remove all selected cards."""
        for card_id in list(self._review_panel.selected_card_ids):
            card = self._get_card_by_id(card_id)
            if card and card.file_hash:
                self._on_remove_card(card.file_hash)

    def _on_update_remove_menu(self, event: wx.UpdateUIEvent) -> None:
        """Enable Remove menu item only when cards are selected."""
        event.Enable(bool(self._review_panel.selected_card_ids))

    def _on_edit_debounce_fire(self, event: wx.TimerEvent) -> None:
        """Fire after user stops typing for 1 second — refresh filters."""
        self._refresh_display()

    def _ensure_api_key(self) -> bool:
        """Check for an API key; prompt the user if missing. Returns True if a key is available."""
        if get_api_key():
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
            self._sidebar.dismiss_notification()
            return True

        return False

    def _get_target_cards(self) -> tuple[list[CardResult], str]:
        """Return (cards, scope) based on selection state.

        If 2+ cards are selected, returns those cards with scope "selected".
        Otherwise, returns all visible (filtered) cards with scope "visible".
        """
        selected_ids = self._review_panel.selected_card_ids
        if len(selected_ids) >= 2:
            cards = self._review_panel.get_cards_by_ids(selected_ids)
            return cards, "selected"
        return self._review_panel.get_cards(), "visible"

    def _on_ai_request(self, card_id: int) -> None:
        """Handle AI button click for single card — delegates to batch path."""
        if self._ai_batch_running:
            return
        card = self._get_card_by_id(card_id)
        if not card or card.error:
            return

        if not card.page_images and not card.preview_image:
            wx.MessageBox(
                "No preview image available for AI analysis.", "No Image", wx.OK | wx.ICON_WARNING, self._frame
            )
            return

        if not self._ensure_api_key():
            return

        # Disable AI button before delegating (after API key check so
        # cancelling the key dialog doesn't leave the button stuck disabled)
        self._review_panel.set_ai_button_state(card_id, "disabled")

        self._start_ai_all(cards=[card], title="AI Analysis")

    def _start_ai_all(self, cards: list[CardResult] | None = None, title: str | None = None) -> None:
        """Start AI analysis for given cards, selected cards, or all visible cards.

        Args:
            cards: Explicit card list (e.g. single card from detail button).
                   If None, determines scope from selection state.
            title: Progress dialog title. If None, auto-generated from scope.
        """
        if not self._cards_by_hash:
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

    def _run_ai_all(self) -> None:
        """Run async AI batch processing in background thread."""
        try:
            asyncio.run(
                run_ai_batch_async(
                    self._ai_target_cards,
                    on_progress=lambda c, t, f, i, card: wx.CallAfter(self._update_ai_all_progress, c, t, f, i, card),
                    on_complete=lambda errors, aborted: wx.CallAfter(self._ai_all_complete, errors, aborted),
                )
            )
        except Exception as e:
            error_msg = str(e)
            logger.error("AI batch processing failed: %s", error_msg)
            wx.CallAfter(self._ai_all_complete, [("Batch", error_msg)])

    def _update_ai_all_progress(
        self, completed: int, total: int, filename: str, card_id: int, card: CardResult | None
    ) -> None:
        """Update progress during batch AI processing."""
        self._update_progress_strip(completed, f"AI analyzing: {filename}")

        if card is not None:
            self._review_panel.update_card(card_id, card)

    def _ai_all_complete(self, errors: list[tuple[str, str]], auth_aborted: bool = False) -> None:
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
            count = len(self._ai_target_cards) or len(self._cards_by_hash)
            self._show_info_message(f"Analysis complete\n{_plural(count, 'card')} analyzed", wx.ICON_INFORMATION)

    def _start_rename(self) -> None:
        """Start rename workflow."""
        cards = self._review_panel.get_cards()
        year_str = self._year_ctrl.GetValue().strip()

        if not year_str or not year_str.isdigit() or len(year_str) != 4:
            wx.MessageBox("Please enter a valid 4-digit year.", "Invalid Year", wx.OK | wx.ICON_WARNING, self._frame)
            return

        # Build rename plan
        plan = build_rename_plan(cards, year_str)

        # Show confirmation dialog
        dialog = RenameConfirmDialog(self._frame, plan)
        if dialog.ShowModal() == wx.ID_OK:
            # Execute rename
            results = execute_rename_plan(plan)

            # Update _hash_by_path and _mtime_by_path mappings for renamed files
            for result in results:
                if result.success and result.message in _RESOLVED_MESSAGES:
                    if result.old_path in self._hash_by_path:
                        file_hash = self._hash_by_path.pop(result.old_path)
                        self._hash_by_path[result.new_path] = file_hash
                    if result.old_path in self._mtime_by_path:
                        self._mtime_by_path[result.new_path] = self._mtime_by_path.pop(result.old_path)

            # Show completion
            errors = sum(1 for r in results if not r.success)
            title = "Rename Complete" if not errors else "Rename Complete (with errors)"
            completion = CompletionDialog(self._frame, title, results)
            completion.ShowModal()
            completion.Destroy()

            # Remove successfully processed paths from cards
            self._remove_completed_results(results)

        dialog.Destroy()

    # noinspection DuplicatedCode
    def _remove_completed_results(self, results: list[RenameResult]) -> None:
        """Remove successfully renamed/skip_same paths from cards; drop empty cards.

        Paths with message "Renamed" or "Already named correctly" are considered
        resolved. Paths that failed or had no name are kept for the user to address.
        """
        # Collect paths to remove (use new_path — that's where the file is now)
        paths_to_remove = filter_completed_renames(results)

        if not paths_to_remove:
            return

        # Remove paths from cards and tracking dicts
        for path in paths_to_remove:
            file_hash = self._hash_by_path.pop(path, None)
            self._mtime_by_path.pop(path, None)
            if path in self._pdf_files:
                self._pdf_files.remove(path)
            if file_hash and file_hash in self._cards_by_hash:
                card = self._cards_by_hash[file_hash]
                if path in card.file_paths:
                    card.file_paths.remove(path)
                # Remove card if it has no remaining paths
                if not card.file_paths:
                    del self._cards_by_hash[file_hash]

        # Rebuild folder list and refresh display
        self._sidebar.update_folders(derive_folders(self._cards_by_hash.values()))
        self._current_folder_filters = self._sidebar.get_selected_folder_filters()
        self._refresh_display()

        # Disable toolbar tools if no cards remain
        if not self._cards_by_hash:
            self._enable_action_tools(reload=False, ai=False, rename=False, clear=False)
            self._search_ctrl.SetValue("")

    def _show_info_message(
        self, message: str, icon: int = wx.ICON_INFORMATION, duration_ms: int = Layout.INFO_DISMISS_MS
    ) -> None:
        """Show notification in sidebar bottom.

        Args:
            message: Message to display
            icon: Icon to show (wx.ICON_INFORMATION, wx.ICON_WARNING, wx.ICON_ERROR)
            duration_ms: Time in milliseconds before auto-dismiss (0 = no auto-dismiss)
        """
        self._sidebar.show_notification(message, icon, duration_ms)

    def _on_appearance_changed(self) -> None:
        """Handle macOS dark/light mode switch."""
        from app.gui import icons
        from app.gui.appearance import is_dark_mode

        mode = "Dark" if is_dark_mode() else "Light"
        logger.info("Appearance changed to %s mode", mode)

        # Refresh color palette and icon cache
        Color.refresh()
        icons.clear_cache()

        # Update toolbar icons in-place
        self._refresh_toolbar_icons()

        # Re-apply colors on long-lived panels
        self._sidebar.refresh_colors()
        self._preview_panel.refresh_colors()
        self._review_panel.refresh_colors()
        self._progress_label.SetForegroundColour(Color.TEXT_PRIMARY)
        self._progress_count.SetForegroundColour(Color.TEXT_SECONDARY)
        self._progress_gauge.Refresh()

        # Repaint all windows; call refresh_colors() on those that support it
        # noinspection PyArgumentList
        for window in wx.GetTopLevelWindows():
            if hasattr(window, "refresh_colors"):
                window.refresh_colors()
            window.Refresh()
            window.Update()

    def _refresh_toolbar_icons(self) -> None:
        """Re-render toolbar icons for current appearance."""
        self._toolbar_mgr.refresh_icons()

    # --- End dark mode ---

    _RELOAD_COOLDOWN = 2.0  # seconds between auto-reloads

    def _on_frame_activate(self, event: wx.ActivateEvent) -> None:
        """Auto-reload cards when the app window is re-activated."""
        event.Skip()
        if not event.GetActive():
            return
        if not self._hash_by_path:
            return
        # Skip if processing is in progress (reload tool is disabled)
        if not self._toolbar.GetToolEnabled(self._reload_id):
            return
        now = time.monotonic()
        if now - self._last_reload_time < self._RELOAD_COOLDOWN:
            return
        self._last_reload_time = now
        self._reload_cards(mtime_only=True)

    def _on_close_window(self, _event: wx.CommandEvent) -> None:
        """Handle Cmd+W: close the macOS key window (not always the main frame).

        Uses AppKit to find the actual frontmost window so that Cmd+W closes
        the preferences editor, about panel, or any other non-main window
        when it is focused.
        """
        from AppKit import NSApplication  # type: ignore[import-untyped]

        key_win = NSApplication.sharedApplication().keyWindow()
        if key_win is not None:
            key_win.performClose_(None)
        else:
            self._frame.Close()

    def _on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close event."""
        from app.gui import appearance

        appearance.stop_observer()

        self._edit_debounce_timer.Stop()
        if self._prefs_editor is not None:
            self._prefs_editor.Dismiss()
        self._frame.Destroy()

    def run(self) -> None:
        """Start the application event loop."""
        self._frame.Show()
