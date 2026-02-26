"""Data loading and normalized lookup for family name sets.

Provides three public containers:

- ``FamilyNameDatabase`` — master database of 213K+ family names with Census
  frequency data, proper display forms, and accepted alternate forms. Supports
  ``in`` checks, display lookup, rank/count queries, and display form matching.
- ``FilteredNames`` — generic words that should never become family-name
  candidates (e.g. "Family", "Holiday", "Snapfish").

The database is loaded from a gzip-compressed TSV file at
``content/data/family_name_database.tsv.gz`` with columns:
``normalized<TAB>display<TAB>rank<TAB>count<TAB>alternates``.
"""

import gzip
import logging
import re
import unicodedata
from dataclasses import dataclass

from app.core.paths import get_runtime_content_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FamilyNameEntry:
    """Single entry in the family name database."""

    display_form: str  # "O'Brien", "van der Berg"
    rank: int  # Census rank (0 = not in Census)
    count: int  # Census count (0 = not in Census)
    alternates: tuple[str, ...]  # Accepted alternate display forms (may be empty)


class FamilyNameDatabase:
    """Immutable family name database with normalized lookup.

    Provides:
    - ``name in db``           — normalized membership test
    - ``db.lookup(name)``      — FamilyNameEntry or None
    - ``db.display(name)``     — canonical display form, or None
    - ``db.rank(name)``        — Census rank (0 if not found/not in Census)
    - ``db.count(name)``       — Census count (0 if not found/not in Census)
    - ``db.alternates(name)``  — alternate display forms tuple
    - ``db.match_display(raw)``  — match against any display form (primary or alternate)
    - ``db.related_forms(raw)``  — other forms for a matched display form
    """

    def __init__(self, entries: dict[str, FamilyNameEntry]) -> None:
        self._entries: dict[str, FamilyNameEntry] = entries
        # Reverse index: lowercased display form → (original display form, normalized key)
        # Uses case-insensitive but punctuation-preserving keys so "Van-Dyke" and
        # "Van Dyke" remain distinct (unlike normalize() which strips both to "vandyke").
        self._display_index: dict[str, tuple[str, str]] = {}
        for norm_key, entry in entries.items():
            # Index the primary display form
            lc = entry.display_form.lower()
            if lc not in self._display_index:
                self._display_index[lc] = (entry.display_form, norm_key)
            # Index alternate display forms
            for alt in entry.alternates:
                alt_lc = alt.lower()
                if alt_lc not in self._display_index:
                    self._display_index[alt_lc] = (alt, norm_key)

    # Characters that NFKD decomposition doesn't handle.
    _UNICODE_SPECIAL: dict[str, str] = {"ß": "ss", "ø": "o", "æ": "ae", "ð": "d", "þ": "th", "đ": "d", "ł": "l"}

    @staticmethod
    def normalize(name: str) -> str:
        """Normalize for lookup: Unicode-fold to ASCII, lowercase, strip non-alpha.

        Uses NFKD decomposition (ñ→n, ü→u, é→e, etc.) plus a small manual map
        for characters that NFKD doesn't decompose (ß→ss, ø→o).
        """
        lowered = name.lower()
        for char, repl in FamilyNameDatabase._UNICODE_SPECIAL.items():
            if char in lowered:
                lowered = lowered.replace(char, repl)
        decomposed = unicodedata.normalize("NFKD", lowered)
        return re.sub(r"[^a-z]", "", decomposed)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return self.normalize(name) in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    def lookup(self, name: str) -> FamilyNameEntry | None:
        """Look up a name, returning its entry or None."""
        return self._entries.get(self.normalize(name))

    def display(self, name: str) -> str | None:
        """Return the canonical display form, or None if not in the database."""
        entry = self.lookup(name)
        return entry.display_form if entry else None

    def rank(self, name: str) -> int:
        """Return Census rank (0 if not found or not in Census)."""
        entry = self.lookup(name)
        return entry.rank if entry else 0

    def count(self, name: str) -> int:
        """Return Census count (0 if not found or not in Census)."""
        entry = self.lookup(name)
        return entry.count if entry else 0

    def alternates(self, name: str) -> tuple[str, ...]:
        """Return alternate display forms for a name (empty tuple if none)."""
        entry = self.lookup(name)
        return entry.alternates if entry else ()

    def match_display(self, raw_name: str) -> str | None:
        """Match a raw name against any known display form (primary or alternate).

        Returns the matched form as-is (preserving the original form), or None
        if no match is found. Uses case-insensitive matching that preserves
        punctuation (hyphens, apostrophes) so "Van-Dyke" and "Van Dyke" are
        distinct matches. This is used to bypass cleaning for known forms.
        """
        hit = self._display_index.get(raw_name.lower())
        if hit is None:
            return None
        return hit[0]  # The display form that matched

    def related_forms(self, raw_name: str) -> list[str]:
        """Return all OTHER display forms for a matched name.

        If ``raw_name`` matches a primary or alternate display form, returns
        all other forms (primary + alternates) excluding the matched one.
        Used to generate additional candidates.
        """
        hit = self._display_index.get(raw_name.lower())
        if hit is None:
            return []

        matched_form, norm_key = hit
        entry = self._entries.get(norm_key)
        if entry is None:
            return []

        # Collect all forms: primary + alternates
        all_forms = [entry.display_form, *entry.alternates]
        # Return all except the matched one
        return [f for f in all_forms if f != matched_form]

    @classmethod
    def load(cls) -> FamilyNameDatabase:
        """Load from the runtime gzip-compressed TSV file."""
        path = get_runtime_content_path("data/family_name_database.tsv.gz")
        if not path.exists():
            logger.warning("Family name database not found: %s", path)
            return cls({})

        entries: dict[str, FamilyNameEntry] = {}
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 4:
                    continue
                normalized = parts[0]
                display = parts[1]
                rank = int(parts[2])
                count_val = int(parts[3])
                alternates = tuple(parts[4].split("|")) if len(parts) > 4 and parts[4] else ()
                entries[normalized] = FamilyNameEntry(
                    display_form=display,
                    rank=rank,
                    count=count_val,
                    alternates=alternates,
                )

        logger.debug("Loaded %d family names from %s", len(entries), path)
        return cls(entries)


class FilteredNames:
    """Names that should never be treated as family name candidates.

    Uses the same normalization as ``FamilyNameDatabase`` so that
    ``"FAMILY"`` and ``"family"`` both match.
    """

    _ENTRIES = {
        # AI fallbacks
        "unknown",
        # Card printing services
        "snapfish",
        "shutterfly",
        "minted",
        # Generic card words (not surnames)
        "family",
        "holiday",
        "holidays",
        "greeting",
        "greetings",
        "card",
        "cards",
        # Holiday names
        "christmas",
        "hanukkah",
        "new year",
        "thanksgiving",
        "easter",
        "diwali",
        "eid",
        "kwanzaa",
        "chinese new year",
        "season's greetings",
        "valentine's day",
        "fourth of july",
    }

    def __init__(self) -> None:
        self._normalized: frozenset[str] = frozenset(FamilyNameDatabase.normalize(n) for n in self._ENTRIES)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return FamilyNameDatabase.normalize(name) in self._normalized

    def __len__(self) -> int:
        return len(self._normalized)


# Module-level singletons — loaded once at first import
family_name_db: FamilyNameDatabase = FamilyNameDatabase.load()
filtered_names: FilteredNames = FilteredNames()
