"""Keychain scanning: find codesigning identities via macOS security CLI."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

_IDENTITY_RE = re.compile(r'^\s*\d+\)\s+([0-9A-F]+)\s+"(.+)"$', re.MULTILINE)


@dataclass(frozen=True)
class SigningIdentity:
    """A code-signing identity from the macOS Keychain."""

    sha1: str
    common_name: str


def find_signing_identities() -> list[SigningIdentity]:
    """Scan the Keychain for valid codesigning identities.

    Returns an empty list on error or if no certificates are found.
    """
    try:
        result = subprocess.run(
            ["security", "find-identity", "-v", "-p", "codesigning"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []

    return [SigningIdentity(sha1=m.group(1), common_name=m.group(2)) for m in _IDENTITY_RE.finditer(result.stdout)]
