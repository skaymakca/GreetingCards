"""Tests for wx_review_panel_master_detail.py - Master-Detail Review Panel."""

import wx
import wx.dataview as dv
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from app.gui.wx_review_panel_master_detail import (
    CardListModel,
    DetailPanel,
    ReviewPanelMasterDetail,
)
from app.models.card import CardResult, Confidence, CandidateInfo


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
        assert panel._selected_card_id is None

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
        assert "6 cards" in label_text

    def test_load_cards_stores_card_data(self, parent_frame, mock_cards):
        """load_cards stores cards by ID."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        assert 1 in panel._cards_by_id
        assert panel._cards_by_id[1].family_name == "Smith"

    def test_load_cards_selects_first(self, parent_frame, mock_cards):
        """load_cards auto-selects first card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # First card should be selected
        assert panel._selected_card_id == 1
        on_select.assert_called_once_with(1)

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
        assert panel._count_label.GetLabel() == "0 cards"


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

        # Select second card
        item = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item)
        wx.GetApp().Yield()  # Process events

        on_select.assert_called_with(2)

    def test_select_updates_selected_card_id(self, parent_frame, mock_cards):
        """Selecting card updates _selected_card_id."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Select second card
        item = panel._model.get_item_by_card_id(2)
        panel._list_ctrl.Select(item)
        wx.GetApp().Yield()

        assert panel._selected_card_id == 2

    def test_select_next_card_from_start(self, parent_frame, mock_cards):
        """select_next_card from first card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Clear mock from initial selection
        on_select.reset_mock()

        # Should be on card 1, next should go to card 2
        panel.select_next_card()
        wx.GetApp().Yield()

        assert panel._selected_card_id == 2

    def test_select_next_card_stops_at_end(self, parent_frame, mock_cards):
        """select_next_card stops at last card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Go to last card
        for _ in range(10):  # More than needed
            panel.select_next_card()
            wx.GetApp().Yield()

        # Should be on last card (id=6)
        assert panel._selected_card_id == 6

    def test_select_prev_card_from_middle(self, parent_frame, mock_cards):
        """select_prev_card goes back."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Go forward then back
        panel.select_next_card()  # To card 2
        wx.GetApp().Yield()
        on_select.reset_mock()

        panel.select_prev_card()  # Back to card 1
        wx.GetApp().Yield()

        assert panel._selected_card_id == 1

    def test_select_prev_card_stops_at_start(self, parent_frame, mock_cards):
        """select_prev_card stops at first card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

        # Try to go before first
        for _ in range(3):
            panel.select_prev_card()
            wx.GetApp().Yield()

        # Should still be on first card
        assert panel._selected_card_id == 1


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
        wx.GetApp().Yield()  # Process UI updates

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

        # Edit name in detail panel
        panel._detail_panel._name_text.SetValue("New Name")
        wx.GetApp().Yield()

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

        # Clear mock from initial load
        on_ai.reset_mock()

        # Click AI button
        event = wx.CommandEvent(wx.EVT_BUTTON.typeId)
        panel._detail_panel._on_ai(event)
        wx.GetApp().Yield()

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

        panel.set_ai_button_state(1, "disabled")

        assert not panel._detail_panel._ai_btn.IsEnabled()

    def test_set_ai_button_only_affects_selected(self, parent_frame, mock_cards):
        """set_ai_button_state only affects currently selected card."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards(mock_cards)

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

        # Select manual card
        item = panel._model.get_item_by_card_id(5)
        panel._list_ctrl.Select(item)
        wx.GetApp().Yield()

        assert panel._detail_panel._name_text.GetValue() == "Brown"

    def test_empty_list_no_selection(self, parent_frame):
        """Empty card list has no selection."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards([])

        assert panel._selected_card_id is None

    def test_select_next_with_no_cards(self, parent_frame):
        """select_next_card with no cards doesn't crash."""
        on_select = Mock()
        on_ai = Mock()
        panel = ReviewPanelMasterDetail(parent_frame, on_select, on_ai)
        panel.load_cards([])

        # Should not crash
        panel.select_next_card()
        wx.GetApp().Yield()

        assert panel._selected_card_id is None


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
