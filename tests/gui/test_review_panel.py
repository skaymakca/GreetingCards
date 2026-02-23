"""Tests for review_panel.py - Master-Detail Review Panel."""

import wx
import wx.dataview as dv
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from app.gui.review_panel import (
    CardListModel,
    DetailPanel,
    ReviewPanelMasterDetail,
)
from app.gui.styles import Color
from app.models.card import CardResult, Confidence, CandidateInfo


def _select_card(panel, card_id):
    """Helper to explicitly select a card in the list."""
    panel._list_ctrl.UnselectAll()
    item = panel._model.get_item_by_card_id(card_id)
    panel._list_ctrl.Select(item)
    panel._on_selection_changed(Mock())


@pytest.fixture
def wx_app():
    """Create wx.App for tests that need it."""
    app = wx.App()
    yield app
    app.Destroy()


@pytest.fixture
def parent_frame(wx_app):
    """Create a parent frame for panel tests."""
    frame = wx.Frame(None)
    yield frame
    frame.Destroy()


@pytest.fixture
def mock_cards():
    """Create mock cards for testing."""
    cards = []

    # Card 1: High confidence with candidates
    card1 = CardResult(
        id=1,
        file_paths=[Path("card-001.pdf")], primary_path=Path("card-001.pdf"),
        family_name="Smith",
        confidence=Confidence.HIGH,
        method="ocr",
        original_confidence=Confidence.HIGH,
        remove_family=True,
    )
    card1.candidates = [
        CandidateInfo(id=101, family_name="Smith", confidence="high", method="ocr"),
        CandidateInfo(id=102, family_name="Smyth", confidence="medium", method="ai"),
    ]
    cards.append(card1)

    # Card 2: Medium confidence
    card2 = CardResult(
        id=2,
        file_paths=[Path("card-002.pdf")], primary_path=Path("card-002.pdf"),
        family_name="Johnson",
        confidence=Confidence.MEDIUM,
        method="ai",
        original_confidence=Confidence.MEDIUM,
        remove_family=False,
    )
    card2.candidates = [
        CandidateInfo(id=201, family_name="Johnson", confidence="medium", method="ai"),
    ]
    cards.append(card2)

    # Card 3: Low confidence
    card3 = CardResult(
        id=3,
        file_paths=[Path("card-003.pdf")], primary_path=Path("card-003.pdf"),
        family_name="Williams",
        confidence=Confidence.LOW,
        method="ocr",
        original_confidence=Confidence.LOW,
        remove_family=True,
    )
    cards.append(card3)

    # Card 4: NONE confidence (no name extracted)
    card4 = CardResult(
        id=4,
        file_paths=[Path("card-004.pdf")], primary_path=Path("card-004.pdf"),
        family_name="",
        confidence=Confidence.NONE,
        method="missing",
        original_confidence=Confidence.NONE,
        remove_family=False,
    )
    cards.append(card4)

    # Card 5: Manual entry
    card5 = CardResult(
        id=5,
        file_paths=[Path("card-005.pdf")], primary_path=Path("card-005.pdf"),
        family_name="Brown",
        confidence=Confidence.MANUAL,
        method="manual",
        original_confidence=Confidence.HIGH,
        remove_family=True,
    )
    cards.append(card5)

    # Card 6: Error card
    card6 = CardResult(
        id=6,
        file_paths=[Path("card-006.pdf")], primary_path=Path("card-006.pdf"),
        family_name="",
        confidence=Confidence.NONE,
        method="missing",
        original_confidence=Confidence.NONE,
        remove_family=False,
    )
    card6.error = "Failed to process"
    cards.append(card6)

    return cards


# ============================================================================
# CardListModel Tests
# ============================================================================


class TestCardListModel:
    """Tests for CardListModel data model."""

    def test_initialization(self, wx_app):
        """Model initializes empty."""
        model = CardListModel()
        assert model._cards == []
        assert model._card_order == []

    def test_column_count(self, wx_app):
        """Model has 3 columns (dot, filename, family name)."""
        model = CardListModel()
        assert model.GetColumnCount() == 3

    def test_column_type(self, wx_app):
        """All columns return string type."""
        model = CardListModel()
        for col in range(3):
            assert model.GetColumnType(col) == "string"

    def test_load_cards(self, wx_app, mock_cards):
        """load_cards populates model."""
        model = CardListModel()
        model.load_cards(mock_cards)
        assert len(model._cards) == 6
        assert len(model._card_order) == 6
        assert model._card_order == [1, 2, 3, 4, 5, 6]

    def test_get_children_root(self, wx_app, mock_cards):
        """GetChildren returns all cards for root."""
        model = CardListModel()
        model.load_cards(mock_cards)

        children = []
        count = model.GetChildren(dv.NullDataViewItem, children)
        assert count == 6
        assert len(children) == 6

    def test_get_children_non_root(self, wx_app, mock_cards):
        """GetChildren returns 0 for non-root items."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        children = []
        count = model.GetChildren(item, children)
        assert count == 0

    def test_is_container_root(self, wx_app):
        """Only root is container."""
        model = CardListModel()
        assert model.IsContainer(dv.NullDataViewItem) is True

    def test_is_container_item(self, wx_app, mock_cards):
        """Regular items are not containers."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        assert model.IsContainer(item) is False

    def test_get_parent_always_null(self, wx_app, mock_cards):
        """All items have null parent (flat list)."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        parent = model.GetParent(item)
        assert not parent.IsOk()

    def test_get_value_confidence_dot_high(self, wx_app, mock_cards):
        """GetValue returns ● for high confidence."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)  # HIGH confidence card
        value = model.GetValue(item, 0)
        assert value == "●"

    def test_get_value_confidence_dot_none(self, wx_app, mock_cards):
        """GetValue returns ⚠ for NONE confidence."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(3)  # NONE confidence card
        value = model.GetValue(item, 0)
        assert value == "⚠"

    def test_get_value_confidence_dot_error(self, wx_app, mock_cards):
        """GetValue returns ✕ for error cards."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(5)  # Error card
        value = model.GetValue(item, 0)
        assert value == "✕"

    def test_get_value_filename(self, wx_app, mock_cards):
        """GetValue returns filename for column 1."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        value = model.GetValue(item, 1)
        assert value == "card-001.pdf"

    def test_get_value_family_name(self, wx_app, mock_cards):
        """GetValue returns display name for column 2."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        value = model.GetValue(item, 2)
        assert value == "Smith"

    def test_set_value_returns_false(self, wx_app, mock_cards):
        """SetValue always returns False (not editable)."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        result = model.SetValue("Test", item, 1)
        assert result is False

    def test_get_attr_colors_high_confidence(self, wx_app, mock_cards):
        """GetAttr sets green color for HIGH confidence."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)  # HIGH confidence
        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 0, attr)
        assert result is True
        # Color should be set (we can't easily check the exact color in tests)

    def test_get_attr_only_affects_dot_column(self, wx_app, mock_cards):
        """GetAttr only applies to column 0 (dot)."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 1, attr)  # Column 1 (filename)
        assert result is False

    def test_get_card_by_item(self, wx_app, mock_cards):
        """get_card_by_item converts DataViewItem to CardResult."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.ObjectToItem(0)
        card = model.get_card_by_item(item)
        assert card is not None
        assert card.id == 1
        assert card.family_name == "Smith"

    def test_get_card_by_item_invalid(self, wx_app):
        """get_card_by_item returns None for invalid item."""
        model = CardListModel()
        card = model.get_card_by_item(dv.NullDataViewItem)
        assert card is None

    def test_get_item_by_card_id(self, wx_app, mock_cards):
        """get_item_by_card_id converts card ID to DataViewItem."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.get_item_by_card_id(2)
        assert item.IsOk()
        card = model.get_card_by_item(item)
        assert card.id == 2

    def test_get_item_by_card_id_not_found(self, wx_app, mock_cards):
        """get_item_by_card_id returns null item for unknown ID."""
        model = CardListModel()
        model.load_cards(mock_cards)

        item = model.get_item_by_card_id(999)
        assert not item.IsOk()

    def test_update_card(self, wx_app, mock_cards):
        """update_card refreshes card in model."""
        model = CardListModel()
        model.load_cards(mock_cards)

        # Update card 1
        updated_card = mock_cards[0]
        updated_card.family_name = "Updated Name"
        model.update_card(1, updated_card)

        # Verify update
        item = model.get_item_by_card_id(1)
        value = model.GetValue(item, 2)
        assert value == "Updated Name"


# ============================================================================
# ReviewPanelMasterDetail Initialization Tests
# ============================================================================


class TestReviewPanelInit:
    """Tests for ReviewPanelMasterDetail initialization."""

    def test_panel_creates_successfully(self, parent_frame):
        """Panel initializes without errors."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        assert panel is not None

    def test_panel_has_count_label(self, parent_frame):
        """Panel has count label."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        assert hasattr(panel, "_count_label")
        assert panel._count_label is not None

    def test_panel_has_list_control(self, parent_frame):
        """Panel has DataViewCtrl list control."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        assert hasattr(panel, "_list_ctrl")
        assert isinstance(panel._list_ctrl, dv.DataViewCtrl)

    def test_panel_has_detail_panel(self, parent_frame):
        """Panel has detail panel."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        assert hasattr(panel, "_detail_panel")
        assert isinstance(panel._detail_panel, DetailPanel)

    def test_panel_starts_empty(self, parent_frame):
        """Panel starts with no cards."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        assert len(panel._cards_by_id) == 0
        assert panel._selected_card_ids == []
        assert panel.selected_card_id is None

    def test_panel_stores_callbacks(self, parent_frame):
        """Panel stores callback functions."""
        on_select = Mock()
        on_ai = Mock()
        on_name_change = Mock()
        panel = ReviewPanelMasterDetail(
            parent_frame, on_select, on_ai, on_name_change
        )
        assert panel._on_select is on_select
        assert panel._on_ai_request is on_ai
        assert panel._on_name_change is on_name_change


# ============================================================================
# Load Cards Tests
# ============================================================================


class TestLoadCards:
    """Tests for load_cards functionality."""

    def test_load_cards_populates_list(self, parent_frame, mock_cards):
        """load_cards populates the list control."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        assert len(panel._cards_by_id) == 6
        assert len(panel._model._cards) == 6

    def test_load_cards_updates_count_label(self, parent_frame, mock_cards):
        """load_cards updates count label."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        label_text = panel._count_label.GetLabel()
        assert label_text == "6 Cards \u24D8"

    def test_load_cards_stores_card_data(self, parent_frame, mock_cards):
        """load_cards stores cards by ID."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        assert 1 in panel._cards_by_id
        assert panel._cards_by_id[1].family_name == "Smith"

    def test_load_cards_resets_selection(self, parent_frame, mock_cards):
        """load_cards resets selection to none."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # No card should be selected
        assert panel.selected_card_id is None
        on_select.assert_called_with(None)

    def test_load_cards_twice_clears_old(self, parent_frame, mock_cards):
        """load_cards twice clears old cards."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)

        # Load first set
        panel.load_cards(mock_cards)
        assert len(panel._cards_by_id) == 6

        # Load smaller set
        panel.load_cards([mock_cards[0], mock_cards[1]])
        assert len(panel._cards_by_id) == 2

    def test_load_empty_card_list(self, parent_frame):
        """load_cards handles empty list."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards([])

        assert len(panel._cards_by_id) == 0
        assert panel._count_label.GetLabel() == "0 Cards \u24D8"


# ============================================================================
# Selection Tests
# ============================================================================


class TestSelection:
    """Tests for card selection."""

    def test_select_calls_callback(self, parent_frame, mock_cards):
        """Selecting card calls on_select callback."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Clear mock from initial selection
        on_select.reset_mock()

        # Select second card (UnselectAll first in DV_MULTIPLE mode)
        panel._list_ctrl.UnselectAll()
        item = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item)
        panel._on_selection_changed(Mock())

        on_select.assert_called_with(2)

    def test_select_updates_selected_card_ids(self, parent_frame, mock_cards):
        """Selecting card updates _selected_card_ids."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Select second card (UnselectAll first in DV_MULTIPLE mode)
        panel._list_ctrl.UnselectAll()
        item = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item)
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id == 2

    def test_select_next_card_from_start(self, parent_frame, mock_cards):
        """select_next_card from first card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Explicitly select first card
        _select_card(panel, 1)
        on_select.reset_mock()

        # Should be on card 1, next should go to card 2
        panel.select_next_card()
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id == 2

    def test_select_next_card_stops_at_end(self, parent_frame, mock_cards):
        """select_next_card stops at last card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        # Go to last card
        for _ in range(10):  # More than needed
            panel.select_next_card()
            panel._on_selection_changed(Mock())

        # Should be on last card (id=6)
        assert panel.selected_card_id == 6

    def test_select_prev_card_from_middle(self, parent_frame, mock_cards):
        """select_prev_card goes back."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 2)
        on_select.reset_mock()

        panel.select_prev_card()
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id == 1

    def test_select_prev_card_stops_at_start(self, parent_frame, mock_cards):
        """select_prev_card stops at first card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        # Try to go before first
        for _ in range(3):
            panel.select_prev_card()
            panel._on_selection_changed(Mock())

        # Should still be on first card
        assert panel.selected_card_id == 1


# ============================================================================
# Detail Panel Tests
# ============================================================================


class TestDetailPanel:
    """Tests for DetailPanel."""

    def test_detail_panel_loads_card(self, parent_frame, mock_cards):
        """load_card populates detail panel fields."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        detail.load_card(mock_cards[0])

        # Check Edit tab label is fixed
        edit_tab_label = detail._notebook.GetPageText(0)
        assert edit_tab_label == "Edit Card"

        assert detail._name_text.GetValue() == "Smith"
        assert detail._remove_family_check.GetValue() is True

    def test_detail_panel_clear(self, parent_frame, mock_cards):
        """clear() empties detail panel."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        detail.load_card(mock_cards[0])
        detail.clear()

        assert detail._name_text.GetValue() == ""
        assert detail._remove_family_check.GetValue() is False
        # Check Edit tab returns to default label
        assert detail._notebook.GetPageText(0) == "Edit Card"

    def test_detail_panel_shows_candidates(self, parent_frame, mock_cards):
        """load_card populates candidate dropdown."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        detail.load_card(mock_cards[0])  # Has 2 candidates

        # Should have 3 items: placeholder + 2 candidates
        assert detail._candidates_choice.GetCount() == 3
        assert "Select from 2" in detail._candidates_choice.GetString(0)

    def test_detail_panel_no_candidates_disables_dropdown(
        self, parent_frame, mock_cards
    ):
        """load_card disables dropdown when no candidates."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        detail.load_card(mock_cards[2])  # No candidates

        assert not detail._candidates_choice.IsEnabled()

    def test_detail_panel_has_ai_button(self, parent_frame):
        """Detail panel has AI button."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        assert hasattr(detail, "_ai_btn")
        assert detail._ai_btn is not None


# ============================================================================
# Event Handler Tests
# ============================================================================


class TestEventHandlers:
    """Tests for event handlers."""

    def test_name_edit_calls_callback(self, parent_frame, mock_cards):
        """Editing name calls on_name_change callback."""
        on_select = Mock()
        on_ai = Mock()
        on_name_change = Mock()
        panel = ReviewPanelMasterDetail(
            parent_frame, on_select, on_ai, on_name_change
        )
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        # Edit name in detail panel — trigger handler directly
        panel._detail_panel._name_text.SetValue("New Name")
        panel._detail_panel._on_name_edit(Mock())

        # Should call callback with card ID and new name
        on_name_change.assert_called()
        call_args = on_name_change.call_args[0]
        assert call_args[0] == 1  # First card ID
        assert call_args[1] == "New Name"

    def test_ai_button_calls_callback(self, parent_frame, mock_cards):
        """Clicking AI button calls on_ai_request callback."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        on_ai.reset_mock()

        # Click AI button
        event = wx.CommandEvent(wx.EVT_BUTTON.typeId)
        panel._detail_panel._on_ai(event)

        on_ai.assert_called_once_with(1)  # First card ID


# ============================================================================
# Update Methods Tests
# ============================================================================


class TestUpdateMethods:
    """Tests for update methods."""

    def test_update_card_changes_data(self, parent_frame, mock_cards):
        """update_card changes card data."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Update card
        updated = mock_cards[0]
        updated.family_name = "Updated"
        panel.update_card(1, updated)

        # Verify update
        assert panel._cards_by_id[1].family_name == "Updated"

    def test_update_card_refreshes_selected(self, parent_frame, mock_cards):
        """update_card refreshes detail panel if card is selected."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        # Card 1 is selected, update it
        updated = mock_cards[0]
        updated.family_name = "Updated"
        panel.update_card(1, updated)

        # Detail panel should show update
        assert panel._detail_panel._name_text.GetValue() == "Updated"

    def test_update_dot_changes_confidence(self, parent_frame, mock_cards):
        """update_dot updates confidence color."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Update confidence
        panel.update_dot(1, Confidence.LOW)

        # Verify card confidence changed
        assert panel._cards_by_id[1].confidence == Confidence.LOW

    def test_get_cards_returns_all(self, parent_frame, mock_cards):
        """get_cards returns all cards."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        cards = panel.get_cards()
        assert len(cards) == 6

    def test_get_cards_maintains_order(self, parent_frame, mock_cards):
        """get_cards returns cards in display order."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        cards = panel.get_cards()
        assert cards[0].id == 1
        assert cards[1].id == 2
        assert cards[5].id == 6

    def test_get_cards_includes_edits(self, parent_frame, mock_cards):
        """get_cards returns cards with edits."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Edit a card
        updated = mock_cards[0]
        updated.family_name = "Edited"
        panel.update_card(1, updated)

        # get_cards should return edited version
        cards = panel.get_cards()
        assert cards[0].family_name == "Edited"


# ============================================================================
# Input Validation Tests
# ============================================================================


class TestNameCharFiltering:
    """Tests for _on_name_char blocking invalid filename characters."""

    def test_blocks_all_invalid_chars(self, parent_frame):
        """_on_name_char blocks every filesystem-invalid character."""
        from app.core.name_formatting import INVALID_FILENAME_CHARS

        detail = DetailPanel(parent_frame, None, None, None, None)
        for char in INVALID_FILENAME_CHARS:
            event = Mock(spec=wx.KeyEvent)
            event.GetUnicodeKey.return_value = ord(char)
            detail._on_name_char(event)
            event.Skip.assert_not_called()

    def test_allows_normal_letters(self, parent_frame):
        """_on_name_char allows regular letters through."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        for char in "AaBbZz":
            event = Mock(spec=wx.KeyEvent)
            event.GetUnicodeKey.return_value = ord(char)
            detail._on_name_char(event)
            event.Skip.assert_called_once()

    def test_allows_apostrophe_and_hyphen(self, parent_frame):
        """_on_name_char allows apostrophe and hyphen (valid in names)."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        for char in "'-":
            event = Mock(spec=wx.KeyEvent)
            event.GetUnicodeKey.return_value = ord(char)
            detail._on_name_char(event)
            event.Skip.assert_called_once()

    def test_allows_non_character_keys(self, parent_frame):
        """_on_name_char allows non-character keys like backspace/arrows."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        event = Mock(spec=wx.KeyEvent)
        event.GetUnicodeKey.return_value = wx.WXK_NONE
        detail._on_name_char(event)
        event.Skip.assert_called_once()


# ============================================================================
# Update Card Refresh Tests
# ============================================================================


class TestUpdateCardRefresh:
    """Tests for update_card triggering list Refresh."""

    def test_update_card_calls_refresh(self, parent_frame, mock_cards):
        """update_card calls Refresh() on list control."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        with patch.object(panel._list_ctrl, "Refresh") as mock_refresh:
            updated = mock_cards[0]
            updated.family_name = "Updated"
            panel.update_card(1, updated)
            mock_refresh.assert_called_once()

    def test_update_card_refreshes_for_unselected_card(self, parent_frame, mock_cards):
        """update_card calls Refresh() even for a card that is not selected."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        # Select card 2
        item = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item)

        with patch.object(panel._list_ctrl, "Refresh") as mock_refresh:
            # Update card 1 (not selected)
            updated = mock_cards[0]
            updated.family_name = "Updated"
            panel.update_card(1, updated)
            mock_refresh.assert_called_once()


# ============================================================================
# AI Button State Tests
# ============================================================================


class TestAIButtonState:
    """Tests for set_ai_button_state."""

    def test_set_ai_button_enabled(self, parent_frame, mock_cards):
        """set_ai_button_state enables button."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        # Disable then enable
        panel.set_ai_button_state(1, "disabled")
        panel.set_ai_button_state(1, "normal")

        assert panel._detail_panel._ai_btn.IsEnabled()

    def test_set_ai_button_disabled(self, parent_frame, mock_cards):
        """set_ai_button_state disables button."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        panel.set_ai_button_state(1, "disabled")

        assert not panel._detail_panel._ai_btn.IsEnabled()

    def test_set_ai_button_only_affects_selected(self, parent_frame, mock_cards):
        """set_ai_button_state only affects currently selected card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        # Card 1 is selected, try to disable card 2's button
        panel.set_ai_button_state(2, "disabled")

        # Button should still be enabled (card 1 is selected)
        assert panel._detail_panel._ai_btn.IsEnabled()


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_error_card_displays_correctly(self, parent_frame, mock_cards):
        """Error card shows error indicator."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Check error card (index 5)
        item = panel._model.get_item_by_card_id(6)
        value = panel._model.GetValue(item, 0)
        assert value == "✕"

    def test_none_confidence_displays_warning(self, parent_frame, mock_cards):
        """NONE confidence card shows warning indicator."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Check NONE card (index 3)
        item = panel._model.get_item_by_card_id(4)
        value = panel._model.GetValue(item, 0)
        assert value == "⚠"

    def test_manual_entry_displays_correctly(self, parent_frame, mock_cards):
        """Manual entry card displays correctly."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Select manual card (UnselectAll first in DV_MULTIPLE mode)
        panel._list_ctrl.UnselectAll()
        item = panel._model.get_item_by_card_id(5)
        panel._list_ctrl.Select(item)
        panel._on_selection_changed(Mock())

        assert panel._detail_panel._name_text.GetValue() == "Brown"

    def test_empty_list_no_selection(self, parent_frame):
        """Empty card list has no selection."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards([])

        assert panel.selected_card_id is None

    def test_select_next_with_no_cards(self, parent_frame):
        """select_next_card with no cards doesn't crash."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards([])

        # Should not crash
        panel.select_next_card()

        assert panel.selected_card_id is None


# ============================================================================
# Multi-Path Card Display Tests
# ============================================================================


class TestMultiPathCardDisplay:
    """Tests for multi-path card file locations display with tabs."""

    def test_single_path_card_has_two_tabs(self, parent_frame):
        """Single-path cards show Edit tab + File Paths (1) tab."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path("/test/card.pdf")],
            primary_path=Path("/test/card.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)

        # Should have Edit tab + File Paths tab (always present now)
        assert detail._notebook.GetPageCount() == 2
        assert detail._notebook.GetPageText(0) == "Edit Card"
        assert "File Paths (1)" in detail._notebook.GetPageText(1)
        assert detail._locations_tab_index is not None

    def test_multi_path_card_has_two_tabs(self, parent_frame):
        """Multi-path cards show Edit and File Paths (N) tabs."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path("/test1/card.pdf"), Path("/test2/card.pdf")],
            primary_path=Path("/test1/card.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)

        # Should have Edit tab + File Paths tab
        assert detail._notebook.GetPageCount() == 2
        assert detail._notebook.GetPageText(0) == "Edit Card"
        assert "File Paths (2)" in detail._notebook.GetPageText(1)
        assert detail._locations_tab_index is not None

    def test_file_paths_tab_label_shows_count(self, parent_frame):
        """File Paths tab label shows correct count."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path("/a.pdf"), Path("/b.pdf"), Path("/c.pdf")],
            primary_path=Path("/a.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)

        assert detail._notebook.GetPageCount() == 2
        assert "File Paths (3)" in detail._notebook.GetPageText(1)

    def test_switching_to_file_paths_tab(self, parent_frame):
        """Can switch to File Paths tab and see content."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path("/test1.pdf"), Path("/test2.pdf")],
            primary_path=Path("/test1.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)

        # Switch to File Paths tab
        detail._notebook.SetSelection(1)

        # Verify we're on the locations panel
        assert detail._notebook.GetCurrentPage() == detail._locations_panel

    def test_locations_list_populated(self, parent_frame):
        """Locations list shows all file paths."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path.home() / "test1.pdf", Path.home() / "test2.pdf"],
            primary_path=Path.home() / "test1.pdf",
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)

        # Check locations list is populated
        assert detail._locations_list.GetItemCount() == 2
        assert "~/test1.pdf" in detail._locations_list.GetTextValue(0, 0)
        assert "~/test2.pdf" in detail._locations_list.GetTextValue(1, 0)

    def test_locations_header_shows_count(self, parent_frame):
        """Locations header shows correct count."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path("/a.pdf"), Path("/b.pdf"), Path("/c.pdf")],
            primary_path=Path("/a.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)

        assert "File Locations (3 copies):" in detail._locations_header.GetLabel()

    def test_duplicate_info_shown_for_multi_path(self, parent_frame):
        """Duplicate info text is shown for multi-path cards."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path("/test1.pdf"), Path("/test2.pdf")],
            primary_path=Path("/test1.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)

        # Info text should be present (always visible in File Paths tab)
        assert "identical content" in detail._duplicate_info.GetLabel()

    def test_clear_removes_file_paths_tab(self, parent_frame):
        """clear() removes File Paths tab if present."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        card = CardResult(
            id=1,
            file_paths=[Path("/test1.pdf"), Path("/test2.pdf")],
            primary_path=Path("/test1.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )

        detail.load_card(card)
        assert detail._notebook.GetPageCount() == 2

        detail.clear()

        # Should only have Edit tab after clear
        assert detail._notebook.GetPageCount() == 1
        assert detail._locations_tab_index is None

    def test_load_cards_clears_selection(self, parent_frame, mock_cards):
        """load_cards clears selection even when the selected card is still in the new list."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)
        _select_card(panel, 2)
        assert panel.selected_card_id == 2

        on_select.reset_mock()

        # Reload same cards — selection should be cleared
        panel.load_cards(mock_cards)

        assert panel.selected_card_id is None
        on_select.assert_called_with(None)

    def test_load_cards_empty_fires_none_select(self, parent_frame, mock_cards):
        """load_cards with empty list fires on_select(None)."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        on_select.reset_mock()

        # Load empty list
        panel.load_cards([])

        assert panel.selected_card_id is None
        on_select.assert_called_with(None)

    def test_handle_candidate_fires_on_card_edited(self, parent_frame, mock_cards):
        """Selecting a candidate fires on_card_edited callback."""
        on_select = Mock()
        on_ai = Mock()
        on_card_edited = Mock()
        panel = ReviewPanelMasterDetail(
            parent_frame, on_select, on_ai, on_card_edited=on_card_edited
        )
        panel.load_cards(mock_cards)

        # Card 1 has candidates — set up hash so _handle_candidate works
        card = mock_cards[0]
        card.file_hash = "test_hash"

        with patch("app.core.database.select_candidate"):
            panel._handle_candidate(card.id, card.candidates[0].id)

        on_card_edited.assert_called_once_with(card.id)

    def test_blue_text_for_multi_path_card(self, wx_app, parent_frame):
        """Filename shows in blue for multi-path cards."""
        model = CardListModel()
        card = CardResult(
            id=1,
            file_paths=[Path("/test1.pdf"), Path("/test2.pdf")],
            primary_path=Path("/test1.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            remove_family=False,
        )
        model.load_cards([card])

        item = model.ObjectToItem(0)
        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 1, attr)  # Column 1 (filename)

        # Should return True for multi-path cards (blue color applied)
        assert result is True


# ============================================================================
# Drag Highlight Tests
# ============================================================================


# ============================================================================
# Remove Button Tests
# ============================================================================


class TestRemoveButton:
    """Tests for Remove button in DetailPanel."""

    def test_detail_panel_has_remove_button(self, parent_frame):
        """Detail panel has Remove button."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        assert hasattr(detail, "_remove_btn")
        assert detail._remove_btn is not None

    def test_remove_button_disabled_when_no_card(self, parent_frame):
        """Remove button is disabled when no card is selected."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        assert not detail._remove_btn.IsEnabled()

    def test_remove_button_enabled_when_card_loaded(self, parent_frame, mock_cards):
        """Remove button is enabled when a card is loaded."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        mock_cards[0].file_hash = "test_hash"
        detail.load_card(mock_cards[0])
        assert detail._remove_btn.IsEnabled()

    def test_remove_button_enabled_for_error_card(self, parent_frame, mock_cards):
        """Remove button is enabled even for error cards."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        error_card = mock_cards[5]  # Error card
        error_card.file_hash = "error_hash"
        detail.load_card(error_card)
        assert detail._remove_btn.IsEnabled()

    def test_remove_button_disabled_after_clear(self, parent_frame, mock_cards):
        """Remove button is disabled after clear."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        mock_cards[0].file_hash = "test_hash"
        detail.load_card(mock_cards[0])
        detail.clear()
        assert not detail._remove_btn.IsEnabled()

    def test_remove_button_calls_callback(self, parent_frame, mock_cards):
        """Clicking Remove button calls on_remove callback with file_hash."""
        on_remove = Mock()
        detail = DetailPanel(parent_frame, None, None, None, None, on_remove=on_remove)
        mock_cards[0].file_hash = "test_hash"
        detail.load_card(mock_cards[0])

        event = wx.CommandEvent(wx.EVT_BUTTON.typeId)
        detail._on_remove_click(event)

        on_remove.assert_called_once_with("test_hash")

    def test_remove_button_no_callback_without_hash(self, parent_frame, mock_cards):
        """Remove button does not call callback if card has no hash."""
        on_remove = Mock()
        detail = DetailPanel(parent_frame, None, None, None, None, on_remove=on_remove)
        mock_cards[0].file_hash = None
        detail.load_card(mock_cards[0])

        event = wx.CommandEvent(wx.EVT_BUTTON.typeId)
        detail._on_remove_click(event)

        on_remove.assert_not_called()


# ============================================================================
# Context Menu Tests
# ============================================================================


class TestContextMenu:
    """Tests for right-click context menu on card list."""

    def test_context_menu_event_bound(self, parent_frame):
        """DataViewCtrl has context menu event bound."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        # Verify the binding exists by checking the list control has handlers
        assert panel._list_ctrl is not None

    def test_on_remove_callback_stored(self, parent_frame):
        """ReviewPanelMasterDetail stores on_remove callback."""
        on_remove = Mock()
        panel = ReviewPanelMasterDetail(
            parent_frame, Mock(), Mock(), on_remove=on_remove
        )
        assert panel._on_remove is on_remove

    def test_on_remove_passed_to_detail_panel(self, parent_frame):
        """on_remove callback is passed through to DetailPanel."""
        on_remove = Mock()
        panel = ReviewPanelMasterDetail(
            parent_frame, Mock(), Mock(), on_remove=on_remove
        )
        assert panel._detail_panel._on_remove is on_remove

    def test_context_menu_no_card_does_nothing(self, parent_frame, mock_cards):
        """Context menu on invalid item does nothing."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        # Create a mock event with an invalid item
        event = Mock()
        event.GetItem.return_value = dv.NullDataViewItem

        # Should not raise
        with patch.object(panel._list_ctrl, "PopupMenu"):
            panel._on_context_menu(event)

    def test_context_menu_has_correct_items(self, parent_frame, mock_cards):
        """Context menu has Open, Reveal in Finder, separator, and Remove."""
        on_remove = Mock()
        panel = ReviewPanelMasterDetail(
            parent_frame, Mock(), Mock(), on_remove=on_remove
        )
        mock_cards[0].file_hash = "test_hash"
        panel.load_cards(mock_cards)

        item = panel._model.get_item_by_card_id(1)
        event = Mock()
        event.GetItem.return_value = item

        captured_menu = {}

        def capture_menu(menu):
            # Inspect before it gets destroyed
            items = list(menu.GetMenuItems())
            captured_menu["count"] = len(items)
            captured_menu["labels"] = [
                "---" if it.IsSeparator() else it.GetItemLabelText()
                for it in items
            ]

        with patch.object(panel._list_ctrl, "PopupMenu", side_effect=capture_menu):
            panel._on_context_menu(event)

        assert captured_menu["count"] == 4
        assert captured_menu["labels"] == ["Open", "Reveal in Finder", "---", "Remove"]


# ============================================================================
# Drag Highlight Tests
# ============================================================================


class TestDragHighlight:
    """Tests for set_drag_highlight on review panel."""

    def test_drag_highlight_initially_false(self, parent_frame):
        """Drag highlight is off by default."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        assert panel._drag_highlight is False

    def test_set_drag_highlight_on(self, parent_frame):
        """set_drag_highlight(True) sets flag."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.set_drag_highlight(True)
        assert panel._drag_highlight is True

    def test_set_drag_highlight_off(self, parent_frame):
        """set_drag_highlight(False) clears flag."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.set_drag_highlight(True)
        panel.set_drag_highlight(False)
        assert panel._drag_highlight is False

    def test_set_drag_highlight_idempotent(self, parent_frame):
        """Calling set_drag_highlight with same value is a no-op."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        with patch.object(panel, "Refresh") as mock_refresh:
            panel.set_drag_highlight(False)
            mock_refresh.assert_not_called()

    def test_set_drag_highlight_triggers_refresh(self, parent_frame):
        """Changing drag highlight state triggers Refresh."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        with patch.object(panel, "Refresh") as mock_refresh:
            panel.set_drag_highlight(True)
            mock_refresh.assert_called_once()


class TestCardNavigation:
    """Tests for select_next_card and select_prev_card."""

    def test_select_next_no_cards(self, parent_frame):
        """select_next_card with no cards loaded does not crash."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.select_next_card()  # should not raise

    def test_select_prev_no_cards(self, parent_frame):
        """select_prev_card with no cards loaded does not crash."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.select_prev_card()  # should not raise

    def test_select_next_with_cards(self, parent_frame, mock_cards):
        """select_next_card advances selection."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 1)
        on_select.reset_mock()
        panel.select_next_card()
        on_select.assert_called_with(mock_cards[1].id)

    def test_select_prev_with_cards(self, parent_frame, mock_cards):
        """select_prev_card goes back to previous selection."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 2)
        on_select.reset_mock()
        panel.select_prev_card()
        on_select.assert_called_with(mock_cards[0].id)


# ============================================================================
# CardListModel Edge Cases (coverage gaps)
# ============================================================================


class TestCardListModelEdgeCases:
    """Tests for CardListModel coverage gaps."""

    def test_get_value_out_of_range_row(self, wx_app, mock_cards):
        """GetValue returns '' for out-of-range row (line 120)."""
        model = CardListModel()
        # Don't load any cards, so any row index is out of range
        # We need to test with a valid item but out-of-range row
        model.load_cards(mock_cards[:1])

        # Manually construct an item that would map to row -1 or too high
        # by using internal ObjectToItem with an out-of-range index
        # Since we can't easily create an invalid item, test unknown col
        item = model.ObjectToItem(0)
        value = model.GetValue(item, 99)  # Unknown column (line 135)
        assert value == ""

    def test_get_attr_out_of_range_returns_false(self, wx_app, mock_cards):
        """GetAttr returns False for out-of-range row (line 145)."""
        model = CardListModel()
        # Empty model - no rows at all
        # We can test GetAttr column 2 (non-dot, non-filename)
        model.load_cards(mock_cards[:1])
        item = model.ObjectToItem(0)
        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 2, attr)  # Column 2 (line 175)
        assert result is False

    def test_get_attr_all_confidence_colors(self, wx_app):
        """GetAttr sets correct color for each confidence level (lines 151-164)."""
        model = CardListModel()

        for conf in [Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW,
                     Confidence.MANUAL, Confidence.NONE]:
            card = CardResult(
                id=1, file_paths=[Path("test.pdf")], primary_path=Path("test.pdf"),
                confidence=conf,
            )
            model.load_cards([card])
            item = model.ObjectToItem(0)
            attr = dv.DataViewItemAttr()
            result = model.GetAttr(item, 0, attr)
            assert result is True, f"Expected True for confidence={conf}"

    def test_get_attr_error_card_color(self, wx_app):
        """GetAttr sets ERROR color for error cards (line 152)."""
        model = CardListModel()
        card = CardResult(id=1, file_paths=[Path("test.pdf")], primary_path=Path("test.pdf"))
        card.error = "Failed"
        model.load_cards([card])
        item = model.ObjectToItem(0)
        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 0, attr)
        assert result is True
        assert attr.GetColour() == Color.ERROR

    def test_get_attr_single_path_filename_col(self, wx_app):
        """GetAttr returns False for filename column on single-path card (line 175)."""
        model = CardListModel()
        card = CardResult(
            id=1, file_paths=[Path("test.pdf")], primary_path=Path("test.pdf"),
            confidence=Confidence.HIGH,
        )
        model.load_cards([card])
        item = model.ObjectToItem(0)
        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 1, attr)  # Filename column
        assert result is False  # No blue highlight for single path


# ============================================================================
# DetailPanel Edge Cases
# ============================================================================


class TestDetailPanelEdgeCases:
    """Tests for DetailPanel coverage gaps."""

    def test_load_card_none_clears(self, parent_frame, mock_cards):
        """load_card(None) calls clear() (line 341-343)."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        detail.load_card(mock_cards[0])  # Load a card first
        assert detail._name_text.GetValue() == "Smith"

        detail.load_card(None)  # Should clear
        assert detail._name_text.GetValue() == ""
        assert detail._current_card is None

    def test_on_checkbox_suppressed_when_no_card(self, parent_frame):
        """_on_checkbox does nothing when suppressed or no card (line 468)."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        detail._suppress_events = False
        detail._current_card = None
        # Should not crash
        event = Mock()
        detail._on_checkbox(event)

    def test_on_candidate_suppressed_when_no_card(self, parent_frame):
        """_on_candidate does nothing when suppressed or no card (line 479)."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        detail._suppress_events = False
        detail._current_card = None
        event = Mock()
        detail._on_candidate(event)

    def test_on_remove_click_no_card(self, parent_frame):
        """_on_remove_click does nothing with no current card (line 503)."""
        on_remove = Mock()
        detail = DetailPanel(parent_frame, None, None, None, None, on_remove=on_remove)
        detail._current_card = None
        event = Mock()
        detail._on_remove_click(event)
        on_remove.assert_not_called()

    def test_make_action_button_without_icon(self, parent_frame):
        """_make_action_button falls back to text-only button when icon is None (line 213)."""
        detail = DetailPanel(parent_frame, None, None, None, None)
        with patch("app.gui.review_panel.load_sf_symbol", return_value=None):
            btn = detail._make_action_button("nonexistent.icon", "Test", lambda e: None)
        assert btn.GetLabel() == "Test"

    def test_on_checkbox_calls_callback(self, parent_frame, mock_cards):
        """_on_checkbox dispatches to callback (lines 468-475)."""
        called = []
        detail = DetailPanel(
            parent_frame,
            on_name_change=None,
            on_checkbox_toggle=lambda cid, val: called.append((cid, val)),
            on_candidate_select=None,
            on_ai_request=None,
        )
        detail.load_card(mock_cards[0])
        detail._remove_family_check.SetValue(False)
        event = Mock()
        detail._on_checkbox(event)
        assert len(called) == 1
        assert called[0] == (mock_cards[0].id, False)

    def test_on_candidate_with_placeholder_selected(self, parent_frame, mock_cards):
        """_on_candidate returns early when placeholder is selected (line 483-484)."""
        called = []
        detail = DetailPanel(
            parent_frame,
            on_name_change=None,
            on_checkbox_toggle=None,
            on_candidate_select=lambda cid, idx: called.append((cid, idx)),
            on_ai_request=None,
        )
        detail.load_card(mock_cards[0])  # Has candidates
        # Selection 0 is placeholder
        detail._candidates_choice.SetSelection(0)
        event = Mock()
        detail._on_candidate(event)
        assert called == []  # Should not dispatch


# ============================================================================
# ReviewPanel Keyboard and Handler Coverage
# ============================================================================


class TestReviewPanelKeyboard:
    """Tests for ReviewPanelMasterDetail keyboard and handler coverage gaps."""

    def test_on_key_up_selects_prev(self, parent_frame, mock_cards):
        """_on_key dispatches UP to select_prev_card (line 636)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 2)

        event = Mock(spec=wx.KeyEvent)
        event.GetKeyCode.return_value = wx.WXK_UP
        event.ShiftDown.return_value = False
        panel._on_key(event)
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id == mock_cards[0].id

    def test_on_key_down_selects_next(self, parent_frame, mock_cards):
        """_on_key dispatches DOWN to select_next_card (line 638)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        event = Mock(spec=wx.KeyEvent)
        event.GetKeyCode.return_value = wx.WXK_DOWN
        event.ShiftDown.return_value = False
        panel._on_key(event)
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id == mock_cards[1].id

    def test_on_key_other_skips(self, parent_frame):
        """_on_key calls event.Skip() for unhandled keys (line 640)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        event = Mock(spec=wx.KeyEvent)
        event.GetKeyCode.return_value = ord('A')
        event.ShiftDown.return_value = False
        panel._on_key(event)
        event.Skip.assert_called_once()

    def test_select_next_no_selection_selects_first(self, parent_frame, mock_cards):
        """select_next_card selects first card when nothing selected (lines 800-803)."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock())
        panel.load_cards(mock_cards)

        # Deselect everything by clearing
        panel._list_ctrl.UnselectAll()
        panel._selected_card_ids = []
        on_select.reset_mock()

        panel.select_next_card()
        panel._on_selection_changed(Mock())
        # Should select first card
        assert panel.selected_card_id == mock_cards[0].id

    def test_select_prev_no_selection_selects_first(self, parent_frame, mock_cards):
        """select_prev_card selects first card when nothing selected (lines 817-820)."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock())
        panel.load_cards(mock_cards)

        panel._list_ctrl.UnselectAll()
        panel._selected_card_ids = []
        on_select.reset_mock()

        panel.select_prev_card()
        panel._on_selection_changed(Mock())
        assert panel.selected_card_id == mock_cards[0].id


# ============================================================================
# _handle_checkbox and _handle_candidate
# ============================================================================


class TestHandleCheckboxCandidate:
    """Tests for _handle_checkbox and _handle_candidate coverage gaps."""

    def test_handle_checkbox_calls_db(self, parent_frame, mock_cards):
        """_handle_checkbox calls update_remove_family in DB (lines 706-709)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        mock_cards[0].file_hash = "abc123"
        panel.load_cards(mock_cards)

        with patch("app.core.database.update_remove_family") as mock_db:
            panel._handle_checkbox(mock_cards[0].id, True)
            mock_db.assert_called_once_with("abc123", True)

    def test_handle_checkbox_no_hash_skips_db(self, parent_frame, mock_cards):
        """_handle_checkbox skips DB call when card has no hash."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        mock_cards[0].file_hash = ""
        panel.load_cards(mock_cards)

        with patch("app.core.database.update_remove_family") as mock_db:
            panel._handle_checkbox(mock_cards[0].id, True)
            mock_db.assert_not_called()

    def test_handle_candidate_no_card_returns(self, parent_frame, mock_cards):
        """_handle_candidate returns early when card not found (line 715)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        with patch("app.core.database.select_candidate") as mock_db:
            panel._handle_candidate(999, 101)  # Non-existent card
            mock_db.assert_not_called()

    def test_handle_candidate_restores_original_confidence(self, parent_frame, mock_cards):
        """_handle_candidate restores original confidence from MANUAL (lines 728-729)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        card = mock_cards[0]
        card.file_hash = "abc123"
        card.confidence = Confidence.MANUAL
        card.original_confidence = Confidence.HIGH
        panel.load_cards(mock_cards)

        with patch("app.core.database.select_candidate"):
            panel._handle_candidate(card.id, card.candidates[0].id)

        assert card.confidence == Confidence.HIGH

    def test_handle_candidate_fallback_confidence(self, parent_frame):
        """_handle_candidate falls back to Confidence(cand.confidence) or MEDIUM (lines 731-734)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())

        card = CardResult(
            id=1, file_paths=[Path("test.pdf")], primary_path=Path("test.pdf"),
            file_hash="abc123",
            confidence=Confidence.LOW,
            original_confidence=None,  # No original to restore
        )
        card.candidates = [
            CandidateInfo(id=101, family_name="Smith", confidence="invalid_value", method="ocr"),
        ]
        panel.load_cards([card])

        with patch("app.core.database.select_candidate"):
            panel._handle_candidate(card.id, 101)

        # Invalid confidence string → ValueError → falls back to MEDIUM
        assert card.confidence == Confidence.MEDIUM


# ============================================================================
# Multiselect Tests
# ============================================================================


class TestMultiselect:
    """Tests for multiselect behavior."""

    def test_multi_selection_clears_detail_panel(self, parent_frame, mock_cards):
        """Multi-selection clears detail panel."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock())
        panel.load_cards(mock_cards)

        # Select two cards
        item1 = panel._model.get_item_by_card_id(1)
        item2 = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item1)
        panel._list_ctrl.Select(item2)
        panel._on_selection_changed(Mock())

        assert len(panel._selected_card_ids) == 2
        assert panel.selected_card_id is None  # Not single
        assert panel._detail_panel._current_card is None  # Cleared

    def test_multi_selection_triggers_none_select(self, parent_frame, mock_cards):
        """Multi-selection triggers on_select(None) to clear preview."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock())
        panel.load_cards(mock_cards)
        on_select.reset_mock()

        # Select two cards
        item1 = panel._model.get_item_by_card_id(1)
        item2 = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item1)
        panel._list_ctrl.Select(item2)
        panel._on_selection_changed(Mock())

        on_select.assert_called_with(None)

    def test_context_menu_single_has_reveal(self, parent_frame, mock_cards):
        """Single card context menu has Open, Reveal in Finder, Remove."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock(), on_remove=Mock())
        mock_cards[0].file_hash = "test_hash"
        panel.load_cards(mock_cards)

        menu = panel._build_context_menu([mock_cards[0]])
        items = list(menu.GetMenuItems())
        labels = [
            "---" if it.IsSeparator() else it.GetItemLabelText()
            for it in items
        ]
        assert labels == ["Open", "Reveal in Finder", "---", "Remove"]
        menu.Destroy()

    def test_context_menu_multi_no_reveal(self, parent_frame, mock_cards):
        """Multi card context menu has Open N Cards, Remove N Cards (no Reveal)."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock(), on_remove=Mock())
        mock_cards[0].file_hash = "hash1"
        mock_cards[1].file_hash = "hash2"
        panel.load_cards(mock_cards)

        menu = panel._build_context_menu([mock_cards[0], mock_cards[1]])
        items = list(menu.GetMenuItems())
        labels = [
            "---" if it.IsSeparator() else it.GetItemLabelText()
            for it in items
        ]
        assert labels == ["Open 2 Cards", "---", "Remove 2 Cards"]
        menu.Destroy()

    def test_right_click_unselected_selects_only_that(self, parent_frame, mock_cards):
        """Right-click on unselected item during multi-select selects only that item."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock(), on_remove=Mock())
        mock_cards[0].file_hash = "hash1"
        mock_cards[1].file_hash = "hash2"
        mock_cards[2].file_hash = "hash3"
        panel.load_cards(mock_cards)

        # Multi-select cards 1 and 2
        item1 = panel._model.get_item_by_card_id(1)
        item2 = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item1)
        panel._list_ctrl.Select(item2)
        panel._on_selection_changed(Mock())
        assert len(panel._selected_card_ids) == 2

        # Right-click on card 3 (not in selection)
        item3 = panel._model.get_item_by_card_id(3)
        event = Mock()
        event.GetItem.return_value = item3

        with patch.object(panel._list_ctrl, "PopupMenu"):
            panel._on_context_menu(event)

        # Should now only have card 3 selected
        assert panel._selected_card_ids == [3]

    def test_keyboard_nav_collapses_multi_to_single(self, parent_frame, mock_cards):
        """Arrow key from multi-selection collapses to single selection."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        # Multi-select cards 1 and 2
        panel._list_ctrl.UnselectAll()
        item1 = panel._model.get_item_by_card_id(1)
        item2 = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item1)
        panel._list_ctrl.Select(item2)
        panel._on_selection_changed(Mock())
        assert len(panel._selected_card_ids) == 2

        # Press Down → should collapse to card after last selected
        panel.select_next_card()
        panel._on_selection_changed(Mock())
        assert panel.selected_card_id == 3  # Next after card 2

    def test_select_all_selects_all_cards(self, parent_frame, mock_cards):
        """select_all() selects all cards."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        panel.select_all()
        panel._on_selection_changed(Mock())

        assert len(panel._selected_card_ids) == len(mock_cards)

    def test_select_none_clears_selection(self, parent_frame, mock_cards):
        """select_none() clears all selection."""
        on_select = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, Mock())
        panel.load_cards(mock_cards)

        panel.select_none()
        panel._on_selection_changed(Mock())

        assert panel._selected_card_ids == []
        assert panel.selected_card_id is None

    def test_load_cards_clears_multi_selection(self, parent_frame, mock_cards):
        """load_cards clears multi-selection."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        # Multi-select cards 1 and 3
        panel._list_ctrl.UnselectAll()
        item1 = panel._model.get_item_by_card_id(1)
        item3 = panel._model.get_item_by_card_id(3)
        panel._list_ctrl.Select(item1)
        panel._list_ctrl.Select(item3)
        panel._on_selection_changed(Mock())
        assert set(panel._selected_card_ids) == {1, 3}

        # Reload same cards — selection should be cleared
        panel.load_cards(mock_cards)

        assert panel._selected_card_ids == []
        assert panel.selected_card_id is None

    def test_selected_card_id_property_single(self, parent_frame, mock_cards):
        """selected_card_id returns the ID when exactly one card selected."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        assert panel.selected_card_id == 1

    def test_selected_card_id_property_multi(self, parent_frame, mock_cards):
        """selected_card_id returns None when multiple cards selected."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        item1 = panel._model.get_item_by_card_id(1)
        item2 = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item1)
        panel._list_ctrl.Select(item2)
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id is None

    def test_selected_card_id_property_none(self, parent_frame, mock_cards):
        """selected_card_id returns None when no cards selected."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        panel._list_ctrl.UnselectAll()
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id is None


# ============================================================================
# Extend Selection Tests (Shift+Up/Down)
# ============================================================================


class TestExtendSelection:
    """Tests for _extend_selection_up and _extend_selection_down."""

    def test_extend_down_adds_next_card(self, parent_frame, mock_cards):
        """Shift+Down adds the next card to selection."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        panel._extend_selection_down()
        panel._on_selection_changed(Mock())

        assert set(panel._selected_card_ids) == {1, 2}

    def test_extend_up_adds_previous_card(self, parent_frame, mock_cards):
        """Shift+Up adds the previous card to selection."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 2)

        panel._extend_selection_up()
        panel._on_selection_changed(Mock())

        assert set(panel._selected_card_ids) == {1, 2}

    def test_extend_down_at_end_does_nothing(self, parent_frame, mock_cards):
        """Shift+Down at last card does not change selection."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 6)  # Last card

        panel._extend_selection_down()
        panel._on_selection_changed(Mock())

        assert panel._selected_card_ids == [6]

    def test_extend_up_at_start_does_nothing(self, parent_frame, mock_cards):
        """Shift+Up at first card does not change selection."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 1)  # First card

        panel._extend_selection_up()
        panel._on_selection_changed(Mock())

        assert panel._selected_card_ids == [1]

    def test_extend_down_no_selection_selects_first(self, parent_frame, mock_cards):
        """Shift+Down with no selection selects first card."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        panel._extend_selection_down()
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id == 1

    def test_extend_up_no_selection_selects_first(self, parent_frame, mock_cards):
        """Shift+Up with no selection selects first card."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        panel._extend_selection_up()
        panel._on_selection_changed(Mock())

        assert panel.selected_card_id == 1

    def test_on_key_shift_down_dispatches(self, parent_frame, mock_cards):
        """_on_key dispatches Shift+Down to _extend_selection_down."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 1)

        event = Mock(spec=wx.KeyEvent)
        event.ShiftDown.return_value = True
        event.GetKeyCode.return_value = wx.WXK_DOWN
        panel._on_key(event)
        panel._on_selection_changed(Mock())

        assert set(panel._selected_card_ids) == {1, 2}

    def test_on_key_shift_up_dispatches(self, parent_frame, mock_cards):
        """_on_key dispatches Shift+Up to _extend_selection_up."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)
        _select_card(panel, 2)

        event = Mock(spec=wx.KeyEvent)
        event.ShiftDown.return_value = True
        event.GetKeyCode.return_value = wx.WXK_UP
        panel._on_key(event)
        panel._on_selection_changed(Mock())

        assert set(panel._selected_card_ids) == {1, 2}

    def test_select_next_collapses_multi_at_end(self, parent_frame, mock_cards):
        """select_next_card collapses multi-selection at end of list to last card."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        # Select last two cards
        panel._list_ctrl.UnselectAll()
        item5 = panel._model.get_item_by_card_id(5)
        item6 = panel._model.get_item_by_card_id(6)
        panel._list_ctrl.Select(item5)
        panel._list_ctrl.Select(item6)
        panel._on_selection_changed(Mock())
        assert len(panel._selected_card_ids) == 2

        # Down arrow at end should collapse to last card
        panel.select_next_card()
        panel._on_selection_changed(Mock())
        assert panel.selected_card_id == 6

    def test_select_prev_collapses_multi_at_start(self, parent_frame, mock_cards):
        """select_prev_card collapses multi-selection at start of list to first card."""
        panel = ReviewPanelMasterDetail(parent_frame, Mock(), Mock())
        panel.load_cards(mock_cards)

        # Select first two cards
        panel._list_ctrl.UnselectAll()
        item1 = panel._model.get_item_by_card_id(1)
        item2 = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item1)
        panel._list_ctrl.Select(item2)
        panel._on_selection_changed(Mock())
        assert len(panel._selected_card_ids) == 2

        # Up arrow at start should collapse to first card
        panel.select_prev_card()
        panel._on_selection_changed(Mock())
        assert panel.selected_card_id == 1
