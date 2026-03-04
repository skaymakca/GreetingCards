"""Release automation for Greeting Cards.

Subcommands for changelog extraction, checksum generation, and GitHub Release
management via the gh CLI.

Usage:
    uv run python -m scripts.release changelog        # Extract release notes
    uv run python -m scripts.release checksum         # Generate SHA256 checksum
    uv run python -m scripts.release draft            # Create draft GitHub release
    uv run python -m scripts.release publish          # Publish the latest draft
    uv run python -m scripts.release --dry-run draft  # Print commands only
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import subprocess
import sys

from scripts.helpers import PROJECT_ROOT, dmg_path, read_version

_CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
_REPO = "skaymakca/GreetingCards"


class ReleaseError(ValueError):
    """User-facing error in the release pipeline (clean output, no traceback)."""


def _run(cmd: list[str], *, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command, printing it first. In dry-run mode, skip execution."""
    print(f"  {'[dry-run] ' if dry_run else ''}{' '.join(cmd)}")
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return subprocess.run(cmd, check=True, text=True)


def _checksum_path(version: str) -> pathlib.Path:
    return PROJECT_ROOT / "dist" / f"Greeting-Cards-{version}.sha256"


def _release_notes_path() -> pathlib.Path:
    out = PROJECT_ROOT / "dist"
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
        available = re.findall(r"^## (\S+)", text, re.MULTILINE)
        raise ReleaseError(f"Version {version} not found in {path}. Found: {', '.join(available)}")

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


def _preflight_tag_check(version: str, *, dry_run: bool = False) -> None:
    """Validate that the git tag exists locally, remotely, and points to HEAD.

    Raises ReleaseError if the local or remote tag is missing.
    For a tag-on-HEAD mismatch, prompts interactively (or warns in dry-run mode).
    """
    tag = f"v{version}"
    print(f"Pre-flight tag check for {tag}:")

    # 1. Local tag exists
    result = subprocess.run(
        ["git", "tag", "--list", tag],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        print(f"  \u2717 Local tag {tag} does not exist")
        raise ReleaseError(f"Local tag {tag} not found. Run: make tag")
    print(f"  \u2713 Local tag {tag} exists")

    # 2. Remote tag exists
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", tag],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        print(f"  \u2717 Remote tag {tag} does not exist")
        raise ReleaseError(f"Remote tag {tag} not found. Run: make tag-push")
    print(f"  \u2713 Remote tag {tag} exists")

    # 3. Tag matches HEAD
    tag_sha = subprocess.run(
        ["git", "rev-parse", f"{tag}^{{commit}}"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    if tag_sha == head_sha:
        print("  \u2713 Tag is on current HEAD")
    else:
        tag_short = tag_sha[:10]
        head_short = head_sha[:10]
        print(f"  \u26a0 Tag {tag} ({tag_short}) is not on HEAD ({head_short})")
        if dry_run:
            print("  [dry-run] Skipping interactive prompt")
            return
        if not sys.stdin.isatty():
            raise ReleaseError(f"Tag {tag} is not on HEAD (non-interactive, aborting)")
        answer = input("  Continue anyway? [y/N] ").strip().lower()
        if answer != "y":
            raise ReleaseError(f"Aborted: tag {tag} is not on HEAD")
    print()


def cmd_changelog(version: str) -> None:
    """Extract release notes and write to dist/release-notes.md."""
    notes = extract_changelog(version)
    if not notes.strip():
        raise ReleaseError(f"Release notes for {version} are empty in CHANGELOG.md")
    out = _release_notes_path()
    out.write_text(notes, encoding="utf-8")
    print(f"Release notes: {out}")


def cmd_checksum(version: str) -> None:
    """Generate SHA256 checksum for the DMG."""
    generate_checksum(version)


def cmd_draft(version: str, *, dry_run: bool = False) -> None:
    """Create a draft GitHub release with the DMG and checksum."""
    _preflight_tag_check(version, dry_run=dry_run)
    notes_file = _release_notes_path()
    if not notes_file.exists():
        print("Extracting release notes first …")
        cmd_changelog(version)

    dmg = dmg_path(version)
    checksum = _checksum_path(version)

    if not dmg.exists():
        raise FileNotFoundError(f"DMG not found: {dmg}\n  Run the earlier pipeline steps first.")
    if not checksum.exists():
        raise FileNotFoundError(f"Checksum not found: {checksum}\n  Run the earlier pipeline steps first.")

    cmd = build_draft_command(version, notes_file, dmg, checksum)
    print(f"Creating draft release v{version} …")
    try:
        _run(cmd, dry_run=dry_run)
    except subprocess.CalledProcessError as exc:
        print(f"gh exited with status {exc.returncode}.")
        print("Check that 'gh' is installed and authenticated (gh auth status).")
        raise SystemExit(1) from None
    print(f"Draft release v{version} created.")


def cmd_publish(version: str, *, dry_run: bool = False) -> None:
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
    try:
        _run(cmd, dry_run=dry_run)
    except subprocess.CalledProcessError as exc:
        print(f"gh exited with status {exc.returncode}.")
        print("Check that 'gh' is installed and authenticated (gh auth status).")
        raise SystemExit(1) from None
    print(f"Release v{version} published.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Release automation for Greeting Cards.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("changelog", help="Extract release notes from CHANGELOG.md")
    subparsers.add_parser("checksum", help="Generate SHA256 checksum for the DMG")
    subparsers.add_parser("draft", help="Create a draft GitHub release")
    subparsers.add_parser("publish", help="Publish the latest draft release")
    args = parser.parse_args()

    version = read_version()

    if args.command in ("draft", "publish"):
        {"draft": cmd_draft, "publish": cmd_publish}[args.command](version, dry_run=args.dry_run)
    else:
        {"changelog": cmd_changelog, "checksum": cmd_checksum}[args.command](version)
