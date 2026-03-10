"""Tests for scripts/profiling/report.py — formatting helpers and system-info functions."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from scripts.profiling.report import _fmt_throughput, _fmt_time, _git_short_hash, _macos_version, _ram_gb

# ---------------------------------------------------------------------------
# _fmt_time()
# ---------------------------------------------------------------------------


class TestFmtTime:
    """Tests for _fmt_time() — human-readable time formatting."""

    def test_microseconds(self) -> None:
        """Sub-millisecond values are formatted as microseconds."""
        assert _fmt_time(0.0005) == "500\u00b5s"

    def test_microseconds_very_small(self) -> None:
        """Very small values produce integer microseconds."""
        assert _fmt_time(0.000001) == "1\u00b5s"

    def test_microseconds_boundary(self) -> None:
        """Values just below 1ms use microsecond format."""
        # 0.000999 < 0.001 → microseconds
        result = _fmt_time(0.000999)
        assert result.endswith("\u00b5s")

    def test_milliseconds(self) -> None:
        """Values between 1ms and 1s are formatted as milliseconds."""
        assert _fmt_time(0.5) == "500.0ms"

    def test_milliseconds_small(self) -> None:
        """Just above the microsecond boundary uses millisecond format."""
        assert _fmt_time(0.001) == "1.0ms"

    def test_milliseconds_near_one_second(self) -> None:
        """Values just below 1s still use millisecond format."""
        assert _fmt_time(0.999) == "999.0ms"

    def test_seconds(self) -> None:
        """Values between 1s and 60s are formatted as seconds."""
        assert _fmt_time(1.0) == "1.00s"

    def test_seconds_fractional(self) -> None:
        assert _fmt_time(42.567) == "42.57s"

    def test_seconds_near_one_minute(self) -> None:
        """Values just below 60s still use seconds format."""
        assert _fmt_time(59.99) == "59.99s"

    def test_minutes(self) -> None:
        """Values at or above 60s are formatted as minutes + seconds."""
        assert _fmt_time(60.0) == "1m 0.0s"

    def test_minutes_with_seconds(self) -> None:
        assert _fmt_time(90.5) == "1m 30.5s"

    def test_multiple_minutes(self) -> None:
        assert _fmt_time(125.3) == "2m 5.3s"

    def test_zero(self) -> None:
        """Zero seconds produces microsecond format with 0."""
        assert _fmt_time(0.0) == "0\u00b5s"


# ---------------------------------------------------------------------------
# _fmt_throughput()
# ---------------------------------------------------------------------------


class TestFmtThroughput:
    """Tests for _fmt_throughput() — cards-per-second formatting."""

    def test_normal_throughput(self) -> None:
        assert _fmt_throughput(10, 2.0) == "5.0/s"

    def test_single_card(self) -> None:
        assert _fmt_throughput(1, 0.5) == "2.0/s"

    def test_high_throughput(self) -> None:
        assert _fmt_throughput(1000, 1.0) == "1000.0/s"

    def test_zero_seconds_returns_dash(self) -> None:
        """Division by zero is handled with an em-dash."""
        assert _fmt_throughput(10, 0.0) == "\u2014"

    def test_negative_seconds_returns_dash(self) -> None:
        """Negative time is treated like zero — returns em-dash."""
        assert _fmt_throughput(10, -1.0) == "\u2014"

    def test_fractional_rate(self) -> None:
        assert _fmt_throughput(1, 3.0) == "0.3/s"


# ---------------------------------------------------------------------------
# _macos_version()
# ---------------------------------------------------------------------------


class TestMacosVersion:
    """Tests for _macos_version() — macOS version string via sw_vers."""

    @patch("scripts.profiling.report.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        """Returns 'macOS <version>' on success."""
        mock_run.return_value = subprocess.CompletedProcess(["sw_vers", "-productVersion"], 0, stdout="15.4.1\n")
        assert _macos_version() == "macOS 15.4.1"

    @patch("scripts.profiling.report.subprocess.run")
    def test_strips_whitespace(self, mock_run: MagicMock) -> None:
        """Trailing whitespace and newlines are stripped."""
        mock_run.return_value = subprocess.CompletedProcess(["sw_vers"], 0, stdout="  14.0  \n")
        assert _macos_version() == "macOS 14.0"

    @patch("scripts.profiling.report.platform")
    @patch("scripts.profiling.report.subprocess.run")
    def test_os_error_fallback(self, mock_run: MagicMock, mock_platform: MagicMock) -> None:
        """Falls back to platform info when sw_vers is not found."""
        mock_run.side_effect = OSError("not found")
        mock_platform.system.return_value = "Darwin"
        mock_platform.release.return_value = "24.5.0"
        assert _macos_version() == "Darwin 24.5.0"

    @patch("scripts.profiling.report.platform")
    @patch("scripts.profiling.report.subprocess.run")
    def test_called_process_error_fallback(self, mock_run: MagicMock, mock_platform: MagicMock) -> None:
        """Falls back to platform info when sw_vers returns non-zero."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "sw_vers")
        mock_platform.system.return_value = "Linux"
        mock_platform.release.return_value = "6.1.0"
        assert _macos_version() == "Linux 6.1.0"


# ---------------------------------------------------------------------------
# _ram_gb()
# ---------------------------------------------------------------------------


class TestRamGb:
    """Tests for _ram_gb() — physical RAM in GB via sysctl."""

    @patch("scripts.profiling.report.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        """Converts bytes to GB correctly."""
        # 16 GB = 16 * 1024^3
        ram_bytes = 16 * (1024**3)
        mock_run.return_value = subprocess.CompletedProcess(["sysctl"], 0, stdout=f"{ram_bytes}\n")
        assert _ram_gb() == 16.0

    @patch("scripts.profiling.report.subprocess.run")
    def test_fractional_gb(self, mock_run: MagicMock) -> None:
        """Non-round GB values are returned as floats."""
        ram_bytes = 8 * (1024**3)
        mock_run.return_value = subprocess.CompletedProcess(["sysctl"], 0, stdout=f"{ram_bytes}\n")
        assert _ram_gb() == 8.0

    @patch("scripts.profiling.report.subprocess.run")
    def test_os_error_returns_zero(self, mock_run: MagicMock) -> None:
        """Returns 0 when sysctl is not available."""
        mock_run.side_effect = OSError("not found")
        assert _ram_gb() == 0

    @patch("scripts.profiling.report.subprocess.run")
    def test_called_process_error_returns_zero(self, mock_run: MagicMock) -> None:
        """Returns 0 when sysctl fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "sysctl")
        assert _ram_gb() == 0

    @patch("scripts.profiling.report.subprocess.run")
    def test_value_error_returns_zero(self, mock_run: MagicMock) -> None:
        """Returns 0 when sysctl output is not a valid integer."""
        mock_run.return_value = subprocess.CompletedProcess(["sysctl"], 0, stdout="not-a-number\n")
        assert _ram_gb() == 0


# ---------------------------------------------------------------------------
# _git_short_hash()
# ---------------------------------------------------------------------------


class TestGitShortHash:
    """Tests for _git_short_hash() — git short revision hash."""

    @patch("scripts.profiling.report.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        """Returns the stripped hash on success."""
        mock_run.return_value = subprocess.CompletedProcess(["git"], 0, stdout="abc1234\n")
        assert _git_short_hash() == "abc1234"

    @patch("scripts.profiling.report.subprocess.run")
    def test_strips_whitespace(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(["git"], 0, stdout="  deadbeef  \n")
        assert _git_short_hash() == "deadbeef"

    @patch("scripts.profiling.report.subprocess.run")
    def test_os_error_returns_unknown(self, mock_run: MagicMock) -> None:
        """Returns 'unknown' when git is not installed."""
        mock_run.side_effect = OSError("git not found")
        assert _git_short_hash() == "unknown"

    @patch("scripts.profiling.report.subprocess.run")
    def test_called_process_error_returns_unknown(self, mock_run: MagicMock) -> None:
        """Returns 'unknown' when not in a git repo."""
        mock_run.side_effect = subprocess.CalledProcessError(128, "git")
        assert _git_short_hash() == "unknown"
