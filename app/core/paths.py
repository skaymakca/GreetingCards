import sys
from pathlib import Path


def is_bundled() -> bool:
    """True when running inside a PyInstaller .app bundle."""
    return getattr(sys, "_MEIPASS", None) is not None


def get_data_dir() -> Path:
    """Return the directory for user data (DB, preferences).

    Dev mode  : project root (directory containing main.py)
    Bundled   : ~/Library/Application Support/GreetingCards/ (auto-created)
    """
    if is_bundled():
        data_dir = Path.home() / "Library" / "Application Support" / "GreetingCards"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    # Dev mode — project root (two levels up from this file: core/ -> app/ -> project)
    return Path(__file__).resolve().parent.parent.parent


def get_db_path() -> Path:
    return get_data_dir() / "GreetingCards.sqlite"
