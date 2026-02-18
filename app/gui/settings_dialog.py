"""Preferences pages for native macOS Preferences editor."""
import subprocess
from collections.abc import Callable

import wx

from app.gui import styles
from app.core.config import get_api_key, save_api_key
from app.core.database import reset_database


def get_commit_hash() -> str:
    """Get short git commit hash, or empty string if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


class ApiKeyPrompt(wx.Dialog):
    """Simple prompt for API key when needed for AI features."""

    def __init__(self, parent):
        super().__init__(
            parent,
            title="API Key Required",
            size=(500, 200),
            style=wx.DEFAULT_DIALOG_STYLE
        )

        self.result = None

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Message
        msg = wx.StaticText(
            self,
            label="AI analysis requires an Anthropic API key."
        )
        msg.SetFont(styles.Font.BODY())
        msg.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(msg, 0, wx.ALL, 20)

        link = wx.StaticText(
            self,
            label="Get one at: console.anthropic.com"
        )
        link.SetFont(styles.Font.SMALL())
        link.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(link, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        # Key entry
        key_frame = wx.Panel(self)
        key_sizer = wx.BoxSizer(wx.HORIZONTAL)

        key_label = wx.StaticText(key_frame, label="API Key:")
        key_label.SetFont(styles.Font.BODY())
        key_label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        key_sizer.Add(key_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._key_entry = wx.TextCtrl(
            key_frame,
            style=wx.TE_PASSWORD,
            size=(300, -1)
        )
        self._key_entry.SetFont(styles.Font.BODY())
        key_sizer.Add(self._key_entry, 1, wx.EXPAND)

        key_frame.SetSizer(key_sizer)
        sizer.Add(key_frame, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, 8)

        save_btn = wx.Button(self, wx.ID_OK, "Save")
        save_btn.Bind(wx.EVT_BUTTON, self._on_save)
        btn_sizer.Add(save_btn, 0)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 20)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Focus key entry
        self._key_entry.SetFocus()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_save(self, event):
        """Handle Save button click."""
        key = self._key_entry.GetValue().strip()
        if key:
            save_api_key(key)
            self.result = True
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox(
                "Please enter an API key.",
                "Empty Key",
                wx.OK | wx.ICON_WARNING,
                self
            )

    def _on_cancel(self, event):
        """Handle Cancel button click."""
        self.result = False
        self.EndModal(wx.ID_CANCEL)

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        key_code = event.GetKeyCode()
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_save(event)
        elif key_code == wx.WXK_ESCAPE:
            self._on_cancel(event)
        else:
            event.Skip()


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
        sizer.Add(api_heading, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(8)

        # Key entry with Save button
        key_frame = wx.Panel(panel)
        key_frame.SetMaxSize(wx.Size(340, -1))
        key_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._key_entry = wx.TextCtrl(key_frame, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        self._key_entry.SetFont(styles.Font.BODY())
        current_key = get_api_key()
        if current_key:
            self._key_entry.SetValue(current_key)
        self._key_entry.Bind(wx.EVT_TEXT_ENTER, self._save_api_key)
        key_sizer.Add(self._key_entry, 1, wx.EXPAND)

        save_btn = wx.Button(key_frame, label="Save")
        save_btn.Bind(wx.EVT_BUTTON, self._save_api_key)
        key_sizer.Add(save_btn, 0, wx.LEFT, 8)

        key_frame.SetSizer(key_sizer)
        sizer.Add(key_frame, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(4)

        # Status label
        self._key_status = wx.StaticText(panel, label="")
        self._key_status.SetFont(styles.Font.SMALL())
        sizer.Add(self._key_status, 0, wx.LEFT | wx.RIGHT, 20)

        panel.SetSizer(sizer)
        return panel

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
        sizer.Add(db_heading, 0, wx.LEFT | wx.RIGHT, 20)

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
        sizer.Add(db_frame, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

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
