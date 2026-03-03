"""Apple notarization for the Greeting Cards DMG.

Submits the signed DMG to Apple's notary service, waits for approval,
and staples the notarization ticket to both the .app and .dmg.

Usage:
    uv run python -m scripts.notarize
    uv run python -m scripts.notarize --keychain-profile MyProfile
    uv run python -m scripts.notarize --dry-run
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import tomllib

_ROOT = pathlib.Path(__file__).parent.parent.parent
_APP_PATH = _ROOT / "dist" / "Greeting Cards.app"


def _read_version() -> str:
    with open(_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def _dmg_path(version: str) -> pathlib.Path:
    return _ROOT / "dist" / f"Greeting-Cards-{version}.dmg"


def _run(cmd: list[str], *, dry_run: bool = False, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command, printing it first. In dry-run mode, skip execution."""
    print(f"  {'[dry-run] ' if dry_run else ''}{' '.join(cmd)}")
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return subprocess.run(cmd, check=True, capture_output=capture, text=True)


def submit(dmg: pathlib.Path, profile: str, *, dry_run: bool = False) -> str | None:
    """Submit DMG to Apple's notary service and wait for completion.

    Returns the submission ID on success, or None in dry-run mode.
    """
    print("Submitting to Apple notary service …")
    result = _run(
        [
            "xcrun",
            "notarytool",
            "submit",
            str(dmg),
            "--keychain-profile",
            profile,
            "--wait",
        ],
        dry_run=dry_run,
        capture=True,
    )

    if dry_run:
        return None

    # Parse submission ID from output
    match = re.search(r"id:\s*([0-9a-f-]+)", result.stdout)
    submission_id = match.group(1) if match else None

    if "status: Accepted" not in result.stdout:
        print(f"Notarization failed!\n{result.stdout}")
        if submission_id:
            print("Fetching notarization log …")
            _run(
                ["xcrun", "notarytool", "log", submission_id, "--keychain-profile", profile],
            )
        raise SystemExit(1)

    print(f"Notarization accepted (ID: {submission_id})")
    return submission_id


def staple(app: pathlib.Path, dmg: pathlib.Path, *, dry_run: bool = False) -> None:
    """Staple the notarization ticket to both the .app and the .dmg."""
    print("Stapling ticket …")
    _run(["xcrun", "stapler", "staple", str(app)], dry_run=dry_run)
    _run(["xcrun", "stapler", "staple", str(dmg)], dry_run=dry_run)


def verify(app: pathlib.Path, *, dry_run: bool = False) -> None:
    """Verify the notarized app passes Gatekeeper assessment."""
    print("Verifying Gatekeeper assessment …")
    _run(
        ["spctl", "--assess", "--type", "execute", "--verbose", str(app)],
        dry_run=dry_run,
    )
    print("Gatekeeper assessment passed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Notarize the Greeting Cards DMG for distribution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "One-time setup:\n"
            "  xcrun notarytool store-credentials GreetingCards \\\n"
            "    --apple-id your@email.com \\\n"
            "    --team-id TEAMID \\\n"
            "    --password app-specific-password"
        ),
    )
    parser.add_argument(
        "--keychain-profile",
        default="GreetingCards",
        help='Keychain profile name for notarytool (default: "GreetingCards").',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    args = parser.parse_args()

    version = _read_version()
    dmg = _dmg_path(version)

    if not args.dry_run:
        if not dmg.exists():
            parser.error(f"DMG not found at {dmg}\n  Run 'make dmg' first.")
        if not _APP_PATH.exists():
            parser.error(f"App bundle not found at {_APP_PATH}\n  Run 'make app' first.")

    submit(dmg, args.keychain_profile, dry_run=args.dry_run)
    staple(_APP_PATH, dmg, dry_run=args.dry_run)
    verify(_APP_PATH, dry_run=args.dry_run)

    print("Notarization complete.")
