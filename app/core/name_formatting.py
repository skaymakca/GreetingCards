"""Name formatting utilities for proper capitalization of family names."""


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
        "van der berg" → "van der Berg" (first word) or "Van der Berg"
        "smith-jones" → "Smith-Jones"
        "john smith jr" → "John Smith Jr"
    """
    if not name:
        return name

    # Special prefixes that should have internal capitals
    MAC_PREFIXES = ['mc', 'mac']
    # Particles that should be lowercase (unless first word)
    PARTICLES = ['van', 'von', 'de', 'del', 'der', 'den', 'la', 'le', 'da', 'di', 'st']
    # Suffixes that should be uppercase
    SUFFIXES = ['ii', 'iii', 'iv', 'v', 'jr', 'sr']

    words = name.split()
    result = []

    for i, word in enumerate(words):
        is_first_word = (i == 0)

        # Handle apostrophes (O'Brian → O'Brian)
        if "'" in word:
            parts = word.split("'")
            formatted = parts[0].capitalize() + "'" + "'".join(p.capitalize() for p in parts[1:])
            result.append(formatted)

        # Handle hyphens (Smith-Jones → Smith-Jones)
        elif "-" in word:
            parts = word.split("-")
            formatted = "-".join(p.capitalize() for p in parts)
            result.append(formatted)

        # Handle Mc/Mac prefixes
        elif any(word.lower().startswith(prefix) for prefix in MAC_PREFIXES):
            if word.lower().startswith('mc') and len(word) > 2:
                result.append('Mc' + word[2:].capitalize())
            elif word.lower().startswith('mac') and len(word) > 3:
                result.append('Mac' + word[3:].capitalize())
            else:
                result.append(word.capitalize())

        # Handle suffixes (keep uppercase)
        elif word.lower() in SUFFIXES:
            # Format as title with periods for Jr./Sr.
            if word.lower() in ['jr', 'sr']:
                result.append(word.capitalize() + '.')
            else:
                result.append(word.upper())

        # Handle particles (keep lowercase unless first word)
        elif word.lower() in PARTICLES:
            if is_first_word:
                result.append(word.capitalize())
            else:
                result.append(word.lower())

        # Default title case
        else:
            result.append(word.capitalize())

    return ' '.join(result)
