"""Apple notarization for the Greeting Cards DMG.

Async workflow: submit → wait externally → check status → staple.

Usage:
    uv run python -m scripts.notarize submit                    # fire-and-forget
    uv run python -m scripts.notarize status                    # check notarization status
    uv run python -m scripts.notarize log                       # fetch notarization log
    uv run python -m scripts.notarize staple                    # staple + verify
    uv run python -m scripts.notarize --dry-run submit          # global flags before subcommand
    uv run python -m scripts.notarize staple --submission-id X  # explicit ID override
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
from datetime import datetime

from scripts.helpers import PROJECT_ROOT, dmg_path, read_version, run_command

_SUBMISSION_ID_FILE = PROJECT_ROOT / "_build" / "release" / "submission-id.txt"
_ID_PATTERN = re.compile(r"id:\s*([0-9a-f-]+)")


def save_submission_id(submission_id: str, path: pathlib.Path = _SUBMISSION_ID_FILE) -> None:
    """Write the submission ID to a file for later retrieval."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(submission_id + "\n", encoding="utf-8")
    print(f"Submission ID saved to {path}")


def load_submission_id(path: pathlib.Path = _SUBMISSION_ID_FILE) -> str:
    """Read a previously saved submission ID.

    Raises FileNotFoundError if the file does not exist.
    """
    text = path.read_text(encoding="utf-8").strip()
    return text


def backup_dmg(dmg: pathlib.Path) -> pathlib.Path:
    """Copy the DMG to _build/release/ with a datetime stamp.

    Preserves the exact artifact submitted to Apple so it can be recovered
    if the DMG is accidentally rebuilt before stapling.
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M")
    backup_name = f"{dmg.stem}-{timestamp}{dmg.suffix}"
    backup_path = _SUBMISSION_ID_FILE.parent / backup_name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dmg, backup_path)
    print(f"DMG backed up to {backup_path}")
    return backup_path


def submit(dmg: pathlib.Path, profile: str, *, dry_run: bool = False) -> str | None:
    """Submit DMG to Apple's notary service (fire-and-forget).

    Returns the submission ID on success, or None in dry-run mode.
    """
    print("Submitting to Apple notary service …")
    result = run_command(
        [
            "xcrun",
            "notarytool",
            "submit",
            str(dmg),
            "--keychain-profile",
            profile,
        ],
        dry_run=dry_run,
        capture=True,
    )

    if dry_run:
        return None

    print(result.stdout)

    # Parse submission ID from output
    match = _ID_PATTERN.search(result.stdout)
    if not match:
        print("Could not parse submission ID from output.")
        raise SystemExit(1)

    return match.group(1)


def check_status(submission_id: str, profile: str, *, dry_run: bool = False) -> str | None:
    """Check notarization status via ``xcrun notarytool info``.

    Prints raw output verbatim, then parses and returns the status string
    (e.g. ``"Accepted"``, ``"In Progress"``). Returns None in dry-run mode.
    """
    print(f"Checking status for {submission_id} …")
    result = run_command(
        ["xcrun", "notarytool", "info", submission_id, "--keychain-profile", profile],
        dry_run=dry_run,
        capture=True,
    )

    if dry_run:
        return None

    print(result.stdout)

    match = re.search(r"status:\s*(.+)", result.stdout)
    return match.group(1).strip() if match else None


def fetch_history(profile: str, *, dry_run: bool = False) -> str | None:
    """Fetch notarization history and return the most recent submission ID.

    Runs ``xcrun notarytool history`` and parses the first ``id:`` from the
    output.  Returns ``None`` if no ID is found or in dry-run mode.
    """
    print("Fetching notarization history …")
    result = run_command(
        ["xcrun", "notarytool", "history", "--keychain-profile", profile],
        dry_run=dry_run,
        capture=True,
    )

    if dry_run:
        return None

    print(result.stdout)

    match = _ID_PATTERN.search(result.stdout)
    return match.group(1) if match else None


def fetch_log(submission_id: str, profile: str, *, dry_run: bool = False) -> None:
    """Fetch the notarization log via ``xcrun notarytool log``.

    Prints the output verbatim (no parsing).  If the log is not yet
    available, prints a friendly message instead of a traceback.
    """
    print(f"Fetching log for {submission_id} …")
    try:
        run_command(
            ["xcrun", "notarytool", "log", submission_id, "--keychain-profile", profile],
            dry_run=dry_run,
        )
    except subprocess.CalledProcessError as exc:
        print(f"notarytool log exited with status {exc.returncode}.")
        print("The log may not be available yet — try again later.")
        raise SystemExit(1) from None


def staple(dmg: pathlib.Path, *, dry_run: bool = False) -> None:
    """Staple the notarization ticket to the DMG."""
    print("Stapling ticket …")
    run_command(["xcrun", "stapler", "staple", str(dmg)], dry_run=dry_run)


def verify(dmg: pathlib.Path, *, dry_run: bool = False) -> None:
    """Verify the notarization ticket is stapled to the DMG."""
    print("Verifying stapled ticket …")
    run_command(
        ["xcrun", "stapler", "validate", str(dmg)],
        dry_run=dry_run,
    )
    print("Stapler validation passed.")


def _resolve_submission_id(args: argparse.Namespace) -> str:
    """Resolve the submission ID from flag, saved file, or history fallback."""
    explicit: str | None = getattr(args, "submission_id", None)
    if explicit:
        return explicit
    try:
        return load_submission_id()
    except FileNotFoundError:
        print("No saved submission ID found. Checking notarization history …")
        sid = fetch_history(args.keychain_profile, dry_run=args.dry_run)
        if sid:
            save_submission_id(sid)
            print(f"Using most recent submission: {sid}")
            return sid
        print("No submission ID found. Pass --submission-id or run 'submit' first.")
        print(f"  Expected file: {_SUBMISSION_ID_FILE}")
        raise SystemExit(1) from None


def _cmd_submit(args: argparse.Namespace) -> None:
    """Submit handler: validate DMG, submit, save ID, print hints."""
    version = read_version()
    dmg = dmg_path(version)

    if not args.dry_run and not dmg.exists():
        print(f"Error: DMG not found at {dmg}")
        print("  Run 'make dmg' first.")
        raise SystemExit(1)

    submission_id = submit(dmg, args.keychain_profile, dry_run=args.dry_run)

    if submission_id:
        save_submission_id(submission_id)
        backup = backup_dmg(dmg)
        print()
        print(f"Submission ID: {submission_id}")
        print(f"DMG backup:    {backup}")
        print("Next steps:")
        print("  uv run python -m scripts.notarize status   # check progress")
        print("  uv run python -m scripts.notarize staple   # after acceptance")


def _cmd_status(args: argparse.Namespace) -> None:
    """Status handler: resolve ID, check status, hint if accepted."""
    submission_id = _resolve_submission_id(args)
    status = check_status(submission_id, args.keychain_profile, dry_run=args.dry_run)

    if status and "Accepted" in status:
        print("Ready to staple:")
        print("  uv run python -m scripts.notarize staple")


def _cmd_log(args: argparse.Namespace) -> None:
    """Log handler: resolve ID, fetch log."""
    submission_id = _resolve_submission_id(args)
    fetch_log(submission_id, args.keychain_profile, dry_run=args.dry_run)


def _cmd_staple(args: argparse.Namespace) -> None:
    """Staple handler: resolve ID, check status, staple + verify."""
    version = read_version()
    dmg = dmg_path(version)

    if not args.dry_run and not dmg.exists():
        print(f"Error: DMG not found at {dmg}")
        print("  Run 'make dmg' first.")
        raise SystemExit(1)

    submission_id = _resolve_submission_id(args)
    status = check_status(submission_id, args.keychain_profile, dry_run=args.dry_run)

    if status and "Accepted" not in status:
        print(f"Notarization not yet accepted (status: {status}).")
        print("Run 'status' or 'log' to check progress.")
        raise SystemExit(1)

    staple(dmg, dry_run=args.dry_run)
    verify(dmg, dry_run=args.dry_run)
    print("Notarization complete.")


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

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("submit", help="Submit DMG to Apple notary service")

    status_parser = subparsers.add_parser("status", help="Check notarization status")
    status_parser.add_argument(
        "--submission-id",
        help="Submission ID (default: read from saved file).",
    )

    log_parser = subparsers.add_parser("log", help="Fetch notarization log")
    log_parser.add_argument(
        "--submission-id",
        help="Submission ID (default: read from saved file).",
    )

    staple_parser = subparsers.add_parser("staple", help="Staple ticket and verify")
    staple_parser.add_argument(
        "--submission-id",
        help="Submission ID (default: read from saved file).",
    )

    args = parser.parse_args()

    commands = {
        "submit": _cmd_submit,
        "status": _cmd_status,
        "log": _cmd_log,
        "staple": _cmd_staple,
    }
    commands[args.command](args)
