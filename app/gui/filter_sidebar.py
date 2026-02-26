"""wxPython Filter Sidebar for three-column Mail.app style layout."""

from collections.abc import Callable
from pathlib import Path

import wx

from app.gui import styles
from app.models.card import CardResult, Confidence

_SIDEBAR_MIN_WIDTH = 175
_SIDEBAR_PAD = 10
_NOTIFY_PAD = 20


# noinspection PyAttributeOutsideInit,PyMethodMayBeStatic,PyUnusedLocal,PyTypeChecker,GrazieInspection
class FilterSidebar(wx.Panel):
    """Sidebar for filtering cards by confidence level, status, and source folder.

    Provides Mail.app style filtering with multi-select checkboxes:
    - Confidence section (always visible):
      - All Cards, Manual Entry, High Confidence, Needs Review, Errors
    - Folder section (visible when cards come from 2+ folders):
      - All Folders, one checkbox per source folder
    """

    def __init__(
        self,
        parent: wx.Window,
        on_category_filter: Callable[[list[str]], None],
        on_folder_filter: Callable[[list[str]], None] | None = None,
    ) -> None:
        """Initialize filter sidebar.

        Args:
            parent: Parent window
            on_category_filter: Callback(selected: list[str]) when category filters change
            on_folder_filter: Callback(selected: list[str]) when folder filters change
        """
        super().__init__(parent)
        self._on_category_filter = on_category_filter
        self._on_folder_filter = on_folder_filter or (lambda keys: None)

        # Category filter state
        self._selected_category_filters = ["all"]
        self._category_card_counts: dict[str, int] = {}
        self._category_disabled_keys: set[str] = set()

        # Category definitions (in priority order)
        self._category_filters = [
            ("all", "All Cards"),
            ("manual", "Manual Entry"),
            ("high", "High Confidence"),
            ("needs_review", "Needs Review"),
            ("errors", "Errors"),
        ]
        self._category_keys = [f[0] for f in self._category_filters]

        # Folder filter state
        self._selected_folder_filters = ["all_folders"]
        self._folder_filters: list[tuple[str, str]] = []  # (key, label) pairs
        self._folder_keys: list[str] = []
        self._folder_disabled_keys: set[str] = set()

        self._build_ui()

    def _build_ui(self) -> None:
        """Build sidebar UI with category and folder sections."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Category section ---
        header = wx.StaticText(self, label="CONFIDENCE")
        header.SetFont(styles.Font.SECTION_HEADER())
        header.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(header, 0, wx.ALL, _SIDEBAR_PAD)

        self._category_checkboxes: list[wx.CheckBox] = []
        for key, label in self._category_filters:
            cb = wx.CheckBox(self, label=label)
            cb.Bind(wx.EVT_CHECKBOX, lambda evt, k=key: self._on_category_check(k))
            self._category_checkboxes.append(cb)
            sizer.Add(cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, _SIDEBAR_PAD)

        # Check "All Cards" by default; disable others until cards load
        self._category_checkboxes[0].SetValue(True)
        for cb in self._category_checkboxes[1:]:
            cb.Enable(False)

        # --- Folder section (hidden initially) ---
        self._folder_separator = wx.StaticLine(self)
        sizer.Add(self._folder_separator, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, _SIDEBAR_PAD)
        self._folder_separator.Hide()

        self._folder_header = wx.StaticText(self, label="FOLDERS")
        self._folder_header.SetFont(styles.Font.SECTION_HEADER())
        self._folder_header.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(self._folder_header, 0, wx.LEFT | wx.RIGHT, _SIDEBAR_PAD)
        self._folder_header.Hide()

        self._folder_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._folder_sizer, 0, wx.EXPAND)
        self._folder_checkboxes: list[wx.CheckBox] = []

        # --- Footer ---
        self.SetToolTip("Click to select a filter.\nOption-click to select multiple filters.")

        sizer.AddSpacer(_SIDEBAR_PAD)

        info = wx.StaticText(self, label="\u2325-click to multi-select")
        info.SetFont(styles.Font.SMALL())
        info.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(info, 0, wx.ALL, _SIDEBAR_PAD)

        # Push notification to bottom
        sizer.AddStretchSpacer()

        # Notification area
        self._notify_label = wx.StaticText(self, label="")
        self._notify_label.SetFont(styles.Font.SMALL())
        self._notify_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        self._notify_label.Wrap(_SIDEBAR_MIN_WIDTH - _NOTIFY_PAD)
        sizer.Add(self._notify_label, 0, wx.ALL, _SIDEBAR_PAD)
        self._notify_label.Hide()
        self._notify_timer: wx.CallLater | None = None

        self.SetSizer(sizer)
        self.SetMinSize((_SIDEBAR_MIN_WIDTH, -1))

    # --- Notification area ---

    def show_notification(self, message: str, icon: int = wx.ICON_INFORMATION, duration_ms: int = 4000) -> None:
        """Show a notification message at the bottom of the sidebar."""
        if self._notify_timer is not None:
            self._notify_timer.Stop()
            self._notify_timer = None
        if icon in (wx.ICON_WARNING, wx.ICON_ERROR):
            colour = styles.Color.ERROR
        else:
            colour = styles.Color.TEXT_SECONDARY
        self._notify_label.SetForegroundColour(colour)
        self._notify_label.SetLabel(message)
        self._notify_label.Wrap(self.GetClientSize().width - _NOTIFY_PAD)
        self._notify_label.Show()
        self.Layout()
        if duration_ms > 0:
            self._notify_timer = wx.CallLater(duration_ms, self.dismiss_notification)

    def dismiss_notification(self) -> None:
        """Hide the notification message."""
        if self._notify_timer is not None:
            self._notify_timer.Stop()
            self._notify_timer = None
        self._notify_label.SetLabel("")
        self._notify_label.Hide()
        self.Layout()

    # --- Shared click logic ---

    def _compute_new_selection(
        self,
        filter_key: str,
        all_key: str,
        checkboxes: list[wx.CheckBox],
        keys: list[str],
        option_held: bool,
    ) -> list[str]:
        """Compute new selection after a checkbox click (Finder-style).

        Regular click: select exclusively. Option+click: toggle multi-select.
        Updates checkbox visual state but does NOT fire callbacks.

        Returns:
            New selected list
        """
        idx = keys.index(filter_key)

        if filter_key == all_key:
            self._select_exclusive(checkboxes, 0)
            return [all_key]

        if option_held:
            if checkboxes[idx].GetValue():
                checkboxes[0].SetValue(False)

            new_selected = [keys[i] for i in range(1, len(keys)) if checkboxes[i].GetValue()]

            if not new_selected:
                checkboxes[0].SetValue(True)
                return [all_key]
            return new_selected

        self._select_exclusive(checkboxes, idx)
        return [filter_key]

    def _select_exclusive(self, checkboxes: list[wx.CheckBox], index: int) -> None:
        """Check only the checkbox at index, uncheck all others."""
        for i, cb in enumerate(checkboxes):
            cb.SetValue(i == index)

    # --- Category handlers ---

    def _on_category_check(self, filter_key: str, option_held: bool | None = None) -> None:
        """Handle category checkbox click."""
        if option_held is None:
            option_held = wx.GetKeyState(wx.WXK_ALT)

        # Update internal state BEFORE firing callback, so _refresh_display
        # sees the correct selection when it syncs from sidebar.
        self._selected_category_filters = self._compute_new_selection(
            filter_key,
            "all",
            self._category_checkboxes,
            self._category_keys,
            option_held,
        )
        self._on_category_filter(self._selected_category_filters)

    # --- Folder handlers ---

    def _on_folder_check(self, filter_key: str, option_held: bool | None = None) -> None:
        """Handle folder checkbox click."""
        if option_held is None:
            option_held = wx.GetKeyState(wx.WXK_ALT)

        # Update internal state BEFORE firing callback, so _refresh_display
        # sees the correct selection when it syncs from sidebar.
        self._selected_folder_filters = self._compute_new_selection(
            filter_key,
            "all_folders",
            self._folder_checkboxes,
            self._folder_keys,
            option_held,
        )
        self._on_folder_filter(self._selected_folder_filters)

    # --- Dynamic folder management ---

    def update_folders(self, folder_paths: list[Path]) -> None:
        """Rebuild folder checkboxes from current source folders.

        Shows folder section only when 2+ folders are present.
        Resets folder selection to ["all_folders"] on rebuild.

        Args:
            folder_paths: Sorted list of unique folder Path objects
        """
        # Destroy existing folder checkboxes
        for cb in self._folder_checkboxes:
            cb.Destroy()
        self._folder_checkboxes.clear()
        self._folder_sizer.Clear()

        if len(folder_paths) < 2:
            # Hide folder section
            self._folder_separator.Hide()
            self._folder_header.Hide()
            self._selected_folder_filters = ["all_folders"]
            self._folder_filters = []
            self._folder_keys = []
            self._folder_disabled_keys.clear()
            self.GetSizer().Layout()
            return

        # Build labels with disambiguation for colliding basenames
        basenames = [p.name for p in folder_paths]
        labels = []
        for _i, p in enumerate(folder_paths):
            if basenames.count(p.name) > 1:
                labels.append(f"{p.parent.name}/{p.name}")
            else:
                labels.append(p.name)

        # Build filter list: "All Folders" + one per folder
        self._folder_filters = [("all_folders", "All Folders")]
        for path, label in zip(folder_paths, labels, strict=False):
            self._folder_filters.append((str(path), label))
        self._folder_keys = [f[0] for f in self._folder_filters]

        # Show section
        self._folder_separator.Show()
        self._folder_header.Show()

        # Create checkboxes
        for key, label in self._folder_filters:
            cb = wx.CheckBox(self, label=label)
            cb.Bind(wx.EVT_CHECKBOX, lambda evt, k=key: self._on_folder_check(k))
            self._folder_checkboxes.append(cb)
            self._folder_sizer.Add(cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, _SIDEBAR_PAD)

        # Default: "All Folders" checked
        self._folder_checkboxes[0].SetValue(True)
        self._selected_folder_filters = ["all_folders"]
        self._folder_disabled_keys.clear()

        self.GetSizer().Layout()

    # --- Count updates (cross-filtered) ---

    def _apply_count_fallback(
        self,
        all_key: str,
        selected: list[str],
        disabled_keys: set[str],
        checkboxes: list[wx.CheckBox],
        keys: list[str],
    ) -> list[str]:
        """Reset selection to all_key if every selected filter was disabled.

        Returns:
            Updated selection list
        """
        if all_key in selected:
            return selected

        remaining = [k for k in selected if k not in disabled_keys]
        if not remaining:
            for cb in checkboxes:
                cb.SetValue(False)
            checkboxes[0].SetValue(True)
            return [all_key]
        if remaining != selected:
            return remaining
        return selected

    def update_category_counts(self, cards: list[CardResult]) -> None:
        """Update category counts and disable/enable accordingly.

        Args:
            cards: Cards filtered by search + folder selection (for cross-filtered counts)
        """
        counts = {
            "all": len(cards),
            "manual": sum(1 for c in cards if c.confidence == Confidence.MANUAL),
            "high": sum(1 for c in cards if c.confidence == Confidence.HIGH),
            "needs_review": sum(1 for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW)),
            "errors": sum(1 for c in cards if c.error or c.confidence == Confidence.NONE),
        }

        self._category_card_counts = counts
        self._category_disabled_keys.clear()

        for i, (key, base_label) in enumerate(self._category_filters):
            count = counts.get(key, 0)
            self._category_checkboxes[i].SetLabel(f"{base_label} ({count})")

            if key != "all" and count == 0:
                self._category_disabled_keys.add(key)
                self._category_checkboxes[i].SetValue(False)
                self._category_checkboxes[i].Enable(False)
            else:
                self._category_checkboxes[i].Enable(True)

        self._selected_category_filters = self._apply_count_fallback(
            "all",
            self._selected_category_filters,
            self._category_disabled_keys,
            self._category_checkboxes,
            self._category_keys,
        )

    def update_folder_counts(self, cards: list[CardResult]) -> None:
        """Update folder counts and disable/enable accordingly.

        Args:
            cards: Cards filtered by search + category selection (for cross-filtered counts)
        """
        if not self._folder_keys:
            return

        # Count cards per folder
        counts: dict[str, int] = {"all_folders": len(cards)}
        for key in self._folder_keys[1:]:  # skip "all_folders"
            folder_path = Path(key)
            counts[key] = sum(1 for c in cards if any(p.parent == folder_path for p in c.file_paths))

        self._folder_disabled_keys.clear()

        for i, (key, base_label) in enumerate(self._folder_filters):
            count = counts.get(key, 0)
            self._folder_checkboxes[i].SetLabel(f"{base_label} ({count})")

            if key != "all_folders" and count == 0:
                self._folder_disabled_keys.add(key)
                self._folder_checkboxes[i].SetValue(False)
                self._folder_checkboxes[i].Enable(False)
            else:
                self._folder_checkboxes[i].Enable(True)

        self._selected_folder_filters = self._apply_count_fallback(
            "all_folders",
            self._selected_folder_filters,
            self._folder_disabled_keys,
            self._folder_checkboxes,
            self._folder_keys,
        )

    # --- Public API ---

    def get_selected_category_filters(self) -> list[str]:
        """Get currently selected category filter keys."""
        return self._selected_category_filters

    def get_selected_folder_filters(self) -> list[str]:
        """Get currently selected folder filter keys."""
        return self._selected_folder_filters

    def set_category_filters(self, filter_keys: list[str]) -> None:
        """Programmatically set active category filters."""
        for cb in self._category_checkboxes:
            cb.SetValue(False)
        for key in filter_keys:
            if key in self._category_keys:
                index = self._category_keys.index(key)
                self._category_checkboxes[index].SetValue(True)
        self._selected_category_filters = filter_keys if filter_keys else ["all"]

    def refresh_colors(self) -> None:
        """Re-apply mode-dependent colors after an appearance change."""
        # Section headers and info labels use TEXT_SECONDARY
        for child in self.GetChildren():
            if isinstance(child, wx.StaticText) and child is not self._notify_label:
                child.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        # Notification label keeps its current color (may be ERROR)
        self.Refresh()

    def set_folder_filters(self, filter_keys: list[str]) -> None:
        """Programmatically set active folder filters."""
        for cb in self._folder_checkboxes:
            cb.SetValue(False)
        for key in filter_keys:
            if key in self._folder_keys:
                index = self._folder_keys.index(key)
                self._folder_checkboxes[index].SetValue(True)
        self._selected_folder_filters = filter_keys if filter_keys else ["all_folders"]
