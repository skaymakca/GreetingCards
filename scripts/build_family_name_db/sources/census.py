"""US Census Bureau 2010 surname data.

Downloads and parses the Census surname frequency file (~162K names with rank
and count data).

Source: https://www2.census.gov/topics/genealogy/2010surnames/names.zip
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from rich.console import Console

from scripts.build_family_name_db._unicode import normalize

CENSUS_URL = "https://www2.census.gov/topics/genealogy/2010surnames/names.zip"
CENSUS_CSV_NAME = "Names_2010Census.csv"


@dataclass(frozen=True, slots=True)
class CensusEntry:
    """Single Census surname entry."""

    name: str  # Original ALL-CAPS name from Census
    rank: int
    count: int


def download_census(console: Console, cache_dir: Path) -> dict[str, CensusEntry]:
    """Download and parse Census 2010 surname data.

    Returns dict mapping normalized key → CensusEntry.
    """
    zip_path = cache_dir / "names.zip"

    if not zip_path.exists():
        console.print("[bold]Downloading Census 2010 surname data...[/bold]")
        with urlopen(CENSUS_URL) as resp:  # nosec B310
            zip_path.write_bytes(resp.read())
        console.print(f"  Downloaded {zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        console.print("[dim]Using cached Census data[/dim]")

    console.print("Parsing Census CSV...")
    entries: dict[str, CensusEntry] = {}

    with zipfile.ZipFile(zip_path) as zf, zf.open(CENSUS_CSV_NAME) as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
        for row in reader:
            name = row["name"].strip()
            if not name:
                continue
            rank_str = row.get("rank", "0")
            count_str = row.get("count", "0")
            # Some entries have "(S)" for suppressed values
            rank = int(rank_str) if rank_str.isdigit() else 0
            count = int(count_str) if count_str.isdigit() else 0
            key = normalize(name)
            if key:
                entries[key] = CensusEntry(name=name, rank=rank, count=count)

    console.print(f"  Parsed {len(entries):,} Census surnames")
    return entries
