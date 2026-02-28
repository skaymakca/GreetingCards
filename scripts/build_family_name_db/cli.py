"""CLI and orchestration for the family name database build."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from rich.console import Console

from scripts.build_family_name_db.merger import apply_overrides, merge_sources, write_tsv
from scripts.build_family_name_db.sources.census import download_census
from scripts.build_family_name_db.sources.faker_names import extract_faker_names
from scripts.build_family_name_db.sources.smashew import download_smashew_names

# Default output path for the generated TSV
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent.parent / "content" / "data" / "family_name_database.tsv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_family_name_db",
        description="Build the master family name database from Census, Faker, and smashew sources.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output TSV path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Cache directory for downloaded files (default: system temp)",
    )
    parser.add_argument(
        "--no-smashew",
        action="store_true",
        help="Skip smashew/NameDatabases download (faster, fewer names)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    # Cache directory for downloads
    if args.cache_dir:
        cache_dir = args.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
    else:
        cache_dir = Path(tempfile.mkdtemp(prefix="family_name_db_"))

    console.print(f"[dim]Cache directory: {cache_dir}[/dim]")
    console.print()

    # 1. Download and parse Census data
    census = download_census(console, cache_dir)
    console.print()

    # 2. Extract Faker locale names
    faker, faker_all_forms = extract_faker_names(console)
    console.print()

    # 3. Download smashew names (optional)
    if args.no_smashew:
        smashew: dict[str, str] = {}
        console.print("[dim]Skipping smashew download (--no-smashew)[/dim]")
    else:
        smashew = download_smashew_names(console, cache_dir)
    console.print()

    # 4. Merge sources
    rows = merge_sources(console, census, faker, smashew, faker_all_forms=faker_all_forms)
    console.print()

    # 5. Apply manual overrides
    override_path = args.output.parent / "family_name_overrides.tsv"
    rows = apply_overrides(console, rows, override_path)
    console.print()

    # 6. Write TSV
    write_tsv(console, rows, args.output)

    console.print()
    console.print("[bold green]Done![/bold green] Database written to:")
    console.print(f"  TSV: {args.output}")
    console.print("[dim]  Run 'make content' to compress and copy to runtime_content[/dim]")
