"""Settings dialog with API key management and database controls."""
import subprocess
import wx
from app.gui import styles
from app.core.config import get_api_key, save_api_key
from app.core.database import reset_database
from app.version import __version__


def get_commit_hash() -> str:
    """Get short git commit hash, or empty string if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def show_settings_dialog(parent, on_db_reset=None):
    """Show settings dialog.

    Args:
        parent: Parent window
        on_db_reset: Optional callback when database is reset
    """
    dialog = SettingsDialog(parent, on_db_reset)
    dialog.ShowModal()
    dialog.Destroy()


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


class SettingsDialog(wx.Dialog):
    """Settings window with API key management and database controls."""

    def __init__(self, parent, on_db_reset=None):
        super().__init__(
            parent,
            title="Settings",
            size=(420, 330),
            style=wx.DEFAULT_DIALOG_STYLE
        )

        self._on_db_reset = on_db_reset

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- About section ---
        sizer.AddSpacer(20)

        app_name = wx.StaticText(self, label="Greeting Cards")
        app_name.SetFont(styles.Font.TITLE())
        app_name.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(app_name, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(4)

        commit = get_commit_hash()
        version_text = f"Version {__version__}"
        if commit:
            version_text += f" ({commit})"
        version_label = wx.StaticText(self, label=version_text)
        version_label.SetFont(styles.Font.SMALL())
        version_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(version_label, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(16)

        # Separator
        sep1 = wx.StaticLine(self)
        sizer.Add(sep1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(16)

        # --- API Key section ---
        api_heading = wx.StaticText(self, label="API Key")
        api_heading.SetFont(styles.Font.HEADING())
        api_heading.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(api_heading, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(8)

        # Key entry frame
        key_frame = wx.Panel(self)
        key_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._key_entry = wx.TextCtrl(key_frame, style=wx.TE_PASSWORD)
        self._key_entry.SetFont(styles.Font.BODY())
        current_key = get_api_key()
        if current_key:
            self._key_entry.SetValue(current_key)
        key_sizer.Add(self._key_entry, 1, wx.EXPAND)

        self._save_key_btn = wx.Button(key_frame, label="Save")
        self._save_key_btn.Bind(wx.EVT_BUTTON, self._save_api_key)
        key_sizer.Add(self._save_key_btn, 0, wx.LEFT, 8)

        key_frame.SetSizer(key_sizer)
        sizer.Add(key_frame, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(4)

        # Status label
        self._key_status = wx.StaticText(self, label="")
        self._key_status.SetFont(styles.Font.SMALL())
        sizer.Add(self._key_status, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(16)

        # Separator
        sep2 = wx.StaticLine(self)
        sizer.Add(sep2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(16)

        # --- Database section ---
        db_heading = wx.StaticText(self, label="Database")
        db_heading.SetFont(styles.Font.HEADING())
        db_heading.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(db_heading, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(8)

        db_frame = wx.Panel(self)
        db_sizer = wx.BoxSizer(wx.HORIZONTAL)

        db_desc = wx.StaticText(
            db_frame,
            label="Clear all cached OCR/AI results and rebuild."
        )
        db_desc.SetFont(styles.Font.SMALL())
        db_desc.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        db_sizer.Add(db_desc, 1, wx.ALIGN_CENTER_VERTICAL)

        self._rebuild_btn = wx.Button(db_frame, label="Rebuild")
        self._rebuild_btn.Bind(wx.EVT_BUTTON, self._rebuild_db)
        db_sizer.Add(self._rebuild_btn, 0, wx.LEFT, 8)

        db_frame.SetSizer(db_sizer)
        sizer.Add(db_frame, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        # Add spacer before close button
        sizer.AddStretchSpacer()

        # Close button
        close_btn = wx.Button(self, wx.ID_CLOSE, "Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CLOSE))
        sizer.Add(close_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 20)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

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
        self.Layout()

    def _rebuild_db(self, event):
        """Rebuild database after confirmation."""
        result = wx.MessageBox(
            "This will delete all cached OCR results, AI results, and manual edits.\n\nContinue?",
            "Rebuild Database",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
            self
        )
        if result != wx.YES:
            return

        reset_database()
        wx.MessageBox(
            "The cache has been cleared.",
            "Database Rebuilt",
            wx.OK | wx.ICON_INFORMATION,
            self
        )

        if self._on_db_reset:
            self._on_db_reset()

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CLOSE)
        else:
            event.Skip()
