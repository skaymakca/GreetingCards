"""Merge data sources and write the master family name database TSV."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

from rich.console import Console

from scripts.build_family_name_db._unicode import UNICODE_SPECIAL as _UNICODE_SPECIAL
from scripts.build_family_name_db._unicode import normalize
from scripts.build_family_name_db.sources.census import CensusEntry

# Row format: (normalized, display, rank, count, alternates)
type MergedRow = tuple[str, str, int, int, list[str]]


def ascii_fold(name: str) -> str:
    """Fold a display form to ASCII, preserving spaces/punctuation.

    Used to generate ASCII alternates: Müller→Muller, Núñez→Nunez, Weiß→Weiss.
    Returns the original if it's already pure ASCII.
    """
    result: list[str] = []
    for char in name:
        lc = char.lower()
        if lc in _UNICODE_SPECIAL:
            repl = _UNICODE_SPECIAL[lc]
            # Preserve case of first letter
            if char.isupper() and repl:
                repl = repl[0].upper() + repl[1:]
            result.append(repl)
        elif ord(char) > 127:
            decomposed = unicodedata.normalize("NFKD", char)
            # Keep only the base character (strip combining marks)
            base = "".join(c for c in decomposed if not unicodedata.combining(c))
            result.append(base if base else char)
        else:
            result.append(char)
    return "".join(result)


def _heuristic_display(raw_name: str) -> str:
    """Generate a heuristic display form from a raw name.

    Uses the heuristic formatting functions directly (not the DB-first
    smart_title_case_family_name wrapper) to avoid a chicken-and-egg
    dependency: the build script *generates* the DB, so it can't rely
    on the DB for formatting during the build.
    """
    # noinspection PyProtectedMember
    from app.core.naming.family_name.formatting import _format_particle, _format_word_with_structure

    words = raw_name.split()
    result = []
    for i, word in enumerate(words):
        particle = _format_particle(word, is_first_word=(i == 0))
        if particle:
            result.append(particle)
        else:
            result.append(_format_word_with_structure(word))
    return " ".join(result)


def merge_sources(
    console: Console,
    census: dict[str, CensusEntry],
    faker: dict[str, str],
    smashew: dict[str, str],
    *,
    faker_all_forms: dict[str, list[str]] | None = None,
) -> list[MergedRow]:
    """Merge all sources into a sorted list of (normalized, display, rank, count, alternates).

    Display form priority:
    1. Faker locales (highest — hand-curated with proper formatting)
    2. smashew/NameDatabases (good international coverage)
    3. Census heuristic (smart_title_case_family_name as fallback)

    Non-winning display forms become alternates (if they differ from the winner).
    Rank/count always from Census (0 for non-Census names).
    """
    console.print("[bold]Merging sources...[/bold]")

    # Collect all unique normalized keys
    all_keys: set[str] = set()
    all_keys.update(census.keys())
    all_keys.update(faker.keys())
    all_keys.update(smashew.keys())

    console.print(f"  Census keys: {len(census):,}")
    console.print(f"  Faker keys:  {len(faker):,}")
    console.print(f"  Smashew keys: {len(smashew):,}")
    console.print(f"  Union keys:  {len(all_keys):,}")

    rows: list[MergedRow] = []
    faker_wins = 0
    smashew_wins = 0
    heuristic_wins = 0
    total_alternates = 0

    for key in all_keys:
        # Rank/count from Census
        census_entry = census.get(key)
        rank = census_entry.rank if census_entry else 0
        count = census_entry.count if census_entry else 0

        # Collect all candidate display forms from each source
        candidates: list[str] = []
        if key in faker:
            candidates.append(faker[key])
        if key in smashew:
            candidates.append(_heuristic_display(smashew[key]))
        if census_entry:
            candidates.append(_heuristic_display(census_entry.name.title()))

        if not candidates:
            continue

        # Winner is the first candidate (priority order: faker > smashew > census)
        display = candidates[0]
        if key in faker:
            faker_wins += 1
        elif key in smashew:
            smashew_wins += 1
        else:
            heuristic_wins += 1

        # Non-winning forms become alternates (deduplicated, excluding the winner)
        alternates: list[str] = []
        seen = {display}
        for candidate in candidates[1:]:
            if candidate not in seen:
                alternates.append(candidate)
                seen.add(candidate)

        # Add any extra Faker display forms from other locales (e.g., de_DE "Müller"
        # when nl_NL "Muller" won). These are Unicode/ASCII variants of the same name.
        if faker_all_forms and key in faker_all_forms:
            for form in faker_all_forms[key]:
                if form not in seen:
                    alternates.append(form)
                    seen.add(form)

        # Auto-generate ASCII alternate if display has Unicode letters
        ascii_display = ascii_fold(display)
        if ascii_display != display and ascii_display not in seen:
            alternates.append(ascii_display)
            seen.add(ascii_display)

        total_alternates += len(alternates)
        rows.append((key, display, rank, count, alternates))

    console.print(
        f"  Display form sources: Faker={faker_wins:,}, smashew={smashew_wins:,}, heuristic={heuristic_wins:,}"
    )
    console.print(f"  Entries with alternates: {sum(1 for r in rows if r[4]):,} ({total_alternates:,} total)")

    # Sort by normalized key for binary search / deterministic output
    rows.sort(key=lambda r: r[0])
    console.print(f"  Total merged entries: {len(rows):,}")

    return rows


def apply_overrides(console: Console, rows: list[MergedRow], override_path: Path) -> list[MergedRow]:
    """Apply manual overrides from a TSV file.

    Overrides can replace existing entries or add new ones.
    Same format as the main TSV: normalized, display, rank, count, alternates (optional).
    """
    if not override_path.exists():
        console.print("[dim]No override file found, skipping[/dim]")
        return rows

    overrides: dict[str, MergedRow] = {}
    with override_path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            norm_key = parts[0]
            display = parts[1]
            rank = int(parts[2]) if parts[2] else 0
            count_val = int(parts[3]) if parts[3] else 0
            alternates = parts[4].split("|") if len(parts) > 4 and parts[4] else []
            overrides[norm_key] = (norm_key, display, rank, count_val, alternates)

    if not overrides:
        console.print("[dim]Override file is empty, skipping[/dim]")
        return rows

    # Build a lookup for existing rows
    row_index: dict[str, int] = {r[0]: i for i, r in enumerate(rows)}

    replaced = 0
    added = 0
    for key, override in overrides.items():
        if key in row_index:
            idx = row_index[key]
            existing = rows[idx]
            # Override display form; keep existing rank/count if override is 0
            new_rank = override[2] if override[2] else existing[2]
            new_count = override[3] if override[3] else existing[3]
            rows[idx] = (key, override[1], new_rank, new_count, override[4])
            replaced += 1
        else:
            rows.append(override)
            added += 1

    # Re-sort if we added new entries
    if added:
        rows.sort(key=lambda r: r[0])

    console.print(f"  Overrides applied: {replaced:,} replaced, {added:,} added")
    return rows


def write_tsv(console: Console, rows: list[MergedRow], output_path: Path) -> None:
    """Write the merged data to a TSV file."""
    console.print(f"[bold]Writing TSV to {output_path}...[/bold]")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        f.write("# normalized\tdisplay\trank\tcount\talternates\n")
        for normalized, display, rank, count, alternates in rows:
            alts_str = "|".join(alternates) if alternates else ""
            f.write(f"{normalized}\t{display}\t{rank}\t{count}\t{alts_str}\n")

    size_mb = output_path.stat().st_size / 1024 / 1024
    console.print(f"  Written {len(rows):,} entries ({size_mb:.1f} MB)")

    # Quick sanity checks
    _sanity_check(console, rows)


def _sanity_check(console: Console, rows: list[MergedRow]) -> None:
    """Run sanity checks on the merged data."""
    lookup = {r[0]: r for r in rows}
    errors = []

    # Must-have names
    checks = {
        "smith": "Smith",
        "jones": "Jones",
        "williams": "Williams",
        "obrien": "O'Brien",
        "mcdonald": "McDonald",
        "macdonald": "MacDonald",
    }

    for key, expected_display in checks.items():
        if key not in lookup:
            errors.append(f"Missing expected name: {key}")
        elif lookup[key][1] != expected_display:
            errors.append(f"Display mismatch for {key}: got '{lookup[key][1]}', expected '{expected_display}'")

    # Smith should be rank 1
    if "smith" in lookup and lookup["smith"][2] != 1:
        errors.append(f"Smith rank should be 1, got {lookup['smith'][2]}")

    if errors:
        for err in errors:
            console.print(f"  [red]ERROR: {err}[/red]")
        sys.exit(1)
    else:
        console.print("  [green]Sanity checks passed[/green]")
