import sys
from pathlib import Path


def is_bundled() -> bool:
    """True when running inside a PyInstaller .app bundle."""
    return getattr(sys, "_MEIPASS", None) is not None


def get_data_dir() -> Path:
    """Return the directory for user data (DB, preferences).

    Dev mode  : project_root/.local/ (auto-created)
    Bundled   : ~/Library/Application Support/GreetingCards/ (auto-created)
    """
    if is_bundled():
        data_dir = Path.home() / "Library" / "Application Support" / "GreetingCards"
    else:
        # Dev mode — .local/ subdir of project root (keeps project root clean)
        data_dir = Path(__file__).resolve().parent.parent.parent / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    return get_data_dir() / "GreetingCards.sqlite"
