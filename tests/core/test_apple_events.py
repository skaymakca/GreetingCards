"""Tests for app.core.apple_events — helpers, serialization, registration."""

from __future__ import annotations

import json
import struct
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.apple_events import (
    AppleEventHandler,
    _ai_models_to_json,
    _call_on_main_thread,
    _card_summary,
    _card_to_json,
    _get_bool_param,
    _get_int_param,
    _get_text_list_param,
    _get_text_param,
    _set_bool_reply,
    _set_int_reply,
    _set_text_reply,
    _status_to_json,
    ae_keyword,
    register_apple_event_handlers,
    register_quit_handler,
)
from app.models.card import CandidateInfo, CardResult, Confidence

# ── ae_keyword ──────────────────────────────────────────────────────────


class TestAeKeyword:
    def test_known_code_grcd(self):
        result = ae_keyword("GrCd")
        assert result == struct.unpack(">I", b"GrCd")[0]

    def test_known_code_direct_param(self):
        result = ae_keyword("----")
        assert result == struct.unpack(">I", b"----")[0]

    def test_known_code_new_name(self):
        result = ae_keyword("newN")
        assert result == struct.unpack(">I", b"newN")[0]

    def test_round_trip(self):
        """Encode a 4-char code and decode back to the original string."""
        code = "RnCd"
        packed = ae_keyword(code)
        decoded = struct.pack(">I", packed).decode("mac_roman")
        assert decoded == code

    def test_invalid_length_raises(self):
        with pytest.raises(struct.error):
            ae_keyword("AB")
        with pytest.raises(struct.error):
            ae_keyword("ABCDE")


# ── Param extraction ────────────────────────────────────────────────────


def _make_descriptor(string_value=None, int32_value=None, boolean_value=None):
    """Create a mock NSAppleEventDescriptor with the given values."""
    desc = MagicMock()
    desc.stringValue.return_value = string_value
    desc.int32Value.return_value = int32_value
    desc.booleanValue.return_value = boolean_value
    return desc


class TestParamExtraction:
    def test_get_text_param_present(self):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = _make_descriptor(string_value="hello")
        result = _get_text_param(event, ae_keyword("newN"))
        assert result == "hello"

    def test_get_text_param_missing(self):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = None
        result = _get_text_param(event, ae_keyword("newN"))
        assert result is None

    def test_get_int_param_present(self):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = _make_descriptor(int32_value=42)
        result = _get_int_param(event, ae_keyword("rank"))
        assert result == 42

    def test_get_int_param_missing(self):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = None
        result = _get_int_param(event, ae_keyword("rank"))
        assert result is None

    def test_get_bool_param_present(self):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = _make_descriptor(boolean_value=True)
        result = _get_bool_param(event, ae_keyword("newV"))
        assert result is True

    def test_get_bool_param_missing(self):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = None
        result = _get_bool_param(event, ae_keyword("newV"))
        assert result is None


class TestTextListParam:
    def test_empty_when_no_direct(self):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = None
        assert _get_text_list_param(event) == []

    def test_single_string(self):
        desc = MagicMock()
        desc.numberOfItems.return_value = 0
        desc.stringValue.return_value = "/path/to/file.pdf"
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = desc
        result = _get_text_list_param(event)
        assert result == ["/path/to/file.pdf"]

    def test_list_of_strings(self):
        item1 = MagicMock()
        item1.stringValue.return_value = "/a.pdf"
        item2 = MagicMock()
        item2.stringValue.return_value = "/b.pdf"

        desc = MagicMock()
        desc.numberOfItems.return_value = 2
        desc.descriptorAtIndex_.side_effect = lambda i: [None, item1, item2][i]

        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = desc
        result = _get_text_list_param(event)
        assert result == ["/a.pdf", "/b.pdf"]


# ── Reply helpers ────────────────────────────────────────────────────────


class TestReplyHelpers:
    def test_set_text_reply(self):
        reply = MagicMock()
        _set_text_reply(reply, "result text")
        reply.setParamDescriptor_forKeyword_.assert_called_once()
        call_args = reply.setParamDescriptor_forKeyword_.call_args
        assert call_args[0][1] == ae_keyword("----")

    def test_set_bool_reply(self):
        reply = MagicMock()
        _set_bool_reply(reply, True)
        reply.setParamDescriptor_forKeyword_.assert_called_once()

    def test_set_int_reply(self):
        reply = MagicMock()
        _set_int_reply(reply, 42)
        reply.setParamDescriptor_forKeyword_.assert_called_once()


# ── Card serialization ──────────────────────────────────────────────────


def _make_card(**kwargs) -> CardResult:
    """Create a CardResult with sensible defaults."""
    defaults = {
        "id": 1,
        "file_paths": [Path("/tmp/test.pdf")],
        "primary_path": Path("/tmp/test.pdf"),
        "family_name": "Smith",
        "confidence": Confidence.HIGH,
        "method": "ocr",
        "file_hash": "abc123",
    }
    defaults.update(kwargs)
    return CardResult(**defaults)


class TestCardSerialization:
    def test_card_to_json_full(self):
        card = _make_card(
            candidates=[
                CandidateInfo(id=10, family_name="Smith", method="ai", confidence="high"),
                CandidateInfo(id=11, family_name="Jones", method="ocr", confidence="medium"),
            ],
            ai_analyzed=True,
            manual_override="Override",
            remove_family=True,
        )
        data = json.loads(_card_to_json(card))
        assert data["filename"] == "test.pdf"
        assert data["file_hash"] == "abc123"
        assert data["family_name"] == "Smith"
        assert data["confidence"] == "high"
        assert data["method"] == "ocr"
        assert data["manual_override"] == "Override"
        assert data["remove_family"] is True
        assert data["ai_analyzed"] is True
        assert len(data["candidates"]) == 2
        assert data["candidates"][0]["rank"] == 1
        assert data["candidates"][0]["name"] == "Smith"
        assert data["candidates"][1]["rank"] == 2
        assert data["file_paths"] == ["/tmp/test.pdf"]

    def test_card_to_json_minimal(self):
        card = _make_card(candidates=[], ai_analyzed=False)
        data = json.loads(_card_to_json(card))
        assert data["candidates"] == []
        assert data["ai_analyzed"] is False
        assert data["error"] == ""

    def test_card_summary(self):
        card = _make_card()
        summary = _card_summary(card)
        assert summary["filename"] == "test.pdf"
        assert summary["file_hash"] == "abc123"
        assert summary["family_name"] == "Smith"
        assert summary["confidence"] == "high"
        assert len(summary) == 4

    def test_ai_models_to_json(self):
        data = json.loads(_ai_models_to_json())
        assert isinstance(data, list)
        assert len(data) == 3
        assert all("model_id" in m for m in data)
        assert all("label" in m for m in data)
        assert all("speed" in m for m in data)
        assert all("quality" in m for m in data)

    def test_status_to_json(self):
        window = MagicMock()
        window.get_status_for_script.return_value = {
            "is_processing": False,
            "is_analyzing": False,
            "loaded_count": 5,
            "current_model": "claude-sonnet-4-6",
            "year": "2025",
        }
        data = json.loads(_status_to_json(window))
        assert data["is_processing"] is False
        assert data["loaded_count"] == 5
        assert data["current_model"] == "claude-sonnet-4-6"


# ── _call_on_main_thread ────────────────────────────────────────────────


class TestCallOnMainThread:
    def test_direct_on_main_thread(self):
        """When already on main thread, function is called directly."""
        called = []

        def fn():
            called.append(threading.current_thread().name)
            return 42

        result = _call_on_main_thread(fn)
        assert result == 42
        assert len(called) == 1


# ── Registration ─────────────────────────────────────────────────────────


class TestRegistration:
    @patch("app.core.apple_events.NSAppleEventManager")
    def test_registers_all_fourteen_handlers(self, mock_mgr_class):
        mock_mgr = MagicMock()
        mock_mgr_class.sharedAppleEventManager.return_value = mock_mgr
        window = MagicMock()
        handler = register_apple_event_handlers(window)
        assert handler is not None
        assert mock_mgr.setEventHandler_andSelector_forEventClass_andEventID_.call_count == 14

    @patch("app.core.apple_events.NSAppleEventManager")
    def test_no_aevt_quit_in_initial_registration(self, mock_mgr_class):
        """register_apple_event_handlers must NOT register aevt/quit (deferred)."""
        mock_mgr = MagicMock()
        mock_mgr_class.sharedAppleEventManager.return_value = mock_mgr
        register_apple_event_handlers(MagicMock())

        calls = mock_mgr.setEventHandler_andSelector_forEventClass_andEventID_.call_args_list
        aevt_code = ae_keyword("aevt")
        quit_code = ae_keyword("quit")

        aevt_quit_calls = [c for c in calls if c[0][2] == aevt_code and c[0][3] == quit_code]
        assert len(aevt_quit_calls) == 0, "aevt/quit must not be registered eagerly"

    @patch("app.core.apple_events.NSAppleEventManager")
    def test_register_quit_handler(self, mock_mgr_class):
        """register_quit_handler registers exactly one aevt/quit entry."""
        mock_mgr = MagicMock()
        mock_mgr_class.sharedAppleEventManager.return_value = mock_mgr
        # Build a real handler so the call succeeds
        handler = AppleEventHandler.alloc().initWithWindow_(MagicMock())
        register_quit_handler(handler)

        calls = mock_mgr.setEventHandler_andSelector_forEventClass_andEventID_.call_args_list
        aevt_code = ae_keyword("aevt")
        quit_code = ae_keyword("quit")
        grcd_code = ae_keyword("GrCd")

        quit_calls = [c for c in calls if c[0][2] == aevt_code and c[0][3] == quit_code]
        assert len(quit_calls) == 1, "Expected exactly one aevt/quit registration"

        # Ensure the quit handler was NOT registered under GrCd
        grcd_quit_calls = [c for c in calls if c[0][2] == grcd_code and c[0][3] == quit_code]
        assert len(grcd_quit_calls) == 0

    @patch("app.core.apple_events.NSAppleEventManager")
    def test_handler_holds_window_reference(self, mock_mgr_class):
        mock_mgr_class.sharedAppleEventManager.return_value = MagicMock()
        window = MagicMock()
        handler = register_apple_event_handlers(window)
        assert handler._window is window

    @patch("app.core.apple_events.NSAppleEventManager")
    def test_returns_handler_instance(self, mock_mgr_class):
        mock_mgr_class.sharedAppleEventManager.return_value = MagicMock()
        handler = register_apple_event_handlers(MagicMock())
        assert isinstance(handler, AppleEventHandler)


# ── Handler param validation ─────────────────────────────────────────────


def _make_event(
    direct: str | None = None, new_name: str | None = None, rank: int | None = None, new_value: bool | None = None
) -> MagicMock:
    """Build a mock Apple Event descriptor with given param values."""
    from app.core.apple_events import _K_AE_DIRECT_OBJECT, _K_NEW_NAME, _K_NEW_VALUE, _K_RANK

    def param_descriptor(keyword):
        if keyword == _K_AE_DIRECT_OBJECT and direct is not None:
            return _make_descriptor(string_value=direct)
        if keyword == _K_NEW_NAME and new_name is not None:
            return _make_descriptor(string_value=new_name)
        if keyword == _K_RANK and rank is not None:
            return _make_descriptor(int32_value=rank)
        if keyword == _K_NEW_VALUE and new_value is not None:
            return _make_descriptor(boolean_value=new_value)
        return None

    event = MagicMock()
    event.paramDescriptorForKeyword_.side_effect = param_descriptor
    return event


class TestHandlerParamValidation:
    """Handler-level tests for missing/invalid parameter validation."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_set_card_name_missing_filename(self, handler):
        event = _make_event(new_name="Smith")  # no direct/filename
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSetCardName_reply_(event, reply)
        mock_reply.assert_called_once()
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "error" in result

    def test_set_card_name_missing_name(self, handler):
        event = _make_event(direct="test.pdf")  # no new_name
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSetCardName_reply_(event, reply)
        mock_reply.assert_called_once()
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False

    def test_select_candidate_missing_filename(self, handler):
        event = _make_event(rank=1)  # no filename
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSelectCandidate_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False

    def test_select_candidate_missing_rank(self, handler):
        event = _make_event(direct="test.pdf")  # no rank
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSelectCandidate_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False

    def test_set_remove_family_missing_filename(self, handler):
        event = _make_event(new_value=True)  # no filename
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSetRemoveFamily_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False

    def test_set_remove_family_missing_value(self, handler):
        event = _make_event(direct="test.pdf")  # no value
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSetRemoveFamily_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False

    def test_set_model_missing_param(self, handler):
        event = _make_event()  # no model_id
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSetModel_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "missing" in result["error"].lower()

    def test_set_model_invalid_model(self, handler):
        event = _make_event(direct="nonexistent-model")
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSetModel_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "unknown" in result["error"].lower()


class TestHandlerGetModels:
    """Tests for handleGetModels_reply_ handler."""

    def test_returns_json_array(self):
        handler = AppleEventHandler.alloc().initWithWindow_(MagicMock())
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleGetModels_reply_(MagicMock(), reply)
        text = mock_reply.call_args[0][1]
        models = json.loads(text)
        assert isinstance(models, list)
        assert len(models) == 3


class TestHandlerSetModel:
    """Tests for handleSetModel_reply_ success path."""

    def test_valid_model_returns_success(self):
        handler = AppleEventHandler.alloc().initWithWindow_(MagicMock())
        event = _make_event(direct="claude-haiku-4-5")
        reply = MagicMock()
        with (
            patch("app.core.apple_events._set_text_reply") as mock_reply,
            patch("app.core.apple_events.save_ai_model"),
        ):
            handler.handleSetModel_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True
