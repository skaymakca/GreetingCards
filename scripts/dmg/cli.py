"""DMG build orchestrator.

Generates the Read Me.rtf and invokes dmgbuild to produce the installer DMG.
The app bundle must already be built (run 'make app' first, or use 'make dmg'
which calls 'make app' automatically).

Usage:
    uv run python -m scripts.dmg
    uv run python -m scripts.dmg --verify-signature
    uv run python -m scripts.dmg --help

Output: dist/Greeting-Cards-X.Y.Z.dmg
"""

import argparse
import subprocess
import sys
from pathlib import Path

import dmgbuild  # type: ignore[import-untyped]

from scripts.dmg.background import generate as _generate_background
from scripts.dmg.readme import generate as _generate_readme
from scripts.helpers import PROJECT_ROOT, build_number_path, dmg_path, read_build_number, read_version
from scripts.helpers import app_path as _app_path


def verify_app_signature(bundle_path: Path) -> None:
    """Verify the app bundle is code-signed. Exit with error if not."""
    print("Verifying code signature …")
    result = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(bundle_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"Error: App bundle is not properly signed: {bundle_path}\n"
            f"{result.stderr.strip()}\n"
            "Hint: Run './release-local.sh sign' before creating the DMG.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print("Signature OK.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the Greeting Cards DMG installer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Reads version from pyproject.toml.\nOutput: dist/Greeting-Cards-X.Y.Z.dmg",
    )
    parser.add_argument(
        "--editable",
        action="store_true",
        help="Build a read-write (UDRW) DMG that can be edited in Finder.",
    )
    parser.add_argument(
        "--verify-signature",
        action="store_true",
        help="Verify the app bundle is code-signed before building the DMG.",
    )
    args = parser.parse_args()

    version = read_version()
    volume_name = f"Greeting Cards - {version}"

    settings_path = PROJECT_ROOT / "scripts" / "dmg" / "dmgbuild_settings.py"
    app = _app_path()
    sample_cards_path = PROJECT_ROOT / "content" / "dmg" / "Sample Cards"
    output_path = dmg_path(version)

    if args.verify_signature:
        verify_app_signature(app)

    # Step 1: Generate background image
    print("Generating background …")
    bg_path = _generate_background()

    # Step 2: Generate Read Me.rtf
    print("Generating Read Me.rtf …")
    readme_path = _generate_readme(version)

    # Step 3: Build DMG
    print(f"Building {volume_name} …")
    dmgbuild.build_dmg(
        filename=str(output_path),
        volume_name=volume_name,
        settings_file=str(settings_path),
        defines={
            "app_path": str(app),
            "readme_path": str(readme_path),
            "sample_cards_path": str(sample_cards_path),
            "background": str(bg_path),
            **({"format": "UDRW"} if args.editable else {}),
        },
    )

    print(f"Built: {output_path}")

    # Write build-number sidecar so the appcast step reads the build number
    # of the app *actually inside* the DMG, not whatever is on disk later.
    build_number = read_build_number()
    sidecar = build_number_path(version)
    sidecar.write_text(build_number, encoding="utf-8")
    print(f"Build number sidecar: {sidecar.name} ({build_number})")
