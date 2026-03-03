"""Extract properly-formatted family names from Faker locale providers.

Faker locales contain hand-curated name lists with correct capitalization,
apostrophes, and multi-word forms — exactly what we need for display forms.

Key locales:
- en_IE: Irish names (O'Brien, O'Connor, McCarthy)
- nl_NL: Dutch names (van der Berg, de Vries)
- es_MX: Spanish names (De La Cruz, Garcia)
- fr_FR: French names (de la Fontaine)
- pt_BR: Portuguese names (da Silva, dos Santos)
- en_GB: British names (MacDonald, McIntyre)
- de_DE: German names (von Braun)
"""

from __future__ import annotations

from rich.console import Console

from scripts.build_family_name_db._unicode import normalize

# Locales to extract, in priority order (earlier = higher priority for display form)
FAKER_LOCALES = [
    "en_IE",
    "nl_NL",
    "es_MX",
    "fr_FR",
    "pt_BR",
    "en_GB",
    "de_DE",
    "en_US",
]


def _extract_locale_names(locale: str) -> list[str]:
    """Extract last_names from a single Faker locale provider."""
    try:
        from faker.providers.person import Provider as BaseProvider

        # Dynamic import of locale-specific provider
        module_path = f"faker.providers.person.{locale}"
        import importlib

        module = importlib.import_module(module_path)
        provider_cls = module.Provider

        # last_names can be a tuple, list, or dict (dict has weights)
        last_names: tuple[str, ...] | list[str] | dict[str, object] | None = getattr(provider_cls, "last_names", None)
        if last_names is None:
            # Some locales use prefixes/suffixes instead — check base
            last_names = getattr(BaseProvider, "last_names", None)
        if last_names is None:
            return []

        if isinstance(last_names, dict):
            return list(last_names.keys())
        return list(last_names)
    except ImportError, AttributeError:
        return []


def extract_faker_names(console: Console) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Extract family names from Faker locale providers.

    Returns:
        - Primary dict: normalized key → display form (highest-priority locale wins).
        - All forms dict: normalized key → list of ALL distinct display forms from
          all locales (including the winner). Used by the merger to populate alternates
          for Unicode/ASCII variants (e.g., nl_NL "Muller" + de_DE "Müller").
    """
    console.print("[bold]Extracting Faker locale names...[/bold]")
    all_names: dict[str, str] = {}
    all_forms: dict[str, list[str]] = {}

    for locale in FAKER_LOCALES:
        names = _extract_locale_names(locale)
        added = 0
        for name in names:
            name = name.strip()
            if not name:
                continue
            key = normalize(name)
            if not key:
                continue
            # Only set display form if not already set by a higher-priority locale
            if key not in all_names:
                all_names[key] = name
                added += 1
            # Collect all distinct forms for alternate generation
            forms = all_forms.setdefault(key, [])
            if name not in forms:
                forms.append(name)
        console.print(f"  {locale}: {len(names):,} names ({added:,} new)")

    console.print(f"  Total unique Faker names: {len(all_names):,}")
    return all_names, all_forms
