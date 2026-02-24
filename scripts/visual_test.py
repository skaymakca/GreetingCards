#!/usr/bin/env python3
"""Visual test harness — opens all app dialogs and panels with mock data.

Usage (from source):
    uv run python scripts/visual_test.py

Usage (bundled):
    make visual-test-app
    open "dist/Visual Test.app"
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wx

from app.gui import appearance  # type: ignore[attr-defined]
from app.gui.icons import clear_cache
from app.gui.styles import Color, Font
from app.models.card import (
    STATUS_DUPLICATE,
    STATUS_OK,
    STATUS_SKIP_NO_NAME,
    STATUS_SKIP_SAME,
    CandidateInfo,
    CardResult,
    Confidence,
    RenamePlanItem,
    RenameResult,
)

# ---------------------------------------------------------------------------
# Mock data factories
# ---------------------------------------------------------------------------


def _mock_cards() -> list[CardResult]:
    """Create a set of mock CardResult objects covering all confidence levels.

    Cards span two folders so the folder filter section is visible.
    """
    cards: list[CardResult] = []
    samples = [
        ("Johnson", Confidence.HIGH, "ocr", True, "cards"),
        ("Williams", Confidence.MEDIUM, "ai", True, "cards"),
        ("Garcia", Confidence.LOW, "ocr", False, "cards"),
        ("Smith", Confidence.MANUAL, "manual", False, "cards"),
        ("", Confidence.NONE, "missing", False, "cards"),
        ("O'Brien-Takahashi", Confidence.HIGH, "ai", True, "archive"),
        ("Van der Berg", Confidence.MEDIUM, "ocr", False, "archive"),
        ("Davis", Confidence.HIGH, "ai", True, "archive"),
    ]
    for i, (name, conf, method, analyzed, folder) in enumerate(samples, start=1):
        pdf_path = Path(f"/tmp/mock/{folder}/card_{i:03d}.pdf")
        card = CardResult(
            id=i,
            file_paths=[pdf_path],
            primary_path=pdf_path,
            family_name=name,
            confidence=conf,
            method=method,
            ai_analyzed=analyzed,
            ocr_text=f"Sample OCR text for card {i}\nDear {name or 'Friend'} Family,\nHappy Holidays!",
            candidates=[
                CandidateInfo(id=i * 10, family_name=name, method=method, confidence=conf.value),
                CandidateInfo(
                    id=i * 10 + 1, family_name=name + "son" if name else "Unknown", method="ocr", confidence="low"
                ),
            ]
            if name
            else [],
            selected_candidate_id=i * 10 if name else None,
        )
        if name:
            card.alternates = [name + "son", name[0:3] + "ley"]
        cards.append(card)
    return cards


def _mock_rename_plan() -> list[RenamePlanItem]:
    """Create a mock rename plan for RenameConfirmDialog."""
    return [
        RenamePlanItem(
            old_path=Path("/tmp/mock/cards/card_001.pdf"),
            new_path=Path("/tmp/mock/cards/Johnson Family.pdf"),
            status=STATUS_OK,
        ),
        RenamePlanItem(
            old_path=Path("/tmp/mock/cards/card_002.pdf"),
            new_path=Path("/tmp/mock/cards/Williams Family.pdf"),
            status=STATUS_OK,
        ),
        RenamePlanItem(
            old_path=Path("/tmp/mock/cards/card_003.pdf"),
            new_path=Path("/tmp/mock/cards/card_003.pdf"),
            status=STATUS_SKIP_SAME,
        ),
        RenamePlanItem(
            old_path=Path("/tmp/mock/cards/card_005.pdf"),
            new_path=Path("/tmp/mock/cards/card_005.pdf"),
            status=STATUS_SKIP_NO_NAME,
        ),
        RenamePlanItem(
            old_path=Path("/tmp/mock/cards/card_006.pdf"),
            new_path=Path("/tmp/mock/cards/O'Brien-Takahashi Family.pdf"),
            status=STATUS_DUPLICATE,
        ),
    ]


def _mock_rename_results() -> list[RenameResult]:
    """Create mock rename results for CompletionDialog."""
    return [
        RenameResult(
            old_path=Path("/tmp/mock/card_001.pdf"),
            new_path=Path("/tmp/mock/Johnson Family.pdf"),
            success=True,
            message="Renamed",
        ),
        RenameResult(
            old_path=Path("/tmp/mock/card_002.pdf"),
            new_path=Path("/tmp/mock/Williams Family.pdf"),
            success=True,
            message="Renamed",
        ),
        RenameResult(
            old_path=Path("/tmp/mock/card_003.pdf"),
            new_path=Path("/tmp/mock/Garcia Family.pdf"),
            success=False,
            message="Permission denied",
        ),
    ]


def _mock_errors() -> list[tuple[str, str]]:
    """Create mock errors for ErrorListDialog."""
    return [
        ("card_010.pdf", "File is encrypted and cannot be read"),
        ("card_011.pdf", "Corrupt PDF — no pages found"),
        ("card_012.pdf", "API rate limit exceeded (429)"),
    ]


# ---------------------------------------------------------------------------
# Launcher window
# ---------------------------------------------------------------------------


# noinspection PyProtectedMember,PyMethodMayBeStatic
class VisualTestFrame(wx.Frame):
    """Main launcher window with buttons to open each dialog/panel."""

    def __init__(self) -> None:
        Color.refresh()
        mode = "Dark" if appearance.is_dark_mode() else "Light"
        super().__init__(None, title=f"Visual Test Harness — {mode} Mode", size=wx.Size(420, 1060))

        self._cards = _mock_cards()
        self._prefs_editor: wx.PreferencesEditor | None = None
        from app.gui.main_window import MainWindow

        self._last_main_window: MainWindow | None = None

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Mode indicator
        self._mode_label = wx.StaticText(panel, label=f"Current Mode: {mode}")
        self._mode_label.SetFont(Font.TITLE())
        sizer.Add(self._mode_label, 0, wx.ALL, 12)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Section: Dialogs
        h1 = wx.StaticText(panel, label="Dialogs")
        h1.SetFont(Font.HEADING())
        sizer.Add(h1, 0, wx.ALL, 12)

        buttons = [
            ("Rename Confirm Dialog", self._open_rename_confirm),
            ("Completion Dialog (success + errors)", self._open_completion),
            ("Error List Dialog", self._open_error_list),
            ("Progress Dialog", self._open_progress),
            ("API Key Dialog", self._open_api_key),
            ("Settings / Preferences", self._open_settings),
        ]
        for label, handler in buttons:
            btn = wx.Button(panel, label=label)
            btn.Bind(wx.EVT_BUTTON, handler)
            sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Section: HTML Viewers
        h2 = wx.StaticText(panel, label="HTML Viewers")
        h2.SetFont(Font.HEADING())
        sizer.Add(h2, 0, wx.ALL, 12)

        viewer_buttons = [
            ("Help Viewer", self._open_help),
            ("Changelog Viewer", self._open_changelog),
            ("Licenses Viewer", self._open_licenses),
        ]
        for label, handler in viewer_buttons:
            btn = wx.Button(panel, label=label)
            btn.Bind(wx.EVT_BUTTON, handler)
            sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Section: Panels (embedded in standalone frames)
        h3 = wx.StaticText(panel, label="Panels (standalone)")
        h3.SetFont(Font.HEADING())
        sizer.Add(h3, 0, wx.ALL, 12)

        panel_buttons = [
            ("Filter Sidebar", self._open_filter_sidebar),
            ("Preview Panel", self._open_preview_panel),
            ("Review Panel (with mock cards)", self._open_review_panel),
        ]
        for label, handler in panel_buttons:
            btn = wx.Button(panel, label=label)
            btn.Bind(wx.EVT_BUTTON, handler)
            sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Section: Full main window
        h4 = wx.StaticText(panel, label="Full App")
        h4.SetFont(Font.HEADING())
        sizer.Add(h4, 0, wx.ALL, 12)

        btn_main = wx.Button(panel, label="Main Window (empty)")
        btn_main.Bind(wx.EVT_BUTTON, self._open_main_window)
        sizer.Add(btn_main, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        btn_main_data = wx.Button(panel, label="Main Window (with mock cards)")
        btn_main_data.Bind(wx.EVT_BUTTON, self._open_main_window_with_data)
        sizer.Add(btn_main_data, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Section: Notifications (shown in sidebar of "with mock cards" window)
        h5 = wx.StaticText(panel, label="Notifications")
        h5.SetFont(Font.HEADING())
        sizer.Add(h5, 0, wx.ALL, 12)

        note = wx.StaticText(panel, label="Opens in the last 'Main Window (with mock cards)' launched.")
        note.SetFont(Font.SMALL())
        note.SetForegroundColour(Color.TEXT_SECONDARY)
        sizer.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        notify_buttons = [
            ("Info: Cards loaded", self._notify_cards_loaded),
            ("Info: Processing complete", self._notify_processing_complete),
            ("Info: All cards cleared", self._notify_all_cleared),
            ("Info: AI results cleared", self._notify_ai_cleared),
            ("Info: Analysis complete", self._notify_analysis_complete),
            ("Warning: No PDF files found", self._notify_no_pdfs),
            ("Warning: API key not configured", self._notify_no_api_key),
            ("Dismiss notification", self._notify_dismiss),
        ]
        for label, handler in notify_buttons:
            btn = wx.Button(panel, label=label)
            btn.Bind(wx.EVT_BUTTON, handler)
            sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        panel.SetSizer(sizer)

        # Wire up appearance observer
        appearance.start_observer(self._on_appearance_changed)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Centre()
        self.Show()

    def _on_appearance_changed(self) -> None:
        Color.refresh()
        clear_cache()
        mode = "Dark" if appearance.is_dark_mode() else "Light"
        self._mode_label.SetLabel(f"Current Mode: {mode}")
        self.SetTitle(f"Visual Test Harness — {mode} Mode")
        # Repaint all top-level windows and refresh colors on dialogs
        # noinspection PyArgumentList
        for window in wx.GetTopLevelWindows():
            if hasattr(window, "refresh_colors"):
                window.refresh_colors()
            window.Refresh()
            window.Update()

    def _on_close(self, event: wx.CloseEvent) -> None:
        appearance.stop_observer()
        event.Skip()

    # -- Dialog launchers --

    def _open_rename_confirm(self, _evt: wx.CommandEvent) -> None:
        from app.gui.dialogs import RenameConfirmDialog

        dlg = RenameConfirmDialog(self, _mock_rename_plan())
        dlg.ShowModal()
        dlg.Destroy()

    def _open_completion(self, _evt: wx.CommandEvent) -> None:
        from app.gui.dialogs import CompletionDialog

        dlg = CompletionDialog(self, "Rename Complete", _mock_rename_results())
        dlg.ShowModal()
        dlg.Destroy()

    def _open_error_list(self, _evt: wx.CommandEvent) -> None:
        from app.gui.dialogs import ErrorListDialog

        dlg = ErrorListDialog(self, "Processing Errors", _mock_errors())
        dlg.ShowModal()
        dlg.Destroy()

    def _open_progress(self, _evt: wx.CommandEvent) -> None:
        from app.gui.dialogs import ProgressDialog

        dlg = ProgressDialog(self, "Analyzing Cards…", total=8)
        dlg.Show()
        # Simulate progress with a timer
        self._progress_dlg = dlg
        self._progress_count = 0
        self._progress_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_progress_tick, self._progress_timer)
        self._progress_timer.Start(400)

    def _on_progress_tick(self, _evt: wx.TimerEvent) -> None:
        self._progress_count += 1
        if self._progress_count <= 8:
            names = ["Johnson", "Williams", "Garcia", "Smith", "", "O'Brien", "Van der Berg", "Davis"]
            name = names[self._progress_count - 1] or "(no name)"
            self._progress_dlg.update_progress(self._progress_count, f"Processing: {name}")
        else:
            self._progress_timer.Stop()
            self._progress_dlg.Destroy()

    def _open_api_key(self, _evt: wx.CommandEvent) -> None:
        from app.gui.api_key_dialog import show_api_key_dialog

        result = show_api_key_dialog(self)
        if result:
            wx.MessageBox(f"Key entered: {result[:8]}…", "API Key Result")
        else:
            wx.MessageBox("Cancelled", "API Key Result")

    def _open_settings(self, _evt: wx.CommandEvent) -> None:
        from app.gui.settings_dialog import create_preferences_editor

        if self._prefs_editor is None:
            self._prefs_editor = create_preferences_editor(on_db_reset=lambda: None)
        self._prefs_editor.Show(self)

    # -- HTML Viewer launchers --

    def _open_help(self, _evt: wx.CommandEvent) -> None:
        from app.gui.help_dialog import show_help

        show_help(self)

    def _open_changelog(self, _evt: wx.CommandEvent) -> None:
        from app.gui.changelog_dialog import show_changelog

        show_changelog(self)

    def _open_licenses(self, _evt: wx.CommandEvent) -> None:
        from app.gui.licenses_dialog import show_licenses

        show_licenses(self)

    # -- Panel launchers (in standalone frames) --

    def _open_filter_sidebar(self, _evt: wx.CommandEvent) -> None:
        from app.gui.filter_sidebar import FilterSidebar

        frame = wx.Frame(self, title="Filter Sidebar", size=wx.Size(250, 500))
        sidebar = FilterSidebar(
            frame,
            on_category_filter=lambda keys: print(f"Category filter: {keys}"),
            on_folder_filter=lambda keys: print(f"Folder filter: {keys}"),
        )
        # Populate with mock filter data
        sidebar.update_folders([Path("/tmp/mock/cards"), Path("/tmp/mock/archive")])
        sidebar.update_category_counts(self._cards)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(sidebar, 1, wx.EXPAND)
        frame.SetSizer(sizer)
        frame.Show()

    def _open_preview_panel(self, _evt: wx.CommandEvent) -> None:
        from app.gui.preview_panel import PreviewPanel

        frame = wx.Frame(self, title="Preview Panel", size=wx.Size(500, 600))
        panel = PreviewPanel(frame)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel, 1, wx.EXPAND)
        frame.SetSizer(sizer)
        frame.Show()

    def _open_review_panel(self, _evt: wx.CommandEvent) -> None:
        from app.gui.review_panel import ReviewPanelMasterDetail

        frame = wx.Frame(self, title="Review Panel", size=wx.Size(700, 500))
        _noop = print  # Avoid verbose lambda type issues
        panel = ReviewPanelMasterDetail(
            frame,
            on_select=lambda card: _noop(f"Selected: {card}"),
            on_ai_request=lambda card: _noop(f"AI request: {card}"),
            on_name_change=lambda card, name: _noop(f"Name change: {name}"),
            on_card_edited=lambda card: _noop(f"Card edited: {card}"),
            on_remove=lambda card: _noop(f"Remove: {card}"),
        )
        panel.load_cards(self._cards)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel, 1, wx.EXPAND)
        frame.SetSizer(sizer)
        frame.Show()

    # -- Full main window --

    def _open_main_window(self, _evt: wx.CommandEvent) -> None:
        from app.gui.main_window import MainWindow

        window = MainWindow()
        window.run()

    def _open_main_window_with_data(self, _evt: wx.CommandEvent) -> None:
        from app.gui.main_window import MainWindow

        window = MainWindow()
        window.run()
        # Inject mock cards into the main window's internal state
        for card in self._cards:
            fake_hash = f"mock_hash_{card.id}"
            card.file_hash = fake_hash
            window._cards_by_hash[fake_hash] = card
            for fp in card.file_paths:
                window._hash_by_path[fp] = fake_hash
        window._next_card_id = len(self._cards) + 1
        folders = list({fp.parent for c in self._cards for fp in c.file_paths})
        window._sidebar.update_folders(sorted(folders))
        window._refresh_display()
        window._set_empty_state(False)
        self._last_main_window = window

    # -- Notification triggers (sent to last "with mock cards" main window) --

    def _get_sidebar(self):  # type: ignore[no-untyped-def]
        """Get the sidebar from the last main window, or show error."""
        if self._last_main_window is None:
            wx.MessageBox(
                "Launch 'Main Window (with mock cards)' first.",
                "No Main Window",
                wx.OK | wx.ICON_WARNING,
            )
            return None
        return self._last_main_window._sidebar

    def _notify_cards_loaded(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.show_notification("Added 5 new cards\n8 cards loaded", wx.ICON_INFORMATION)

    def _notify_processing_complete(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.show_notification("Processing complete\n8 cards loaded", wx.ICON_INFORMATION)

    def _notify_all_cleared(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.show_notification("All cards cleared", wx.ICON_INFORMATION)

    def _notify_ai_cleared(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.show_notification("AI results cleared for 5 card(s). 3 reverted to OCR names.", wx.ICON_INFORMATION)

    def _notify_analysis_complete(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.show_notification("Analysis complete\n5 cards analyzed", wx.ICON_INFORMATION)

    def _notify_no_pdfs(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.show_notification("No PDF files found", wx.ICON_WARNING, duration_ms=0)

    def _notify_no_api_key(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.show_notification(
                "API key not configured\nUse Settings to add your Anthropic API key", wx.ICON_WARNING, duration_ms=0
            )

    def _notify_dismiss(self, _evt: wx.CommandEvent) -> None:
        sidebar = self._get_sidebar()
        if sidebar:
            sidebar.dismiss_notification()


def main() -> None:
    app = wx.App()
    VisualTestFrame()
    app.MainLoop()


if __name__ == "__main__":
    main()
