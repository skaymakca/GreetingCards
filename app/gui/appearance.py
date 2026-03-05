"""macOS appearance detection and live-switching support.

Uses KVO on NSApplication.effectiveAppearance to detect dark/light mode
changes in real time. The observer fires immediately when the user toggles
the system appearance in System Settings.

Public API:
    is_dark_mode() -> bool
    start_observer(callback) -> None
    stop_observer() -> None
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import objc  # type: ignore[import-untyped]
import wx
from AppKit import NSApplication  # type: ignore[import-untyped]
from Foundation import NSKeyValueObservingOptionNew, NSObject  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_KEY_PATH = "effectiveAppearance"

# Module-level state
_observer: _AppearanceObserver | None = None


def is_dark_mode() -> bool:
    """Return True if macOS is currently in dark mode."""
    # noinspection PyBroadException
    try:
        app = NSApplication.sharedApplication()
        name = app.effectiveAppearance().name()
        return "Dark" in name
    except Exception:
        return False


class _AppearanceObserver(NSObject):
    """KVO observer for NSApplication.effectiveAppearance changes."""

    # noinspection PyUnresolvedReferences
    _callback = objc.ivar()  # pyright: ignore[reportAttributeAccessIssue]

    # noinspection PyPep8Naming,PyUnusedLocal
    def observeValueForKeyPath_ofObject_change_context_(
        self, path: str, obj: object, change: object, ctx: int
    ) -> None:  # pragma: no cover
        if callable(self._callback):
            wx.CallAfter(self._callback)


def start_observer(callback: Callable[[], None]) -> None:
    """Register a KVO observer on NSApp.effectiveAppearance.

    The callback is invoked on the wx main thread (via wx.CallAfter)
    whenever the system appearance changes.

    Args:
        callback: Function to call when appearance changes (no args).
    """
    global _observer
    if _observer is not None:
        logger.warning("Appearance observer already running; ignoring duplicate start")
        return

    _observer = _AppearanceObserver.alloc().init()
    _observer._callback = callback  # pyright: ignore[reportOptionalMemberAccess]

    NSApplication.sharedApplication().addObserver_forKeyPath_options_context_(
        _observer, _KEY_PATH, NSKeyValueObservingOptionNew, 0
    )
    logger.debug("Appearance KVO observer started")


def stop_observer() -> None:
    """Remove the KVO observer. Safe to call if not started."""
    global _observer
    if _observer is None:
        return

    # noinspection PyBroadException
    try:
        NSApplication.sharedApplication().removeObserver_forKeyPath_(_observer, _KEY_PATH)
    except Exception:
        logger.debug("Failed to remove appearance observer", exc_info=True)

    _observer = None
    logger.debug("Appearance KVO observer stopped")
