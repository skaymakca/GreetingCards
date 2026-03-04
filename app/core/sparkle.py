"""Sparkle 2 auto-update integration via PyObjC.

Loads Sparkle.framework from the app bundle's Frameworks directory and provides
a thin Python API for the SPUStandardUpdaterController. All functions are safe
no-ops when running from source (not bundled) or when the framework is not found.

Public API:
    init() -> bool          Load framework, create controller (deferred start)
    start() -> None         Begin automatic update check schedule
    check_for_updates() -> None   User-initiated check (menu item)
    is_available() -> bool  True if Sparkle loaded successfully
    get_auto_check_enabled() -> bool   Read SUEnableAutomaticChecks
    set_auto_check_enabled(enabled) -> None   Write SUEnableAutomaticChecks
    cleanup() -> None       Release resources
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level state — typed as Any because the ObjC classes are dynamically loaded
_controller: Any = None
_updater: Any = None


def _get_frameworks_path() -> Path | None:
    """Return the Frameworks directory inside the app bundle, or None."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        return None
    # _MEIPASS points to Contents/Resources inside the .app bundle
    # Frameworks is at Contents/Frameworks
    contents = Path(meipass).parent
    frameworks = contents / "Frameworks"
    if frameworks.is_dir():
        return frameworks
    return None


def init() -> bool:
    """Load Sparkle.framework and create the updater controller.

    Returns True if Sparkle was loaded successfully, False otherwise.
    The controller is created with deferred start — call start() after
    the main event loop begins.
    """
    global _controller, _updater

    from app.core.paths import is_bundled

    if not is_bundled():
        logger.debug("Sparkle: not bundled, skipping init")
        return False

    frameworks_path = _get_frameworks_path()
    if frameworks_path is None:
        logger.warning("Sparkle: Frameworks directory not found")
        return False

    sparkle_path = frameworks_path / "Sparkle.framework"
    if not sparkle_path.exists():
        logger.warning("Sparkle: framework not found at %s", sparkle_path)
        return False

    # noinspection PyBroadException
    try:
        import objc  # type: ignore[import-untyped]
        from Foundation import NSBundle  # type: ignore[import-untyped]

        bundle = NSBundle.bundleWithPath_(str(sparkle_path))
        if bundle is None or not bundle.load():
            logger.warning("Sparkle: failed to load framework bundle")
            return False

        SPUStandardUpdaterController = objc.lookUpClass("SPUStandardUpdaterController")

        # Init with deferred start (startingUpdater=False)
        _controller = SPUStandardUpdaterController.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(
            False, None, None
        )
        _updater = _controller.updater()

        logger.info("Sparkle: framework loaded successfully")
        return True
    except Exception:
        logger.warning("Sparkle: failed to initialize", exc_info=True)
        _controller = None
        _updater = None
        return False


def start() -> None:
    """Begin the automatic update check schedule.

    Must be called after the main event loop has started (e.g. via wx.CallAfter).
    """
    if _controller is None:
        return

    # noinspection PyBroadException
    try:
        _controller.startUpdater()
        logger.debug("Sparkle: updater started")
    except Exception:
        logger.warning("Sparkle: failed to start updater", exc_info=True)


def check_for_updates() -> None:
    """Trigger a user-initiated update check.

    Shows the Sparkle update UI. Safe to call when controller is None.
    """
    if _controller is None:
        return

    # noinspection PyBroadException
    try:
        _controller.checkForUpdates_(None)
    except Exception:
        logger.warning("Sparkle: check for updates failed", exc_info=True)


def is_available() -> bool:
    """Return True if Sparkle was loaded and the controller is ready."""
    return _controller is not None


def get_auto_check_enabled() -> bool:
    """Return whether automatic update checks are enabled.

    Reads from Sparkle's own NSUserDefaults key (SUEnableAutomaticChecks).
    Returns True by default if Sparkle is not available.
    """
    if _updater is None:
        return True

    # noinspection PyBroadException
    try:
        return bool(_updater.automaticallyChecksForUpdates())
    except Exception:
        return True


def set_auto_check_enabled(enabled: bool) -> None:
    """Set whether automatic update checks are enabled.

    Writes to Sparkle's own NSUserDefaults key.
    """
    if _updater is None:
        return

    # noinspection PyBroadException
    try:
        _updater.setAutomaticallyChecksForUpdates_(enabled)
    except Exception:
        logger.warning("Sparkle: failed to set auto-check preference", exc_info=True)


def cleanup() -> None:
    """Release Sparkle resources. Safe to call multiple times."""
    global _controller, _updater
    _controller = None
    _updater = None
    logger.debug("Sparkle: cleaned up")
