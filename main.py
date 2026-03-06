#!/usr/bin/env python3
"""wxPython version of Greeting Cards App."""

import logging
import multiprocessing
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import wx

from app.core.apple_events import register_apple_event_handlers, register_quit_handler
from app.core.config import has_prompted_auto_update, set_prompted_auto_update
from app.core.sparkle import init as sparkle_init
from app.core.sparkle import set_auto_check_enabled
from app.core.sparkle import start as sparkle_start
from app.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _startup_sparkle(window: MainWindow) -> None:
    """Show first-launch auto-update opt-in, then start Sparkle."""
    if not has_prompted_auto_update():
        result = wx.MessageBox(
            "Would you like Greeting Cards to automatically check for updates?\n\n"
            "You can change this later in Settings.",
            "Automatic Updates",
            wx.YES_NO | wx.ICON_QUESTION,
            window._frame,
        )
        set_auto_check_enabled(result == wx.YES)
        set_prompted_auto_update()
    sparkle_start()


def main():
    """Main entry point for wxPython version."""
    multiprocessing.freeze_support()  # PyInstaller support

    app = wx.App()

    # Sparkle auto-update: init framework before window (menu bar checks is_available)
    sparkle_init()

    window = MainWindow()

    _ae_handler = register_apple_event_handlers(window, main_thread_dispatch=wx.CallAfter)

    # Defer aevt/quit registration until after MainLoop starts so our handler
    # overwrites wxPython's own aevt/quit handler installed during MainLoop init.
    wx.CallAfter(register_quit_handler, _ae_handler)

    # Sparkle auto-update: defer start until after MainLoop
    wx.CallAfter(_startup_sparkle, window)

    window.run()
    app.MainLoop()


if __name__ == "__main__":
    main()
