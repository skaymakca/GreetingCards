#!/usr/bin/env python3
"""wxPython version of Greeting Cards App."""

import sys
import multiprocessing
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import wx
from app.gui.main_window import MainWindow


def main():
    """Main entry point for wxPython version."""
    multiprocessing.freeze_support()  # PyInstaller support

    app = wx.App()
    window = MainWindow()
    window.run()
    app.MainLoop()


if __name__ == "__main__":
    main()
