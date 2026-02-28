"""Filename sanitization utilities."""

import re

# Characters invalid in filenames on Windows, macOS, or Linux
INVALID_FILENAME_CHARS: frozenset[str] = frozenset('\\/:*?"<>|')
_INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_for_filename(name: str) -> str:
    """Replace characters that are invalid in filenames across OS platforms."""
    return _INVALID_FS_CHARS.sub("-", name).strip()
