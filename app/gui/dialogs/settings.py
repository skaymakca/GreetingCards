"""Preferences pages for native macOS Preferences editor."""

from collections.abc import Callable

import wx

from app.core import sparkle
from app.core.services.config_service import ConfigService
from app.gui import styles

_PREFS_PAD = 20
_PREFS_WIDTH = 480
_STATUS_DISPLAY_MS = 3000
_SECTION_GAP = 16
_HEADING_GAP = 8
_BUTTON_LEFT_MARGIN = 12
_BOTTOM_PADDING = 20
_ADVANCED_BOTTOM_PADDING = 30
_MODEL_CHOICE_MAX_WIDTH = 340


# noinspection PyAttributeOutsideInit,PyUnusedLocal
class GeneralPreferencesPage(wx.StockPreferencesPage):
    """General preferences page with API key management."""

    def __init__(
        self,
        get_api_key: Callable[[], str | None],
        save_api_key: Callable[[str], None],
        get_ai_model: Callable[[], str],
        save_ai_model: Callable[[str], None],
    ) -> None:
        super().__init__(wx.StockPreferencesPage.Kind_General)
        self._get_api_key = get_api_key
        self._save_api_key_cb = save_api_key
        self._get_ai_model = get_ai_model
        self._save_ai_model_cb = save_ai_model

    def CreateWindow(self, parent: wx.Window) -> wx.Panel:
        """Create the preferences panel. May be called multiple times."""
        panel = wx.Panel(parent)
        panel.SetMaxSize(wx.Size(_PREFS_WIDTH, -1))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(_SECTION_GAP)

        # API Key heading
        api_heading = wx.StaticText(panel, label="API Key")
        api_heading.SetFont(styles.Font.HEADING())
        sizer.Add(api_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(_HEADING_GAP)

        # Key entry with Save button
        key_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._key_entry = wx.TextCtrl(panel, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        self._key_entry.SetFont(styles.Font.BODY())
        current_key = self._get_api_key()
        if current_key:
            self._key_entry.SetValue(current_key)
        self._key_entry.Bind(wx.EVT_TEXT_ENTER, self._save_api_key)
        key_sizer.Add(self._key_entry, 1, wx.EXPAND)

        save_btn = wx.Button(panel, label="Save")
        save_btn.Bind(wx.EVT_BUTTON, self._save_api_key)
        key_sizer.Add(save_btn, 0, wx.LEFT, _BUTTON_LEFT_MARGIN)

        sizer.Add(key_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _PREFS_PAD)

        # Status label (hidden until save action)
        self._key_status = wx.StaticText(panel, label="")
        self._key_status.SetFont(styles.Font.SMALL())
        sizer.Add(self._key_status, 0, wx.LEFT | wx.RIGHT | wx.TOP, _PREFS_PAD)
        self._key_status.Hide()
        self._status_timer = None

        # Reset status when preferences window is reopened
        panel.Bind(wx.EVT_SHOW, self._on_panel_shown)

        sizer.AddSpacer(_SECTION_GAP)

        # AI Model heading
        model_heading = wx.StaticText(panel, label="AI Model")
        model_heading.SetFont(styles.Font.HEADING())
        sizer.Add(model_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(_HEADING_GAP)

        # Model dropdown
        models = ConfigService.get_available_models()
        model_labels = [f"{m.label} \u2014 {m.description}" for m in models]
        self._model_choice = wx.Choice(panel, choices=model_labels)
        self._model_choice.SetMaxSize(wx.Size(_MODEL_CHOICE_MAX_WIDTH, -1))

        current_model = self._get_ai_model()
        for i, m in enumerate(models):
            if m.model_id == current_model:
                self._model_choice.SetSelection(i)
                break

        self._model_choice.Bind(wx.EVT_CHOICE, self._on_model_changed)
        sizer.Add(self._model_choice, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        model_desc = wx.StaticText(panel, label="Used for AI-assisted name extraction")
        model_desc.SetFont(styles.Font.SMALL())
        sizer.Add(model_desc, 0, wx.LEFT | wx.RIGHT | wx.TOP, _PREFS_PAD)

        # Updates section (only when running as app bundle with Sparkle)
        if sparkle.is_available():  # pragma: no cover — Sparkle framework not available in tests
            sizer.AddSpacer(_SECTION_GAP)

            updates_heading = wx.StaticText(panel, label="Updates")
            updates_heading.SetFont(styles.Font.HEADING())
            sizer.Add(updates_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

            sizer.AddSpacer(_HEADING_GAP)

            self._auto_update_cb = wx.CheckBox(panel, label="Automatically check for updates")
            self._auto_update_cb.SetValue(sparkle.get_auto_check_enabled())
            self._auto_update_cb.Bind(wx.EVT_CHECKBOX, self._on_auto_update_changed)
            sizer.Add(self._auto_update_cb, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(_BOTTOM_PADDING)

        panel.SetSizer(sizer)
        return panel

    # noinspection PyMethodMayBeStatic
    def _on_auto_update_changed(self, event: wx.CommandEvent) -> None:  # pragma: no cover — Sparkle UI only
        """Toggle automatic update checks via Sparkle."""
        sparkle.set_auto_check_enabled(event.IsChecked())

    def _on_model_changed(self, event: wx.CommandEvent) -> None:
        """Save model selection immediately."""
        if not self._model_choice:
            return
        idx = self._model_choice.GetSelection()
        if idx != wx.NOT_FOUND:
            self._save_ai_model_cb(ConfigService.get_available_models()[idx].model_id)

    def _save_api_key(self, event: wx.CommandEvent) -> None:
        """Save API key and show status."""
        # Guard against stale widget reference after CreateWindow re-creation
        if not self._key_entry or not self._key_status:
            return
        key = self._key_entry.GetValue().strip()
        if key:
            self._save_api_key_cb(key)
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


# noinspection PyAttributeOutsideInit,PyUnusedLocal
class AdvancedPreferencesPage(wx.StockPreferencesPage):
    """Advanced preferences page with database controls."""

    def __init__(
        self,
        on_db_reset: Callable[[], None] | None = None,
        is_ai_running: Callable[[], bool] | None = None,
    ):
        super().__init__(wx.StockPreferencesPage.Kind_Advanced)
        self._on_db_reset = on_db_reset
        self._is_ai_running = is_ai_running

    def CreateWindow(self, parent: wx.Window) -> wx.Panel:
        """Create the preferences panel. May be called multiple times."""
        panel = wx.Panel(parent)
        panel.SetMaxSize(wx.Size(_PREFS_WIDTH, -1))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(_SECTION_GAP)

        # Database heading
        db_heading = wx.StaticText(panel, label="Database")
        db_heading.SetFont(styles.Font.HEADING())
        sizer.Add(db_heading, 0, wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(_HEADING_GAP)

        db_row = wx.BoxSizer(wx.HORIZONTAL)

        db_desc = wx.StaticText(
            panel,
            label="Erase all manual entries, candidates, cached OCR,\nand cached AI results. Cards will be reprocessed on next load.",
        )
        db_desc.SetFont(styles.Font.SMALL())
        db_row.Add(db_desc, 1, wx.ALIGN_CENTER_VERTICAL)

        rebuild_btn = wx.Button(panel, label="Reset All Card Data")
        rebuild_btn.Bind(wx.EVT_BUTTON, self._reset_card_data)
        db_row.Add(rebuild_btn, 0, wx.LEFT, _BUTTON_LEFT_MARGIN)

        sizer.Add(db_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _PREFS_PAD)

        sizer.AddSpacer(_ADVANCED_BOTTOM_PADDING)

        panel.SetSizer(sizer)
        return panel

    def _reset_card_data(self, event: wx.CommandEvent) -> None:
        """Reset all card data after confirmation."""
        if self._is_ai_running and self._is_ai_running():
            wx.MessageBox(
                "Cannot reset database while AI analysis is running.\n\nWait for the current batch to finish first.",
                "Reset Blocked",
                wx.OK | wx.ICON_WARNING,
            )
            return

        result = wx.MessageBox(
            "This will reset all card data including manual name entries, "
            "collected candidates, cached OCR text, and cached AI results.\n\n"
            "Cards will need to be reloaded and reprocessed.\n\nContinue?",
            "Reset All Card Data",
            wx.OK | wx.CANCEL | wx.ICON_WARNING,
        )
        if result != wx.OK:
            return

        if self._on_db_reset:
            self._on_db_reset()

        wx.MessageBox(
            "All card data has been reset.",
            "Reset Complete",
            wx.OK | wx.ICON_INFORMATION,
        )


def create_preferences_editor(
    on_db_reset: Callable[[], None] | None = None,
    is_ai_running: Callable[[], bool] | None = None,
    *,
    get_api_key: Callable[[], str | None],
    save_api_key: Callable[[str], None],
    get_ai_model: Callable[[], str],
    save_ai_model: Callable[[str], None],
) -> wx.PreferencesEditor:
    """Create and return a wx.PreferencesEditor with all preference pages.

    Args:
        on_db_reset: Optional callback when database is reset
        is_ai_running: Optional callback to check if AI batch is running
        get_api_key: Callback to retrieve the API key
        save_api_key: Callback to persist the API key
        get_ai_model: Callback to retrieve the AI model
        save_ai_model: Callback to persist the AI model

    Returns:
        wx.PreferencesEditor instance
    """
    editor = wx.PreferencesEditor("Greeting Cards")
    editor.AddPage(
        GeneralPreferencesPage(
            get_api_key=get_api_key,
            save_api_key=save_api_key,
            get_ai_model=get_ai_model,
            save_ai_model=save_ai_model,
        )
    )
    editor.AddPage(AdvancedPreferencesPage(on_db_reset=on_db_reset, is_ai_running=is_ai_running))
    return editor
