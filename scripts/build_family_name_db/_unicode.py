"""Shared Unicode normalization constants for family name build scripts."""

# Characters that NFKD decomposition doesn't handle — map to ASCII equivalents.
UNICODE_SPECIAL: dict[str, str] = {"ß": "ss", "ø": "o", "æ": "ae", "ð": "d", "þ": "th", "đ": "d", "ł": "l"}
