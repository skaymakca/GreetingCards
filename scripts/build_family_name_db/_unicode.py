"""Shared Unicode normalization constants for family name build scripts."""

from __future__ import annotations

import re
import unicodedata

# Characters that NFKD decomposition doesn't handle — map to ASCII equivalents.
UNICODE_SPECIAL: dict[str, str] = {"ß": "ss", "ø": "o", "æ": "ae", "ð": "d", "þ": "th", "đ": "d", "ł": "l"}


def normalize(name: str) -> str:
    """Normalize for lookup: Unicode-fold to ASCII, lowercase, strip non-alpha.

    Uses NFKD decomposition (ñ→n, ü→u, é→e, etc.) plus a small manual map
    for characters that NFKD doesn't decompose (ß→ss, ø→o).
    """
    lowered = name.lower()
    # Apply special character map first
    for char, repl in UNICODE_SPECIAL.items():
        if char in lowered:
            lowered = lowered.replace(char, repl)
    # NFKD decompose (ñ→n+combining_tilde, ü→u+combining_diaeresis, etc.)
    decomposed = unicodedata.normalize("NFKD", lowered)
    # Strip everything except ASCII a-z
    return re.sub(r"[^a-z]", "", decomposed)
