"""Tests for project version metadata."""

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def _read_version() -> str:
    with open(_PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_version_is_valid_string():
    """pyproject.toml contains a non-empty version string."""
    v = _read_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_version_format():
    """Version follows major.minor.patch format."""
    v = _read_version()
    parts = v.split(".")
    assert len(parts) == 3, f"Expected 3 version parts, got {len(parts)}: {v}"
    for part in parts:
        assert part.isdigit(), f"Non-numeric version part: {part}"
