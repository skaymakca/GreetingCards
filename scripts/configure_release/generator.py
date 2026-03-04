"""Pure logic for generating the release-local.sh script.

No I/O — takes a config, returns a string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Scope(Enum):
    """Where a release step runs."""

    LOCAL = "Local"
    APPLE = "Apple"
    GITHUB = "GitHub"


@dataclass(frozen=True)
class Step:
    """A single release pipeline step."""

    number: int
    word_id: str
    label: str
    command: str
    scope: Scope


@dataclass(frozen=True)
class Utility:
    """A non-pipeline utility command (not part of the numbered step sequence)."""

    word_id: str
    label: str
    command: str
    scope: Scope


STEPS: tuple[Step, ...] = (
    Step(1, "build", "Building app", "make app", Scope.LOCAL),
    Step(2, "sign", "Signing app", 'uv run python -m scripts.sign --identity "$CODESIGN_IDENTITY"', Scope.LOCAL),
    Step(3, "dmg", "Creating DMG", "uv run python -m scripts.dmg", Scope.LOCAL),
    Step(
        4,
        "submit",
        "Submitting to notary",
        'uv run python -m scripts.notarize --keychain-profile "$KEYCHAIN_PROFILE" submit',
        Scope.APPLE,
    ),
    Step(
        5,
        "staple",
        "Stapling ticket",
        'uv run python -m scripts.notarize --keychain-profile "$KEYCHAIN_PROFILE" staple',
        Scope.APPLE,
    ),
    Step(6, "checksum", "Generating checksum", "uv run python -m scripts.release checksum", Scope.LOCAL),
    Step(7, "changelog", "Extracting changelog", "uv run python -m scripts.release changelog", Scope.LOCAL),
    Step(8, "draft", "Creating draft release", "uv run python -m scripts.release draft", Scope.GITHUB),
)

UTILITIES: tuple[Utility, ...] = (
    Utility(
        "status",
        "Check notarization status",
        'uv run python -m scripts.notarize --keychain-profile "$KEYCHAIN_PROFILE" status',
        Scope.APPLE,
    ),
    Utility(
        "log",
        "Fetch notarization log",
        'uv run python -m scripts.notarize --keychain-profile "$KEYCHAIN_PROFILE" log',
        Scope.APPLE,
    ),
    Utility(
        "publish",
        "Publish the draft release",
        "uv run python -m scripts.release publish",
        Scope.GITHUB,
    ),
)

# Module-level guards: word IDs must be unique across steps AND utilities, and lowercase-alpha
_all_word_ids = [s.word_id for s in STEPS] + [u.word_id for u in UTILITIES]
if len(_all_word_ids) != len(set(_all_word_ids)):
    raise ValueError(f"Duplicate word IDs across STEPS/UTILITIES: {_all_word_ids}")
for _wid in _all_word_ids:
    if not re.fullmatch(r"[a-z]+", _wid):
        raise ValueError(f"Word ID must be lowercase alpha only, got: {_wid!r}")


@dataclass(frozen=True)
class ReleaseConfig:
    """Configuration for generating the release script."""

    signing_identity: str
    keychain_profile: str


@dataclass(frozen=True)
class ExistingConfig:
    """Values parsed from an existing release-local.sh."""

    signing_identity: str | None = None
    keychain_profile: str | None = None


def parse_existing_script(content: str) -> ExistingConfig:
    """Extract config values from an existing release-local.sh.

    Pure function: string in, dataclass out.
    """
    identity: str | None = None
    profile: str | None = None

    m = re.search(r'^export CODESIGN_IDENTITY="(.+)"$', content, re.MULTILINE)
    if m:
        identity = m.group(1)

    m = re.search(r'^KEYCHAIN_PROFILE="(.+)"$', content, re.MULTILINE)
    if m:
        profile = m.group(1)

    return ExistingConfig(signing_identity=identity, keychain_profile=profile)


def generate_script(config: ReleaseConfig) -> str:
    """Generate the complete release-local.sh script content."""
    # noinspection PyListCreation
    lines: list[str] = []

    # Header
    lines.append("#!/bin/bash")
    lines.append("set -euo pipefail")
    lines.append("")

    # Configuration
    lines.append(f'export CODESIGN_IDENTITY="{config.signing_identity}"')
    lines.append(f'KEYCHAIN_PROFILE="{config.keychain_profile}"')
    lines.append("")

    # Compute column widths for help tables (across both steps and utilities)
    all_ids = [s.word_id for s in STEPS] + [u.word_id for u in UTILITIES]
    all_labels = [s.label for s in STEPS] + [u.label for u in UTILITIES]
    id_width = max(len(wid) for wid in all_ids)
    name_width = max(len(label) for label in all_labels)

    # Help function
    lines.append("# --- Help ---")
    lines.append("show_help() {")
    lines.append('    echo "Usage: ./release-local.sh [STEP | RANGE | UTILITY]"')
    lines.append('    echo ""')
    lines.append('    echo "Steps:"')
    header = f"{'ID':<{id_width}}  {'Name':<{name_width}}  Scope"
    lines.append(f'    echo "  {header}"')
    separator = f"{'—' * id_width}  {'—' * name_width}  {'—' * 6}"
    lines.append(f'    echo "  {separator}"')
    for step in STEPS:
        row = f"{step.word_id:<{id_width}}  {step.label:<{name_width}}  {step.scope.value}"
        lines.append(f'    echo "  {row}"')
    lines.append('    echo ""')
    lines.append('    echo "Utilities:"')
    lines.append(f'    echo "  {header}"')
    lines.append(f'    echo "  {separator}"')
    for util in UTILITIES:
        row = f"{util.word_id:<{id_width}}  {util.label:<{name_width}}  {util.scope.value}"
        lines.append(f'    echo "  {row}"')
    lines.append('    echo ""')
    lines.append('    echo "Examples:"')
    lines.append('    echo "  ./release-local.sh              Show this help"')
    lines.append('    echo "  ./release-local.sh dmg          Run the dmg step only"')
    lines.append('    echo "  ./release-local.sh build-dmg    Run steps build through dmg"')
    lines.append('    echo "  ./release-local.sh status       Check notarization status"')
    lines.append('    echo "  ./release-local.sh submit       Submit to notary (async)"')
    lines.append("}")
    lines.append("")

    # Step number lookup function
    lines.append("# --- Word-to-number mapping ---")
    lines.append("step_number() {")
    lines.append('    case "$1" in')
    for step in STEPS:
        lines.append(f"        {step.word_id}) echo {step.number} ;;")
    lines.append('        *) echo "" ;;')
    lines.append("    esac")
    lines.append("}")
    lines.append("")

    # Step functions
    lines.append("# --- Steps ---")
    for step in STEPS:
        total = len(STEPS)
        lines.append(
            f'step_{step.number}() {{ echo ">>> Step {step.number}/{total}: {step.label}..."; {step.command}; }}'
        )
    lines.append("")

    # Utility functions
    lines.append("# --- Utilities ---")
    for util in UTILITIES:
        lines.append(f'util_{util.word_id}() {{ echo ">>> {util.label}..."; {util.command}; }}')
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

    # Utility dispatch — check before range parsing
    lines.append("# Utility dispatch (runs and exits)")
    lines.append('case "$ARG" in')
    for util in UTILITIES:
        lines.append(f"    {util.word_id}) util_{util.word_id}; exit 0 ;;")
    lines.append("esac")
    lines.append("")

    # Word-based parsing: single word or word-word range
    lines.append('if [[ "$ARG" == *-* ]]; then')
    lines.append('    FROM_WORD="${ARG%%-*}"')
    lines.append('    TO_WORD="${ARG##*-}"')
    lines.append('    START=$(step_number "$FROM_WORD")')
    lines.append('    END=$(step_number "$TO_WORD")')
    lines.append('    if [ -z "$START" ] || [ -z "$END" ]; then')
    lines.append(
        """        echo "Error: Unknown step in range '$ARG'. Run without arguments to see available steps.\""""
    )
    lines.append("        exit 1")
    lines.append("    fi")
    lines.append("else")
    lines.append('    START=$(step_number "$ARG")')
    lines.append('    if [ -z "$START" ]; then')
    lines.append("""        echo "Error: Unknown step '$ARG'. Run without arguments to see available steps.\"""")
    lines.append("        exit 1")
    lines.append("    fi")
    lines.append('    END="$START"')
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
