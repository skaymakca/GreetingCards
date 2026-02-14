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
        """Build sidebar UI with native checkbox list control."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(self, label="FILTERS")
        header.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        header.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(header, 0, wx.ALL, 10)

        # Native checkbox list control (multi-select)
        self._checklist = wx.CheckListBox(
            self,
            choices=[label for _, label in self._filters],
            style=wx.LB_NEEDED_SB
        )
        self._checklist.Check(0)  # Check "All Cards" by default
        self._checklist.Bind(wx.EVT_CHECKLISTBOX, self._on_check_change)

        self._checklist.SetToolTip(
            "Select one or more categories to filter cards.\n"
            "All Cards clears other selections."
        )

        sizer.Add(self._checklist, 1, wx.EXPAND | wx.ALL, 5)

        # Info text at bottom
        info = wx.StaticText(self, label="Tip: Use ⌘F to search")
        info.SetFont(wx_styles.Font.SMALL())
        info.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(info, 0, wx.ALL, 10)

        self.SetSizer(sizer)
        self.SetMinSize((150, -1))

    def _on_check_change(self, event):
        """Handle checkbox change.

        Args:
            event: wx.EVT_CHECKLISTBOX event
        """
        checked_index = event.GetSelection()
        is_checked = self._checklist.IsChecked(checked_index)
        filter_key = self._filter_keys[checked_index]

        # Special handling for "All Cards"
        if filter_key == "all":
            if is_checked:
                # "All Cards" selected - uncheck all others
                for i in range(len(self._filter_keys)):
                    if i != 0:  # Don't uncheck "All Cards" itself
                        self._checklist.Check(i, False)
                self._selected_filters = ["all"]
            else:
                # If "All Cards" unchecked and nothing else checked, re-check it
                if not any(self._checklist.IsChecked(i) for i in range(1, len(self._filter_keys))):
                    self._checklist.Check(0, True)
                    self._selected_filters = ["all"]
                else:
                    self._selected_filters = [
                        self._filter_keys[i]
                        for i in range(1, len(self._filter_keys))
                        if self._checklist.IsChecked(i)
                    ]
        else:
            # Other filter selected - uncheck "All Cards"
            if is_checked:
                self._checklist.Check(0, False)

            # Get all checked filters (excluding "All Cards")
            self._selected_filters = [
                self._filter_keys[i]
                for i in range(1, len(self._filter_keys))
                if self._checklist.IsChecked(i)
            ]

            # If nothing selected, re-check "All Cards"
            if not self._selected_filters:
                self._checklist.Check(0, True)
                self._selected_filters = ["all"]

        # Notify parent with list of selected filters
        self._on_filter(self._selected_filters)

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

        # Update labels with counts and enable/disable
        for i, (key, base_label) in enumerate(self._filters):
            count = counts.get(key, 0)
            label = f"{base_label} ({count})"
            self._checklist.SetString(i, label)

            # Disable if count is 0 (except "All Cards")
            if key != "all" and count == 0:
                # Can't directly disable individual items in CheckListBox
                # But we can uncheck them if they were checked
                if self._checklist.IsChecked(i):
                    self._checklist.Check(i, False)

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
        for i in range(len(self._filter_keys)):
            self._checklist.Check(i, False)

        # Check specified filters
        for key in filter_keys:
            if key in self._filter_keys:
                index = self._filter_keys.index(key)
                self._checklist.Check(index, True)

        self._selected_filters = filter_keys if filter_keys else ["all"]
