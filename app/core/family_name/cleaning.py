"""Family name cleaning and filtering.

Consolidates cleaning logic previously scattered across ``ai_analyzer.py``,
``name_formatting.py``, and ``database.py`` into a single module.
"""

import re

from app.core.family_name.data import filtered_names, preserved_family_names


def strip_plural_family_name(name: str) -> str:
    """Strip plural 's' or 'es' from a family name, preserving known surnames.

    Data-driven: names in the preserved-family-names corpus (Census Bureau)
    are returned unchanged.  Falls back to conservative heuristics for names
    not in the corpus.

    Examples::

        "Morales"  → "Morales"   (preserved — Census)
        "Walshes"  → "Walsh"     (strip 'es' after 'sh')
        "Smiths"   → "Smith"     (strip 's' after 'th')
        "Jones"    → "Jones"     (preserved — Census)
        "Williams" → "Williams"  (preserved — Census)
    """
    if not name or len(name) < 3:
        return name

    # Data-driven: check the preserved-family-names corpus
    if name in preserved_family_names:
        return name

    # --- Heuristic fallbacks (conservative) ---

    # Strip "es" after sibilants (very safe plurals)
    if name.endswith("shes") and len(name) > 4:
        return name[:-2]  # "Walshes" → "Walsh"
    if name.endswith("ches") and len(name) > 4:
        return name[:-2]  # "Marches" → "March"
    if name.endswith("xes") and len(name) > 3:
        return name[:-2]  # "Foxes" → "Fox"

    # Strip single 's' after specific consonant patterns (safe plurals)
    if (
        len(name) >= 4
        and name.endswith("s")
        and not name.endswith("ss")
        and name[-3:-1] in {"th", "wn", "ck", "rd", "rt", "nd", "nt"}
    ):
        return name[:-1]

    return name


def clean_family_name(name: str) -> str:
    """Clean a family name by removing common unwanted patterns and quotes.

    Applied after loading raw data from the database.  Handles prefixes
    ("The", "From:", "Sent by:"), the " Family" suffix, quote variants,
    and trailing punctuation, then strips obvious plurals.
    """
    if not name:
        return ""

    name = name.strip()

    # Remove common prefixes/suffixes
    name = name.split(":", 1)[-1].strip()  # Remove "Page 1:" etc.
    name = name.replace("The ", "").replace(" Family", "")
    name = name.replace("From: ", "").replace("Sent by: ", "")

    # Remove ALL double-quote variants (straight, curly, low-9, high-reversed-9)
    name = re.sub(r'["""\"\u201C\u201D\u201E\u201F]', "", name).strip()

    # Remove single quotes only at start/end (not in middle like O'Brien)
    name = re.sub(r"^[''\u2018\u2019]+", "", name).strip()
    name = re.sub(r"[''\u2018\u2019]+$", "", name).strip()

    # Final aggressive strip of remaining punctuation at the ends
    name = name.strip('.,!;:-\u2014\u2013"\'"\u2018\u2019\u201c\u201d')

    # Strip plural 's' or 'es' in obvious cases
    name = strip_plural_family_name(name)

    return name


def strip_family_name_punctuation(name: str) -> str:
    """Clean up an extracted name by stripping OCR punctuation artefacts."""
    name = name.strip().strip(".,!;:-—–\"'''")
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def clean_and_filter_family_names(names: list[str]) -> list[str]:
    """Apply unified cleaning and filtering to a list of names.

    Pipeline: ``clean_family_name()`` → ``sanitize_for_filename()``
    → filter against blocklist.

    This is the single entry point for cleaning raw name candidates.
    """
    from app.core.name_formatting import sanitize_for_filename

    cleaned = []
    for name in names:
        if not name:
            continue
        clean_name = clean_family_name(name)
        clean_name = sanitize_for_filename(clean_name)
        if clean_name and clean_name not in filtered_names:
            cleaned.append(clean_name)

    return cleaned
