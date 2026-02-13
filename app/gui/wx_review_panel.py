"""wxPython Review Panel - Scrollable card list with editable rows.

This panel displays a scrollable list of greeting cards with controls for:
- Confidence indicator (colored dot)
- Filename display
- Editable family name
- Remove family suffix checkbox
- Alternative candidates dropdown
- AI analysis button

Each row is selectable and supports keyboard navigation.
"""

import wx
import wx.lib.scrolledpanel as scrolled
from typing import Callable, Optional
from dataclasses import dataclass
from app.models.card import CardResult, Confidence
from app.gui.wx_styles import Color, Font, Layout
from app.gui.wx_icons import load_sf_symbol
from app.gui.wx_context_menu import add_entry_context_menu


@dataclass
class ReviewRow:
    """Container for all widgets in a review panel row."""
    panel: wx.Panel
    selection_icon: wx.StaticBitmap  # Arrow icon for selected row
    dot: wx.Panel  # Panel with painted circle/symbol
    fn_label: wx.StaticText
    name_text: wx.TextCtrl
    remove_family_check: wx.CheckBox
    alt_choice: wx.Choice
    ai_btn: wx.Button
    candidate_id_map: dict[str, int]  # Maps choice labels to candidate IDs


def _dot_style(is_error: bool, confidence: Confidence) -> tuple[wx.Colour, str | None]:
    """Return (color, symbol) for a confidence dot. Symbol is None for a filled circle."""
    if is_error:
        return wx.Colour(Color.ERROR), "✕"
    if confidence == Confidence.NONE:
        return wx.Colour(Color.TEXT_SECONDARY), "⚠"
    return wx.Colour(confidence.color()), None


def _tooltip_text(card: CardResult | None, confidence: Confidence) -> str:
    """Build tooltip text from card state and confidence."""
    if card and card.error:
        return f"Error: {card.error}"
    if confidence == Confidence.MANUAL:
        return "Manual Entry"
    if card and card.method == "missing":
        return "⚠️ No name extracted"
    if card and card.method in {"ocr", "ai"}:
        return f"{card.method.upper()} - {confidence.value.capitalize()} confidence"
    return confidence.tooltip()


class _ConfidenceDot(wx.Panel):
    """Custom panel that draws a confidence dot (circle or symbol)."""

    def __init__(self, parent, color: wx.Colour, symbol: str | None = None):
        super().__init__(parent, size=(14, 14))
        self._color = color
        self._symbol = symbol
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, event):
        """Draw the dot or symbol."""
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()

        if self._symbol:
            # Draw symbol text (8pt font in 14x14 panel for no clipping)
            dc.SetTextForeground(self._color)
            font = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
            dc.SetFont(font)
            text_width, text_height = dc.GetTextExtent(self._symbol)
            x = (14 - text_width) // 2
            y = (14 - text_height) // 2
            dc.DrawText(self._symbol, x, y)
        else:
            # Draw filled circle
            dc.SetBrush(wx.Brush(self._color))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawCircle(7, 7, 4)

    def update_style(self, color: wx.Colour, symbol: str | None = None):
        """Update the dot color and symbol, then refresh."""
        self._color = color
        self._symbol = symbol
        self.Refresh()


class ReviewPanel(wx.Panel):
    """Scrollable card list with edit controls for reviewing extracted names."""

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
        self._card_order: list[int] = []  # Ordered list of card IDs (display order)
        self._cards_by_id: dict[int, CardResult] = {}  # Card lookup by ID
        self._rows_by_id: dict[int, ReviewRow] = {}  # UI row lookup by card ID
        self._selected_card_id: Optional[int] = None
        self._suppress_text_event = False

        # Load AI icon (use hex string, not wx.Colour)
        self._ai_icon = load_sf_symbol("sparkles", 6, "#1D1D1F")

        # Main layout
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header with count
        header_panel = wx.Panel(self)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        heading = wx.StaticText(header_panel, label="Cards")
        heading.SetFont(Font.HEADING())
        heading.SetForegroundColour(Color.TEXT_PRIMARY)
        header_sizer.Add(heading, 0, wx.ALIGN_CENTER_VERTICAL)

        header_sizer.AddStretchSpacer()

        self._count_label = wx.StaticText(header_panel, label="")
        self._count_label.SetFont(Font.SMALL())
        self._count_label.SetForegroundColour(Color.TEXT_SECONDARY)
        header_sizer.Add(self._count_label, 0, wx.ALIGN_CENTER_VERTICAL)

        header_panel.SetSizer(header_sizer)
        sizer.Add(header_panel, 0, wx.EXPAND | wx.ALL, Layout.PAD)

        # Column headers
        col_header_panel = wx.Panel(self)
        col_header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Selection icon + dot column spacer (matches row layout)
        # Selection: 16px + 2px left + 2px right = 20px
        # Dot: 14px + 4px left + 4px right = 22px
        # Total: 42px
        col_header_sizer.Add((42, -1), 0)

        # Filename header (matches 4px left margin from row)
        fn_header = wx.StaticText(col_header_panel, label="Filename", size=(280, -1))
        fn_header.SetFont(Font.SMALL())
        fn_header.SetForegroundColour(Color.TEXT_SECONDARY)
        col_header_sizer.Add(fn_header, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # Family Name header (matches 4px left margin from row)
        name_header = wx.StaticText(col_header_panel, label="Family Name")
        name_header.SetFont(Font.SMALL())
        name_header.SetForegroundColour(Color.TEXT_SECONDARY)
        col_header_sizer.Add(name_header, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # Checkbox column spacer (no header per user preference)
        col_header_sizer.Add((20, -1), 0, wx.LEFT, 4)

        col_header_panel.SetSizer(col_header_sizer)
        sizer.Add(col_header_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, Layout.PAD)

        # Scrollable area for rows
        self._scroll_panel = scrolled.ScrolledPanel(self)
        self._scroll_panel.SetupScrolling(scroll_x=False, scroll_y=True)
        self._scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        self._scroll_panel.SetSizer(self._scroll_sizer)

        sizer.Add(self._scroll_panel, 1, wx.EXPAND | wx.ALL, Layout.PAD)

        self.SetSizer(sizer)

        # Bind keyboard navigation
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_key(self, event):
        """Handle keyboard navigation."""
        keycode = event.GetKeyCode()

        if keycode == wx.WXK_UP:
            self.select_prev_card()
        elif keycode == wx.WXK_DOWN:
            self.select_next_card()
        else:
            event.Skip()

    def load_cards(self, cards: list[CardResult]):
        """Load card results into the review panel."""
        # Build card lookup and order list
        self._cards_by_id.clear()
        self._card_order.clear()
        for card in cards:
            self._cards_by_id[card.id] = card
            self._card_order.append(card.id)

        self._selected_card_id = None

        # Clear existing rows
        for row in self._rows_by_id.values():
            row.panel.Destroy()
        self._rows_by_id.clear()

        # Update count
        self._count_label.SetLabel(f"{len(cards)} cards")

        # Create rows
        for card in cards:
            self._create_row(card)

        # Refresh scrolling and force layout
        self._scroll_panel.SetupScrolling(scroll_x=False, scroll_y=True)
        self._scroll_panel.Layout()
        self.Layout()  # Force parent layout refresh

    def _create_row(self, card: CardResult):
        """Create a single row for a card."""
        card_id = card.id
        is_error = bool(card.error)

        # Row panel
        row_panel = wx.Panel(self._scroll_panel)
        row_panel.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Selection indicator icon (always allocates space to prevent shifting)
        # Start with transparent bitmap
        empty_bitmap = wx.Bitmap(16, 16)
        # Make it actually transparent by creating an empty image
        empty_image = wx.Image(16, 16)
        empty_image.InitAlpha()
        for x in range(16):
            for y in range(16):
                empty_image.SetAlpha(x, y, 0)  # Fully transparent
        empty_bitmap = wx.Bitmap(empty_image)

        selection_icon = wx.StaticBitmap(row_panel, bitmap=empty_bitmap, size=(16, -1))
        row_sizer.Add(selection_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 2)

        # Confidence dot
        dot_color, symbol = _dot_style(is_error, card.confidence)
        dot = _ConfidenceDot(row_panel, dot_color, symbol)
        dot.SetToolTip(_tooltip_text(card, card.confidence))
        row_sizer.Add(dot, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 4)

        # Filename label
        fn_label = wx.StaticText(row_panel, label=card.filename, size=(280, -1))
        fn_label.SetFont(Font.SMALL())
        fn_label.SetForegroundColour(Color.TEXT_PRIMARY)
        row_sizer.Add(fn_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # Editable name entry
        name_text = wx.TextCtrl(row_panel, value=card.display_name)
        name_text.SetFont(Font.BODY())
        row_sizer.Add(name_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # Add context menu to text control
        add_entry_context_menu(name_text)

        # Bind text change event
        name_text.Bind(wx.EVT_TEXT, lambda e, cid=card_id: self._on_name_edit(cid, e))

        # Remove Family checkbox (with fixed spacing for alignment)
        remove_family_check = wx.CheckBox(row_panel, size=(20, -1))
        remove_family_check.SetValue(card.remove_family)
        remove_family_check.SetToolTip("Remove 'Family' from filename")
        remove_family_check.Bind(
            wx.EVT_CHECKBOX,
            lambda e, cid=card_id: self._on_remove_family_toggle(cid, e)
        )
        row_sizer.Add(remove_family_check, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)

        # Candidates dropdown with fixed width and placeholder
        candidate_labels = []
        candidate_id_map = {}
        if card.candidates:
            for cand in card.candidates:
                # Format: "Name (method - confidence)"
                label = f"{cand.family_name} ({cand.method.upper()} - {cand.confidence.capitalize()})"
                candidate_labels.append(label)
                candidate_id_map[label] = cand.id

        # Add placeholder as first item
        num_candidates = len(candidate_labels)
        placeholder = f"{num_candidates} Candidate{'s' if num_candidates != 1 else ''}" if num_candidates > 0 else "No Candidates"
        choices = [placeholder] + candidate_labels

        alt_choice = wx.Choice(row_panel, choices=choices, size=(180, -1))
        alt_choice.SetSelection(0)  # Select placeholder initially

        if candidate_labels:
            alt_choice.Bind(
                wx.EVT_CHOICE,
                lambda e, cid=card_id: self._on_alt_select(cid, e)
            )
        else:
            alt_choice.Enable(False)

        row_sizer.Add(alt_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # AI button
        if self._ai_icon:
            ai_btn = wx.BitmapButton(row_panel, bitmap=self._ai_icon)
            ai_btn.SetToolTip("Request AI analysis")
        else:
            ai_btn = wx.Button(row_panel, label="AI")

        ai_btn.Bind(wx.EVT_BUTTON, lambda e, cid=card_id: self._on_ai_request(cid))
        row_sizer.Add(ai_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 4)

        # Disable controls for error cards
        if is_error:
            name_text.Enable(False)
            alt_choice.Enable(False)
            ai_btn.Enable(False)
            remove_family_check.Enable(False)

        row_panel.SetSizer(row_sizer)

        # Store row data
        row_data = ReviewRow(
            panel=row_panel,
            selection_icon=selection_icon,
            dot=dot,
            fn_label=fn_label,
            name_text=name_text,
            remove_family_check=remove_family_check,
            alt_choice=alt_choice,
            ai_btn=ai_btn,
            candidate_id_map=candidate_id_map,
        )
        self._rows_by_id[card_id] = row_data

        # Add to scroll sizer
        self._scroll_sizer.Add(row_panel, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 1)

        # Click to select (bind to row panel, selection icon, dot, and filename label)
        for widget in [row_panel, selection_icon, dot, fn_label]:
            widget.Bind(wx.EVT_LEFT_DOWN, lambda e, cid=card_id: self._select_row(cid))

    def _select_row(self, card_id: int):
        """Select a row and notify callback."""
        # Deselect previous (set to transparent bitmap)
        if self._selected_card_id is not None and self._selected_card_id in self._rows_by_id:
            prev = self._rows_by_id[self._selected_card_id]
            # Create transparent bitmap
            empty_image = wx.Image(16, 16)
            empty_image.InitAlpha()
            for x in range(16):
                for y in range(16):
                    empty_image.SetAlpha(x, y, 0)  # Fully transparent
            empty_bitmap = wx.Bitmap(empty_image)
            prev.selection_icon.SetBitmap(empty_bitmap)

        # Select new (set to visible icon)
        self._selected_card_id = card_id
        if card_id in self._rows_by_id:
            row = self._rows_by_id[card_id]

            # Load selection icon - "scope" in accent blue (6pt to fit in 16x16 space)
            from app.gui.wx_utils import colour_to_hex
            accent_hex = colour_to_hex(Color.ACCENT)
            selection_bitmap = load_sf_symbol("scope", 6, accent_hex)
            if selection_bitmap:
                row.selection_icon.SetBitmap(selection_bitmap)
                row.selection_icon.Refresh()  # Force refresh

            # Scroll to make visible
            self._scroll_panel.ScrollChildIntoView(row.panel)

            # Notify callback
            self._on_select(card_id)

    def _on_name_edit(self, card_id: int, event):
        """Handle name text change."""
        if self._suppress_text_event:
            return

        card = self._cards_by_id.get(card_id)
        row = self._rows_by_id.get(card_id)
        if card and row:
            new_name = row.name_text.GetValue()
            card.manual_override = new_name
            if self._on_name_change:
                self._on_name_change(card_id, new_name)

    def _on_alt_select(self, card_id: int, event):
        """Handle candidate selection from dropdown."""
        row = self._rows_by_id.get(card_id)
        card = self._cards_by_id.get(card_id)

        if not row or not card or not card.file_hash:
            return

        selection = row.alt_choice.GetSelection()
        # Selection 0 is the placeholder, ignore it
        if selection == wx.NOT_FOUND or selection == 0:
            return

        selected_label = row.alt_choice.GetString(selection)
        candidate_id = row.candidate_id_map.get(selected_label)

        if candidate_id:
            from app.core.database import select_candidate
            from app.models.card import Confidence

            # Find the candidate to get its details
            selected_name = ""
            selected_conf = "none"
            selected_method = "missing"
            for cand in card.candidates:
                if cand.id == candidate_id:
                    selected_name = cand.family_name
                    selected_conf = cand.confidence
                    selected_method = cand.method
                    break

            # Update card state
            card.family_name = selected_name
            card.manual_override = ""  # Clear manual override
            card.selected_candidate_id = candidate_id
            card.method = selected_method

            # Restore original confidence if it was previously manual
            if card.confidence == Confidence.MANUAL and card.original_confidence:
                card.confidence = card.original_confidence
            else:
                try:
                    card.confidence = Confidence(selected_conf)
                except ValueError:
                    card.confidence = Confidence.MEDIUM

            # Update UI
            self._suppress_text_event = True
            row.name_text.SetValue(selected_name)
            self._suppress_text_event = False
            self.update_dot(card_id, card.confidence)

            # Save to DB
            select_candidate(card.file_hash, candidate_id, card.remove_family)

    def _on_remove_family_toggle(self, card_id: int, event):
        """Handle checkbox toggle for remove_family option."""
        card = self._cards_by_id.get(card_id)
        row = self._rows_by_id.get(card_id)

        if card and row:
            card.remove_family = row.remove_family_check.GetValue()
            # Save to DB if card has been processed
            if card.file_hash:
                from app.core.database import update_remove_family
                update_remove_family(card.file_hash, card.remove_family)

    def update_dot(self, card_id: int, confidence: Confidence):
        """Update just the confidence dot and tooltip for a row."""
        row = self._rows_by_id.get(card_id)
        card = self._cards_by_id.get(card_id)

        if not row or not isinstance(row.dot, _ConfidenceDot):
            return

        # Update dot color and symbol
        dot_color, symbol = _dot_style(bool(card and card.error), confidence)
        row.dot.update_style(dot_color, symbol)
        row.dot.SetToolTip(_tooltip_text(card, confidence))

    def update_card(self, card_id: int, card: CardResult):
        """Update a single card's display after AI analysis."""
        row = self._rows_by_id.get(card_id)
        if not row:
            return

        # Update card in lookup dict
        self._cards_by_id[card_id] = card

        # Update confidence dot and tooltip
        self.update_dot(card_id, card.confidence)

        # Update name (suppress event to avoid triggering manual override)
        self._suppress_text_event = True
        row.name_text.SetValue(card.display_name)
        self._suppress_text_event = False

        # Update remove_family checkbox
        row.remove_family_check.SetValue(card.remove_family)

        # Update candidates dropdown
        if card.candidates:
            candidate_labels = []
            candidate_id_map = {}
            for cand in card.candidates:
                label = f"{cand.family_name} ({cand.method.upper()} - {cand.confidence.capitalize()})"
                candidate_labels.append(label)
                candidate_id_map[label] = cand.id

            # Add placeholder as first item
            num_candidates = len(candidate_labels)
            placeholder = f"{num_candidates} Candidate{'s' if num_candidates != 1 else ''}"
            choices = [placeholder] + candidate_labels

            row.alt_choice.Clear()
            row.alt_choice.Append(choices)
            row.alt_choice.SetSelection(0)  # Select placeholder
            row.alt_choice.Enable(True)
            row.candidate_id_map = candidate_id_map

            # Rebind event with updated mapping
            row.alt_choice.Unbind(wx.EVT_CHOICE)
            row.alt_choice.Bind(
                wx.EVT_CHOICE,
                lambda e, cid=card_id: self._on_alt_select(cid, e)
            )
        else:
            row.alt_choice.Clear()
            row.alt_choice.Append(["No Candidates"])
            row.alt_choice.SetSelection(0)
            row.alt_choice.Enable(False)

    def get_cards(self) -> list[CardResult]:
        """Return all cards with current edits applied, in display order."""
        return [self._cards_by_id[card_id] for card_id in self._card_order if card_id in self._cards_by_id]

    def select_prev_card(self):
        """Select the previous card in display order."""
        if not self._card_order:
            return
        if self._selected_card_id is None:
            self._select_row(self._card_order[0])
        elif self._selected_card_id in self._card_order:
            idx = self._card_order.index(self._selected_card_id)
            if idx > 0:
                self._select_row(self._card_order[idx - 1])

    def select_next_card(self):
        """Select the next card in display order."""
        if not self._card_order:
            return
        if self._selected_card_id is None:
            self._select_row(self._card_order[0])
        elif self._selected_card_id in self._card_order:
            idx = self._card_order.index(self._selected_card_id)
            if idx < len(self._card_order) - 1:
                self._select_row(self._card_order[idx + 1])

    def set_ai_button_state(self, card_id: int, state: str, text: str = "AI"):
        """Set the AI button state and text for a specific card.

        Args:
            card_id: The card ID
            state: "normal" or "disabled"
            text: Button text (not used for bitmap buttons)
        """
        row = self._rows_by_id.get(card_id)
        if row:
            enable = (state == "normal")
            row.ai_btn.Enable(enable)
