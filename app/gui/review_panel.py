"""Master-Detail Review Panel - Prototype.

Mac-native pattern with DataViewCtrl list and separate detail panel for editing.
More native than scrollable rows, better performance, cleaner code.

Layout:
    ┌─────────────────────────┐
    │ Master List (DataView)  │  ← Select card
    │ • filename              │
    │ • confidence dot        │
    │ • family name           │
    ├─────────────────────────┤
    │ Detail Panel            │  ← Edit selected
    │ [Name: ____________]    │
    │ ☐ Remove Family         │
    │ [Candidates ▾]          │
    │ [✨ AI]                 │
    └─────────────────────────┘

Benefits:
- Native macOS pattern (like Mail.app, Finder)
- Built-in selection, scrolling, keyboard nav
- Better performance (1 set of controls vs 100)
- Cleaner code
"""

import logging
import subprocess
from typing import Callable
from pathlib import Path

import wx
import wx.dataview as dv

logger = logging.getLogger(__name__)
from app.models.card import CardResult, Confidence
from app.gui.styles import Color, Font, Layout
from app.gui.utils import create_static_text
from app.gui.icons import load_sf_symbol, load_menu_icon
from app.gui.context_menu import add_entry_context_menu


class _ConfidenceLegendPopup(wx.PopupWindow):
    """Styled popup showing confidence legend with colored dots."""

    def __init__(self, parent):
        super().__init__(parent, wx.BORDER_SIMPLE)
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        rows = [
            ("●", Color.SUCCESS, "High — strong pattern match or AI result"),
            ("●", Color.WARNING, "Medium — partial pattern match"),
            ("●", Color.ERROR, "Low — weak/fallback match"),
            ("●", Color.MANUAL_BLUE, "Manual — manually entered name"),
            ("⚠", Color.TEXT_SECONDARY, "No name extracted"),
            ("✕", Color.ERROR, "Error during analysis"),
        ]

        for symbol, colour, label_text in rows:
            row_sizer = wx.BoxSizer(wx.HORIZONTAL)
            symbol_st = wx.StaticText(panel, label=symbol)
            symbol_st.SetForegroundColour(colour)
            symbol_st.SetFont(Font.SMALL())
            row_sizer.Add(symbol_st, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

            label_st = wx.StaticText(panel, label=label_text)
            label_st.SetForegroundColour(Color.TEXT_PRIMARY)
            label_st.SetFont(Font.SMALL())
            row_sizer.Add(label_st, 0, wx.ALIGN_CENTER_VERTICAL)

            sizer.Add(row_sizer, 0, wx.ALL, 2)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND | wx.ALL, Layout.PAD)
        self.SetSizerAndFit(outer)


class CardListModel(dv.PyDataViewModel):
    """Data model for the card list (master view).

    Columns: [Confidence Dot, Filename, Family Name]
    """

    def __init__(self):
        super().__init__()
        self._cards: list[CardResult] = []
        self._card_order: list[int] = []  # Card IDs in display order

    def load_cards(self, cards: list[CardResult]) -> None:
        """Load cards into the model."""
        self._cards = cards
        self._card_order = [card.id for card in cards]
        self.Cleared()  # Notify view to refresh

    def get_card_by_item(self, item: dv.DataViewItem) -> CardResult | None:
        """Get CardResult from DataViewItem."""
        if not item.IsOk():
            return None
        row = self.ItemToObject(item)
        if 0 <= row < len(self._cards):
            return self._cards[row]
        return None

    def get_item_by_card_id(self, card_id: int) -> dv.DataViewItem:
        """Get DataViewItem for a card ID."""
        for i, card in enumerate(self._cards):
            if card.id == card_id:
                return self.ObjectToItem(i)
        return dv.NullDataViewItem

    def update_card(self, card_id: int, updated_card: CardResult) -> None:
        """Update a card in the model."""
        for i, card in enumerate(self._cards):
            if card.id == card_id:
                self._cards[i] = updated_card
                item = self.ObjectToItem(i)
                self.ItemChanged(item)
                break

    @property
    def card_count(self) -> int:
        """Return number of cards in the model."""
        return len(self._cards)

    @property
    def card_order(self) -> list[int]:
        """Return card IDs in display order."""
        return list(self._card_order)

    # PyDataViewModel interface
    def GetColumnCount(self) -> int:
        """3 columns: dot, filename, family name."""
        return 3

    def GetColumnType(self, col: int) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        """All columns return strings (we'll use custom renderer for dot)."""
        return "string"

    def GetChildren(self, parent, children) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Flat list - root has all cards, cards have no children."""
        if not parent.IsOk():  # Root
            for i in range(len(self._cards)):
                children.append(self.ObjectToItem(i))
            return len(self._cards)
        return 0  # Cards have no children

    def IsContainer(self, item) -> bool:
        """Only root is container."""
        return not item.IsOk()

    def GetParent(self, item) -> dv.DataViewItem:
        """All items are children of root."""
        return dv.NullDataViewItem

    def GetValue(self, item, col) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Return value for cell."""
        row = self.ItemToObject(item)
        if row < 0 or row >= len(self._cards):
            return ""

        card = self._cards[row]

        match col:
            case 0:  # Confidence dot
                match card:
                    case CardResult(error=e) if e:
                        return "✕"
                    case CardResult(confidence=Confidence.NONE):
                        return "⚠"
                    case _:
                        return "●"
            case 1:  # Filename
                return card.filename
            case 2:  # Family name
                return card.display_name
            case _:
                return ""

    def SetValue(self, value, item, col) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Not editable in list (edit in detail panel)."""
        return False

    def GetAttr(self, item, col, attr) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Set color for confidence dot and filename (blue for multi-path cards)."""
        row = self.ItemToObject(item)
        if row < 0 or row >= len(self._cards):
            return False

        card = self._cards[row]

        match col:
            case 0:  # Confidence dot color
                match card:
                    case CardResult(error=e) if e:
                        attr.SetColour(Color.ERROR)
                    case CardResult(confidence=Confidence.NONE):
                        attr.SetColour(Color.TEXT_SECONDARY)
                    case CardResult(confidence=Confidence.HIGH):
                        attr.SetColour(Color.SUCCESS)
                    case CardResult(confidence=Confidence.MEDIUM):
                        attr.SetColour(Color.WARNING)
                    case CardResult(confidence=Confidence.LOW):
                        attr.SetColour(Color.ERROR)
                    case CardResult(confidence=Confidence.MANUAL):
                        attr.SetColour(Color.MANUAL_BLUE)
                    case _:
                        attr.SetColour(Color.TEXT_PRIMARY)
                return True

            case 1:  # Filename - blue for multi-path cards
                if len(card.file_paths) > 1:
                    attr.SetColour(Color.ACCENT)
                    return True
                return False

        return False


class DetailPanel(wx.Panel):
    """Detail panel for editing the selected card.

    Shows edit controls for: name, remove_family checkbox, candidates, AI button.
    """

    def __init__(
        self,
        parent,
        on_name_change: Callable[[int, str], None] | None,
        on_checkbox_toggle: Callable[[int, bool], None] | None,
        on_candidate_select: Callable[[int, int], None] | None,
        on_ai_request: Callable[[int], None] | None,
        on_remove: Callable[[str], None] | None = None,
    ):
        super().__init__(parent)
        self._on_name_change = on_name_change
        self._on_checkbox_toggle = on_checkbox_toggle
        self._on_candidate_select = on_candidate_select
        self._on_ai_request = on_ai_request
        self._on_remove = on_remove
        self._current_card: CardResult | None = None
        self._suppress_events = False
        self._candidate_map: dict[str, int] = {}

        self._build_ui()
        self.clear()

    def _make_action_button(self, icon_name: str, label: str, handler) -> wx.Button:
        """Create a compact action button with an SF Symbol icon."""
        icon = load_sf_symbol(icon_name, Layout.ACTION_ICON_SIZE)
        if icon:
            btn = wx.Button(self._edit_panel, label=f"  {label}")
            btn.SetBitmap(icon)
        else:
            btn = wx.Button(self._edit_panel, label=label)
        btn.SetFont(Font.BODY())
        btn.SetMinSize(wx.Size(-1, Layout.BUTTON_HEIGHT))
        btn.Bind(wx.EVT_BUTTON, handler)
        return btn

    def _build_ui(self) -> None:
        """Build the detail panel UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Create notebook for tabs (no title/separator - filename shown in tab)
        self._notebook = wx.Notebook(self)

        # === EDIT TAB (always present) ===
        self._edit_panel = wx.Panel(self._notebook)
        edit_sizer = wx.BoxSizer(wx.VERTICAL)

        edit_sizer.AddSpacer(Layout.PAD)

        # Family Name (editable)
        name_label = create_static_text(
            self._edit_panel,
            "Family Name:",
            font=Font.SMALL(),
            colour=Color.TEXT_SECONDARY
        )
        edit_sizer.Add(name_label, 0, wx.LEFT | wx.RIGHT, Layout.PAD)

        self._name_text = wx.TextCtrl(self._edit_panel, style=wx.TE_PROCESS_ENTER)
        self._name_text.SetFont(Font.BODY())
        self._name_text.Bind(wx.EVT_CHAR, self._on_name_char)
        self._name_text.Bind(wx.EVT_TEXT, self._on_name_edit)
        self._name_text.Bind(wx.EVT_TEXT_ENTER, lambda e: self._name_text.Navigate())
        add_entry_context_menu(self._name_text)
        edit_sizer.Add(self._name_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, Layout.PAD)

        # Candidates dropdown (moved directly below Family Name)
        cand_label = create_static_text(
            self._edit_panel,
            "Alternative Candidates:",
            font=Font.SMALL(),
            colour=Color.TEXT_SECONDARY
        )
        edit_sizer.Add(cand_label, 0, wx.LEFT | wx.RIGHT, Layout.PAD)

        self._candidates_choice = wx.Choice(self._edit_panel)
        self._candidates_choice.SetFont(Font.BODY())
        self._candidates_choice.Bind(wx.EVT_CHOICE, self._on_candidate)
        edit_sizer.Add(self._candidates_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, Layout.PAD)

        # Horizontal row: AI button, Remove button, Remove Family checkbox
        action_row = wx.BoxSizer(wx.HORIZONTAL)

        self._ai_btn = self._make_action_button("sparkles", "AI Analyze", self._on_ai)
        action_row.Add(self._ai_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        action_row.AddSpacer(Layout.PAD)

        self._remove_btn = self._make_action_button("minus.circle", "Remove", self._on_remove_click)
        action_row.Add(self._remove_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        action_row.AddSpacer(Layout.PAD * 2)

        # Remove Family checkbox
        self._remove_family_check = wx.CheckBox(self._edit_panel, label="Remove 'Family' from File Name")
        self._remove_family_check.SetFont(Font.BODY())
        self._remove_family_check.Bind(wx.EVT_CHECKBOX, self._on_checkbox)
        action_row.Add(self._remove_family_check, 0, wx.ALIGN_CENTER_VERTICAL)

        edit_sizer.Add(action_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, Layout.PAD)

        self._edit_panel.SetSizer(edit_sizer)
        self._notebook.AddPage(self._edit_panel, "Edit")

        # === FILE PATHS TAB (only added for multi-path cards) ===
        self._locations_panel = wx.Panel(self._notebook)
        locations_sizer = wx.BoxSizer(wx.VERTICAL)

        locations_sizer.AddSpacer(Layout.PAD)

        # Header
        self._locations_header = create_static_text(
            self._locations_panel,
            "File Locations:",
            font=Font.BODY(),
            colour=Color.TEXT_PRIMARY
        )
        locations_sizer.Add(self._locations_header, 0, wx.ALL, Layout.PAD)

        # List of file paths
        self._locations_list = dv.DataViewListCtrl(
            self._locations_panel,
            style=dv.DV_NO_HEADER | dv.DV_SINGLE | dv.DV_ROW_LINES
        )
        self._locations_list.AppendTextColumn("", width=Layout.FILE_PATHS_COL_WIDTH)
        self._locations_list.SetMinSize((-1, 100))
        locations_sizer.Add(self._locations_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, Layout.PAD)

        # Info text (for multiple paths)
        self._duplicate_info = create_static_text(
            self._locations_panel,
            "ℹ️ These files have identical content (same hash).",
            font=Font.SMALL(),
            colour=Color.TEXT_SECONDARY
        )
        locations_sizer.Add(self._duplicate_info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, Layout.PAD)

        self._locations_panel.SetSizer(locations_sizer)
        self._locations_panel.Hide()

        # Track whether locations tab is currently added
        self._locations_tab_index = None

        # Add notebook to main sizer
        sizer.Add(self._notebook, 1, wx.EXPAND | wx.ALL, Layout.PAD)

        self.SetSizer(sizer)

        # Fit to minimum size needed
        sizer.Fit(self)
        self.SetMinSize(self.GetSize())

    def load_card(self, card: CardResult | None) -> None:
        """Load a card into the detail panel."""
        self._current_card = card
        self._suppress_events = True

        if card is None:
            self.clear()
            self._suppress_events = False
            return

        # Edit tab always labeled "Edit Card"
        self._notebook.SetPageText(0, "Edit Card")

        # Update controls
        self._name_text.SetValue(card.display_name)
        self._remove_family_check.SetValue(card.remove_family)

        # Populate candidates
        self._candidates_choice.Clear()
        self._candidate_map = {}
        if card.candidates:
            for cand in card.candidates:
                label = f"{cand.family_name} ({cand.method.upper()} - {cand.confidence.capitalize()})"
                self._candidates_choice.Append(label)
                self._candidate_map[label] = cand.id
            placeholder = f"Select from {len(card.candidates)} candidate{'s' if len(card.candidates) != 1 else ''}"
            self._candidates_choice.Insert(placeholder, 0)
            self._candidates_choice.SetSelection(0)
            self._candidates_choice.Enable()
        else:
            self._candidates_choice.Append("No candidates available")
            self._candidates_choice.SetSelection(0)
            self._candidates_choice.Enable(False)

        # Enable/disable based on error state
        has_error = bool(card.error)
        self._name_text.Enable(not has_error)
        self._remove_family_check.Enable(not has_error)
        self._ai_btn.Enable(not has_error)
        self._remove_btn.Enable(True)

        # Update file locations section
        self._update_locations(card)

        self._suppress_events = False

    def _update_locations(self, card: CardResult) -> None:
        """Update the file locations tab (always shown)."""
        num_paths = len(card.file_paths)

        # Update header
        plural = "copies" if num_paths > 1 else "copy"
        self._locations_header.SetLabel(f"File Locations ({num_paths} {plural}):")

        # Populate list
        self._locations_list.DeleteAllItems()
        for path in card.file_paths:
            # Show relative path from home if possible
            try:
                rel_path = path.relative_to(Path.home())
                display_path = f"~/{rel_path}"
            except ValueError:
                display_path = str(path)

            self._locations_list.AppendItem([display_path])

        # Highlight primary path (first one)
        if num_paths > 0:
            self._locations_list.SelectRow(0)

        # Add/update File Paths tab (always present now)
        if self._locations_tab_index is None:
            self._locations_panel.Show()
            self._notebook.AddPage(
                self._locations_panel,
                f"File Paths ({num_paths})"
            )
            self._locations_tab_index = self._notebook.GetPageCount() - 1
        else:
            # Update tab label
            self._notebook.SetPageText(self._locations_tab_index, f"File Paths ({num_paths})")

    def clear(self) -> None:
        """Clear the detail panel (no card selected)."""
        # Reset current card first to prevent any event handlers from using it
        self._current_card = None
        self._suppress_events = True

        self._name_text.SetValue("")
        self._name_text.Enable(False)
        self._remove_family_check.SetValue(False)
        self._remove_family_check.Enable(False)
        self._candidates_choice.Clear()
        self._candidates_choice.Append("No card selected")
        self._candidates_choice.SetSelection(0)
        self._candidates_choice.Enable(False)
        self._ai_btn.Enable(False)
        self._remove_btn.Enable(False)

        # Clear file locations and remove tab if present
        self._locations_list.DeleteAllItems()
        if self._locations_tab_index is not None:
            self._notebook.RemovePage(self._locations_tab_index)
            self._locations_tab_index = None
            self._locations_panel.Hide()

        # Reset Edit tab to default label (do this after removing File Paths tab)
        if self._notebook.GetPageCount() > 0:
            self._notebook.SetPageText(0, "Edit Card")

        self._suppress_events = False

    def enable_ai_button(self, enable: bool) -> None:
        """Enable or disable the AI analyze button."""
        self._ai_btn.Enable(enable)

    def _on_name_char(self, event: wx.KeyEvent) -> None:
        """Block filesystem-invalid characters from being typed."""
        from app.core.name_formatting import INVALID_FILENAME_CHARS
        key = event.GetUnicodeKey()
        if key != wx.WXK_NONE and chr(key) in INVALID_FILENAME_CHARS:
            return  # Swallow the keystroke
        event.Skip()

    def _on_name_edit(self, event) -> None:
        """Handle name text change."""
        if self._suppress_events or not self._current_card:
            return

        new_name = self._name_text.GetValue()
        self._current_card.manual_override = new_name

        if self._on_name_change:
            self._on_name_change(self._current_card.id, new_name)

    def _on_checkbox(self, event) -> None:
        """Handle checkbox toggle."""
        if self._suppress_events or not self._current_card:
            return

        new_value = self._remove_family_check.GetValue()
        self._current_card.remove_family = new_value

        if self._on_checkbox_toggle:
            self._on_checkbox_toggle(self._current_card.id, new_value)

    def _on_candidate(self, event) -> None:
        """Handle candidate selection."""
        if self._suppress_events or not self._current_card:
            return

        selection = self._candidates_choice.GetSelection()
        if selection <= 0:  # Placeholder selected
            return

        label = self._candidates_choice.GetString(selection)
        candidate_id = self._candidate_map.get(label)

        if candidate_id is not None and self._on_candidate_select:
            self._on_candidate_select(self._current_card.id, candidate_id)

    def _on_ai(self, event) -> None:
        """Handle AI button click."""
        if not self._current_card:
            return

        if self._on_ai_request:
            self._on_ai_request(self._current_card.id)

    def _on_remove_click(self, event) -> None:
        """Handle Remove button click."""
        if not self._current_card:
            return

        if self._on_remove and self._current_card.file_hash:
            self._on_remove(self._current_card.file_hash)


class ReviewPanelMasterDetail(wx.Panel):
    """Master-Detail Review Panel - Mac-native pattern.

    Public API matches original ReviewPanel for easy drop-in replacement.
    """

    def __init__(
        self,
        parent,
        on_select: Callable[[int | None], None],
        on_ai_request: Callable[[int], None],
        on_name_change: Callable[[int, str], None] | None = None,
        on_card_edited: Callable[[int], None] | None = None,
        on_remove: Callable[[str], None] | None = None,
    ):
        super().__init__(parent)
        self._on_select = on_select
        self._on_ai_request = on_ai_request
        self._on_name_change = on_name_change
        self._on_card_edited = on_card_edited
        self._on_remove = on_remove
        self._selected_card_ids: list[int] = []
        self._cards_by_id: dict[int, CardResult] = {}
        self._drag_highlight = False

        self._build_ui()
        self.Bind(wx.EVT_PAINT, self._on_paint_highlight)

    def _build_ui(self) -> None:
        """Build master-detail UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header with count
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        heading = create_static_text(
            self,
            "CARDS",
            font=Font.SECTION_HEADER(),
            colour=Color.TEXT_SECONDARY
        )
        header_sizer.Add(heading, 0, wx.ALIGN_CENTER_VERTICAL)
        header_sizer.AddStretchSpacer()

        self._count_label = create_static_text(
            self,
            "",
            font=Font.SMALL(),
            colour=Color.TEXT_SECONDARY
        )
        header_sizer.Add(self._count_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self._count_label.Bind(wx.EVT_ENTER_WINDOW, self._on_legend_hover)
        self._count_label.Bind(wx.EVT_LEAVE_WINDOW, self._on_legend_leave)
        self._legend_popup = None

        sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, Layout.PAD)

        # Splitter for master-detail
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        self._splitter = splitter

        # Master: DataViewCtrl
        self._list_ctrl = dv.DataViewCtrl(
            splitter,
            style=dv.DV_MULTIPLE | dv.DV_ROW_LINES | dv.DV_VERT_RULES
        )

        # Create model
        self._model = CardListModel()
        self._list_ctrl.AssociateModel(self._model)

        # Add columns
        self._list_ctrl.AppendTextColumn("", 0, width=Layout.DOT_COL_WIDTH, mode=dv.DATAVIEW_CELL_INERT)
        self._list_ctrl.AppendTextColumn("File Name", 1, width=Layout.FILENAME_COL_WIDTH, mode=dv.DATAVIEW_CELL_INERT)
        self._list_ctrl.AppendTextColumn("Family Name", 2, width=Layout.FAMILY_NAME_COL_WIDTH, mode=dv.DATAVIEW_CELL_INERT)

        # Bind selection event
        self._list_ctrl.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_selection_changed)

        # Bind context menu event
        self._list_ctrl.Bind(dv.EVT_DATAVIEW_ITEM_CONTEXT_MENU, self._on_context_menu)

        # Detail: Edit panel
        self._detail_panel = DetailPanel(
            splitter,
            on_name_change=self._handle_name_change,
            on_checkbox_toggle=self._handle_checkbox,
            on_candidate_select=self._handle_candidate,
            on_ai_request=self._on_ai_request,
            on_remove=self._on_remove,
        )

        # Split horizontally (master on top, detail on bottom)
        splitter.SplitHorizontally(self._list_ctrl, self._detail_panel)
        splitter.SetSashGravity(1.0)  # Give all extra space to master list
        splitter.SetMinimumPaneSize(Layout.MIN_PANE_SIZE)

        sizer.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, Layout.PAD)

        self.SetSizer(sizer)

        # Bind keyboard navigation
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

        # After layout, position sash to give detail panel just what it needs
        self.Bind(wx.EVT_SIZE, self._on_panel_size, id=wx.ID_ANY)
        self._initial_sash_set = False

    def _on_legend_hover(self, event) -> None:
        """Show confidence legend popup on hover."""
        if self._legend_popup is not None:
            return
        popup = _ConfidenceLegendPopup(self)
        label = self._count_label
        pos = label.ClientToScreen(wx.Point(0, label.GetSize().height + 2))
        popup.SetPosition(pos)
        popup.Show()
        self._legend_popup = popup

    def _on_legend_leave(self, event) -> None:
        """Hide confidence legend popup when mouse leaves."""
        if self._legend_popup is not None:
            self._legend_popup.Destroy()
            self._legend_popup = None

    def _on_panel_size(self, event) -> None:
        """Set initial sash position to give detail panel minimum space."""
        if not self._initial_sash_set and self.GetSize().GetHeight() > 100:
            # Get the splitter (it's in our sizer)
            for child in self.GetChildren():
                if isinstance(child, wx.SplitterWindow):
                    # Position sash so detail panel gets its minimum height
                    detail_min_height = self._detail_panel.GetMinSize().GetHeight()
                    panel_height = self.GetSize().GetHeight()
                    # Account for padding and splitter sash
                    sash_pos = panel_height - detail_min_height - (Layout.PAD * 4)
                    child.SetSashPosition(sash_pos)
                    self._initial_sash_set = True
                    break
        event.Skip()

    def _on_key(self, event) -> None:
        """Handle keyboard events."""
        keycode = event.GetKeyCode()

        if event.ShiftDown() and keycode == wx.WXK_UP:
            self._extend_selection_up()
        elif event.ShiftDown() and keycode == wx.WXK_DOWN:
            self._extend_selection_down()
        elif keycode == wx.WXK_UP:
            self.select_prev_card()
        elif keycode == wx.WXK_DOWN:
            self.select_next_card()
        else:
            event.Skip()

    @property
    def selected_card_id(self) -> int | None:
        """Return the single selected card ID, or None if zero or multiple selected."""
        if len(self._selected_card_ids) == 1:
            return self._selected_card_ids[0]
        return None

    @property
    def selected_card_ids(self) -> list[int]:
        """Return list of currently selected card IDs."""
        return list(self._selected_card_ids)

    def _on_selection_changed(self, event) -> None:
        """Handle list selection change (supports multi-select)."""
        selections = self._list_ctrl.GetSelections()
        self._selected_card_ids = []
        for item in selections:
            card = self._model.get_card_by_item(item)
            if card:
                self._selected_card_ids.append(card.id)

        if len(self._selected_card_ids) == 1:
            card = self._cards_by_id.get(self._selected_card_ids[0])
            if card:
                self._detail_panel.load_card(card)
                self._on_select(card.id)
            else:
                self._detail_panel.clear()
                self._on_select(None)
        else:
            # No selection or multiple selection: clear detail and preview
            self._detail_panel.clear()
            self._on_select(None)

    def _on_context_menu(self, event: dv.DataViewEvent) -> None:
        """Show context menu on right-click."""
        clicked_item = event.GetItem()
        clicked_card = self._model.get_card_by_item(clicked_item)
        if not clicked_card:
            return

        # Finder behavior: if right-clicked item is not in the current selection,
        # select only that item
        if clicked_card.id not in self._selected_card_ids:
            self._list_ctrl.UnselectAll()
            self._list_ctrl.Select(clicked_item)
            self._selected_card_ids = [clicked_card.id]
            self._detail_panel.load_card(clicked_card)
            self._on_select(clicked_card.id)

        # Gather all selected cards
        selected_cards = [
            self._cards_by_id[cid] for cid in self._selected_card_ids
            if cid in self._cards_by_id
        ]

        menu = self._build_context_menu(selected_cards)
        self._list_ctrl.PopupMenu(menu)
        menu.Destroy()

    def _build_context_menu(self, cards: list[CardResult]) -> wx.Menu:
        """Build context menu for single or multiple card selection."""
        menu = wx.Menu()
        is_multi = len(cards) > 1

        # Open item
        open_label = f"Open {len(cards)} Cards" if is_multi else "Open"
        open_item = menu.Append(wx.ID_ANY, open_label)
        open_icon = load_menu_icon("doc.text")
        if open_icon:
            open_item.SetBitmap(open_icon)

        # Reveal in Finder (single card only)
        reveal_item: wx.MenuItem | None = None
        if not is_multi:
            reveal_item = menu.Append(wx.ID_ANY, "Reveal in Finder")
            reveal_icon = load_menu_icon("folder")
            if reveal_icon:
                reveal_item.SetBitmap(reveal_icon)

        menu.AppendSeparator()

        # Remove item
        remove_label = f"Remove {len(cards)} Cards" if is_multi else "Remove"
        remove_item = menu.Append(wx.ID_ANY, remove_label)
        remove_icon = load_menu_icon("minus.circle")
        if remove_icon:
            remove_item.SetBitmap(remove_icon)

        # Bind handlers
        paths = [str(c.primary_path) for c in cards]

        def _open_files(evt, _paths=paths):
            for p in _paths:
                try:
                    subprocess.Popen(["open", p])
                except OSError:
                    pass

        menu.Bind(wx.EVT_MENU, _open_files, open_item)

        if not is_multi:
            primary_path = paths[0]

            def _reveal_file(evt, _path=primary_path):
                try:
                    subprocess.Popen(["open", "-R", _path])
                except OSError:
                    pass

            menu.Bind(wx.EVT_MENU, _reveal_file, reveal_item)  # reveal_item defined in matching `if not is_multi` above

        hashes = [c.file_hash for c in cards if c.file_hash]
        if self._on_remove and hashes:
            on_remove = self._on_remove

            def _remove_cards(evt, _hashes=hashes):
                for h in _hashes:
                    on_remove(h)

            menu.Bind(wx.EVT_MENU, _remove_cards, remove_item)
        else:
            remove_item.Enable(False)

        return menu

    def _handle_name_change(self, card_id: int, new_name: str) -> None:
        """Handle name change from detail panel."""
        if self._on_name_change:
            self._on_name_change(card_id, new_name)

    def _handle_checkbox(self, card_id: int, new_value: bool) -> None:
        """Handle checkbox toggle from detail panel."""
        card = self._cards_by_id.get(card_id)
        if card and card.file_hash:
            from app.core.database import update_remove_family
            update_remove_family(card.file_hash, new_value)

    def _handle_candidate(self, card_id: int, candidate_id: int) -> None:
        """Handle candidate selection from detail panel."""
        card = self._cards_by_id.get(card_id)
        if not card or not card.file_hash:
            return

        from app.core.database import select_candidate

        # Find the candidate
        for cand in card.candidates:
            if cand.id == candidate_id:
                card.family_name = cand.family_name
                card.manual_override = ""
                card.selected_candidate_id = candidate_id
                card.method = cand.method

                # Restore original confidence
                if card.confidence == Confidence.MANUAL and card.original_confidence:
                    card.confidence = card.original_confidence
                else:
                    try:
                        card.confidence = Confidence(cand.confidence)
                    except ValueError:
                        logger.debug("Unknown confidence %r for candidate %d, defaulting to MEDIUM", cand.confidence, cand.id)
                        card.confidence = Confidence.MEDIUM

                break

        # Update DB
        select_candidate(card.file_hash, candidate_id, card.remove_family)

        # Update UI
        self._model.update_card(card_id, card)
        self._detail_panel.load_card(card)

        if self._on_card_edited:
            self._on_card_edited(card_id)

    # Public API (matches original ReviewPanel)

    def load_cards(self, cards: list[CardResult]) -> None:
        """Load cards into the panel, resetting selection."""
        self._cards_by_id = {card.id: card for card in cards}
        self._model.load_cards(cards)
        n = len(cards)
        self._count_label.SetLabel(f"{n} {'Card' if n == 1 else 'Cards'} \u24D8")

        # Always reset selection — list content changes invalidate prior selection
        self._list_ctrl.UnselectAll()
        self._selected_card_ids = []
        self._detail_panel.clear()
        self._on_select(None)

    def get_cards(self) -> list[CardResult]:
        """Return all cards with edits, in display order."""
        return [self._cards_by_id[cid] for cid in self._model.card_order if cid in self._cards_by_id]

    def update_card(self, card_id: int, card: CardResult) -> None:
        """Update a single card after AI analysis."""
        self._cards_by_id[card_id] = card
        self._model.update_card(card_id, card)
        self._list_ctrl.Refresh()

        # If this card is the sole selection, update detail panel
        if self._selected_card_ids == [card_id]:
            self._detail_panel.load_card(card)

    def update_dot(self, card_id: int, confidence: Confidence) -> None:
        """Update confidence indicator (handled by model)."""
        card = self._cards_by_id.get(card_id)
        if card:
            card.confidence = confidence
            self._model.update_card(card_id, card)

    def select_next_card(self) -> None:
        """Select next card in list (collapses multi-selection to single)."""
        selections = self._list_ctrl.GetSelections()
        if not selections:
            # Select first
            if self._model.card_count > 0:
                item = self._model.ObjectToItem(0)
                self._list_ctrl.UnselectAll()
                self._list_ctrl.Select(item)
                self._list_ctrl.EnsureVisible(item)
            return

        # Use last selected item as anchor
        last_item = selections[-1]
        current_row = self._model.ItemToObject(last_item)
        if current_row < self._model.card_count - 1:
            next_item = self._model.ObjectToItem(current_row + 1)
            self._list_ctrl.UnselectAll()
            self._list_ctrl.Select(next_item)
            self._list_ctrl.EnsureVisible(next_item)
        elif len(selections) > 1:
            # At end but multi-selected: collapse to last item
            self._list_ctrl.UnselectAll()
            self._list_ctrl.Select(last_item)
            self._list_ctrl.EnsureVisible(last_item)

    def select_prev_card(self) -> None:
        """Select previous card in list (collapses multi-selection to single)."""
        selections = self._list_ctrl.GetSelections()
        if not selections:
            # Select first
            if self._model.card_count > 0:
                item = self._model.ObjectToItem(0)
                self._list_ctrl.UnselectAll()
                self._list_ctrl.Select(item)
                self._list_ctrl.EnsureVisible(item)
            return

        # Use first selected item as anchor
        first_item = selections[0]
        current_row = self._model.ItemToObject(first_item)
        if current_row > 0:
            prev_item = self._model.ObjectToItem(current_row - 1)
            self._list_ctrl.UnselectAll()
            self._list_ctrl.Select(prev_item)
            self._list_ctrl.EnsureVisible(prev_item)
        elif len(selections) > 1:
            # At start but multi-selected: collapse to first item
            self._list_ctrl.UnselectAll()
            self._list_ctrl.Select(first_item)
            self._list_ctrl.EnsureVisible(first_item)

    def _extend_selection_down(self) -> None:
        """Extend selection downward (Shift+Down)."""
        selections = self._list_ctrl.GetSelections()
        if not selections:
            if self._model.card_count > 0:
                item = self._model.ObjectToItem(0)
                self._list_ctrl.Select(item)
                self._list_ctrl.EnsureVisible(item)
            return
        last_row = self._model.ItemToObject(selections[-1])
        if last_row < self._model.card_count - 1:
            next_item = self._model.ObjectToItem(last_row + 1)
            self._list_ctrl.Select(next_item)
            self._list_ctrl.EnsureVisible(next_item)

    def _extend_selection_up(self) -> None:
        """Extend selection upward (Shift+Up)."""
        selections = self._list_ctrl.GetSelections()
        if not selections:
            if self._model.card_count > 0:
                item = self._model.ObjectToItem(0)
                self._list_ctrl.Select(item)
                self._list_ctrl.EnsureVisible(item)
            return
        first_row = self._model.ItemToObject(selections[0])
        if first_row > 0:
            prev_item = self._model.ObjectToItem(first_row - 1)
            self._list_ctrl.Select(prev_item)
            self._list_ctrl.EnsureVisible(prev_item)

    def set_drag_highlight(self, on: bool) -> None:
        """Show/hide a macOS-blue drag highlight border around the panel."""
        if self._drag_highlight == on:
            return
        self._drag_highlight = on
        self.Refresh()

    def _on_paint_highlight(self, event: wx.PaintEvent) -> None:
        """Draw blue drag-highlight border around the entire panel when active."""
        dc = wx.PaintDC(self)
        event.Skip()
        if not self._drag_highlight:
            return
        gc = wx.GraphicsContext.Create(dc)
        if not gc:
            return
        w, h = self.GetSize()
        pen = gc.CreatePen(
            wx.GraphicsPenInfo(Color.ACCENT).Width(Layout.HIGHLIGHT_WIDTH)
        )
        gc.SetPen(pen)
        gc.SetBrush(wx.NullBrush)
        path = gc.CreatePath()
        inset = Layout.HIGHLIGHT_INSET
        path.AddRoundedRectangle(inset, inset, w - inset * 2, h - inset * 2, Layout.HIGHLIGHT_RADIUS)
        gc.StrokePath(path)

    def select_all(self) -> None:
        """Select all cards in the list."""
        for card_id in self._model.card_order:
            item = self._model.get_item_by_card_id(card_id)
            if item.IsOk():
                self._list_ctrl.Select(item)

    def select_none(self) -> None:
        """Clear all selection."""
        self._list_ctrl.UnselectAll()

    def set_ai_button_state(self, card_id: int, state: str) -> None:
        """Set AI button state (enabled/disabled)."""
        # Only affects currently selected card in detail panel
        if self.selected_card_id == card_id:
            enable = (state == "normal")
            self._detail_panel.enable_ai_button(enable)
