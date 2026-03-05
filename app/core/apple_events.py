# pyright: reportAttributeAccessIssue=false
"""Apple Events (AppleScript) support for Greeting Cards.

Registers handlers for 15 commands that allow external scripts to control the
application via ``tell application id "com.kaymakcalan.app.greetingcards"``.

All handlers run on the main thread (macOS dispatches Apple Events on the main
run loop, which is the same thread as wxPython's event loop).
"""

from __future__ import annotations

import json
import logging
import struct
import threading
from collections.abc import Callable

import objc

# noinspection PyUnresolvedReferences
from AppKit import NSAppleEventManager

# noinspection PyUnresolvedReferences
from Foundation import NSAppleEventDescriptor

from app.core.scripting_protocol import ScriptingTarget
from app.core.services.config_service import ConfigService
from app.models.card import CardResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Four-char code helpers
# ---------------------------------------------------------------------------


def ae_keyword(code: str) -> int:
    """Convert a 4-character Apple Event code string to its integer value."""
    return struct.unpack(">I", code.encode("mac_roman"))[0]


# Apple Event constants
_K_AE_DIRECT_OBJECT = ae_keyword("----")
# Parameter codes
_K_NEW_NAME = ae_keyword("newN")
_K_YEAR = ae_keyword("year")
_K_RANK = ae_keyword("rank")
_K_NEW_VALUE = ae_keyword("newV")


# ---------------------------------------------------------------------------
# Param extraction helpers
# ---------------------------------------------------------------------------


def _get_text_param(event: NSAppleEventDescriptor, keyword: int) -> str | None:
    """Extract a text parameter from an Apple Event descriptor."""
    desc = event.paramDescriptorForKeyword_(keyword)
    if desc is None:
        return None
    return desc.stringValue()


def _get_direct_text(event: NSAppleEventDescriptor) -> str | None:
    """Extract the direct parameter as text."""
    return _get_text_param(event, _K_AE_DIRECT_OBJECT)


def _get_int_param(event: NSAppleEventDescriptor, keyword: int) -> int | None:
    """Extract an integer parameter from an Apple Event descriptor."""
    desc = event.paramDescriptorForKeyword_(keyword)
    if desc is None:
        return None
    return desc.int32Value()


def _get_bool_param(event: NSAppleEventDescriptor, keyword: int) -> bool | None:
    """Extract a boolean parameter from an Apple Event descriptor."""
    desc = event.paramDescriptorForKeyword_(keyword)
    if desc is None:
        return None
    return desc.booleanValue()


def _get_text_list_param(event: NSAppleEventDescriptor) -> list[str]:
    """Extract a list of text items from the direct parameter."""
    desc = event.paramDescriptorForKeyword_(_K_AE_DIRECT_OBJECT)
    if desc is None:
        return []
    # Could be a single string or a list descriptor
    count = desc.numberOfItems()
    if count == 0:
        # Single text value
        val = desc.stringValue()
        return [val] if val else []
    # List of descriptors
    result = []
    for i in range(1, count + 1):  # 1-based indexing
        item = desc.descriptorAtIndex_(i)
        if item is not None:
            val = item.stringValue()
            if val:
                result.append(val)
    return result


# ---------------------------------------------------------------------------
# Reply helpers
# ---------------------------------------------------------------------------


def _set_text_reply(reply: NSAppleEventDescriptor, value: str) -> None:
    """Set a text result on the reply descriptor."""
    desc = NSAppleEventDescriptor.descriptorWithString_(value)
    reply.setParamDescriptor_forKeyword_(desc, ae_keyword("----"))


def _set_bool_reply(reply: NSAppleEventDescriptor, value: bool) -> None:
    """Set a boolean result on the reply descriptor."""
    desc = NSAppleEventDescriptor.descriptorWithBoolean_(value)
    reply.setParamDescriptor_forKeyword_(desc, ae_keyword("----"))


def _set_int_reply(reply: NSAppleEventDescriptor, value: int) -> None:
    """Set an integer result on the reply descriptor."""
    desc = NSAppleEventDescriptor.descriptorWithInt32_(value)
    reply.setParamDescriptor_forKeyword_(desc, ae_keyword("----"))


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------


def _card_to_json(card: CardResult) -> str:
    """Serialize full card info to JSON."""
    candidates = []
    for rank, c in enumerate(card.candidates, start=1):
        candidates.append(
            {
                "rank": rank,
                "id": c.id,
                "name": c.family_name,
                "method": c.method,
                "confidence": c.confidence,
            }
        )
    data = {
        "filename": card.filename,
        "file_hash": card.file_hash,
        "file_paths": [str(p) for p in card.file_paths],
        "family_name": card.family_name,
        "confidence": card.confidence.value,
        "method": card.method,
        "manual_override": card.manual_override,
        "remove_family": card.remove_family,
        "ai_analyzed": card.ai_analyzed,
        "candidates": candidates,
        "error": card.error,
    }
    return json.dumps(data)


def _card_summary(card: CardResult) -> dict:
    """Return a summary dict for list view."""
    return {
        "filename": card.filename,
        "file_hash": card.file_hash,
        "family_name": card.family_name,
        "confidence": card.confidence.value,
    }


def _ai_models_to_json() -> str:
    """Serialize available AI models to JSON."""
    models = []
    for m in ConfigService.get_available_models():
        models.append(
            {
                "model_id": m.model_id,
                "label": m.label,
                "description": m.description,
                "speed": m.speed,
                "quality": m.quality,
            }
        )
    return json.dumps(models)


def _status_to_json(window: ScriptingTarget) -> str:
    """Serialize current application status to JSON."""
    status = window.get_status_for_script()
    return json.dumps(status)


# ---------------------------------------------------------------------------
# Main-thread safety wrapper
# ---------------------------------------------------------------------------

# Injected by register_apple_event_handlers() — the GUI layer passes its
# main-thread dispatcher (e.g. wx.CallAfter) so the core layer never imports wx.
_main_thread_dispatch: Callable | None = None


_MAIN_THREAD_TIMEOUT_S = 30
_TIMEOUT = object()  # Sentinel distinguishing timeout from legitimate None return


def _call_on_main_thread[T](func: Callable[[], T]) -> T | None:
    """Call func on the main thread. If already on main thread, call directly."""
    if threading.current_thread() is threading.main_thread():
        return func()
    # Safety net — should never happen for AE handlers in a GUI app
    if _main_thread_dispatch is None:
        raise RuntimeError("No main-thread dispatcher registered — call register_apple_event_handlers() first")

    result_holder: list[T | object] = [_TIMEOUT]
    exc_holder: list[BaseException] = []
    done = threading.Event()

    def _wrapper():
        try:
            result_holder[0] = func()
        except BaseException as e:
            exc_holder.append(e)
        finally:
            done.set()

    # noinspection PyCallingNonCallable
    _main_thread_dispatch(_wrapper)
    if not done.wait(timeout=_MAIN_THREAD_TIMEOUT_S):
        logger.error("_call_on_main_thread timed out after %ds", _MAIN_THREAD_TIMEOUT_S)
        return None

    # Re-raise exception from the main thread on the calling thread
    if exc_holder:
        raise exc_holder[0]

    result = result_holder[0]
    return None if result is _TIMEOUT else result  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Apple Event Handler (NSObject subclass)
# ---------------------------------------------------------------------------


# noinspection PyPep8Naming,PyMethodMayBeStatic,PyUnusedLocal
class AppleEventHandler(objc.lookUpClass("NSObject")):  # type: ignore[misc]
    """Handles all 15 Greeting Cards Apple Event commands."""

    _window: ScriptingTarget | None

    # noinspection PyMethodFirstArgAssignment,PyUnresolvedReferences
    def initWithWindow_(self, window: ScriptingTarget):
        self = objc.super(AppleEventHandler, self).init()
        if self is None:  # pragma: no cover
            return None
        self._window = window
        return self

    def _ensure_window(self) -> ScriptingTarget:
        if self._window is None:  # pragma: no cover
            raise RuntimeError("AppleEventHandler not initialized")
        return self._window

    # Note: JSON error strings in handler responses are part of the scripting API
    # contract. Changes to these strings may break external AppleScript clients.

    # -- Loading & Status --------------------------------------------------

    def handleLoadPaths_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """load paths — load PDFs from files/folders."""
        paths = _get_text_list_param(event)
        if not paths:
            _set_text_reply(reply, json.dumps({"success": True, "count": 0}))
            return

        window = self._ensure_window()

        def _do():
            return window.load_paths_for_script(paths)

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    def handleGetStatus_reply_(self, _event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """get status — return app status as JSON."""
        window = self._ensure_window()

        def _do():
            return _status_to_json(window)

        result = _call_on_main_thread(_do)
        _set_text_reply(reply, result or "{}")

    def handleReload_reply_(self, _event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """reload — trigger manual reload."""

        def _do():
            return self._ensure_window().reload_for_script()

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    def handleClearAll_reply_(self, _event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """clear all — clear all loaded cards."""

        def _do():
            return self._ensure_window().clear_all_for_script()

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    # -- Card Queries ------------------------------------------------------

    def handleGetCardInfo_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """get card info — return card state as JSON."""
        filename = _get_direct_text(event)
        if not filename:
            _set_text_reply(reply, json.dumps({"error": "No filename provided"}))
            return

        window = self._ensure_window()

        def _do():
            card = window.get_card_info_for_script(filename)
            if card is None:
                return json.dumps({"error": f"Card not found: {filename}"})
            return _card_to_json(card)

        result = _call_on_main_thread(_do)
        _set_text_reply(reply, result or "{}")

    def handleGetLoadedCards_reply_(self, _event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """get loaded cards — return all cards as JSON array."""
        window = self._ensure_window()

        def _do():
            cards = window.get_all_cards_for_script()
            return json.dumps([_card_summary(c) for c in cards])

        result = _call_on_main_thread(_do)
        _set_text_reply(reply, result or "[]")

    # -- Card Mutations ----------------------------------------------------

    def handleRenameCard_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """rename card — rename a card on disk."""
        filename = _get_direct_text(event)
        new_name = _get_text_param(event, _K_NEW_NAME)
        year = _get_text_param(event, _K_YEAR)

        if not filename or new_name is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Missing filename or name"}))
            return

        window = self._ensure_window()

        def _do():
            return window.rename_card_for_script(filename, new_name, year)

        result = _call_on_main_thread(_do)
        _set_text_reply(reply, json.dumps(result) if result else json.dumps({"success": False, "error": "timeout"}))

    def handleSetCardName_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """set card name — set/clear manual name override."""
        filename = _get_direct_text(event)
        new_name = _get_text_param(event, _K_NEW_NAME)

        if not filename or new_name is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Missing filename or name"}))
            return

        window = self._ensure_window()

        def _do():
            return window.set_card_name_for_script(filename, new_name)

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    def handleSelectCandidate_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """select candidate — select candidate by rank."""
        filename = _get_direct_text(event)
        rank = _get_int_param(event, _K_RANK)

        if not filename or rank is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Missing filename or rank"}))
            return

        window = self._ensure_window()

        def _do():
            return window.select_candidate_for_script(filename, rank)

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    def handleSetRemoveFamily_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """set remove family — toggle Remove Family checkbox."""
        filename = _get_direct_text(event)
        new_value = _get_bool_param(event, _K_NEW_VALUE)

        if not filename or new_value is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Missing filename or value"}))
            return

        window = self._ensure_window()

        def _do():
            return window.set_remove_family_for_script(filename, new_value)

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    # -- AI Operations -----------------------------------------------------

    def handleAnalyzeCards_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """analyze cards — start AI analysis."""
        filename = _get_direct_text(event)
        window = self._ensure_window()

        def _do():
            return window.analyze_for_script(filename)

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    def handleClearAiResults_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """clear AI results — clear AI results."""
        filename = _get_direct_text(event)
        window = self._ensure_window()

        def _do():
            return window.clear_ai_for_script(filename)

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    # -- Model Management --------------------------------------------------

    def handleGetModels_reply_(self, _event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """get models — return available models as JSON."""
        _set_text_reply(reply, _ai_models_to_json())

    def handleSetModel_reply_(self, event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) -> None:
        """set model — set the active AI model."""
        model_id = _get_direct_text(event)
        if not model_id:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Missing model ID"}))
            return

        if not ConfigService.validate_model_id(model_id):
            _set_text_reply(reply, json.dumps({"success": False, "error": f"Unknown model: {model_id}"}))
            return

        window = self._ensure_window()

        def _do():
            return window.set_ai_model_for_script(model_id)

        result = _call_on_main_thread(_do)
        if result is None:
            _set_text_reply(reply, json.dumps({"success": False, "error": "Main thread timeout"}))
        else:
            _set_text_reply(reply, json.dumps(result))

    # -- Lifecycle ---------------------------------------------------------

    def handleQuit_reply_(self, _event: NSAppleEventDescriptor, _reply: NSAppleEventDescriptor) -> None:
        """quit — close the application."""
        window = self._ensure_window()
        _call_on_main_thread(lambda: window.quit_for_script())


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Command code → handler selector mapping
_HANDLER_MAP: dict[str, str] = {
    "LdPa": "handleLoadPaths:reply:",
    "GtSt": "handleGetStatus:reply:",
    "RlCd": "handleReload:reply:",
    "ClAl": "handleClearAll:reply:",
    "InCd": "handleGetCardInfo:reply:",
    "LsCd": "handleGetLoadedCards:reply:",
    "RnCd": "handleRenameCard:reply:",
    "StNm": "handleSetCardName:reply:",
    "SlCa": "handleSelectCandidate:reply:",
    "StRF": "handleSetRemoveFamily:reply:",
    "AnCd": "handleAnalyzeCards:reply:",
    "ClAi": "handleClearAiResults:reply:",
    "GtMo": "handleGetModels:reply:",
    "StMo": "handleSetModel:reply:",
}


def register_apple_event_handlers(
    window: ScriptingTarget,
    *,
    main_thread_dispatch: Callable | None = None,
) -> AppleEventHandler:
    """Register all 14 GrCd Apple Event handlers with NSAppleEventManager.

    Args:
        window: The ScriptingTarget instance for handler callbacks.
        main_thread_dispatch: Callable to dispatch work to the main thread
            (e.g. ``wx.CallAfter``). Stored module-wide for ``_call_on_main_thread``.

    Returns the handler instance (caller must retain a reference to prevent GC).
    The aevt/quit handler must be registered separately via register_quit_handler()
    after MainLoop starts, to overwrite wxPython's own aevt/quit handler.
    """
    global _main_thread_dispatch
    _main_thread_dispatch = main_thread_dispatch

    handler = AppleEventHandler.alloc().initWithWindow_(window)
    mgr = NSAppleEventManager.sharedAppleEventManager()
    event_class = ae_keyword("GrCd")

    for code_suffix, selector in _HANDLER_MAP.items():
        event_id = ae_keyword(code_suffix)
        # noinspection PyUnresolvedReferences
        mgr.setEventHandler_andSelector_forEventClass_andEventID_(
            handler,
            objc.selector(None, selector=selector.encode(), signature=b"v@:@@"),
            event_class,
            event_id,
        )

    logger.info("Registered %d Apple Event handlers", len(_HANDLER_MAP))
    return handler


def register_quit_handler(handler: AppleEventHandler) -> None:
    """Register the aevt/quit handler (must be called after MainLoop starts).

    wxPython re-installs its own aevt/quit handler during MainLoop() startup,
    so this must be deferred (e.g. via wx.CallAfter) to get the last word.
    """
    mgr = NSAppleEventManager.sharedAppleEventManager()
    # noinspection PyUnresolvedReferences
    mgr.setEventHandler_andSelector_forEventClass_andEventID_(
        handler,
        objc.selector(None, selector=b"handleQuit:reply:", signature=b"v@:@@"),
        ae_keyword("aevt"),
        ae_keyword("quit"),
    )
    logger.info("Registered aevt/quit handler (deferred)")
