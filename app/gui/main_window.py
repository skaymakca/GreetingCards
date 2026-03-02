"""wxPython Main Window for Greeting Cards application."""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import wx
import wx.adv

logger = logging.getLogger(__name__)

from app.core.card_service import CardService
from app.core.card_store import CardStore
from app.core.constants import RELOAD_COOLDOWN
from app.core.platform import get_commit_hash
from app.core.processing_service import ProcessingService
from app.core.rename_service import RenameService
from app.gui.components.drop_target import DropOverlay as _DropOverlay
from app.gui.components.drop_target import FileDropTarget
from app.gui.components.filter_sidebar import FilterSidebar
from app.gui.components.preview_panel import PreviewPanel
from app.gui.components.review_panel import ReviewPanelMasterDetail
from app.gui.components.toolbar import ToolbarManager
from app.gui.dialogs import CompletionDialog, RenameConfirmDialog
from app.gui.dialogs.settings import create_preferences_editor
from app.gui.main_window_mixins import AIMixin, AppleEventsMixin, FilterMixin, SelectionMixin
from app.gui.styles import Color, Font, Layout
from app.gui.utils import plural as _plural
from app.models.card import CardResult, RenameResult


# noinspection PyMethodMayBeStatic,PyUnusedLocal,PyTypeChecker,PyUnresolvedReferences,PyBroadException
class MainWindow(FilterMixin, SelectionMixin, AppleEventsMixin, AIMixin):
    """Main application window with toolbar and content panels."""

    def __init__(self) -> None:
        # Create frame
        self._frame = wx.Frame(None, title="Greeting Cards", size=(Layout.WINDOW_WIDTH, Layout.WINDOW_HEIGHT))
        self._frame.SetMinSize(Layout.MIN_FRAME_SIZE)

        # State - Content-based deduplication (multi-load architecture)
        self._card_store = CardStore()
        self._card_service = CardService(self._card_store)
        self._rename_service = RenameService(self._card_store)
        self._processing_service = ProcessingService(self._card_store)
        self._current_category_filters = ["all"]  # Current sidebar category filters
        self._current_folder_filters = ["all_folders"]  # Current sidebar folder filters
        self._ai_target_cards: list[CardResult] = []  # Cards for current AI batch
        self._processing_files: list[Path] = []  # Files currently being processed
        self._is_processing_busy: bool = False  # True while PDF processing thread runs

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
        """Get card by ID. O(1) lookup via CardStore."""
        return self._card_store.get_by_id(card_id)

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
                on_db_reset=self._on_reset_database,
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
            on_checkbox_toggle=self._on_checkbox_toggle,
            on_candidate_select=self._on_candidate_select,
            invalid_chars=RenameService.INVALID_FILENAME_CHARS,
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

    def _load_paths(self, paths: list[Path], auto_process: bool = True) -> int:
        """Load PDFs from multiple files/folders (accumulating, not replacing).

        Args:
            paths: List of file or folder paths
            auto_process: Whether to start processing immediately

        Returns:
            Count of new PDFs found.
        """
        # 1. Scan all paths for PDFs (recursive for folders)
        all_pdfs: list[Path] = []
        for path in paths:
            all_pdfs.extend(self._processing_service.scan_for_pdfs(path))

        # 2. Filter + register via CardStore
        new_pdfs, skipped_pdfs = self._card_store.filter_and_register(all_pdfs)

        # 3. Show feedback
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

        return len(new_pdfs)

    def _clear_all(self) -> None:
        """Clear all loaded cards (from all sources) and reset UI."""
        self._card_store.clear()

        self._review_panel.load_cards([])
        self._preview_panel.clear()
        self._sidebar.update_category_counts({})
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

    def _on_reset_database(self) -> None:
        """Handle database reset from preferences — reset DB then clear UI."""
        self._card_service.reset()
        self._clear_all()

    def _get_year(self) -> str:
        """Return the year value from the year control, stripped."""
        return self._year_ctrl.GetValue().strip()

    def _refresh_folders(self) -> None:
        """Update sidebar folders, sync filter state, and refresh display."""
        self._sidebar.update_folders(self._card_store.derive_folders())
        self._current_folder_filters = self._sidebar.get_selected_folder_filters()
        self._refresh_display()

    def _unlink_path(self, path: Path) -> None:
        """Remove a path from all tracking dicts and its associated card."""
        self._card_store.unlink_path(path)

    def _reload_cards(self, *, mtime_only: bool = False) -> bool:
        """Re-check all loaded paths for modifications and deletions.

        Diff-based reload: iterates over currently loaded paths only.
        Does not scan folders for new files.

        Args:
            mtime_only: When True (auto-reload path), use mtime as a fast
                pre-filter — files whose mtime hasn't changed are skipped
                entirely without computing a hash. Files with changed mtime
                still fall through to hash comparison.
                When False (manual reload), every file is hash-checked.

        Returns:
            True if anything changed (files modified or deleted).
        """
        if not self._card_store.has_paths:
            return False

        # Update cooldown timestamp (prevents rapid re-triggers from EVT_ACTIVATE)
        self._last_reload_time = time.monotonic()

        deleted_paths, needs_processing = self._card_store.compute_reload_diff(mtime_only=mtime_only)

        if needs_processing:
            # Re-add to pdf_files and process (dedup handled by _process_cards)
            self._card_store.register_new_pdfs(needs_processing)
            self._start_processing(needs_processing)
            n_del = len(deleted_paths)
            n_mod = len(needs_processing)
            parts = []
            if n_del:
                parts.append(f"{_plural(n_del, 'file')} removed")
            if n_mod:
                parts.append(f"{_plural(n_mod, 'file')} reprocessing")
            self._show_info_message("Reload: " + ", ".join(parts), wx.ICON_INFORMATION)
            return True
        elif deleted_paths:
            # Only deletions — update UI
            self._refresh_folders()
            if self._card_store.is_empty:
                self._enable_action_tools(reload=False, ai=False, rename=False, clear=False)
            self._show_info_message(
                f"Reload: {_plural(len(deleted_paths), 'file')} removed",
                wx.ICON_INFORMATION,
            )
            return True
        else:
            self._show_info_message("All files up to date", wx.ICON_INFORMATION)
            return False

    def _start_processing(self, files: list[Path] | None = None) -> None:
        """Start processing PDFs in background.

        Args:
            files: Specific files to process. If None, processes all known PDF paths.
        """
        files_to_process = files or list(self._card_store.get_all_paths())
        if not files_to_process:
            return

        # Snapshot the file list for the background thread
        self._processing_files = list(files_to_process)
        self._is_processing_busy = True

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
        """Process PDFs using ProcessingService (runs in background thread)."""

        def _on_progress(completed: int, total: int, filename: str) -> None:
            wx.CallAfter(self._update_processing_progress, completed, total, filename)

        def _on_complete() -> None:
            wx.CallAfter(self._processing_complete)

        self._processing_service.process_files(
            self._processing_files,
            on_progress=_on_progress,
            on_complete=_on_complete,
        )

    def _update_processing_progress(self, current: int, total: int, name: str) -> None:
        """Update progress strip from background thread."""
        self._update_progress_strip(current, f"Processing: {name}")

    def _processing_complete(self) -> None:
        """Called when processing finishes."""
        self._is_processing_busy = False

        # End busy cursor
        if wx.IsBusy():
            wx.EndBusyCursor()

        self._hide_progress_strip()

        # Update folder section, sync filter state, and refresh display
        self._refresh_folders()

        # Enable toolbar tools
        self._enable_action_tools(reload=True, ai=True, rename=True, clear=True)

        # Show success message
        count = self._card_store.count
        self._show_info_message(
            f"Processing complete\n{_plural(count, 'card')} loaded",
            wx.ICON_INFORMATION,
        )

    def _start_rename(self) -> None:
        """Start rename workflow."""
        cards = self._review_panel.get_cards()
        year_str = self._get_year()

        if not RenameService.validate_year(year_str):
            wx.MessageBox("Please enter a valid 4-digit year.", "Invalid Year", wx.OK | wx.ICON_WARNING, self._frame)
            return

        # Build rename plan via service
        plan = self._rename_service.build_plan(cards, year_str)

        # Show confirmation dialog
        dialog = RenameConfirmDialog(self._frame, plan)
        if dialog.ShowModal() == wx.ID_OK:
            # Execute rename via service (updates path mappings automatically)
            results = self._rename_service.execute(plan)

            # Show completion
            counts = RenameService.summarize_results(results)
            title = "Rename Complete" if not counts["errors"] else "Rename Complete (with errors)"
            completion = CompletionDialog(self._frame, title, results)
            completion.ShowModal()
            completion.Destroy()

            # Remove successfully processed paths from cards
            self._remove_completed_results(results)

        dialog.Destroy()

    def _remove_completed_results(self, results: list[RenameResult]) -> None:
        """Remove successfully renamed/skip_same paths from cards; drop empty cards.

        Paths with message "Renamed" or "Already named correctly" are considered
        resolved. Paths that failed or had no name are kept for the user to address.
        """
        # Collect paths to remove (use new_path — that's where the file is now)
        paths_to_remove = self._rename_service.get_completed_paths(results)

        if not paths_to_remove:
            return

        # Remove paths from cards and tracking dicts
        for path in paths_to_remove:
            self._unlink_path(path)

        # Rebuild folder list and refresh display
        self._refresh_folders()

        # Disable toolbar tools if no cards remain
        if self._card_store.is_empty:
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

    def _on_frame_activate(self, event: wx.ActivateEvent) -> None:
        """Auto-reload cards when the app window is re-activated."""
        event.Skip()
        if not event.GetActive():
            return
        if not self._card_store.has_paths:
            return
        # Skip if processing is in progress
        if self._is_processing_busy:
            return
        now = time.monotonic()
        if now - self._last_reload_time < RELOAD_COOLDOWN:
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
