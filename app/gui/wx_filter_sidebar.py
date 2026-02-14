"""wxPython Filter Sidebar for three-column Mail.app style layout."""

import wx
from pathlib import Path
from app.gui import wx_styles
from app.models.card import CardResult, Confidence


class FilterSidebar(wx.Panel):
    """Sidebar for filtering cards by confidence level, status, and source folder.

    Provides Mail.app style filtering with multi-select checkboxes:
    - Confidence section (always visible):
      - All Cards, Manual Entry, High Confidence, Needs Review, Errors
    - Folder section (visible when cards come from 2+ folders):
      - All Folders, one checkbox per source folder
    """

    def __init__(self, parent, on_category_filter, on_folder_filter=None):
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
        self._category_card_counts = {}
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

    def _build_ui(self):
        """Build sidebar UI with category and folder sections."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Category section ---
        header = wx.StaticText(self, label="CONFIDENCE")
        header.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        header.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(header, 0, wx.ALL, 10)

        self._category_checkboxes: list[wx.CheckBox] = []
        for key, label in self._category_filters:
            cb = wx.CheckBox(self, label=label)
            cb.Bind(wx.EVT_CHECKBOX, lambda evt, k=key: self._on_category_check(k))
            self._category_checkboxes.append(cb)
            sizer.Add(cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Check "All Cards" by default
        self._category_checkboxes[0].SetValue(True)

        # --- Folder section (hidden initially) ---
        self._folder_separator = wx.StaticLine(self)
        sizer.Add(self._folder_separator, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 10)
        self._folder_separator.Hide()

        self._folder_header = wx.StaticText(self, label="FOLDERS")
        self._folder_header.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self._folder_header.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(self._folder_header, 0, wx.LEFT | wx.RIGHT, 10)
        self._folder_header.Hide()

        self._folder_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._folder_sizer, 0, wx.EXPAND)
        self._folder_checkboxes: list[wx.CheckBox] = []

        # --- Footer ---
        self.SetToolTip(
            "Click to select a filter.\n"
            "Option-click to select multiple filters."
        )

        sizer.AddSpacer(10)

        info = wx.StaticText(self, label="\u2325-click to multi-select")
        info.SetFont(wx_styles.Font.SMALL())
        info.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(info, 0, wx.ALL, 10)

        self.SetSizer(sizer)
        self.SetMinSize((150, -1))

    # --- Shared click logic ---

    def _handle_check(self, filter_key, all_key, checkboxes, keys, selected_list, callback, option_held):
        """Shared Finder-style click handler for both category and folder sections.

        Regular click: select exclusively. Option+click: toggle multi-select.

        Args:
            filter_key: Key that was clicked
            all_key: The "all" key for this section ("all" or "all_folders")
            checkboxes: List of wx.CheckBox for this section
            keys: List of keys for this section
            selected_list: Current selection list (mutated in place via return)
            callback: Callback to fire with new selection
            option_held: Whether Option key is held

        Returns:
            New selected list
        """
        idx = keys.index(filter_key)

        if filter_key == all_key:
            self._select_exclusive(checkboxes, 0)
            new_selected = [all_key]
        elif option_held:
            is_checked = checkboxes[idx].GetValue()
            if is_checked:
                checkboxes[0].SetValue(False)

            new_selected = [
                keys[i]
                for i in range(1, len(keys))
                if checkboxes[i].GetValue()
            ]

            if not new_selected:
                checkboxes[0].SetValue(True)
                new_selected = [all_key]
        else:
            self._select_exclusive(checkboxes, idx)
            new_selected = [filter_key]

        callback(new_selected)
        return new_selected

    def _select_exclusive(self, checkboxes, index):
        """Check only the checkbox at index, uncheck all others."""
        for i, cb in enumerate(checkboxes):
            cb.SetValue(i == index)

    # --- Category handlers ---

    def _on_category_check(self, filter_key: str, option_held: bool | None = None):
        """Handle category checkbox click."""
        if option_held is None:
            option_held = wx.GetKeyState(wx.WXK_ALT)

        self._selected_category_filters = self._handle_check(
            filter_key, "all",
            self._category_checkboxes, self._category_keys,
            self._selected_category_filters,
            self._on_category_filter,
            option_held,
        )

    # --- Folder handlers ---

    def _on_folder_check(self, filter_key: str, option_held: bool | None = None):
        """Handle folder checkbox click."""
        if option_held is None:
            option_held = wx.GetKeyState(wx.WXK_ALT)

        self._selected_folder_filters = self._handle_check(
            filter_key, "all_folders",
            self._folder_checkboxes, self._folder_keys,
            self._selected_folder_filters,
            self._on_folder_filter,
            option_held,
        )

    # --- Dynamic folder management ---

    def update_folders(self, folder_paths: list[Path]):
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
        for i, p in enumerate(folder_paths):
            if basenames.count(p.name) > 1:
                labels.append(f"{p.parent.name}/{p.name}")
            else:
                labels.append(p.name)

        # Build filter list: "All Folders" + one per folder
        self._folder_filters = [("all_folders", "All Folders")]
        for path, label in zip(folder_paths, labels):
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
            self._folder_sizer.Add(cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Default: "All Folders" checked
        self._folder_checkboxes[0].SetValue(True)
        self._selected_folder_filters = ["all_folders"]
        self._folder_disabled_keys.clear()

        self.GetSizer().Layout()

    # --- Count updates (cross-filtered) ---

    def update_category_counts(self, cards: list[CardResult]):
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

        # Fallback if all selected went to zero
        if "all" not in self._selected_category_filters:
            remaining = [k for k in self._selected_category_filters if k not in self._category_disabled_keys]
            if not remaining:
                for i in range(len(self._category_keys)):
                    self._category_checkboxes[i].SetValue(False)
                self._category_checkboxes[0].SetValue(True)
                self._selected_category_filters = ["all"]
                self._on_category_filter(self._selected_category_filters)
            elif remaining != self._selected_category_filters:
                self._selected_category_filters = remaining

    def update_folder_counts(self, cards: list[CardResult]):
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
            counts[key] = sum(
                1 for c in cards
                if any(p.parent == folder_path for p in c.file_paths)
            )

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

        # Fallback if all selected went to zero
        if "all_folders" not in self._selected_folder_filters:
            remaining = [k for k in self._selected_folder_filters if k not in self._folder_disabled_keys]
            if not remaining:
                for i in range(len(self._folder_keys)):
                    self._folder_checkboxes[i].SetValue(False)
                self._folder_checkboxes[0].SetValue(True)
                self._selected_folder_filters = ["all_folders"]
                self._on_folder_filter(self._selected_folder_filters)
            elif remaining != self._selected_folder_filters:
                self._selected_folder_filters = remaining

    # --- Public API ---

    def get_selected_category_filters(self) -> list[str]:
        """Get currently selected category filter keys."""
        return self._selected_category_filters

    def get_selected_folder_filters(self) -> list[str]:
        """Get currently selected folder filter keys."""
        return self._selected_folder_filters

    def set_category_filters(self, filter_keys: list[str]):
        """Programmatically set active category filters."""
        for cb in self._category_checkboxes:
            cb.SetValue(False)
        for key in filter_keys:
            if key in self._category_keys:
                index = self._category_keys.index(key)
                self._category_checkboxes[index].SetValue(True)
        self._selected_category_filters = filter_keys if filter_keys else ["all"]

    def set_folder_filters(self, filter_keys: list[str]):
        """Programmatically set active folder filters."""
        for cb in self._folder_checkboxes:
            cb.SetValue(False)
        for key in filter_keys:
            if key in self._folder_keys:
                index = self._folder_keys.index(key)
                self._folder_checkboxes[index].SetValue(True)
        self._selected_folder_filters = filter_keys if filter_keys else ["all_folders"]

    # --- Backward compat aliases ---

    def get_selected_filters(self) -> list[str]:
        """Alias for get_selected_category_filters (backward compat)."""
        return self.get_selected_category_filters()

    def set_filters(self, filter_keys: list[str]):
        """Alias for set_category_filters (backward compat)."""
        self.set_category_filters(filter_keys)

    def update_card_counts(self, cards: list[CardResult]):
        """Alias for update_category_counts (backward compat)."""
        self.update_category_counts(cards)
