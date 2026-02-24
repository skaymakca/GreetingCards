import sys
from pathlib import Path


# noinspection PyProtectedMember
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


# noinspection PyProtectedMember
def get_runtime_content_path(rel_path: str = "") -> Path:
    """Return path under _runtime_content/ (works in both dev and bundled mode).

    Args:
        rel_path: Relative path within _runtime_content (e.g. "tessdata/fast", "html/help")
    """
    if is_bundled():
        base = Path(sys._MEIPASS) / "_runtime_content"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent / "_runtime_content"
    return base / rel_path if rel_path else base


def get_db_path() -> Path:
    return get_data_dir() / "GreetingCards.sqlite"
