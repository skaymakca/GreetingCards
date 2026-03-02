"""Tests for app.core.platform — macOS platform utilities."""

from __future__ import annotations

from unittest.mock import patch

from app.core.platform import get_commit_hash


class TestGetCommitHash:
    def test_returns_short_hash(self) -> None:
        with patch("app.core.platform.subprocess.check_output", return_value=b"abc1234\n"):
            assert get_commit_hash() == "abc1234"

    def test_returns_empty_on_os_error(self) -> None:
        with patch("app.core.platform.subprocess.check_output", side_effect=OSError("fail")):
            assert get_commit_hash() == ""

    def test_returns_empty_on_subprocess_error(self) -> None:
        import subprocess

        with patch(
            "app.core.platform.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            assert get_commit_hash() == ""
