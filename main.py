#!/usr/bin/env python3
"""Greeting Card PDF Analyzer & Renamer"""

import sys
import multiprocessing
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from app.gui.main_window import MainWindow


def main():
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    # Required for PyInstaller bundled apps with multiprocessing
    multiprocessing.freeze_support()
    main()
