"""Tests for scripts/sign/__main__.py — clean error output."""

from __future__ import annotations

import runpy
import subprocess
from unittest.mock import patch

import pytest


class TestCleanErrorOutput:
    """__main__.py catches CalledProcessError and exits cleanly (no traceback)."""

    def test_called_process_error_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        exc = subprocess.CalledProcessError(1, ["codesign", "--sign", "ID", "app.app"])
        with (
            patch("scripts.sign.cli.main", side_effect=exc),
            pytest.raises(SystemExit, match="1"),
        ):
            runpy.run_module("scripts.sign", run_name="__main__")

        err = capsys.readouterr().err
        assert "Error: command failed (exit 1)" in err
        assert "codesign" in err
