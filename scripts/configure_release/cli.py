"""Orchestrator: wire keychain + UI + generator, write the release script file."""

from __future__ import annotations

import difflib
import os
import pathlib
import stat

from scripts.configure_release.generator import ReleaseConfig, generate_script
from scripts.configure_release.keychain import find_signing_identities
from scripts.configure_release.ui import InteractiveInput, UserInput

_ROOT = pathlib.Path(__file__).parent.parent.parent
_OUTPUT_PATH = _ROOT / "release-local.sh"

# ANSI color codes
_RED = "\033[31m"
_GREEN = "\033[32m"
_RESET = "\033[0m"


def configure(ui: UserInput) -> ReleaseConfig:
    """Interactively configure signing identity and notarization profile.

    Raises SystemExit if no signing identities are found.
    """
    identities = find_signing_identities()

    if not identities:
        print("No codesigning identities found in Keychain.")
        print("Install a Developer ID Application certificate first.")
        raise SystemExit(1)

    # Build options list and find default
    options = [f"{ident.common_name}  ({ident.sha1[:8]}…)" for ident in identities]
    default_idx: int | None = None
    for i, ident in enumerate(identities):
        if ident.common_name.startswith("Developer ID Application:"):
            default_idx = i
            break

    selected = ui.choose("Select a signing identity:", options, default=default_idx)
    identity = identities[selected].common_name

    print("")
    print("Notarization requires credentials stored in the macOS Keychain.")
    print("If you haven't stored them yet, run:")
    print("")
    print("  xcrun notarytool store-credentials GreetingCards \\")
    print("    --apple-id your@email.com \\")
    print("    --team-id TEAMID \\")
    print("    --password app-specific-password")
    print("")

    profile = ui.ask("Keychain profile name", default="GreetingCards")

    return ReleaseConfig(signing_identity=identity, keychain_profile=profile)


def show_diff(old_content: str | None, new_content: str) -> None:
    """Print a colored diff between old and new content.

    If old_content is None (new file), all lines are shown as green additions.
    """
    if old_content is None:
        print(f"\n{_GREEN}(new file){_RESET}")
        for line in new_content.splitlines():
            print(f"{_GREEN}+ {line}{_RESET}")
        return

    if old_content == new_content:
        print("\nNo changes to release-local.sh.")
        return

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="release-local.sh", tofile="release-local.sh")

    print("")
    for line in diff:
        line_stripped = line.rstrip("\n")
        if line.startswith("+"):
            print(f"{_GREEN}{line_stripped}{_RESET}")
        elif line.startswith("-"):
            print(f"{_RED}{line_stripped}{_RESET}")
        else:
            print(line_stripped)


def write_script(config: ReleaseConfig, output_path: pathlib.Path = _OUTPUT_PATH) -> None:
    """Generate the script, show a diff, and write to disk."""
    old_content: str | None = None
    if output_path.exists():
        old_content = output_path.read_text(encoding="utf-8")

    new_content = generate_script(config)
    show_diff(old_content, new_content)
    output_path.write_text(new_content, encoding="utf-8")
    output_path.chmod(output_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> None:
    """Entry point for configure_release."""
    print("=" * 50)
    print("  Release Configuration")
    print("=" * 50)

    ui = InteractiveInput()
    config = configure(ui)
    write_script(config)

    rel_path = os.path.relpath(_OUTPUT_PATH)
    print(f"\nWrote {rel_path}")
    print(f"Run ./{rel_path} to see available steps.")
