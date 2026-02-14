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

import wx
import wx.dataview as dv
from typing import Callable, Optional
from pathlib import Path
from app.models.card import CardResult, Confidence, CandidateInfo
from app.gui.wx_styles import Color, Font, Layout
from app.gui.wx_utils import create_static_text, create_button
from app.gui.wx_icons import load_sf_symbol
from app.gui.wx_context_menu import add_entry_context_menu


class CardListModel(dv.PyDataViewModel):
    """Data model for the card list (master view).

    Columns: [Confidence Dot, Filename, Family Name]
    """

    def __init__(self):
        super().__init__()
        self._cards: list[CardResult] = []
        self._card_order: list[int] = []  # Card IDs in display order

    def load_cards(self, cards: list[CardResult]):
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

    def update_card(self, card_id: int, updated_card: CardResult):
        """Update a card in the model."""
        for i, card in enumerate(self._cards):
            if card.id == card_id:
                self._cards[i] = updated_card
                item = self.ObjectToItem(i)
                self.ItemChanged(item)
                break

    # PyDataViewModel interface
    def GetColumnCount(self):
        """3 columns: dot, filename, family name."""
        return 3

    def GetColumnType(self, col):
        """All columns return strings (we'll use custom renderer for dot)."""
        return "string"

    def GetChildren(self, parent, children):
        """Flat list - root has all cards, cards have no children."""
        if not parent.IsOk():  # Root
            for i in range(len(self._cards)):
                children.append(self.ObjectToItem(i))
            return len(self._cards)
        return 0  # Cards have no children

    def IsContainer(self, item):
        """Only root is container."""
        return not item.IsOk()

    def GetParent(self, item):
        """All items are children of root."""
        return dv.NullDataViewItem

    def GetValue(self, item, col):
        """Return value for cell."""
        row = self.ItemToObject(item)
        if row < 0 or row >= len(self._cards):
            return ""

        card = self._cards[row]

        if col == 0:  # Confidence dot - return symbol or empty
            if card.error:
                return "✕"
            elif card.confidence == Confidence.NONE:
                return "⚠"
            else:
                return "●"  # Filled circle (we'll color it)
        elif col == 1:  # Filename
            return card.filename
        elif col == 2:  # Family name
            return card.display_name
        return ""

    def SetValue(self, value, item, col):
        """Not editable in list (edit in detail panel)."""
        return False

    def GetAttr(self, item, col, attr):
        """Set color for confidence dot and filename (blue for multi-path cards)."""
        row = self.ItemToObject(item)
        if row < 0 or row >= len(self._cards):
            return False

        card = self._cards[row]

        # Column 0: Confidence dot - set color based on confidence
        if col == 0:
            if card.error:
                attr.SetColour(Color.ERROR)
            elif card.confidence == Confidence.NONE:
                attr.SetColour(Color.TEXT_SECONDARY)
            elif card.confidence == Confidence.HIGH:
                attr.SetColour(Color.SUCCESS)
            elif card.confidence == Confidence.MEDIUM:
                attr.SetColour(Color.WARNING)
            elif card.confidence == Confidence.LOW:
                attr.SetColour(Color.ERROR)
            elif card.confidence == Confidence.MANUAL:
                attr.SetColour(Color.MANUAL_BLUE)
            else:
                attr.SetColour(Color.TEXT_PRIMARY)
            return True

        # Column 1: Filename - show in blue if card has multiple paths
        elif col == 1:
            if len(card.file_paths) > 1:
                # macOS system blue for multi-path indicator
                attr.SetColour(wx.Colour(0, 122, 255))
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
    ):
        super().__init__(parent)
        self._on_name_change = on_name_change
        self._on_checkbox_toggle = on_checkbox_toggle
        self._on_candidate_select = on_candidate_select
        self._on_ai_request = on_ai_request
        self._current_card: CardResult | None = None
        self._suppress_events = False

        self._build_ui()
        self.clear()

    def _build_ui(self):
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

        # Horizontal row: AI button + Remove Family checkbox
        action_row = wx.BoxSizer(wx.HORIZONTAL)

        # AI button (standard height button with icon)
        # Use 9pt icon for compact size
        ai_icon = load_sf_symbol("sparkles", 9, "#1D1D1F")
        if ai_icon:
            self._ai_btn = wx.Button(self._edit_panel, label="  AI Analyze")
            self._ai_btn.SetBitmap(ai_icon)
        else:
            self._ai_btn = wx.Button(self._edit_panel, label="AI Analyze")

        self._ai_btn.SetFont(Font.BODY())
        # Match OK button height (standard macOS button)
        self._ai_btn.SetMinSize(wx.Size(-1, 28))
        self._ai_btn.Bind(wx.EVT_BUTTON, self._on_ai)
        action_row.Add(self._ai_btn, 0, wx.ALIGN_CENTER_VERTICAL)

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
        self._locations_list.AppendTextColumn("", width=400)
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

        # Track whether locations tab is currently added
        self._locations_tab_index = None

        # Add notebook to main sizer
        sizer.Add(self._notebook, 1, wx.EXPAND | wx.ALL, Layout.PAD)

        self.SetSizer(sizer)

        # Fit to minimum size needed
        sizer.Fit(self)
        self.SetMinSize(self.GetSize())

    def load_card(self, card: CardResult | None):
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

        # Update file locations section
        self._update_locations(card)

        self._suppress_events = False

    def _update_locations(self, card: CardResult):
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
            self._locations_tab_index = self._notebook.AddPage(
                self._locations_panel,
                f"File Paths ({num_paths})"
            )
        else:
            # Update tab label
            self._notebook.SetPageText(self._locations_tab_index, f"File Paths ({num_paths})")

    def clear(self):
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

        # Clear file locations and remove tab if present
        self._locations_list.DeleteAllItems()
        if self._locations_tab_index is not None:
            self._notebook.RemovePage(self._locations_tab_index)
            self._locations_tab_index = None

        # Reset Edit tab to default label (do this after removing File Paths tab)
        if self._notebook.GetPageCount() > 0:
            self._notebook.SetPageText(0, "Edit Card")

        self._suppress_events = False

    def _on_name_char(self, event: wx.KeyEvent) -> None:
        """Block filesystem-invalid characters from being typed."""
        from app.core.name_formatting import INVALID_FILENAME_CHARS
        key = event.GetUnicodeKey()
        if key != wx.WXK_NONE and chr(key) in INVALID_FILENAME_CHARS:
            return  # Swallow the keystroke
        event.Skip()

    def _on_name_edit(self, event):
        """Handle name text change."""
        if self._suppress_events or not self._current_card:
            return

        new_name = self._name_text.GetValue()
        self._current_card.manual_override = new_name

        if self._on_name_change:
            self._on_name_change(self._current_card.id, new_name)

    def _on_checkbox(self, event):
        """Handle checkbox toggle."""
        if self._suppress_events or not self._current_card:
            return

        new_value = self._remove_family_check.GetValue()
        self._current_card.remove_family = new_value

        if self._on_checkbox_toggle:
            self._on_checkbox_toggle(self._current_card.id, new_value)

    def _on_candidate(self, event):
        """Handle candidate selection."""
        if self._suppress_events or not self._current_card:
            return

        selection = self._candidates_choice.GetSelection()
        if selection <= 0:  # Placeholder selected
            return

        label = self._candidates_choice.GetString(selection)
        candidate_id = self._candidate_map.get(label)

        if candidate_id and self._on_candidate_select:
            self._on_candidate_select(self._current_card.id, candidate_id)

    def _on_ai(self, event):
        """Handle AI button click."""
        if not self._current_card:
            return

        if self._on_ai_request:
            self._on_ai_request(self._current_card.id)


class ReviewPanelMasterDetail(wx.Panel):
    """Master-Detail Review Panel - Mac-native pattern.

    Public API matches original ReviewPanel for easy drop-in replacement.
    """

    def __init__(
        self,
        parent,
        on_select: Callable[[int], None],
        on_ai_request: Callable[[int], None],
        on_name_change: Callable[[int, str], None] | None = None,
    ):
        super().__init__(parent)
        self._on_select = on_select
        self._on_ai_request = on_ai_request
        self._on_name_change = on_name_change
        self._selected_card_id: int | None = None
        self._cards_by_id: dict[int, CardResult] = {}

        self._build_ui()

    def _build_ui(self):
        """Build master-detail UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header with count
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        heading = create_static_text(
            self,
            "Cards",
            font=Font.HEADING(),
            colour=Color.TEXT_PRIMARY
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

        sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, Layout.PAD)

        # Splitter for master-detail
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)

        # Master: DataViewCtrl
        self._list_ctrl = dv.DataViewCtrl(
            splitter,
            style=dv.DV_SINGLE | dv.DV_ROW_LINES | dv.DV_VERT_RULES
        )

        # Create model
        self._model = CardListModel()
        self._list_ctrl.AssociateModel(self._model)

        # Add columns
        self._list_ctrl.AppendTextColumn("", 0, width=30, mode=dv.DATAVIEW_CELL_INERT)
        self._list_ctrl.AppendTextColumn("File Name", 1, width=280, mode=dv.DATAVIEW_CELL_INERT)
        self._list_ctrl.AppendTextColumn("Family Name", 2, width=200, mode=dv.DATAVIEW_CELL_INERT)

        # Bind selection event
        self._list_ctrl.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_selection_changed)

        # Detail: Edit panel
        self._detail_panel = DetailPanel(
            splitter,
            on_name_change=self._handle_name_change,
            on_checkbox_toggle=self._handle_checkbox,
            on_candidate_select=self._handle_candidate,
            on_ai_request=self._on_ai_request,
        )

        # Split horizontally (master on top, detail on bottom)
        splitter.SplitHorizontally(self._list_ctrl, self._detail_panel)
        splitter.SetSashGravity(1.0)  # Give all extra space to master list
        splitter.SetMinimumPaneSize(100)

        sizer.Add(splitter, 1, wx.EXPAND | wx.ALL, Layout.PAD)

        self.SetSizer(sizer)

        # Bind keyboard navigation
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

        # After layout, position sash to give detail panel just what it needs
        self.Bind(wx.EVT_SIZE, self._on_panel_size, id=wx.ID_ANY)
        self._initial_sash_set = False

    def _on_panel_size(self, event):
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

    def _on_key(self, event):
        """Handle keyboard events (for consistency with original)."""
        # DataViewCtrl handles Up/Down natively, but we intercept for consistency
        keycode = event.GetKeyCode()

        if keycode == wx.WXK_UP:
            self.select_prev_card()
        elif keycode == wx.WXK_DOWN:
            self.select_next_card()
        else:
            event.Skip()

    def _on_selection_changed(self, event):
        """Handle list selection change."""
        item = self._list_ctrl.GetSelection()
        card = self._model.get_card_by_item(item)

        if card:
            self._selected_card_id = card.id
            self._detail_panel.load_card(card)
            self._on_select(card.id)
        else:
            self._selected_card_id = None
            self._detail_panel.clear()

    def _handle_name_change(self, card_id: int, new_name: str):
        """Handle name change from detail panel."""
        if self._on_name_change:
            self._on_name_change(card_id, new_name)

    def _handle_checkbox(self, card_id: int, new_value: bool):
        """Handle checkbox toggle from detail panel."""
        card = self._cards_by_id.get(card_id)
        if card and card.file_hash:
            from app.core.database import update_remove_family
            update_remove_family(card.file_hash, new_value)

    def _handle_candidate(self, card_id: int, candidate_id: int):
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
                        card.confidence = Confidence.MEDIUM

                break

        # Update DB
        select_candidate(card.file_hash, candidate_id, card.remove_family)

        # Update UI
        self._model.update_card(card_id, card)
        self._detail_panel.load_card(card)

    # Public API (matches original ReviewPanel)

    def load_cards(self, cards: list[CardResult]):
        """Load cards into the panel."""
        self._cards_by_id = {card.id: card for card in cards}
        self._model.load_cards(cards)
        self._count_label.SetLabel(f"{len(cards)} cards")

        # Select first card if any
        if cards:
            item = self._model.get_item_by_card_id(cards[0].id)
            self._list_ctrl.Select(item)

    def get_cards(self) -> list[CardResult]:
        """Return all cards with edits, in display order."""
        return [self._cards_by_id[cid] for cid in self._model._card_order if cid in self._cards_by_id]

    def update_card(self, card_id: int, card: CardResult):
        """Update a single card after AI analysis."""
        self._cards_by_id[card_id] = card
        self._model.update_card(card_id, card)
        self._list_ctrl.Refresh()

        # If this card is selected, update detail panel
        if self._selected_card_id == card_id:
            self._detail_panel.load_card(card)

    def update_dot(self, card_id: int, confidence: Confidence):
        """Update confidence indicator (handled by model)."""
        card = self._cards_by_id.get(card_id)
        if card:
            card.confidence = confidence
            self._model.update_card(card_id, card)

    def select_next_card(self):
        """Select next card in list."""
        current_item = self._list_ctrl.GetSelection()
        if not current_item.IsOk():
            # Select first
            if self._model._cards:
                item = self._model.ObjectToItem(0)
                self._list_ctrl.Select(item)
                self._list_ctrl.EnsureVisible(item)
            return

        current_row = self._model.ItemToObject(current_item)
        if current_row < len(self._model._cards) - 1:
            next_item = self._model.ObjectToItem(current_row + 1)
            self._list_ctrl.Select(next_item)
            self._list_ctrl.EnsureVisible(next_item)

    def select_prev_card(self):
        """Select previous card in list."""
        current_item = self._list_ctrl.GetSelection()
        if not current_item.IsOk():
            # Select first
            if self._model._cards:
                item = self._model.ObjectToItem(0)
                self._list_ctrl.Select(item)
                self._list_ctrl.EnsureVisible(item)
            return

        current_row = self._model.ItemToObject(current_item)
        if current_row > 0:
            prev_item = self._model.ObjectToItem(current_row - 1)
            self._list_ctrl.Select(prev_item)
            self._list_ctrl.EnsureVisible(prev_item)

    def set_ai_button_state(self, card_id: int, state: str, text: str = "AI"):
        """Set AI button state (enabled/disabled)."""
        # Only affects currently selected card in detail panel
        if self._selected_card_id == card_id:
            enable = (state == "normal")
            self._detail_panel._ai_btn.Enable(enable)
