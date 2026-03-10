"""Appcast generation and publishing for Sparkle auto-updates.

Generates a Sparkle-compatible appcast.xml from the signed DMG, and pushes
it to the gh-pages branch for hosting via GitHub Pages.

Usage:
    uv run python -m scripts.appcast generate       # Sign DMG + generate appcast.xml
    uv run python -m scripts.appcast push           # Push appcast.xml to gh-pages
    uv run python -m scripts.appcast --dry-run generate  # Print commands only
"""

from __future__ import annotations

import argparse
import subprocess

# isort: split
# noinspection PyPep8NamingInspection,PyPep8Naming
import xml.etree.ElementTree as ET  # nosec B405
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

from scripts.helpers import PROJECT_ROOT, build_number_path, dmg_path, read_version, run_command

_REPO = "skaymakca/GreetingCards"
_SPARKLE_BIN = PROJECT_ROOT / "packaging" / "sparkle-bin"
_SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"
_APPCAST_OUT = PROJECT_ROOT / "dist" / "appcast.xml"


class AppcastError(ValueError):
    """User-facing error in the appcast pipeline."""


def sign_dmg(dmg: Path, *, dry_run: bool = False) -> tuple[str, int]:
    """Sign the DMG with Sparkle's sign_update tool.

    Returns (edSignature, fileLength).
    """
    sign_tool = _SPARKLE_BIN / "sign_update"
    if not sign_tool.exists():
        raise FileNotFoundError(f"sign_update not found: {sign_tool}\n  Run 'make sparkle' first.")

    result = run_command([str(sign_tool), str(dmg)], dry_run=dry_run, capture=True)

    if dry_run:
        return "DRY_RUN_SIGNATURE", 0

    # sign_update outputs: sparkle:edSignature="..." length="..."
    output = result.stdout.strip()
    sig = ""
    length = 0
    for part in output.split():
        if part.startswith('sparkle:edSignature="'):
            sig = part.split('"')[1]
        elif part.startswith('length="'):
            length = int(part.split('"')[1])

    if not sig:
        raise AppcastError(f"Failed to parse sign_update output: {output}")

    return sig, length


def _load_existing_appcast() -> ET.Element | None:
    """Try to load existing appcast from gh-pages branch."""
    # noinspection PyBroadException
    try:
        result = subprocess.run(
            ["git", "show", "gh-pages:appcast.xml"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            return ET.fromstring(result.stdout)  # nosec B314
    except Exception:
        pass  # nosec B110
    return None


def _get_release_notes() -> str:
    """Read release notes from dist/release-notes.md if available."""
    notes_path = PROJECT_ROOT / "dist" / "release-notes.md"
    if notes_path.exists():
        return notes_path.read_text(encoding="utf-8").strip()
    return ""


def generate_appcast_xml(
    version: str,
    build_number: str,
    signature: str,
    length: int,
    dmg_filename: str,
) -> str:
    """Generate a well-formed appcast XML string.

    Prepends a new item to any existing appcast from the gh-pages branch.
    """
    # Register Sparkle namespace before parsing
    ET.register_namespace("sparkle", _SPARKLE_NS)

    existing = _load_existing_appcast()

    if existing is not None:
        root = existing
        channel = root.find("channel")
    else:
        root = ET.Element("rss", {"version": "2.0"})
        channel = ET.SubElement(root, "channel")
        title = ET.SubElement(channel, "title")
        title.text = "Greeting Cards"

    if channel is None:
        channel = ET.SubElement(root, "channel")
        title = ET.SubElement(channel, "title")
        title.text = "Greeting Cards"

    # Check for duplicate version
    for existing_item in channel.findall("item"):
        existing_short = existing_item.find(f"{{{_SPARKLE_NS}}}shortVersionString")
        if existing_short is not None and existing_short.text == version:
            raise AppcastError(
                f"Appcast already contains version {version}. Remove the existing entry before regenerating."
            )

    # Build new item
    item = ET.Element("item")
    item_title = ET.SubElement(item, "title")
    item_title.text = f"Version {version}"

    sparkle_version = ET.SubElement(item, f"{{{_SPARKLE_NS}}}version")
    sparkle_version.text = build_number

    short_version = ET.SubElement(item, f"{{{_SPARKLE_NS}}}shortVersionString")
    short_version.text = version

    min_sys = ET.SubElement(item, f"{{{_SPARKLE_NS}}}minimumSystemVersion")
    min_sys.text = "13.0"

    pub_date = ET.SubElement(item, "pubDate")
    pub_date.text = format_datetime(datetime.now(UTC))

    # Release notes (description)
    notes = _get_release_notes()
    if notes:
        description = ET.SubElement(item, "description")
        description.text = notes

    dmg_url = f"https://github.com/{_REPO}/releases/download/v{version}/{dmg_filename}"
    ET.SubElement(
        item,
        "enclosure",
        {
            "url": dmg_url,
            "sparkle:edSignature": signature,
            "length": str(length),
            "type": "application/octet-stream",
        },
    )

    # Insert new item at the top of the channel (after title)
    title_elem = channel.find("title")
    if title_elem is not None:  # noqa: SIM108
        idx = list(channel).index(title_elem) + 1
    else:
        idx = 0
    channel.insert(idx, item)

    # Generate XML string
    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return xml_str + "\n"


def cmd_generate(version: str, *, dry_run: bool = False) -> None:
    """Sign the DMG and generate/update appcast.xml."""
    dmg = dmg_path(version)
    if not dmg.exists():
        raise FileNotFoundError(f"DMG not found: {dmg}\n  Run the earlier pipeline steps first.")

    print(f"Signing DMG for Sparkle: {dmg.name}")
    signature, length = sign_dmg(dmg, dry_run=dry_run)

    if not dry_run and length == 0:
        # Use file size directly if sign_update didn't report it
        length = dmg.stat().st_size

    sidecar = build_number_path(version)
    if not sidecar.exists():
        raise AppcastError(
            f"Build number sidecar not found: {sidecar}\n  Run the DMG step first (it writes the sidecar)."
        )
    build_number = sidecar.read_text(encoding="utf-8").strip()
    if not build_number:
        raise AppcastError(f"Build number sidecar is empty: {sidecar}")

    print(f"Generating appcast.xml (v{version}, build {build_number})")
    xml = generate_appcast_xml(version, build_number, signature, length, dmg.name)

    if dry_run:
        print("[dry-run] Would write appcast.xml:")
        for line in xml.splitlines()[:10]:
            print(f"  {line}")
        if xml.count("\n") > 10:
            print("  ...")
        return

    _APPCAST_OUT.parent.mkdir(parents=True, exist_ok=True)
    _APPCAST_OUT.write_text(xml, encoding="utf-8")
    print(f"Appcast written: {_APPCAST_OUT}")


def cmd_push(*, dry_run: bool = False) -> None:
    """Push appcast.xml to the gh-pages branch on GitHub."""
    if not _APPCAST_OUT.exists():
        raise FileNotFoundError(f"Appcast not found: {_APPCAST_OUT}\n  Run 'generate' first.")

    appcast_content = _APPCAST_OUT.read_text(encoding="utf-8")

    # Use gh-pages deploy via git operations
    print("Pushing appcast.xml to gh-pages branch...")

    # Create a temporary worktree for gh-pages
    tmp_dir = PROJECT_ROOT / "_build" / "gh-pages-deploy"

    if not dry_run:
        # Check if gh-pages branch exists
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", "gh-pages"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        has_remote = bool(result.stdout.strip())

        # Clean up any existing deploy dir
        if tmp_dir.exists():
            import shutil

            shutil.rmtree(tmp_dir)

        if has_remote:
            run_command(["git", "worktree", "add", str(tmp_dir), "gh-pages"])
        else:
            run_command(["git", "worktree", "add", "--orphan", "-b", "gh-pages", str(tmp_dir)])

        # Write appcast.xml
        (tmp_dir / "appcast.xml").write_text(appcast_content, encoding="utf-8")

        # Commit and push
        subprocess.run(["git", "add", "appcast.xml"], cwd=str(tmp_dir), check=True, text=True)

        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(tmp_dir),
            text=True,
        )
        if diff_result.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", "Update appcast.xml"],
                cwd=str(tmp_dir),
                check=True,
                text=True,
            )
            run_command(["git", "push", "origin", "gh-pages"], dry_run=dry_run)
            print("Appcast pushed to gh-pages.")
        else:
            print("No changes to appcast.xml — nothing to push.")

        # Clean up worktree
        run_command(["git", "worktree", "remove", str(tmp_dir)])
    else:
        print("[dry-run] Would push appcast.xml to gh-pages branch")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Appcast generation for Sparkle auto-updates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate", help="Sign DMG and generate appcast.xml")
    subparsers.add_parser("push", help="Push appcast.xml to gh-pages branch")
    args = parser.parse_args()

    version = read_version()

    if args.command == "generate":
        cmd_generate(version, dry_run=args.dry_run)
    elif args.command == "push":
        cmd_push(dry_run=args.dry_run)
