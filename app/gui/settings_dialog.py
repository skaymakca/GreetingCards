"""Preferences pages for native macOS Preferences editor."""
import subprocess
from collections.abc import Callable

import wx

from app.gui import styles
from app.core.config import get_api_key, save_api_key, AI_MODELS, get_ai_model, save_ai_model
from app.core.database import reset_database

_PREFS_PAD = 20
_PREFS_WIDTH = 480
_STATUS_DISPLAY_MS = 3000


def get_commit_hash() -> str:
    """Get short git commit hash, or empty string if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (OSError, subprocess.SubprocessError):
        return ""


class GeneralPreferencesPage(wx.StockPreferencesPage):
    """General preferences page with API key management."""

    def __init__(self):
        super().__init__(wx.StockPreferencesPage.Kind_General)

    def CreateWindow(self, parent):
        """Create the preferences panel. May be called multiple times."""
        panel = wx.Panel(parent)
        panel.SetMaxSize(wx.Size(_PREFS_WIDTH, -1))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(16)

        # API Key heading
        api_heading = wx.StaticText(panel, label="API Key")
        api_heading.SetFont(styles.Font.HEADING())
        sizer.Add(api_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(8)

        # Key entry with Save button
        key_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._key_entry = wx.TextCtrl(panel, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        self._key_entry.SetFont(styles.Font.BODY())
        current_key = get_api_key()
        if current_key:
            self._key_entry.SetValue(current_key)
        self._key_entry.Bind(wx.EVT_TEXT_ENTER, self._save_api_key)
        key_sizer.Add(self._key_entry, 1, wx.EXPAND)

        save_btn = wx.Button(panel, label="Save")
        save_btn.Bind(wx.EVT_BUTTON, self._save_api_key)
        key_sizer.Add(save_btn, 0, wx.LEFT, 12)

        sizer.Add(key_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _PREFS_PAD)

        # Status label (hidden until save action)
        self._key_status = wx.StaticText(panel, label="")
        self._key_status.SetFont(styles.Font.SMALL())
        sizer.Add(self._key_status, 0, wx.LEFT | wx.RIGHT | wx.TOP, _PREFS_PAD)
        self._key_status.Hide()
        self._status_timer = None

        # Reset status when preferences window is reopened
        panel.Bind(wx.EVT_SHOW, self._on_panel_shown)

        sizer.AddSpacer(16)

        # AI Model heading
        model_heading = wx.StaticText(panel, label="AI Model")
        model_heading.SetFont(styles.Font.HEADING())
        sizer.Add(model_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(8)

        # Model dropdown
        model_labels = [f"{m.label} \u2014 {m.description}" for m in AI_MODELS]
        self._model_choice = wx.Choice(panel, choices=model_labels)
        self._model_choice.SetMaxSize(wx.Size(340, -1))

        current_model = get_ai_model()
        for i, m in enumerate(AI_MODELS):
            if m.model_id == current_model:
                self._model_choice.SetSelection(i)
                break

        self._model_choice.Bind(wx.EVT_CHOICE, self._on_model_changed)
        sizer.Add(self._model_choice, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        model_desc = wx.StaticText(panel, label="Used for AI-assisted name extraction")
        model_desc.SetFont(styles.Font.SMALL())
        sizer.Add(model_desc, 0, wx.LEFT | wx.RIGHT | wx.TOP, _PREFS_PAD)

        sizer.AddSpacer(20)

        panel.SetSizer(sizer)
        return panel

    def _on_model_changed(self, event) -> None:
        """Save model selection immediately."""
        if not self._model_choice:
            return
        idx = self._model_choice.GetSelection()
        if idx != wx.NOT_FOUND:
            save_ai_model(AI_MODELS[idx].model_id)

    def _save_api_key(self, event) -> None:
        """Save API key and show status."""
        # Guard against stale widget reference after CreateWindow re-creation
        if not self._key_entry or not self._key_status:
            return
        key = self._key_entry.GetValue().strip()
        if key:
            save_api_key(key)
            self._key_status.SetLabel("Saved")
            self._key_status.SetForegroundColour(styles.Color.SUCCESS)
        else:
            self._key_status.SetLabel("Key cannot be empty")
            self._key_status.SetForegroundColour(styles.Color.ERROR)
        self._key_status.Show()
        self._key_status.GetParent().Layout()

        # Auto-hide after a few seconds
        if self._status_timer is not None:
            self._status_timer.Stop()
        self._status_timer = wx.CallLater(_STATUS_DISPLAY_MS, self._cancel_status)


    def _on_panel_shown(self, event: wx.ShowEvent) -> None:
        """Clean up status label on show/hide transitions.

        On hide (window closing): immediately hide status and cancel timer,
        so the label is already gone before the next open.
        On show (window reopening): safety net in case hide wasn't called.
        """
        event.Skip()
        self._cancel_status()

    def _cancel_status(self) -> None:
        """Stop the auto-hide timer and hide the status label."""
        if self._status_timer is not None:
            self._status_timer.Stop()
            self._status_timer = None
        if self._key_status and self._key_status.IsShown():
            self._key_status.Hide()
            self._key_status.GetParent().Layout()


class AdvancedPreferencesPage(wx.StockPreferencesPage):
    """Advanced preferences page with database controls."""

    def __init__(self, on_db_reset: Callable[[], None] | None = None):
        super().__init__(wx.StockPreferencesPage.Kind_Advanced)
        self._on_db_reset = on_db_reset

    def CreateWindow(self, parent):
        """Create the preferences panel. May be called multiple times."""
        panel = wx.Panel(parent)
        panel.SetMaxSize(wx.Size(_PREFS_WIDTH, -1))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(16)

        # Database heading
        db_heading = wx.StaticText(panel, label="Database")
        db_heading.SetFont(styles.Font.HEADING())
        sizer.Add(db_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(8)

        db_row = wx.BoxSizer(wx.HORIZONTAL)

        db_desc = wx.StaticText(
            panel,
            label="Erase all manual entries, candidates, cached OCR,\nand cached AI results. Cards will be reprocessed on next load."
        )
        db_desc.SetFont(styles.Font.SMALL())
        db_row.Add(db_desc, 1, wx.ALIGN_CENTER_VERTICAL)

        rebuild_btn = wx.Button(panel, label="Reset All Card Data")
        rebuild_btn.Bind(wx.EVT_BUTTON, self._reset_card_data)
        db_row.Add(rebuild_btn, 0, wx.LEFT, 12)

        sizer.Add(db_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(30)

        panel.SetSizer(sizer)
        return panel

    def _reset_card_data(self, event):
        """Reset all card data after confirmation."""
        result = wx.MessageBox(
            "This will reset all card data including manual name entries, "
            "collected candidates, cached OCR text, and cached AI results.\n\n"
            "Cards will need to be reloaded and reprocessed.\n\nContinue?",
            "Reset All Card Data",
            wx.OK | wx.CANCEL | wx.ICON_WARNING,
        )
        if result != wx.OK:
            return

        reset_database()
        wx.MessageBox(
            "All card data has been reset.",
            "Reset Complete",
            wx.OK | wx.ICON_INFORMATION,
        )

        if self._on_db_reset:
            self._on_db_reset()


def create_preferences_editor(on_db_reset: Callable[[], None] | None = None) -> wx.PreferencesEditor:
    """Create and return a wx.PreferencesEditor with all preference pages.

    Args:
        on_db_reset: Optional callback when database is reset

    Returns:
        wx.PreferencesEditor instance
    """
    editor = wx.PreferencesEditor("Greeting Cards")
    editor.AddPage(GeneralPreferencesPage())
    editor.AddPage(AdvancedPreferencesPage(on_db_reset=on_db_reset))
    return editor
