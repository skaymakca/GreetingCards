import re
from app.models.card import Confidence

# Words to filter out — common greeting card phrases
GREETING_WORDS = {
    "merry", "christmas", "happy", "holidays", "season", "seasons",
    "greetings", "new", "year", "joy", "peace", "love", "hope",
    "wishing", "wish", "warm", "warmest", "best", "wishes",
    "cheers", "noel", "blessings", "blessed", "wonderful",
    "joyful", "joyous", "festive", "celebrate", "celebration",
    "may", "your", "you", "and", "the", "from", "with", "all",
    "have", "very", "this", "that", "for", "our", "are", "was",
    "dear", "friends", "friend", "neighbor", "neighbors",
}


def _clean_name(name: str) -> str:
    """Clean up extracted name."""
    name = name.strip().strip(".,!;:-—–\"'""''")
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _is_valid_name(name: str) -> bool:
    """Check if a string looks like a real family name."""
    if not name or len(name) < 2:
        return False
    words = name.lower().split()
    # All words are greeting words
    if all(w in GREETING_WORDS for w in words):
        return False
    # Too many words for a name
    if len(words) > 6:
        return False
    # Must contain at least one capitalized word
    if not any(w[0].isupper() for w in name.split() if w):
        return False
    return True


def _strip_family_suffix(name: str) -> str:
    """Remove 'Family' suffix if present for normalization."""
    return re.sub(r"\s+[Ff]amily\s*$", "", name).strip()


def _make_family_name(name: str) -> str:
    """Ensure name ends with 'Family' for consistent output, or strip plurals."""
    name = _clean_name(name)
    # "The Smiths" -> "Smith"
    match = re.match(r"^[Tt]he\s+(.+?)s?$", name)
    if match:
        base = match.group(1)
        # Remove trailing 's' for plural family names like "The Johnsons" -> "Johnson"
        if name.endswith("s") and not name.endswith("ss"):
            return base
        return base
    return name


def extract_family_names(text: str) -> list[tuple[str, Confidence]]:
    """
    Extract family names from OCR text.
    Returns list of (name, confidence) tuples, ordered by confidence.
    """
    results = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # HIGH confidence patterns
    # "The Smith Family" or "The Smiths Family"
    for line in lines:
        m = re.search(r"[Tt]he\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+[Ff]amily", line)
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name):
                results.append((name, Confidence.HIGH))

    # "The Smiths" or "The Johnsons" (at end of line or followed by punctuation)
    for line in lines:
        m = re.search(r"[Tt]he\s+([A-Z][a-zA-Z]+s)\b", line)
        if m:
            name = m.group(1)
            # Remove trailing 's' to get family name
            base = name[:-1] if not name.endswith("ss") else name
            if _is_valid_name(base) and base.lower() not in GREETING_WORDS:
                results.append((base, Confidence.HIGH))

    # "From the Johnsons" / "From the Smith Family"
    for line in lines:
        m = re.search(r"[Ff]rom\s+[Tt]he\s+([A-Z][a-zA-Z]+?)(?:s\b|\s+[Ff]amily)", line)
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name):
                results.append((name, Confidence.HIGH))

    # "Love, The Smiths" / "Love, The Smith Family"
    for line in lines:
        m = re.search(r"[Ll]ove,?\s+[Tt]he\s+([A-Z][a-zA-Z]+?)(?:s\b|\s+[Ff]amily)", line)
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name):
                results.append((name, Confidence.HIGH))

    # MEDIUM confidence patterns
    # "With love, John & Jane Smith"
    for line in lines:
        m = re.search(
            r"(?:[Ww]ith\s+)?[Ll]ove,?\s+\w+\s*[&+]\s*\w+\s+([A-Z][a-zA-Z]+)\s*$",
            line,
        )
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name):
                results.append((name, Confidence.MEDIUM))

    # "-- The Smiths" or "— The Smith Family"
    for line in lines:
        m = re.search(r"[-—–]+\s*[Tt]he\s+([A-Z][a-zA-Z]+?)(?:s\b|\s+[Ff]amily)", line)
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name):
                results.append((name, Confidence.MEDIUM))

    # Possessives: "Smith's" or "The Smith's"
    for line in lines:
        m = re.search(r"(?:[Tt]he\s+)?([A-Z][a-zA-Z]+)'s\b", line)
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name) and name.lower() not in GREETING_WORDS:
                results.append((name, Confidence.MEDIUM))

    # "John & Jane Smith" without "love" prefix
    for line in lines:
        m = re.search(r"([A-Z]\w+)\s*[&+]\s*([A-Z]\w+)\s+([A-Z][a-zA-Z]+)\s*$", line)
        if m:
            name = _clean_name(m.group(3))
            if _is_valid_name(name) and name.lower() not in GREETING_WORDS:
                results.append((name, Confidence.MEDIUM))

    # LOW confidence patterns
    # "Love, First Last" (last word as family name)
    for line in lines:
        m = re.search(r"[Ll]ove,?\s+([A-Z]\w+)\s+([A-Z][a-zA-Z]+)\s*$", line)
        if m:
            name = _clean_name(m.group(2))
            if _is_valid_name(name) and name.lower() not in GREETING_WORDS:
                results.append((name, Confidence.LOW))

    # Last line with capitalized words as fallback
    for line in reversed(lines):
        words = line.split()
        caps = [w for w in words if w[0].isupper() and w.lower() not in GREETING_WORDS]
        if caps and len(caps) <= 3:
            name = caps[-1]
            name = _clean_name(name)
            if _is_valid_name(name) and len(name) > 2:
                results.append((name, Confidence.LOW))
                break

    # Deduplicate while preserving order
    # NOTE: Cleaning is applied AFTER loading from DB, not here
    seen = set()
    unique = []
    for name, conf in results:
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append((name, conf))

    return unique
