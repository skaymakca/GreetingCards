#!/usr/bin/env python3
"""wxPython version of Greeting Cards App."""

import logging
import multiprocessing
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import wx

from app.core.apple_events import register_apple_event_handlers, register_quit_handler
from app.core.paths import is_bundled
from app.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main():
    """Main entry point for wxPython version."""
    multiprocessing.freeze_support()  # PyInstaller support

    if not is_bundled() and not os.environ.get("ANTHROPIC_API_KEY"):
        logger.info("ANTHROPIC_API_KEY not set in environment; set via export or enter it in Settings (Cmd+,)")

    app = wx.App()
    window = MainWindow()

    _ae_handler = register_apple_event_handlers(window, main_thread_dispatch=wx.CallAfter)
    assert _ae_handler is not None  # prevent "not accessed" warning

    # Defer aevt/quit registration until after MainLoop starts so our handler
    # overwrites wxPython's own aevt/quit handler installed during MainLoop init.
    wx.CallAfter(register_quit_handler, _ae_handler)

    window.run()
    app.MainLoop()


if __name__ == "__main__":
    main()
