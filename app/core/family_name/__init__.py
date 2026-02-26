"""Family name cleaning, formatting, and data lookup.

Public API — all names are self-descriptive when imported directly::

    from app.core.family_name import clean_family_name
    from app.core.family_name import strip_plural_family_name
    from app.core.family_name import smart_title_case_family_name
    from app.core.family_name import preserved_family_names
"""

from app.core.family_name.cleaning import (
    clean_and_filter_family_names,
    clean_family_name,
    strip_family_name_punctuation,
    strip_plural_family_name,
)
from app.core.family_name.data import (
    FilteredNames,
    PreservedFamilyNames,
    filtered_names,
    preserved_family_names,
)
from app.core.family_name.formatting import smart_title_case_family_name

__all__ = [
    "FilteredNames",
    "PreservedFamilyNames",
    "clean_and_filter_family_names",
    "clean_family_name",
    "filtered_names",
    "preserved_family_names",
    "smart_title_case_family_name",
    "strip_family_name_punctuation",
    "strip_plural_family_name",
]
