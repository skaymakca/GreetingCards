"""Family name cleaning, formatting, and data lookup.

Public API — all names are self-descriptive when imported directly::

    from app.core.naming.family_name import clean_family_name
    from app.core.naming.family_name import strip_plural_family_name
    from app.core.naming.family_name import smart_title_case_family_name
    from app.core.naming.family_name import family_name_db
"""

from app.core.naming.family_name.cleaning import (
    clean_and_filter_family_names,
    clean_family_name,
    strip_family_name_punctuation,
    strip_plural_family_name,
)
from app.core.naming.family_name.data import (
    FamilyNameDatabase,
    FamilyNameEntry,
    FilteredNames,
    family_name_db,
    filtered_names,
)
from app.core.naming.family_name.formatting import smart_title_case_family_name

__all__ = [
    "FamilyNameDatabase",
    "FamilyNameEntry",
    "FilteredNames",
    "clean_and_filter_family_names",
    "clean_family_name",
    "family_name_db",
    "filtered_names",
    "smart_title_case_family_name",
    "strip_family_name_punctuation",
    "strip_plural_family_name",
]
