"""Preferences pages for native macOS Preferences editor."""
import subprocess
from collections.abc import Callable

import wx

from app.gui import styles
from app.core.config import get_api_key, save_api_key, AI_MODELS, get_ai_model, save_ai_model
from app.core.database import reset_database

_PREFS_PAD = 20


def get_commit_hash() -> str:
    """Get short git commit hash, or empty string if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


class GeneralPreferencesPage(wx.StockPreferencesPage):
    """General preferences page with API key management."""

    def __init__(self):
        super().__init__(wx.StockPreferencesPage.Kind_General)

    def CreateWindow(self, parent):
        """Create the preferences panel. May be called multiple times."""
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(16)

        # API Key heading
        api_heading = wx.StaticText(panel, label="API Key")
        api_heading.SetFont(styles.Font.HEADING())
        sizer.Add(api_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(8)

        # Key entry with Save button
        key_frame = wx.Panel(panel)
        key_frame.SetMaxSize(wx.Size(340, -1))
        key_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._key_entry = wx.TextCtrl(key_frame, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        self._key_entry.SetFont(styles.Font.BODY())
        self._key_entry.SetMinSize((250, -1))
        current_key = get_api_key()
        if current_key:
            self._key_entry.SetValue(current_key)
        self._key_entry.Bind(wx.EVT_TEXT_ENTER, self._save_api_key)
        key_sizer.Add(self._key_entry, 1, wx.EXPAND)

        save_btn = wx.Button(key_frame, label="Save")
        save_btn.Bind(wx.EVT_BUTTON, self._save_api_key)
        key_sizer.Add(save_btn, 0, wx.LEFT, 8)

        key_frame.SetSizer(key_sizer)
        sizer.Add(key_frame, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        # Status label (hidden until save action)
        self._key_status = wx.StaticText(panel, label="")
        self._key_status.SetFont(styles.Font.SMALL())
        sizer.Add(self._key_status, 0, wx.LEFT | wx.RIGHT | wx.TOP, _PREFS_PAD)
        self._key_status.Hide()

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

    def _on_model_changed(self, event):
        """Save model selection immediately."""
        idx = self._model_choice.GetSelection()
        if idx != wx.NOT_FOUND:
            save_ai_model(AI_MODELS[idx].model_id)

    def _save_api_key(self, event):
        """Save API key and show status."""
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


class AdvancedPreferencesPage(wx.StockPreferencesPage):
    """Advanced preferences page with database controls."""

    def __init__(self, on_db_reset: Callable[[], None] | None = None):
        super().__init__(wx.StockPreferencesPage.Kind_Advanced)
        self._on_db_reset = on_db_reset

    def CreateWindow(self, parent):
        """Create the preferences panel. May be called multiple times."""
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(16)

        # Database heading
        db_heading = wx.StaticText(panel, label="Database")
        db_heading.SetFont(styles.Font.HEADING())
        sizer.Add(db_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(8)

        db_frame = wx.Panel(panel)
        db_sizer = wx.BoxSizer(wx.HORIZONTAL)

        db_desc = wx.StaticText(
            db_frame,
            label="Clear all cached OCR/AI results and rebuild."
        )
        db_desc.SetFont(styles.Font.SMALL())
        db_sizer.Add(db_desc, 1, wx.ALIGN_CENTER_VERTICAL)

        rebuild_btn = wx.Button(db_frame, label="Rebuild")
        rebuild_btn.Bind(wx.EVT_BUTTON, self._rebuild_db)
        db_sizer.Add(rebuild_btn, 0, wx.LEFT, 8)

        db_frame.SetSizer(db_sizer)
        sizer.Add(db_frame, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(30)

        panel.SetSizer(sizer)
        return panel

    def _rebuild_db(self, event):
        """Rebuild database after confirmation."""
        result = wx.MessageBox(
            "This will delete all cached OCR results, AI results, and manual edits.\n\nContinue?",
            "Rebuild Database",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        if result != wx.YES:
            return

        reset_database()
        wx.MessageBox(
            "The cache has been cleared.",
            "Database Rebuilt",
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
