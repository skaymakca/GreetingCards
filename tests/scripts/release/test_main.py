"""Tests for scripts/release/__main__.py — clean error output."""

from __future__ import annotations

import runpy
import subprocess
from unittest.mock import patch

import pytest
from scripts.release.cli import ReleaseError


class TestCleanErrorOutput:
    """__main__.py catches exceptions and exits cleanly (no traceback)."""

    def test_file_not_found_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("scripts.release.cli.main", side_effect=FileNotFoundError("DMG not found: dist/X.dmg")),
            pytest.raises(SystemExit, match="1"),
        ):
            runpy.run_module("scripts.release", run_name="__main__")

        assert "Error: DMG not found" in capsys.readouterr().err

    def test_release_error_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("scripts.release.cli.main", side_effect=ReleaseError("Version 9.9.9 not found")),
            pytest.raises(SystemExit, match="1"),
        ):
            runpy.run_module("scripts.release", run_name="__main__")

        assert "Error: Version 9.9.9 not found" in capsys.readouterr().err

    def test_called_process_error_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        exc = subprocess.CalledProcessError(1, ["gh", "release", "create"])
        with (
            patch("scripts.release.cli.main", side_effect=exc),
            pytest.raises(SystemExit, match="1"),
        ):
            runpy.run_module("scripts.release", run_name="__main__")

        err = capsys.readouterr().err
        assert "Error: command failed (exit 1)" in err
        assert "gh release create" in err
