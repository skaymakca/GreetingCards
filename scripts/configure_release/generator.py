"""Pure logic for generating the release-local.sh script.

No I/O — takes a config, returns a string.
"""

from __future__ import annotations

from dataclasses import dataclass

STEPS: tuple[tuple[int, str, str], ...] = (
    (1, "Building app", "make app"),
    (2, "Signing app", 'uv run python -m scripts.sign --identity "$CODESIGN_IDENTITY"'),
    (3, "Creating DMG", "uv run python -m scripts.dmg"),
    (4, "Notarizing", 'uv run python -m scripts.notarize --keychain-profile "$KEYCHAIN_PROFILE"'),
    (5, "Generating checksum", "uv run python -m scripts.release checksum"),
    (6, "Extracting changelog", "uv run python -m scripts.release changelog"),
    (7, "Creating draft release", "uv run python -m scripts.release draft"),
)


@dataclass(frozen=True)
class ReleaseConfig:
    """Configuration for generating the release script."""

    signing_identity: str
    keychain_profile: str


def generate_script(config: ReleaseConfig) -> str:
    """Generate the complete release-local.sh script content."""
    lines: list[str] = []

    # Header
    lines.append("#!/bin/bash")
    lines.append("set -euo pipefail")
    lines.append("")

    # Configuration
    lines.append(f'export CODESIGN_IDENTITY="{config.signing_identity}"')
    lines.append(f'KEYCHAIN_PROFILE="{config.keychain_profile}"')
    lines.append("")

    # Help function
    lines.append("# --- Help ---")
    lines.append("show_help() {")
    lines.append('    echo "Usage: ./release-local.sh [STEP | RANGE]"')
    lines.append('    echo ""')
    lines.append('    echo "Steps:"')
    for number, label, _ in STEPS:
        lines.append(f'    echo "  {number}. {label}"')
    lines.append('    echo ""')
    lines.append('    echo "Examples:"')
    lines.append('    echo "  ./release-local.sh         Show this help"')
    lines.append('    echo "  ./release-local.sh 3       Run step 3 only"')
    lines.append('    echo "  ./release-local.sh 1-5     Run steps 1 through 5"')
    lines.append('    echo "  ./release-local.sh 3-7     Run steps 3 through 7"')
    lines.append("}")
    lines.append("")

    # Step functions
    lines.append("# --- Steps ---")
    for number, label, cmd in STEPS:
        total = len(STEPS)
        lines.append(f'step_{number}() {{ echo ">>> Step {number}/{total}: {label}..."; {cmd}; }}')
    lines.append("")

    # Argument parsing
    lines.append("# --- Argument parsing ---")
    lines.append("if [ $# -eq 0 ]; then")
    lines.append("    show_help")
    lines.append("    exit 0")
    lines.append("fi")
    lines.append("")
    lines.append('ARG="$1"')
    lines.append("")
    lines.append('if [[ "$ARG" =~ ^([0-9]+)-([0-9]+)$ ]]; then')
    lines.append('    START="${BASH_REMATCH[1]}"')
    lines.append('    END="${BASH_REMATCH[2]}"')
    lines.append('elif [[ "$ARG" =~ ^[0-9]+$ ]]; then')
    lines.append('    START="$ARG"')
    lines.append('    END="$ARG"')
    lines.append("else")
    lines.append("    echo \"Error: Invalid argument '$ARG'. Expected a step number or range (e.g., 3 or 1-5).\"")
    lines.append("    exit 1")
    lines.append("fi")
    lines.append("")

    # Validation
    total = len(STEPS)
    lines.append(f'if [ "$START" -lt 1 ] || [ "$END" -gt {total} ] || [ "$START" -gt "$END" ]; then')
    lines.append(f'    echo "Error: Invalid range. Steps must be between 1 and {total}, and start <= end."')
    lines.append("    exit 1")
    lines.append("fi")
    lines.append("")

    # Execution loop
    lines.append("for (( i=START; i<=END; i++ )); do")
    lines.append('    "step_$i"')
    lines.append("done")
    lines.append("")

    return "\n".join(lines)
