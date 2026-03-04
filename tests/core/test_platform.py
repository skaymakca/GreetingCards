"""Tests for app.core.platform — macOS platform utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.platform import get_commit_hash, open_file, reveal_in_finder


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


class TestOpenFile:
    def test_calls_popen_with_open_command(self) -> None:
        with patch("app.core.platform.subprocess.Popen") as mock_popen:
            open_file("/tmp/test.pdf")
            mock_popen.assert_called_once_with(["open", "/tmp/test.pdf"])

    def test_accepts_path_object(self) -> None:
        with patch("app.core.platform.subprocess.Popen") as mock_popen:
            open_file(Path("/tmp/test.pdf"))
            mock_popen.assert_called_once_with(["open", "/tmp/test.pdf"])

    def test_logs_warning_on_os_error(self) -> None:
        with (
            patch("app.core.platform.subprocess.Popen", side_effect=OSError("fail")),
            patch("app.core.platform.logger") as mock_logger,
        ):
            open_file("/tmp/test.pdf")
            mock_logger.warning.assert_called_once()


class TestRevealInFinder:
    def test_calls_popen_with_open_reveal_command(self) -> None:
        with patch("app.core.platform.subprocess.Popen") as mock_popen:
            reveal_in_finder("/tmp/test.pdf")
            mock_popen.assert_called_once_with(["open", "-R", "/tmp/test.pdf"])

    def test_accepts_path_object(self) -> None:
        with patch("app.core.platform.subprocess.Popen") as mock_popen:
            reveal_in_finder(Path("/tmp/test.pdf"))
            mock_popen.assert_called_once_with(["open", "-R", "/tmp/test.pdf"])

    def test_logs_warning_on_os_error(self) -> None:
        with (
            patch("app.core.platform.subprocess.Popen", side_effect=OSError("fail")),
            patch("app.core.platform.logger") as mock_logger,
        ):
            reveal_in_finder("/tmp/test.pdf")
            mock_logger.warning.assert_called_once()
