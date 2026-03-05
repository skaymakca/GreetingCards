"""macOS platform utilities — no GUI dependencies."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def open_file(path: str | Path) -> None:
    """Open a file with the default macOS handler."""
    try:
        subprocess.Popen(["open", str(path)])
    except OSError as e:
        logger.warning("Failed to open %s: %s", path, e)


def reveal_in_finder(path: str | Path) -> None:
    """Reveal a file in Finder."""
    try:
        subprocess.Popen(["open", "-R", str(path)])
    except OSError as e:
        logger.warning("Failed to reveal %s: %s", path, e)
