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
    direct: str | None = None,
    new_name: str | None = None,
    rank: int | None = None,
    new_value: bool | None = None,
    year: str | None = None,
) -> MagicMock:
    """Build a mock Apple Event descriptor with given param values."""
    from app.core.apple_events import _K_AE_DIRECT_OBJECT, _K_NEW_NAME, _K_NEW_VALUE, _K_RANK, _K_YEAR

    def param_descriptor(keyword):
        if keyword == _K_AE_DIRECT_OBJECT and direct is not None:
            return _make_descriptor(string_value=direct)
        if keyword == _K_NEW_NAME and new_name is not None:
            return _make_descriptor(string_value=new_name)
        if keyword == _K_RANK and rank is not None:
            return _make_descriptor(int32_value=rank)
        if keyword == _K_NEW_VALUE and new_value is not None:
            return _make_descriptor(boolean_value=new_value)
        if keyword == _K_YEAR and year is not None:
            return _make_descriptor(string_value=year)
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
        window = MagicMock()
        window.set_ai_model_for_script.return_value = {"success": True}
        handler = AppleEventHandler.alloc().initWithWindow_(window)
        event = _make_event(direct="claude-haiku-4-5")
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleSetModel_reply_(event, reply)
        window.set_ai_model_for_script.assert_called_once_with("claude-haiku-4-5")
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True


# ── Handler: rename card ─────────────────────────────────────────────────


class TestHandlerRenameCard:
    """Tests for handleRenameCard_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_missing_filename(self, handler):
        event = _make_event(new_name="Smith")  # no direct/filename
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleRenameCard_reply_(event, reply)
        mock_reply.assert_called_once()
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "error" in result

    def test_missing_name(self, handler):
        event = _make_event(direct="test.pdf")  # no new_name
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleRenameCard_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False

    def test_delegates_to_window(self, handler):
        expected = {"success": True, "new_filename": "Smith 2025.pdf"}
        handler._window.rename_card_for_script.return_value = expected
        event = _make_event(direct="test.pdf", new_name="Smith", year="2025")
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleRenameCard_reply_(event, reply)
        handler._window.rename_card_for_script.assert_called_once_with("test.pdf", "Smith", "2025")
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True
        assert result["new_filename"] == "Smith 2025.pdf"


# ── Handler: reload ──────────────────────────────────────────────────────


class TestHandlerReload:
    """Tests for handleReload_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_delegates_to_window(self, handler):
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value={"success": True, "changed": False}),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleReload_reply_(MagicMock(), MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_timeout_returns_error(self, handler):
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleReload_reply_(MagicMock(), MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()


# ── Handler: clear all ───────────────────────────────────────────────────


class TestHandlerClearAll:
    """Tests for handleClearAll_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_delegates_to_window(self, handler):
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value={"success": True}),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleClearAll_reply_(MagicMock(), MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_timeout_returns_error(self, handler):
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleClearAll_reply_(MagicMock(), MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()


# ── Handler: analyze cards ───────────────────────────────────────────────


class TestHandlerAnalyzeCards:
    """Tests for handleAnalyzeCards_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_delegates_to_window(self, handler):
        expected = {"success": True, "queued": 1}
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=expected) as mock_call,
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleAnalyzeCards_reply_(_make_event(direct="test.pdf"), MagicMock())
        # Verify the inner function calls analyze_for_script with the filename
        mock_call.assert_called_once()
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_no_filename_passes_none(self, handler):
        captured: list = []

        def capture_fn(fn):
            captured.append(fn)
            return fn()

        handler._window.analyze_for_script.return_value = {"success": True, "queued": 0}
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=capture_fn),
            patch("app.core.apple_events._set_text_reply"),
        ):
            handler.handleAnalyzeCards_reply_(_make_event(), MagicMock())
        handler._window.analyze_for_script.assert_called_once_with(None)


# ── Handler: clear AI results ────────────────────────────────────────────


class TestHandlerClearAiResults:
    """Tests for handleClearAiResults_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_delegates_to_window(self, handler):
        expected = {"success": True, "cleared": 1}
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=expected) as mock_call,
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleClearAiResults_reply_(_make_event(direct="test.pdf"), MagicMock())
        mock_call.assert_called_once()
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_no_filename_passes_none(self, handler):
        captured: list = []

        def capture_fn(fn):
            captured.append(fn)
            return fn()

        handler._window.clear_ai_for_script.return_value = {"success": True, "cleared": 0}
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=capture_fn),
            patch("app.core.apple_events._set_text_reply"),
        ):
            handler.handleClearAiResults_reply_(_make_event(), MagicMock())
        handler._window.clear_ai_for_script.assert_called_once_with(None)


# ── Handler: get status ──────────────────────────────────────────────────


class TestHandlerGetStatus:
    """Tests for handleGetStatus_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_delegates_to_window(self, handler):
        status_json = json.dumps({"is_processing": False, "loaded_count": 3})
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=status_json),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetStatus_reply_(MagicMock(), MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["is_processing"] is False
        assert result["loaded_count"] == 3

    def test_timeout_returns_empty(self, handler):
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetStatus_reply_(MagicMock(), MagicMock())
        assert mock_reply.call_args[0][1] == "{}"


# ── Handler: get card info ───────────────────────────────────────────────


class TestHandlerLoadPaths:
    """Tests for handleLoadPaths_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_empty_paths_returns_zero(self, handler):
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = None  # no paths → []
        reply = MagicMock()
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleLoadPaths_reply_(event, reply)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True
        assert result["count"] == 0

    def test_timeout_returns_error(self, handler):
        item = MagicMock()
        item.stringValue.return_value = "/path/a.pdf"
        desc = MagicMock()
        desc.numberOfItems.return_value = 1
        desc.descriptorAtIndex_.return_value = item
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = desc

        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleLoadPaths_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()


class TestHandlerGetCardInfo:
    """Tests for handleGetCardInfo_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_no_filename_returns_error(self, handler):
        event = _make_event()  # no direct param
        with patch("app.core.apple_events._set_text_reply") as mock_reply:
            handler.handleGetCardInfo_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert "error" in result
        assert "no filename" in result["error"].lower()

    def test_card_not_found(self, handler):
        not_found_json = json.dumps({"error": "Card not found: missing.pdf"})
        event = _make_event(direct="missing.pdf")
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=not_found_json),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetCardInfo_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert "error" in result
        assert "Card not found" in result["error"]

    def test_card_not_found_inner(self, handler):
        """Exercise the inner _do() path where get_card_info_for_script returns None."""
        handler._window.get_card_info_for_script.return_value = None

        def _execute_inner(fn):
            return fn()

        event = _make_event(direct="missing.pdf")
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=_execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetCardInfo_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert "error" in result
        assert "Card not found" in result["error"]

    def test_delegates_to_window(self, handler):
        card_json = json.dumps({"filename": "test.pdf", "family_name": "Smith"})
        event = _make_event(direct="test.pdf")
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=card_json),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetCardInfo_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["filename"] == "test.pdf"
        assert result["family_name"] == "Smith"


# ── Handler: get loaded cards ────────────────────────────────────────────


class TestHandlerGetLoadedCards:
    """Tests for handleGetLoadedCards_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_delegates_to_window(self, handler):
        cards_json = json.dumps(
            [
                {"filename": "a.pdf", "family_name": "Smith"},
                {"filename": "b.pdf", "family_name": "Jones"},
            ]
        )
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=cards_json),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetLoadedCards_reply_(MagicMock(), MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["filename"] == "a.pdf"
        assert result[1]["family_name"] == "Jones"

    def test_timeout_returns_empty_list(self, handler):
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetLoadedCards_reply_(MagicMock(), MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result == []


# ── Handler: quit ────────────────────────────────────────────────────────


class TestHandlerQuit:
    """Tests for handleQuit_reply_."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_delegates_to_window(self, handler):
        with patch("app.core.apple_events._call_on_main_thread") as mock_call:
            handler.handleQuit_reply_(MagicMock(), MagicMock())
        mock_call.assert_called_once()
        # Execute the lambda passed to _call_on_main_thread and verify it calls quit_for_script
        fn = mock_call.call_args[0][0]
        fn()
        handler._window.quit_for_script.assert_called_once()


# ── _call_on_main_thread (background thread paths) ──────────────────────


class TestCallOnMainThreadBackground:
    """Tests for _call_on_main_thread when called from a background thread."""

    def test_call_on_main_thread_from_background(self):
        """Success path: function dispatched to main thread returns a result."""
        import app.core.apple_events as ae_mod

        original_dispatch = ae_mod._main_thread_dispatch
        try:
            # Mock _main_thread_dispatch to execute the callback immediately
            def fake_dispatch(fn):
                fn()

            ae_mod._main_thread_dispatch = fake_dispatch

            result_holder: list = []
            error_holder: list = []

            def run_in_thread():
                try:
                    r = _call_on_main_thread(lambda: 42)
                    result_holder.append(r)
                except Exception as exc:
                    error_holder.append(exc)

            t = threading.Thread(target=run_in_thread)
            t.start()
            t.join(timeout=5)

            assert not error_holder, f"Unexpected error: {error_holder}"
            assert result_holder == [42]
        finally:
            ae_mod._main_thread_dispatch = original_dispatch

    def test_call_on_main_thread_timeout(self):
        """Timeout path: dispatcher never signals done, returns None."""
        import app.core.apple_events as ae_mod

        original_dispatch = ae_mod._main_thread_dispatch
        original_timeout = ae_mod._MAIN_THREAD_TIMEOUT_S
        try:
            # Dispatcher that never calls the function (simulates hang)
            ae_mod._main_thread_dispatch = lambda fn: None
            ae_mod._MAIN_THREAD_TIMEOUT_S = 0.05  # Very short timeout

            result_holder: list = []

            def run_in_thread():
                r = _call_on_main_thread(lambda: "should not return")
                result_holder.append(r)

            t = threading.Thread(target=run_in_thread)
            t.start()
            t.join(timeout=5)

            assert result_holder == [None]
        finally:
            ae_mod._main_thread_dispatch = original_dispatch
            ae_mod._MAIN_THREAD_TIMEOUT_S = original_timeout

    def test_call_on_main_thread_exception(self):
        """Exception path: exception from dispatched function is re-raised."""
        import app.core.apple_events as ae_mod

        original_dispatch = ae_mod._main_thread_dispatch
        try:
            ae_mod._main_thread_dispatch = lambda fn: fn()

            error_holder: list = []

            def run_in_thread():
                try:
                    _call_on_main_thread(_raise_value_error)
                except ValueError as exc:
                    error_holder.append(exc)

            t = threading.Thread(target=run_in_thread)
            t.start()
            t.join(timeout=5)

            assert len(error_holder) == 1
            assert str(error_holder[0]) == "test error from main thread"
        finally:
            ae_mod._main_thread_dispatch = original_dispatch

    def test_call_on_main_thread_no_dispatch(self):
        """No dispatcher registered: raises RuntimeError."""
        import app.core.apple_events as ae_mod

        original_dispatch = ae_mod._main_thread_dispatch
        try:
            ae_mod._main_thread_dispatch = None

            error_holder: list = []

            def run_in_thread():
                try:
                    _call_on_main_thread(lambda: 1)
                except RuntimeError as exc:
                    error_holder.append(exc)

            t = threading.Thread(target=run_in_thread)
            t.start()
            t.join(timeout=5)

            assert len(error_holder) == 1
            assert "no main-thread dispatcher" in str(error_holder[0]).lower()
        finally:
            ae_mod._main_thread_dispatch = original_dispatch


def _raise_value_error():
    raise ValueError("test error from main thread")


# ── Handler success paths (executing inner function) ─────────────────────


class TestHandlerSuccessPaths:
    """Tests that exercise the success path of handlers by executing the inner
    function via a side_effect on _call_on_main_thread."""

    @pytest.fixture
    def handler(self):
        window = MagicMock()
        return AppleEventHandler.alloc().initWithWindow_(window)

    @staticmethod
    def _execute_inner(fn):
        """Side effect for _call_on_main_thread that runs the inner function."""
        return fn()

    def test_handle_load_paths_success(self, handler):
        """load paths handler returns success result from window."""
        handler._window.load_paths_for_script.return_value = {"success": True, "count": 3}

        # Build event with a list of paths
        item1 = MagicMock()
        item1.stringValue.return_value = "/path/a.pdf"
        desc = MagicMock()
        desc.numberOfItems.return_value = 1
        desc.descriptorAtIndex_.return_value = item1
        event = MagicMock()
        event.paramDescriptorForKeyword_.return_value = desc

        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleLoadPaths_reply_(event, reply)

        handler._window.load_paths_for_script.assert_called_once_with(["/path/a.pdf"])
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True
        assert result["count"] == 3

    def test_handle_get_status_success(self, handler):
        """get status handler returns JSON status from window."""
        handler._window.get_status_for_script.return_value = {
            "is_processing": False,
            "loaded_count": 5,
        }
        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetStatus_reply_(MagicMock(), reply)

        result = json.loads(mock_reply.call_args[0][1])
        assert result["is_processing"] is False
        assert result["loaded_count"] == 5

    def test_handle_reload_success(self, handler):
        """reload handler returns success result from window."""
        handler._window.reload_for_script.return_value = {"success": True, "changed": False}
        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleReload_reply_(MagicMock(), reply)

        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_handle_clear_all_success(self, handler):
        """clear all handler returns success result from window."""
        handler._window.clear_all_for_script.return_value = {"success": True}
        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleClearAll_reply_(MagicMock(), reply)

        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_handle_get_card_info_success(self, handler):
        """get card info handler returns card JSON from window."""
        card = _make_card(
            candidates=[
                CandidateInfo(id=10, family_name="Smith", method="ai", confidence="high"),
            ],
        )
        handler._window.get_card_info_for_script.return_value = card
        event = _make_event(direct="test.pdf")
        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleGetCardInfo_reply_(event, reply)

        handler._window.get_card_info_for_script.assert_called_once_with("test.pdf")
        result = json.loads(mock_reply.call_args[0][1])
        assert result["filename"] == "test.pdf"
        assert result["family_name"] == "Smith"
        assert len(result["candidates"]) == 1

    def test_handle_set_card_name_success(self, handler):
        """set card name handler returns success result from window."""
        handler._window.set_card_name_for_script.return_value = {"success": True}
        event = _make_event(direct="test.pdf", new_name="Johnson")
        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleSetCardName_reply_(event, reply)

        handler._window.set_card_name_for_script.assert_called_once_with("test.pdf", "Johnson")
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_handle_select_candidate_success(self, handler):
        """select candidate handler returns success result from window."""
        handler._window.select_candidate_for_script.return_value = {"success": True}
        event = _make_event(direct="test.pdf", rank=2)
        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleSelectCandidate_reply_(event, reply)

        handler._window.select_candidate_for_script.assert_called_once_with("test.pdf", 2)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True

    def test_handle_set_remove_family_success(self, handler):
        """set remove family handler returns success result from window."""
        handler._window.set_remove_family_for_script.return_value = {"success": True}
        event = _make_event(direct="test.pdf", new_value=True)
        reply = MagicMock()
        with (
            patch("app.core.apple_events._call_on_main_thread", side_effect=self._execute_inner),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleSetRemoveFamily_reply_(event, reply)

        handler._window.set_remove_family_for_script.assert_called_once_with("test.pdf", True)
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is True


# ── Handler timeout tests ────────────────────────────────────────────────


class TestHandlerTimeouts:
    """Timeout tests for handlers that call _call_on_main_thread."""

    @pytest.fixture
    def handler(self):
        return AppleEventHandler.alloc().initWithWindow_(MagicMock())

    def test_set_card_name_timeout(self, handler):
        event = _make_event(direct="test.pdf", new_name="Smith")
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleSetCardName_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_select_candidate_timeout(self, handler):
        event = _make_event(direct="test.pdf", rank=1)
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleSelectCandidate_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_set_remove_family_timeout(self, handler):
        event = _make_event(direct="test.pdf", new_value=True)
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleSetRemoveFamily_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_analyze_cards_timeout(self, handler):
        event = _make_event(direct="test.pdf")
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleAnalyzeCards_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_clear_ai_results_timeout(self, handler):
        event = _make_event(direct="test.pdf")
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleClearAiResults_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_set_model_timeout(self, handler):
        event = _make_event(direct="claude-haiku-4-5")
        with (
            patch("app.core.apple_events._call_on_main_thread", return_value=None),
            patch("app.core.apple_events._set_text_reply") as mock_reply,
        ):
            handler.handleSetModel_reply_(event, MagicMock())
        result = json.loads(mock_reply.call_args[0][1])
        assert result["success"] is False
        assert "timeout" in result["error"].lower()
