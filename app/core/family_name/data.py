"""Data loading and normalized lookup for family name sets.

Provides two container classes with ``in`` support:

- ``PreservedFamilyNames`` — Census-sourced names ending in 's' that should
  never be de-pluralised (e.g. "Morales", "Torres", "Jones").
- ``FilteredNames`` — generic words that should never become family-name
  candidates (e.g. "Family", "Holiday", "Snapfish").

Both use the same normalization (lowercase, strip all non-alpha) so the lookup
is case-, space-, and punctuation-insensitive while the original name is
preserved at the call site.
"""

import logging
import re
from collections.abc import Iterable

from app.core.paths import get_runtime_content_path

logger = logging.getLogger(__name__)


class PreservedFamilyNames:
    """Immutable set of family names with normalized lookup.

    Normalization (lowercase, strip all non-alpha) is applied both when
    loading names from the data file and when checking membership, so
    ``"O'Brien"``, ``"OBRIEN"``, and ``"o brien"`` all match the same entry.

    Usage::

        preserved = PreservedFamilyNames.load()
        if "Morales" in preserved:
            ...  # True — preserved, don't strip the 's'
    """

    def __init__(self, names: Iterable[str]) -> None:
        self._normalized: frozenset[str] = frozenset(self.normalize(n) for n in names if n.strip())

    @staticmethod
    def normalize(name: str) -> str:
        """Normalize for lookup: lowercase, strip all non-alpha."""
        return re.sub(r"[^a-z]", "", name.lower())

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return self.normalize(name) in self._normalized

    def __len__(self) -> int:
        return len(self._normalized)

    def __bool__(self) -> bool:
        return bool(self._normalized)

    @classmethod
    def load(cls) -> PreservedFamilyNames:
        """Load from the runtime data file. Empty set if file missing."""
        path = get_runtime_content_path("data/preserved_family_names.txt")
        if not path.exists():
            logger.warning("Preserved family names file not found: %s", path)
            return cls([])
        return cls(path.read_text().splitlines())


class FilteredNames:
    """Names that should never be treated as family name candidates.

    Uses the same normalization as ``PreservedFamilyNames`` so that
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
        self._normalized: frozenset[str] = frozenset(PreservedFamilyNames.normalize(n) for n in self._ENTRIES)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return PreservedFamilyNames.normalize(name) in self._normalized

    def __len__(self) -> int:
        return len(self._normalized)


# Module-level singletons — loaded once at first import
preserved_family_names: PreservedFamilyNames = PreservedFamilyNames.load()
filtered_names: FilteredNames = FilteredNames()
