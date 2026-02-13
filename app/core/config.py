import os
import plistlib
from pathlib import Path

from app.core.paths import is_bundled, get_data_dir

_PLIST_NAME = "preferences.plist"
_KEY_NAME = "ANTHROPIC_API_KEY"


def _plist_path() -> Path:
    return get_data_dir() / _PLIST_NAME


def _read_plist() -> dict:
    path = _plist_path()
    if path.exists():
        with open(path, "rb") as f:
            return plistlib.load(f)
    return {}


def _write_plist(data: dict):
    with open(_plist_path(), "wb") as f:
        plistlib.dump(data, f)


def get_api_key() -> str | None:
    """Return the Anthropic API key, or None if not configured.

    Resolution order:
      1. ANTHROPIC_API_KEY environment variable (always checked)
      2. Dev mode: .env file via dotenv
      3. Bundled mode: preferences.plist in data dir
    """
    # 1. Check environment (may already be set externally)
    key = os.environ.get(_KEY_NAME)
    if key and key != "your-api-key-here":
        return key

    if not is_bundled():
        # 2. Dev mode — load .env then re-check
        from dotenv import load_dotenv
        load_dotenv()
        key = os.environ.get(_KEY_NAME)
        if key and key != "your-api-key-here":
            return key
    else:
        # 3. Bundled mode — read from plist
        prefs = _read_plist()
        key = prefs.get(_KEY_NAME)
        if key:
            return key

    return None


def save_api_key(key: str):
    """Persist the API key to preferences.plist in the data dir."""
    prefs = _read_plist()
    prefs[_KEY_NAME] = key
    _write_plist(prefs)
    # Also set in current process so get_api_key() returns it immediately
    os.environ[_KEY_NAME] = key
