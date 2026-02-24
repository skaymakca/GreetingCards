"""Name formatting utilities for proper capitalization of family names."""

import re

# Characters invalid in filenames on Windows, macOS, or Linux
INVALID_FILENAME_CHARS: frozenset[str] = frozenset('\\/:*?"<>|')
_INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_for_filename(name: str) -> str:
    """Replace characters that are invalid in filenames across OS platforms."""
    return _INVALID_FS_CHARS.sub("-", name).strip()


def deparameterize_name(name: str) -> str:
    """Remove plural 's' from family names.

    Examples:
        "Smiths" → "Smith"
        "Jones" → "Jones" (already singular)
        "The Smiths" → "The Smith"
    """
    if not name:
        return name

    words = name.split()
    result = []

    for word in words:
        # Skip articles and particles
        if word.lower() in ["the", "a", "an"]:
            result.append(word)
            continue

        # Remove trailing 's' if it looks like a plural family name
        # But keep names that naturally end in 's' (Jones, Williams, etc.)
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            # Check if the word naturally ends in 's' by looking at common patterns
            # Natural endings: Jones, Williams, Adams, Davis, Thomas, Matthews, etc.
            # These typically end in: -nes, -ms, -vis, -lis, -as, -es (after certain letters)
            lower_word = word.lower()
            natural_endings = ("nes", "mes", "ams", "vis", "lis", "as", "is", "us", "ris", "ies")

            # Check if this looks like a natural 's' ending
            if any(lower_word.endswith(ending) for ending in natural_endings):
                result.append(word)
            else:
                # Looks like a plural, remove the 's'
                result.append(word[:-1])
        else:
            result.append(word)

    return " ".join(result)


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

    Examples:
        "mcdonald" → "McDonald"
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

    Examples:
        "jr" → "Jr."
        "iii" → "III"
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

    Examples:
        "van" (first) → "Van"
        "van" (not first) → "van"
        "smith" → None (not a particle)
    """
    if word.lower() in _PARTICLES:
        return word.capitalize() if is_first_word else word.lower()
    return None


# noinspection GrazieInspection
def _format_word_part(part: str) -> str:
    """Apply capitalization rules to a single part (no apostrophes or hyphens).

    This is the leaf-level formatter. Checks suffixes first, then Mc/Mac rules.

    Examples:
        "mcdonald" → "McDonald"
        "jr" → "Jr."
        "smith" → "Smith"
    """
    # Check for suffixes first
    suffix = _format_suffix(part)
    if suffix:
        return suffix

    # Apply Mc/Mac rules (handles exceptions too)
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

    Examples:
        "o'brien-mcdonald" → "O'Brien-McDonald"
        "smith-jones" → "Smith-Jones"
        "mcdonald" → "McDonald"
    """
    # Split by apostrophes first
    apostrophe_parts = word.split("'")
    formatted_apostrophe_parts = []

    for apos_part in apostrophe_parts:
        # For each apostrophe part, split by hyphens
        if "-" in apos_part:
            hyphen_parts = apos_part.split("-")
            # Format each hyphen part
            formatted_hyphen_parts = [_format_word_part(hp) for hp in hyphen_parts]
            # Join hyphens back
            formatted_apostrophe_parts.append("-".join(formatted_hyphen_parts))
        else:
            # No hyphens, just format the part
            formatted_apostrophe_parts.append(_format_word_part(apos_part))

    # Join apostrophes back
    return "'".join(formatted_apostrophe_parts)


# --- Main Function ---


# noinspection GrazieInspection
def smart_title_case(name: str) -> str:
    """Apply smart title case with special rules for names.

    Handles:
    - O'Brian, D'Angelo → keep apostrophe, capitalize both parts
    - McDonald, MacLeod → keep Mc/Mac internal caps
    - van der Berg, Von Trapp → lowercase particles (unless first word)
    - II, III, IV, Jr, Sr → keep uppercase
    - Names with hyphens → capitalize each part

    Examples:
        "o'brian" → "O'Brian"
        "mcdonald" → "McDonald"
        "van der berg" → "Van der Berg" (first word) or "john van der berg" → "John van der Berg"
        "smith-jones" → "Smith-Jones"
        "john smith jr" → "John Smith Jr."
    """
    if not name:
        return name

    words = name.split()
    result = []

    for i, word in enumerate(words):
        is_first_word = i == 0

        # Check if word is a particle (special handling for position)
        particle = _format_particle(word, is_first_word)
        if particle:
            result.append(particle)
            continue

        # Format word (handles apostrophes, hyphens, Mc/Mac, suffixes)
        formatted = _format_word_with_structure(word)
        result.append(formatted)

    return " ".join(result)
