#!/usr/bin/env python3
"""wxPython version of Greeting Cards App."""

import logging
import os
import sys
import multiprocessing
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import wx
from app.core.paths import is_bundled
from app.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main():
    """Main entry point for wxPython version."""
    multiprocessing.freeze_support()  # PyInstaller support

    if not is_bundled() and not os.environ.get("ANTHROPIC_API_KEY"):
        logger.info(
            "ANTHROPIC_API_KEY not set in environment; "
            "set via export or enter it in Settings (Cmd+,)"
        )

    app = wx.App()
    window = MainWindow()
    window.run()
    app.MainLoop()


if __name__ == "__main__":
    main()
