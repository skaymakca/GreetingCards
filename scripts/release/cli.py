"""Release automation for Greeting Cards.

Subcommands for changelog extraction, checksum generation, and GitHub Release
management via the gh CLI.

Usage:
    uv run python -m scripts.release changelog   # Extract release notes
    uv run python -m scripts.release checksum    # Generate SHA256 checksum
    uv run python -m scripts.release draft       # Create draft GitHub release
    uv run python -m scripts.release publish     # Publish the latest draft
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import subprocess

from scripts.helpers import PROJECT_ROOT, dmg_path, read_version

_CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
_REPO = "skaymakca/GreetingCards"


def _checksum_path(version: str) -> pathlib.Path:
    return PROJECT_ROOT / "dist" / f"Greeting-Cards-{version}.sha256"


def _release_notes_path() -> pathlib.Path:
    out = PROJECT_ROOT / "_build" / "release"
    out.mkdir(parents=True, exist_ok=True)
    return out / "release-notes.md"


def extract_changelog(version: str, changelog_path: pathlib.Path | None = None) -> str:
    """Extract release notes for the given version from CHANGELOG.md.

    Finds the section starting with `## {version}` and extracts all content
    until the next `## ` heading. Returns the body text without the version
    heading itself (since GitHub Release title already contains the version).
    """
    path = changelog_path or _CHANGELOG
    text = path.read_text(encoding="utf-8")

    # Find the heading for this version
    pattern = rf"^## {re.escape(version)}\b.*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"Version {version} not found in {path}")

    # Extract body from after the heading to the next ## or end of file
    start = match.end()
    next_heading = re.search(r"^## ", text[start:], re.MULTILINE)
    if next_heading:
        body = text[start : start + next_heading.start()]
    else:
        body = text[start:]

    return body.strip() + "\n"


def generate_checksum(version: str) -> pathlib.Path:
    """Generate a SHA256 checksum file for the DMG."""
    dmg = dmg_path(version)
    if not dmg.exists():
        raise FileNotFoundError(f"DMG not found: {dmg}")

    sha256 = hashlib.sha256()
    with open(dmg, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    checksum_file = _checksum_path(version)
    checksum_file.write_text(f"{sha256.hexdigest()}  {dmg.name}\n", encoding="utf-8")
    print(f"Checksum: {checksum_file}")
    return checksum_file


def build_draft_command(version: str, notes_file: pathlib.Path, dmg: pathlib.Path, checksum: pathlib.Path) -> list[str]:
    """Build the gh release create command for a draft release."""
    return [
        "gh",
        "release",
        "create",
        f"v{version}",
        "--repo",
        _REPO,
        "--title",
        f"Greeting Cards {version}",
        "--notes-file",
        str(notes_file),
        "--draft",
        str(dmg),
        str(checksum),
    ]


def cmd_changelog(version: str) -> None:
    """Extract release notes and write to _build/release/release-notes.md."""
    notes = extract_changelog(version)
    out = _release_notes_path()
    out.write_text(notes, encoding="utf-8")
    print(f"Release notes: {out}")


def cmd_checksum(version: str) -> None:
    """Generate SHA256 checksum for the DMG."""
    generate_checksum(version)


def cmd_draft(version: str) -> None:
    """Create a draft GitHub release with the DMG and checksum."""
    notes_file = _release_notes_path()
    if not notes_file.exists():
        print("Extracting release notes first …")
        cmd_changelog(version)

    dmg = dmg_path(version)
    checksum = _checksum_path(version)

    if not dmg.exists():
        raise FileNotFoundError(f"DMG not found: {dmg}\n  Run 'make release' first.")
    if not checksum.exists():
        raise FileNotFoundError(f"Checksum not found: {checksum}\n  Run 'make release' first.")

    cmd = build_draft_command(version, notes_file, dmg, checksum)
    print(f"Creating draft release v{version} …")
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Draft release v{version} created.")


def cmd_publish(version: str) -> None:
    """Publish the latest draft release."""
    cmd = [
        "gh",
        "release",
        "edit",
        f"v{version}",
        "--repo",
        _REPO,
        "--draft=false",
    ]
    print(f"Publishing release v{version} …")
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Release v{version} published.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Release automation for Greeting Cards.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("changelog", help="Extract release notes from CHANGELOG.md")
    subparsers.add_parser("checksum", help="Generate SHA256 checksum for the DMG")
    subparsers.add_parser("draft", help="Create a draft GitHub release")
    subparsers.add_parser("publish", help="Publish the latest draft release")
    args = parser.parse_args()

    version = read_version()

    commands = {
        "changelog": cmd_changelog,
        "checksum": cmd_checksum,
        "draft": cmd_draft,
        "publish": cmd_publish,
    }
    commands[args.command](version)
