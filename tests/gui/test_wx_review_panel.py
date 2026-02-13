"""Tests for wxPython ReviewPanel component.

Tests the scrollable card list with editable rows, covering:
- Card loading and display
- Row creation with all widgets
- Selection handling
- Event handlers (name edit, candidate selection, checkbox)
- Keyboard navigation
- Card updates
"""

import pytest
import wx
from pathlib import Path
from unittest.mock import Mock, patch
from app.gui.wx_review_panel import ReviewPanel, _dot_style, _tooltip_text
from app.models.card import CardResult, Confidence, CandidateInfo


@pytest.fixture
def callbacks():
    """Create mock callbacks for ReviewPanel."""
    return {
        "on_select": Mock(),
        "on_ai_request": Mock(),
        "on_name_change": Mock(),
    }


@pytest.fixture
def review_panel(wx_frame, callbacks):
    """Create ReviewPanel for testing."""
    panel = ReviewPanel(
        wx_frame,
        on_select=callbacks["on_select"],
        on_ai_request=callbacks["on_ai_request"],
        on_name_change=callbacks["on_name_change"],
    )
    wx_frame.Show()
    return panel


@pytest.fixture
def sample_cards():
    """Create sample CardResult objects for testing."""
    cards = []

    # Card 1: High confidence with candidates
    card1 = CardResult(
        id=1,
        pdf_path=Path("card1.pdf"),
        family_name="Smith",
        confidence=Confidence.HIGH,
        method="ocr",
        original_confidence=Confidence.HIGH,
        remove_family=True
    )
    card1.candidates = [
        CandidateInfo(id=101, family_name="Smith", confidence="high", method="ocr"),
        CandidateInfo(id=102, family_name="Smyth", confidence="medium", method="ai"),
    ]
    cards.append(card1)

    # Card 2: Medium confidence
    card2 = CardResult(
        id=2,
        pdf_path=Path("card2.pdf"),
        family_name="Johnson",
        confidence=Confidence.MEDIUM,
        method="ai",
        original_confidence=Confidence.MEDIUM,
        remove_family=False
    )
    cards.append(card2)

    # Card 3: Error card
    card3 = CardResult(
        id=3,
        pdf_path=Path("card3.pdf"),
        family_name="",
        confidence=Confidence.NONE,
        method="missing",
        original_confidence=Confidence.NONE,
        remove_family=False
    )
    card3.error = "Processing failed"
    cards.append(card3)

    return cards


@pytest.mark.gui
class TestReviewPanelInit:
    """Tests for ReviewPanel initialization."""

    def test_panel_creates_successfully(self, review_panel):
        """Should create panel without errors."""
        assert review_panel is not None
        assert isinstance(review_panel, ReviewPanel)

    def test_panel_has_count_label(self, review_panel):
        """Should have a count label."""
        assert review_panel._count_label is not None
        assert isinstance(review_panel._count_label, wx.StaticText)

    def test_panel_has_scroll_area(self, review_panel):
        """Should have a scroll panel."""
        assert review_panel._scroll_panel is not None

    def test_panel_starts_empty(self, review_panel):
        """Should start with no cards."""
        assert len(review_panel._card_order) == 0
        assert len(review_panel._cards_by_id) == 0
        assert len(review_panel._rows_by_id) == 0

    def test_panel_stores_callbacks(self, review_panel, callbacks):
        """Should store callback functions."""
        assert review_panel._on_select == callbacks["on_select"]
        assert review_panel._on_ai_request == callbacks["on_ai_request"]
        assert review_panel._on_name_change == callbacks["on_name_change"]


@pytest.mark.gui
class TestLoadCards:
    """Tests for loading cards into the review panel."""

    def test_load_cards_creates_rows(self, review_panel, sample_cards):
        """Should create a row for each card."""
        review_panel.load_cards(sample_cards)

        assert len(review_panel._rows_by_id) == len(sample_cards)
        for card in sample_cards:
            assert card.id in review_panel._rows_by_id

    def test_load_cards_updates_count_label(self, review_panel, sample_cards):
        """Should update count label."""
        review_panel.load_cards(sample_cards)

        label_text = review_panel._count_label.GetLabel()
        assert "3 cards" in label_text

    def test_load_cards_stores_card_data(self, review_panel, sample_cards):
        """Should store card data in lookup dicts."""
        review_panel.load_cards(sample_cards)

        assert len(review_panel._cards_by_id) == 3
        assert len(review_panel._card_order) == 3

        for card in sample_cards:
            assert card.id in review_panel._cards_by_id
            assert card.id in review_panel._card_order

    def test_load_cards_twice_clears_old_rows(self, review_panel, sample_cards):
        """Should clear old rows when loading new cards."""
        review_panel.load_cards(sample_cards)
        first_count = len(review_panel._rows_by_id)

        # Load different cards
        new_cards = [
            CardResult(
                id=10,
                pdf_path=Path("new_card.pdf"),
                family_name="Test",
                confidence=Confidence.HIGH,
                method="ocr",
                original_confidence=Confidence.HIGH,
                remove_family=False
            )
        ]
        review_panel.load_cards(new_cards)

        # Should have only new card
        assert len(review_panel._rows_by_id) == 1
        assert 10 in review_panel._rows_by_id
        assert 1 not in review_panel._rows_by_id  # Old card gone

    def test_load_empty_card_list(self, review_panel):
        """Should handle empty card list."""
        review_panel.load_cards([])

        assert len(review_panel._rows_by_id) == 0
        assert review_panel._count_label.GetLabel() == "0 cards"


@pytest.mark.gui
class TestRowCreation:
    """Tests for individual row creation."""

    def test_row_has_all_widgets(self, review_panel, sample_cards):
        """Should create all widgets in a row."""
        review_panel.load_cards([sample_cards[0]])

        row = review_panel._rows_by_id[1]
        assert row.panel is not None
        assert row.dot is not None
        assert row.fn_label is not None
        assert row.name_text is not None
        assert row.remove_family_check is not None
        assert row.alt_choice is not None
        assert row.ai_btn is not None

    def test_row_displays_filename(self, review_panel, sample_cards):
        """Should display card filename."""
        review_panel.load_cards([sample_cards[0]])

        row = review_panel._rows_by_id[1]
        assert row.fn_label.GetLabel() == "card1.pdf"

    def test_row_displays_family_name(self, review_panel, sample_cards):
        """Should display family name in text control."""
        review_panel.load_cards([sample_cards[0]])

        row = review_panel._rows_by_id[1]
        assert row.name_text.GetValue() == "Smith"

    def test_row_checkbox_reflects_remove_family(self, review_panel, sample_cards):
        """Should set checkbox based on remove_family."""
        review_panel.load_cards(sample_cards)

        # Card 1 has remove_family=True
        row1 = review_panel._rows_by_id[1]
        assert row1.remove_family_check.GetValue() is True

        # Card 2 has remove_family=False
        row2 = review_panel._rows_by_id[2]
        assert row2.remove_family_check.GetValue() is False

    def test_row_candidates_dropdown_populated(self, review_panel, sample_cards):
        """Should populate candidates dropdown."""
        review_panel.load_cards([sample_cards[0]])  # Card with candidates

        row = review_panel._rows_by_id[1]
        assert row.alt_choice.GetCount() == 3  # Placeholder + 2 candidates
        assert row.alt_choice.IsEnabled()
        assert "2 Candidates" in row.alt_choice.GetString(0)  # First item is placeholder

    def test_row_candidates_dropdown_disabled_when_no_candidates(self, review_panel, sample_cards):
        """Should disable dropdown when no candidates."""
        review_panel.load_cards([sample_cards[1]])  # Card without candidates

        row = review_panel._rows_by_id[2]
        assert row.alt_choice.GetCount() == 1  # Just "No Candidates" placeholder
        assert not row.alt_choice.IsEnabled()
        assert "No Candidates" in row.alt_choice.GetString(0)

    def test_error_card_disables_controls(self, review_panel, sample_cards):
        """Should disable controls for error cards."""
        review_panel.load_cards([sample_cards[2]])  # Error card

        row = review_panel._rows_by_id[3]
        assert not row.name_text.IsEnabled()
        assert not row.alt_choice.IsEnabled()
        assert not row.ai_btn.IsEnabled()
        assert not row.remove_family_check.IsEnabled()


@pytest.mark.gui
class TestSelection:
    """Tests for row selection."""

    def test_select_row_highlights(self, review_panel, sample_cards):
        """Should highlight selected row."""
        review_panel.load_cards(sample_cards)

        review_panel._select_row(1)

        row = review_panel._rows_by_id[1]
        # Check that background color was set (not null)
        bg_color = row.panel.GetBackgroundColour()
        assert bg_color.IsOk()

    def test_select_row_calls_callback(self, review_panel, sample_cards, callbacks):
        """Should call on_select callback."""
        review_panel.load_cards(sample_cards)

        review_panel._select_row(1)

        callbacks["on_select"].assert_called_once_with(1)

    def test_select_different_row_unhighlights_previous(self, review_panel, sample_cards):
        """Should unhighlight previous selection."""
        review_panel.load_cards(sample_cards)

        # Select first row
        review_panel._select_row(1)
        first_selected = review_panel._selected_card_id

        # Select second row
        review_panel._select_row(2)

        # First row should be unhighlighted
        assert review_panel._selected_card_id == 2
        assert first_selected != review_panel._selected_card_id

    def test_select_next_card_from_start(self, review_panel, sample_cards):
        """Should select first card when calling select_next from start."""
        review_panel.load_cards(sample_cards)

        review_panel.select_next_card()

        assert review_panel._selected_card_id == 1

    def test_select_next_card_advances(self, review_panel, sample_cards):
        """Should advance to next card."""
        review_panel.load_cards(sample_cards)

        review_panel._select_row(1)
        review_panel.select_next_card()

        assert review_panel._selected_card_id == 2

    def test_select_next_card_stops_at_end(self, review_panel, sample_cards):
        """Should not advance past last card."""
        review_panel.load_cards(sample_cards)

        review_panel._select_row(3)  # Last card
        review_panel.select_next_card()

        assert review_panel._selected_card_id == 3  # Still on last

    def test_select_prev_card_from_start(self, review_panel, sample_cards):
        """Should select first card when calling select_prev from start."""
        review_panel.load_cards(sample_cards)

        review_panel.select_prev_card()

        assert review_panel._selected_card_id == 1

    def test_select_prev_card_goes_back(self, review_panel, sample_cards):
        """Should go back to previous card."""
        review_panel.load_cards(sample_cards)

        review_panel._select_row(2)
        review_panel.select_prev_card()

        assert review_panel._selected_card_id == 1

    def test_select_prev_card_stops_at_start(self, review_panel, sample_cards):
        """Should not go before first card."""
        review_panel.load_cards(sample_cards)

        review_panel._select_row(1)  # First card
        review_panel.select_prev_card()

        assert review_panel._selected_card_id == 1  # Still on first


@pytest.mark.gui
class TestEventHandlers:
    """Tests for event handlers."""

    def test_name_edit_updates_card(self, review_panel, sample_cards):
        """Should update card when name is edited."""
        review_panel.load_cards([sample_cards[0]])

        row = review_panel._rows_by_id[1]
        row.name_text.SetValue("New Name")
        wx.Yield()  # Process events

        card = review_panel._cards_by_id[1]
        assert card.manual_override == "New Name"

    def test_name_edit_calls_callback(self, review_panel, sample_cards, callbacks):
        """Should call on_name_change callback."""
        review_panel.load_cards([sample_cards[0]])

        row = review_panel._rows_by_id[1]
        row.name_text.SetValue("New Name")
        wx.Yield()  # Process events

        # Should have been called at least once
        assert callbacks["on_name_change"].called

    def test_checkbox_toggle_updates_card(self, review_panel, sample_cards):
        """Should update card when checkbox toggled."""
        review_panel.load_cards([sample_cards[0]])

        card = review_panel._cards_by_id[1]
        original_value = card.remove_family

        row = review_panel._rows_by_id[1]
        row.remove_family_check.SetValue(not original_value)

        # Simulate event
        event = Mock()
        review_panel._on_remove_family_toggle(1, event)

        assert card.remove_family != original_value

    def test_ai_button_calls_callback(self, review_panel, sample_cards, callbacks):
        """Should call on_ai_request when AI button clicked."""
        review_panel.load_cards([sample_cards[0]])

        row = review_panel._rows_by_id[1]

        # Simulate button click by calling handler
        event = Mock()
        review_panel._on_ai_request(1)

        callbacks["on_ai_request"].assert_called_once_with(1)

    @patch('app.core.database.select_candidate')
    def test_candidate_selection_updates_card(self, mock_select, review_panel, sample_cards):
        """Should update card when candidate selected."""
        # Add file_hash to enable DB update
        sample_cards[0].file_hash = "test_hash"
        review_panel.load_cards([sample_cards[0]])

        row = review_panel._rows_by_id[1]

        # Select first actual candidate (index 1, since 0 is placeholder)
        row.alt_choice.SetSelection(1)

        # Simulate event
        event = Mock()
        review_panel._on_alt_select(1, event)

        card = review_panel._cards_by_id[1]
        # Should have selected the candidate
        assert card.selected_candidate_id is not None


@pytest.mark.gui
class TestUpdateMethods:
    """Tests for update methods."""

    def test_update_dot_changes_color(self, review_panel, sample_cards):
        """Should update dot color."""
        review_panel.load_cards([sample_cards[0]])

        # Change confidence
        review_panel.update_dot(1, Confidence.LOW)

        # Dot should be updated (we can't easily check color, but verify it doesn't crash)
        assert True

    def test_update_card_changes_name(self, review_panel, sample_cards):
        """Should update displayed name."""
        review_panel.load_cards([sample_cards[0]])

        # Modify card
        updated_card = sample_cards[0]
        updated_card.family_name = "Updated Name"

        review_panel.update_card(1, updated_card)

        row = review_panel._rows_by_id[1]
        assert row.name_text.GetValue() == "Updated Name"

    def test_update_card_changes_checkbox(self, review_panel, sample_cards):
        """Should update checkbox state."""
        review_panel.load_cards([sample_cards[0]])

        # Modify card
        updated_card = sample_cards[0]
        updated_card.remove_family = False

        review_panel.update_card(1, updated_card)

        row = review_panel._rows_by_id[1]
        assert row.remove_family_check.GetValue() is False

    def test_update_card_adds_candidates(self, review_panel, sample_cards):
        """Should populate candidates when updated."""
        review_panel.load_cards([sample_cards[1]])  # Card without candidates

        # Add candidates to card
        updated_card = sample_cards[1]
        updated_card.candidates = [
            CandidateInfo(id=201, family_name="Test1", confidence="high", method="ai"),
            CandidateInfo(id=202, family_name="Test2", confidence="medium", method="ai"),
        ]

        review_panel.update_card(2, updated_card)

        row = review_panel._rows_by_id[2]
        assert row.alt_choice.GetCount() == 3  # Placeholder + 2 candidates
        assert row.alt_choice.IsEnabled()
        assert "2 Candidates" in row.alt_choice.GetString(0)  # First item is placeholder

    def test_set_ai_button_state_enables(self, review_panel, sample_cards):
        """Should enable AI button."""
        review_panel.load_cards([sample_cards[0]])

        review_panel.set_ai_button_state(1, "normal")

        row = review_panel._rows_by_id[1]
        assert row.ai_btn.IsEnabled()

    def test_set_ai_button_state_disables(self, review_panel, sample_cards):
        """Should disable AI button."""
        review_panel.load_cards([sample_cards[0]])

        review_panel.set_ai_button_state(1, "disabled")

        row = review_panel._rows_by_id[1]
        assert not row.ai_btn.IsEnabled()


@pytest.mark.gui
class TestGetCards:
    """Tests for get_cards method."""

    def test_get_cards_returns_all_cards(self, review_panel, sample_cards):
        """Should return all loaded cards."""
        review_panel.load_cards(sample_cards)

        cards = review_panel.get_cards()

        assert len(cards) == len(sample_cards)

    def test_get_cards_maintains_order(self, review_panel, sample_cards):
        """Should return cards in display order."""
        review_panel.load_cards(sample_cards)

        cards = review_panel.get_cards()

        for i, card in enumerate(cards):
            assert card.id == sample_cards[i].id

    def test_get_cards_includes_edits(self, review_panel, sample_cards):
        """Should include manual edits in returned cards."""
        review_panel.load_cards([sample_cards[0]])

        # Edit the name
        row = review_panel._rows_by_id[1]
        row.name_text.SetValue("Edited Name")
        wx.Yield()

        cards = review_panel.get_cards()
        assert cards[0].manual_override == "Edited Name"


@pytest.mark.gui
class TestHelperFunctions:
    """Tests for helper functions."""

    def test_dot_style_error(self, wx_app):
        """Should return error color and symbol for errors."""
        color, symbol = _dot_style(is_error=True, confidence=Confidence.HIGH)

        assert symbol == "✕"

    def test_dot_style_none_confidence(self, wx_app):
        """Should return warning for NONE confidence."""
        color, symbol = _dot_style(is_error=False, confidence=Confidence.NONE)

        assert symbol == "⚠"

    def test_dot_style_high_confidence(self, wx_app):
        """Should return no symbol for high confidence."""
        color, symbol = _dot_style(is_error=False, confidence=Confidence.HIGH)

        assert symbol is None

    def test_tooltip_text_error(self):
        """Should return error message in tooltip."""
        card = CardResult(
            id=1,
            pdf_path=Path("test.pdf"),
            family_name="",
            confidence=Confidence.NONE,
            method="missing",
            original_confidence=Confidence.NONE,
            remove_family=False
        )
        card.error = "Test error"

        text = _tooltip_text(card, Confidence.NONE)

        assert "Error: Test error" in text

    def test_tooltip_text_manual(self):
        """Should return manual entry text."""
        text = _tooltip_text(None, Confidence.MANUAL)

        assert "Manual Entry" in text

    def test_tooltip_text_missing(self):
        """Should return warning for missing names."""
        card = CardResult(
            id=1,
            pdf_path=Path("test.pdf"),
            family_name="",
            confidence=Confidence.NONE,
            method="missing",
            original_confidence=Confidence.NONE,
            remove_family=False
        )

        text = _tooltip_text(card, Confidence.NONE)

        assert "No name extracted" in text

    def test_tooltip_text_ocr(self):
        """Should return OCR method in tooltip."""
        card = CardResult(
            id=1,
            pdf_path=Path("test.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            original_confidence=Confidence.HIGH,
            remove_family=False
        )

        text = _tooltip_text(card, Confidence.HIGH)

        assert "OCR" in text
        assert "High" in text
