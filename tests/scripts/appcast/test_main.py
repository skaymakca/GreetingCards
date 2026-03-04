"""Tests for scripts/appcast/__main__.py — clean error output."""

from __future__ import annotations

import runpy
import subprocess
from unittest.mock import patch

import pytest
from scripts.appcast.cli import AppcastError


class TestCleanErrorOutput:
    """__main__.py catches exceptions and exits cleanly (no traceback)."""

    def test_file_not_found_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("scripts.appcast.cli.main", side_effect=FileNotFoundError("DMG not found: dist/X.dmg")),
            pytest.raises(SystemExit, match="1"),
        ):
            runpy.run_module("scripts.appcast", run_name="__main__")

        assert "Error: DMG not found" in capsys.readouterr().err

    def test_appcast_error_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("scripts.appcast.cli.main", side_effect=AppcastError("Failed to parse signature")),
            pytest.raises(SystemExit, match="1"),
        ):
            runpy.run_module("scripts.appcast", run_name="__main__")

        assert "Error: Failed to parse signature" in capsys.readouterr().err

    def test_called_process_error_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        exc = subprocess.CalledProcessError(1, ["sign_update", "test.dmg"])
        with (
            patch("scripts.appcast.cli.main", side_effect=exc),
            pytest.raises(SystemExit, match="1"),
        ):
            runpy.run_module("scripts.appcast", run_name="__main__")

        err = capsys.readouterr().err
        assert "Error: command failed (exit 1)" in err
        assert "sign_update" in err
