"""Smart title-case formatting for family names.

Handles Mc/Mac prefixes, particles (van, von, de …), apostrophes, hyphens,
and suffixes (Jr., Sr., II, III …).

When a family name database is available, database-backed display forms take
priority over heuristic formatting.
"""

from __future__ import annotations

from app.core.naming.family_name.data import family_name_db

# --- Constants ---

_MAC_EXCEPTIONS = ["macintosh", "machine", "mach", "macro", "mace"]
_PARTICLES = ["van", "von", "de", "del", "der", "den", "la", "le", "da", "di", "st"]
_SUFFIXES = ["ii", "iii", "iv", "v", "jr", "sr"]


# --- Helper Functions ---


def _is_mac_exception(word: str) -> bool:
    """Check if word is a Mac exception (macintosh, machine, etc.)."""
    return word.lower() in _MAC_EXCEPTIONS


# noinspection GrazieInspection
def _apply_mc_mac_rules(word: str) -> str:
    """Apply Mc/Mac capitalization rules.

    Examples::

        "mcdonald"  → "McDonald"
        "macdonald" → "MacDonald"
        "macintosh" → "Macintosh" (exception)
    """
    if _is_mac_exception(word):
        return word.capitalize()
    elif word.lower().startswith("mc") and len(word) > 2:
        return "Mc" + word[2:].capitalize()
    elif word.lower().startswith("mac") and len(word) > 3:
        return "Mac" + word[3:].capitalize()
    else:
        return word.capitalize()


def _format_suffix(word: str) -> str | None:
    """Format suffixes: jr/sr with period, roman numerals uppercase.

    Returns:
        Formatted suffix if word is a suffix, None otherwise.

    Examples::

        "jr"    → "Jr."
        "iii"   → "III"
        "smith" → None (not a suffix)
    """
    lower = word.lower()
    if lower in ["jr", "sr"]:
        return word.capitalize() + "."
    elif lower in _SUFFIXES:
        return word.upper()
    return None


def _format_particle(word: str, is_first_word: bool) -> str | None:
    """Format particles: lowercase unless first word.

    Returns:
        Formatted particle if word is a particle, None otherwise.

    Examples::

        "van" (first)     → "Van"
        "van" (not first) → "van"
        "smith"           → None (not a particle)
    """
    if word.lower() in _PARTICLES:
        return word.capitalize() if is_first_word else word.lower()
    return None


# noinspection GrazieInspection
def _format_word_part(part: str) -> str:
    """Apply capitalization rules to a single part (no apostrophes or hyphens).

    This is the leaf-level formatter. Checks suffixes first, then Mc/Mac rules.

    Examples::

        "mcdonald" → "McDonald"
        "jr"       → "Jr."
        "smith"    → "Smith"
    """
    suffix = _format_suffix(part)
    if suffix:
        return suffix
    return _apply_mc_mac_rules(part)


# noinspection GrazieInspection
def _format_word_with_structure(word: str) -> str:
    """Format a word by splitting hierarchically, formatting parts, and rejoining.

    Process:
    1. Split by apostrophes
    2. For each apostrophe part, split by hyphens
    3. Format each leaf part (apply Mc/Mac, suffix rules, etc.)
    4. Join hyphens back together
    5. Join apostrophes back together

    Examples::

        "o'brien-mcdonald" → "O'Brien-McDonald"
        "smith-jones"      → "Smith-Jones"
        "mcdonald"         → "McDonald"
    """
    apostrophe_parts = word.split("'")
    formatted_apostrophe_parts = []

    for apos_part in apostrophe_parts:
        if "-" in apos_part:
            hyphen_parts = apos_part.split("-")
            formatted_hyphen_parts = [_format_word_part(hp) for hp in hyphen_parts]
            formatted_apostrophe_parts.append("-".join(formatted_hyphen_parts))
        else:
            formatted_apostrophe_parts.append(_format_word_part(apos_part))

    return "'".join(formatted_apostrophe_parts)


# --- Main Function ---


# noinspection GrazieInspection
def smart_title_case_family_name(name: str) -> str:
    """Apply smart title case with special rules for names.

    Handles:
    - O'Brian, D'Angelo → keep apostrophe, capitalize both parts
    - McDonald, MacLeod → keep Mc/Mac internal caps
    - van der Berg, Von Trapp → lowercase particles (unless first word)
    - II, III, IV, Jr, Sr → keep uppercase
    - Names with hyphens → capitalize each part

    Examples::

        "o'brian"          → "O'Brian"
        "mcdonald"         → "McDonald"
        "van der berg"     → "Van der Berg"
        "smith-jones"      → "Smith-Jones"
        "john smith jr"    → "John Smith Jr."
    """
    if not name:
        return name

    words = name.split()

    # Database-first: use canonical display form for single-token inputs
    # that have no structural characters.  When the input already has
    # apostrophes, hyphens, or spaces, it carries word-boundary info that
    # the heuristic handles better than a DB form that may lose it
    # (e.g. input "o'brian" → heuristic "O'Brian" > DB "Obrian").
    if len(words) == 1 and "-" not in name and "'" not in name:
        display = family_name_db.display(name)
        if display is not None:
            return display
    result = []

    for i, word in enumerate(words):
        is_first_word = i == 0

        particle = _format_particle(word, is_first_word)
        if particle:
            result.append(particle)
            continue

        formatted = _format_word_with_structure(word)
        result.append(formatted)

    return " ".join(result)
