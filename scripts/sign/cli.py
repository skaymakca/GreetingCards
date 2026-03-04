"""Inside-out code signing for the Greeting Cards app bundle.

Signs all Mach-O binaries in the correct order (innermost first) so that
the outer signatures cover already-signed inner binaries.

Usage:
    uv run python -m scripts.sign
    uv run python -m scripts.sign --identity "-"       # ad-hoc signing
    uv run python -m scripts.sign --dry-run --verbose
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess

from scripts.helpers import PROJECT_ROOT, app_path

_ENTITLEMENTS = PROJECT_ROOT / "packaging" / "entitlements.plist"

# Mach-O magic numbers (big-endian and little-endian, including fat/universal)
_MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce",  # MH_MAGIC (32-bit)
    b"\xce\xfa\xed\xfe",  # MH_CIGAM (32-bit, reversed)
    b"\xfe\xed\xfa\xcf",  # MH_MAGIC_64 (64-bit)
    b"\xcf\xfa\xed\xfe",  # MH_CIGAM_64 (64-bit, reversed)
    b"\xca\xfe\xba\xbe",  # FAT_MAGIC (universal)
    b"\xbe\xba\xfe\xca",  # FAT_CIGAM (universal, reversed)
}


def _run(cmd: list[str], *, dry_run: bool = False, verbose: bool = False) -> None:
    """Run a command, printing it in dry-run or verbose mode. Skip execution in dry-run mode."""
    if dry_run or verbose:
        print(f"  {'[dry-run] ' if dry_run else ''}{' '.join(cmd)}")
    if not dry_run:
        subprocess.run(cmd, check=True)


def is_macho(path: pathlib.Path) -> bool:
    """Check if a file is a Mach-O binary by reading its magic number."""
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        return magic in _MACHO_MAGICS
    except OSError:
        return False


def _classify_tier(path: pathlib.Path) -> int:
    """Classify a Mach-O binary into a signing tier (lower = sign first).

    Tier 0: .so and .dylib files (innermost libraries)
    Tier 1: Framework binaries (inside .framework bundles)
    Tier 2: The main executable
    """
    suffix = path.suffix.lower()
    if suffix in (".so", ".dylib"):
        return 0

    # Check if inside a .framework bundle
    for parent in path.parents:
        if parent.suffix == ".framework":
            return 1

    return 2


def find_binaries(bundle_path: pathlib.Path) -> list[pathlib.Path]:
    """Walk the app bundle and return all Mach-O binaries sorted by signing tier."""
    binaries: list[pathlib.Path] = []
    for item in bundle_path.rglob("*"):
        if item.is_file() and is_macho(item):
            binaries.append(item)

    # Sort by tier (innermost first), then by path for determinism
    binaries.sort(key=lambda p: (_classify_tier(p), str(p)))
    return binaries


def sign_binary(
    path: pathlib.Path,
    identity: str,
    entitlements: pathlib.Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Sign a single binary with codesign."""
    cmd = [
        "codesign",
        "--force",
        "--options",
        "runtime",
        "--timestamp",
        "--entitlements",
        str(entitlements),
        "--sign",
        identity,
        str(path),
    ]
    _run(cmd, dry_run=dry_run, verbose=verbose)


def sign_app(
    bundle_path: pathlib.Path,
    identity: str,
    entitlements: pathlib.Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Sign all binaries in the app bundle, then sign the bundle itself."""
    binaries = find_binaries(bundle_path)
    print(f"Found {len(binaries)} Mach-O binaries to sign")

    for binary in binaries:
        sign_binary(binary, identity, entitlements, dry_run=dry_run, verbose=verbose)

    # Sign the .app bundle itself
    print("Signing app bundle …")
    bundle_cmd = [
        "codesign",
        "--force",
        "--options",
        "runtime",
        "--timestamp",
        "--entitlements",
        str(entitlements),
        "--sign",
        identity,
        str(bundle_path),
    ]
    _run(bundle_cmd, dry_run=dry_run, verbose=verbose)

    # Verify
    print("Verifying …")
    verify_cmd = [
        "codesign",
        "--verify",
        "--deep",
        "--strict",
        str(bundle_path),
    ]
    _run(verify_cmd, dry_run=dry_run, verbose=verbose)

    print("Signing complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sign the Greeting Cards app bundle for distribution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Use --identity "-" for ad-hoc signing (testing only).',
    )
    parser.add_argument(
        "--identity",
        default=None,
        help='Signing identity (default: $CODESIGN_IDENTITY env var). Use "-" for ad-hoc.',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print codesign commands without executing them.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each codesign command as it executes.",
    )
    args = parser.parse_args()

    identity = args.identity or os.environ.get("CODESIGN_IDENTITY")
    if not identity:
        parser.error(
            "No signing identity specified.\n"
            "  Use --identity IDENTITY or set CODESIGN_IDENTITY env var.\n"
            '  For testing, use --identity "-" (ad-hoc signing).'
        )

    _app = app_path()
    if not _app.exists():
        parser.error(f"App bundle not found at {_app}\n  Run 'make app' first.")

    if not _ENTITLEMENTS.exists():
        parser.error(f"Entitlements file not found at {_ENTITLEMENTS}")

    sign_app(_app, identity, _ENTITLEMENTS, dry_run=args.dry_run, verbose=args.verbose)
