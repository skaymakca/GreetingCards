"""DMG build orchestrator.

Generates the Read Me.rtf and invokes dmgbuild to produce the installer DMG.
The app bundle must already be built (run 'make app' first, or use 'make dmg'
which calls 'make app' automatically).

Usage:
    uv run python -m scripts.dmg
    uv run python -m scripts.dmg --help

Output: dist/Greeting-Cards-X.Y.Z.dmg
"""

import argparse

import dmgbuild  # type: ignore[import-untyped]

from scripts.dmg.background import generate as _generate_background
from scripts.dmg.readme import generate as _generate_readme
from scripts.helpers import PROJECT_ROOT, dmg_path, read_version
from scripts.helpers import app_path as _app_path


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
    args = parser.parse_args()

    version = read_version()
    volume_name = f"Greeting Cards - {version}"

    settings_path = PROJECT_ROOT / "scripts" / "dmg" / "dmgbuild_settings.py"
    app = _app_path()
    sample_cards_path = PROJECT_ROOT / "content" / "dmg" / "Sample Cards"
    output_path = dmg_path(version)

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


if __name__ == "__main__":
    main()
