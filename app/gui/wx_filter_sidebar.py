"""wxPython Filter Sidebar for three-column Mail.app style layout."""

import wx
from app.gui import wx_styles
from app.models.card import CardResult, Confidence


class FilterSidebar(wx.Panel):
    """Sidebar for filtering cards by confidence level and status.

    Provides Mail.app style filtering with multi-select checkboxes:
    - All Cards (clears others when selected)
    - Manual Entry
    - High Confidence (green)
    - Needs Review (yellow/red)
    - Errors (failed to process)
    """

    def __init__(self, parent, on_filter):
        """Initialize filter sidebar.

        Args:
            parent: Parent window
            on_filter: Callback function(selected_filters: list[str]) called when filters change
        """
        super().__init__(parent)
        self._on_filter = on_filter
        self._selected_filters = ["all"]  # Default to "all"
        self._card_counts = {}  # Track card count per category
        self._disabled_keys: set[str] = set()  # Zero-count filter keys

        # Filter definitions (in priority order)
        self._filters = [
            ("all", "All Cards"),
            ("manual", "Manual Entry"),
            ("high", "High Confidence"),
            ("needs_review", "Needs Review"),
            ("errors", "Errors"),
        ]

        self._filter_keys = [f[0] for f in self._filters]

        self._build_ui()

    def _build_ui(self):
        """Build sidebar UI with individual checkboxes for per-item enable/disable."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(self, label="FILTERS")
        header.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        header.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(header, 0, wx.ALL, 10)

        # Individual checkboxes (enables native grayed-out appearance per item)
        self._checkboxes: list[wx.CheckBox] = []
        for key, label in self._filters:
            cb = wx.CheckBox(self, label=label)
            cb.Bind(wx.EVT_CHECKBOX, lambda evt, k=key: self._on_check_change_key(k))
            self._checkboxes.append(cb)
            sizer.Add(cb, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Check "All Cards" by default
        self._checkboxes[0].SetValue(True)

        self.SetToolTip(
            "Click to select a filter.\n"
            "Option-click to select multiple filters."
        )

        sizer.AddSpacer(10)

        # Info text at bottom
        info = wx.StaticText(self, label="⌥-click to multi-select")
        info.SetFont(wx_styles.Font.SMALL())
        info.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(info, 0, wx.ALL, 10)

        self.SetSizer(sizer)
        self.SetMinSize((150, -1))

    def _on_check_change_key(self, filter_key: str, option_held: bool | None = None):
        """Handle checkbox change with Finder-style click behavior.

        Regular click: select this filter exclusively.
        Option+click: toggle this filter in/out of a multi-selection.

        Args:
            filter_key: The filter key that was clicked
            option_held: Override for Option key state (for testing; None = detect)
        """
        if option_held is None:
            option_held = wx.GetKeyState(wx.WXK_ALT)

        idx = self._filter_keys.index(filter_key)

        if filter_key == "all":
            # "All Cards" always selects exclusively
            self._select_exclusive(0)
            self._selected_filters = ["all"]
        elif option_held:
            # Option+click: toggle in/out of multi-selection
            is_checked = self._checkboxes[idx].GetValue()  # already toggled by wx

            if is_checked:
                # Adding — uncheck "All Cards"
                self._checkboxes[0].SetValue(False)
            else:
                # Removing — if nothing left, fall back to "All Cards"
                pass

            self._selected_filters = [
                self._filter_keys[i]
                for i in range(1, len(self._filter_keys))
                if self._checkboxes[i].GetValue()
            ]

            if not self._selected_filters:
                self._checkboxes[0].SetValue(True)
                self._selected_filters = ["all"]
        else:
            # Regular click: exclusive selection of this filter
            self._select_exclusive(idx)
            self._selected_filters = [filter_key]

        self._on_filter(self._selected_filters)

    def _select_exclusive(self, index: int):
        """Check only the checkbox at index, uncheck all others."""
        for i, cb in enumerate(self._checkboxes):
            cb.SetValue(i == index)

    def update_card_counts(self, cards: list[CardResult]):
        """Update card counts for each category and disable/enable accordingly.

        Args:
            cards: List of all cards to count
        """
        # Count cards in each category
        counts = {
            "all": len(cards),
            "manual": sum(1 for c in cards if c.confidence == Confidence.MANUAL),
            "high": sum(1 for c in cards if c.confidence == Confidence.HIGH),
            "needs_review": sum(1 for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW)),
            "errors": sum(1 for c in cards if c.error or c.confidence == Confidence.NONE),
        }

        self._card_counts = counts

        # Update labels, enable/disable, and track disabled keys
        self._disabled_keys.clear()
        for i, (key, base_label) in enumerate(self._filters):
            count = counts.get(key, 0)
            self._checkboxes[i].SetLabel(f"{base_label} ({count})")

            # Disable zero-count categories (except "All Cards")
            if key != "all" and count == 0:
                self._disabled_keys.add(key)
                self._checkboxes[i].SetValue(False)
                self._checkboxes[i].Enable(False)
            else:
                self._checkboxes[i].Enable(True)

        # If all selected filters went to zero, fall back to "All Cards"
        if "all" not in self._selected_filters:
            remaining = [k for k in self._selected_filters if k not in self._disabled_keys]
            if not remaining:
                for i in range(len(self._filter_keys)):
                    self._checkboxes[i].SetValue(False)
                self._checkboxes[0].SetValue(True)
                self._selected_filters = ["all"]
                self._on_filter(self._selected_filters)
            elif remaining != self._selected_filters:
                self._selected_filters = remaining

    def get_selected_filters(self) -> list[str]:
        """Get currently selected filter keys.

        Returns:
            List of filter keys: ["all"], ["high", "manual"], etc.
        """
        return self._selected_filters

    def set_filters(self, filter_keys: list[str]):
        """Programmatically set active filters.

        Args:
            filter_keys: List of filter keys to activate
        """
        # Clear all checks
        for cb in self._checkboxes:
            cb.SetValue(False)

        # Check specified filters
        for key in filter_keys:
            if key in self._filter_keys:
                index = self._filter_keys.index(key)
                self._checkboxes[index].SetValue(True)

        self._selected_filters = filter_keys if filter_keys else ["all"]
