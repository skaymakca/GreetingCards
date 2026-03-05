"""smashew/NameDatabases surname data.

Downloads surname files from the smashew/NameDatabases GitHub repo for
additional international coverage (Irish, Spanish, Basque, etc.).

Source: https://github.com/smashew/NameDatabases
"""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

from rich.console import Console

from scripts.build_family_name_db._unicode import normalize

# Raw GitHub URLs for surname files
SMASHEW_BASE = "https://raw.githubusercontent.com/smashew/NameDatabases/master/NamesDatabases/surnames"

SMASHEW_FILES = [
    "us.txt",
    "gb.txt",
    "ie.txt",  # Irish
    "es.txt",  # Spanish
    "fr.txt",  # French
    "de.txt",  # German
    "br.txt",  # Brazilian
    "it.txt",  # Italian
    "nl.txt",  # Dutch
    "in.txt",  # Indian
]


def _download_file(url: str, cache_path: Path) -> str:
    """Download a file, using cache if available."""
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    with urlopen(url) as resp:  # nosec B310
        content = resp.read().decode("utf-8")
    cache_path.write_text(content, encoding="utf-8")
    return content


def download_smashew_names(console: Console, cache_dir: Path) -> dict[str, str]:
    """Download and parse smashew/NameDatabases surname files.

    Returns dict mapping normalized key → display form (cleaned).
    """
    console.print("[bold]Downloading smashew/NameDatabases...[/bold]")
    smashew_cache = cache_dir / "smashew"
    smashew_cache.mkdir(parents=True, exist_ok=True)

    all_names: dict[str, str] = {}

    for filename in SMASHEW_FILES:
        url = f"{SMASHEW_BASE}/{filename}"
        cache_path = smashew_cache / filename

        try:
            content = _download_file(url, cache_path)
        except Exception as exc:
            console.print(f"  [yellow]Warning: Could not download {filename}: {exc}[/yellow]")
            continue

        added = 0
        lines = content.splitlines()
        for line in lines:
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            key = normalize(name)
            if not key or len(key) < 2:
                continue
            # Only set display form if not already set
            if key not in all_names:
                all_names[key] = name
                added += 1

        console.print(f"  {filename}: {len(lines):,} lines ({added:,} new)")

    console.print(f"  Total unique smashew names: {len(all_names):,}")
    return all_names
