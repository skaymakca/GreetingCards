"""Tests for scripts/run_tests.py — scope resolution and pytest arg building."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.run_tests import (
    _create_cov_dir,
    _generate_grouped_html,
    _generate_lcov,
    _open_coverage,
    _parse_args,
    _print_coverage_locations,
    _print_help,
    _update_latest_symlink,
    build_pytest_args,
    main,
    resolve_scopes,
)

# --- resolve_scopes ---


class TestResolveScopes:
    """Tests for resolve_scopes()."""

    def test_empty_list_returns_no_directories(self) -> None:
        result = resolve_scopes([])
        assert result.directories == []
        assert result.run_integration is False

    def test_default_scope_expands_to_core_gui_scripts(self) -> None:
        result = resolve_scopes(["default"])
        assert result.directories == ["tests/core/", "tests/gui/", "tests/scripts/"]
        assert result.run_integration is False

    def test_core_scope(self) -> None:
        result = resolve_scopes(["core"])
        assert result.directories == ["tests/core/"]
        assert result.run_integration is False

    def test_gui_scope(self) -> None:
        result = resolve_scopes(["gui"])
        assert result.directories == ["tests/gui/"]
        assert result.run_integration is False

    def test_scripts_scope(self) -> None:
        result = resolve_scopes(["scripts"])
        assert result.directories == ["tests/scripts/"]
        assert result.run_integration is False

    def test_integration_scope_sets_flag(self) -> None:
        result = resolve_scopes(["integration"])
        assert result.directories == ["tests/integration/"]
        assert result.run_integration is True

    def test_all_scope_includes_everything(self) -> None:
        result = resolve_scopes(["all"])
        assert result.directories == [
            "tests/core/",
            "tests/gui/",
            "tests/scripts/",
            "tests/integration/",
        ]
        assert result.run_integration is True

    def test_combine_gui_and_scripts(self) -> None:
        result = resolve_scopes(["gui", "scripts"])
        assert result.directories == ["tests/gui/", "tests/scripts/"]
        assert result.run_integration is False

    def test_combine_core_and_integration(self) -> None:
        result = resolve_scopes(["core", "integration"])
        assert result.directories == ["tests/core/", "tests/integration/"]
        assert result.run_integration is True

    def test_deduplication(self) -> None:
        result = resolve_scopes(["core", "core"])
        assert result.directories == ["tests/core/"]

    def test_default_and_extra_scope_deduplicates(self) -> None:
        result = resolve_scopes(["default", "core"])
        # core already included via default, should not appear twice
        assert result.directories == ["tests/core/", "tests/gui/", "tests/scripts/"]

    def test_unknown_scope_ignored(self) -> None:
        result = resolve_scopes(["nonexistent"])
        assert result.directories == []
        assert result.run_integration is False

    def test_unknown_scope_mixed_with_valid(self) -> None:
        result = resolve_scopes(["core", "nonexistent", "gui"])
        assert result.directories == ["tests/core/", "tests/gui/"]


# --- build_pytest_args ---


class TestBuildPytestArgs:
    """Tests for build_pytest_args()."""

    def test_basic_directories(self) -> None:
        args = build_pytest_args(directories=["tests/core/"])
        assert args == ["tests/core/"]

    def test_multiple_directories(self) -> None:
        args = build_pytest_args(directories=["tests/core/", "tests/gui/"])
        assert args == ["tests/core/", "tests/gui/"]

    def test_run_integration_flag(self) -> None:
        args = build_pytest_args(directories=["tests/integration/"], run_integration=True)
        assert "--run-integration" in args
        assert "tests/integration/" in args

    def test_stop_first(self) -> None:
        args = build_pytest_args(directories=["tests/core/"], stop_first=True)
        assert "-x" in args

    def test_keyword_filter(self) -> None:
        args = build_pytest_args(directories=["tests/core/"], keyword="family_name")
        assert "-k" in args
        idx = args.index("-k")
        assert args[idx + 1] == "family_name"

    def test_coverage_args(self) -> None:
        cov_dir = Path("/tmp/test_cov")
        args = build_pytest_args(
            directories=["tests/core/"],
            coverage=True,
            cov_run_dir=cov_dir,
        )
        assert "--cov=app" in args
        assert "--cov=scripts" in args
        assert "--cov-report=term-missing" in args
        assert f"--cov-report=html:{cov_dir / 'htmlcov'}" in args

    def test_coverage_without_dir_is_noop(self) -> None:
        args = build_pytest_args(directories=["tests/core/"], coverage=True, cov_run_dir=None)
        # No coverage args when cov_run_dir is None
        assert "--cov=app" not in args

    def test_all_options_combined(self) -> None:
        cov_dir = Path("/tmp/test_cov")
        args = build_pytest_args(
            directories=["tests/core/", "tests/integration/"],
            run_integration=True,
            coverage=True,
            cov_run_dir=cov_dir,
            stop_first=True,
            keyword="apple",
        )
        assert "--cov=app" in args
        assert "--run-integration" in args
        assert "-x" in args
        assert "-k" in args
        # Directories always at end
        assert args[-2:] == ["tests/core/", "tests/integration/"]

    def test_directories_at_end(self) -> None:
        """Directories should always be the last arguments."""
        args = build_pytest_args(
            directories=["tests/gui/"],
            stop_first=True,
            keyword="test_toolbar",
        )
        assert args[-1] == "tests/gui/"


# --- _parse_args ---


class TestParseArgs:
    def test_cov_flag(self) -> None:
        args = _parse_args(["default", "--cov"])
        assert args.cov is True

    def test_open_implies_cov(self) -> None:
        args = _parse_args(["default", "--open"])
        assert args.open_cov is True

    def test_keyword(self) -> None:
        args = _parse_args(["core", "-k", "family"])
        assert args.keyword == "family"


# --- coverage helpers ---


class TestCreateCovDir:
    def test_creates_timestamped_directory(self, tmp_path: Path) -> None:
        with (
            patch("scripts.run_tests.COV_DIR", tmp_path),
            patch("scripts.run_tests.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260303T1422"
            result = _create_cov_dir()

        assert result == tmp_path / "20260303T1422"
        assert result.is_dir()


class TestUpdateLatestSymlink:
    def test_creates_symlink(self, tmp_path: Path) -> None:
        cov_run = tmp_path / "20260303T1422"
        cov_run.mkdir()

        with patch("scripts.run_tests.COV_DIR", tmp_path):
            _update_latest_symlink(cov_run)

        latest = tmp_path / "latest"
        assert latest.is_symlink()
        assert latest.resolve() == cov_run


class TestGenerateLcov:
    def test_runs_coverage_lcov_command(self, tmp_path: Path) -> None:
        with patch("scripts.run_tests.subprocess.run") as mock_run:
            _generate_lcov(tmp_path)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "coverage" in cmd
        assert "lcov" in cmd


class TestGenerateGroupedHtml:
    def test_genhtml_missing_skips(self, tmp_path: Path) -> None:
        with (
            patch("scripts.run_tests.shutil.which", return_value=None),
            patch("scripts.run_tests.subprocess.run") as mock_run,
        ):
            _generate_grouped_html(tmp_path)

        mock_run.assert_not_called()

    def test_genhtml_available_runs_command(self, tmp_path: Path) -> None:
        mock_result = MagicMock(returncode=0)
        with (
            patch("scripts.run_tests.shutil.which", return_value="/usr/local/bin/genhtml"),
            patch("scripts.run_tests.subprocess.run", return_value=mock_result) as mock_run,
        ):
            _generate_grouped_html(tmp_path)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/local/bin/genhtml"
        assert str(tmp_path / "coverage.lcov") in cmd
        assert "-o" in cmd
        assert str(tmp_path / "htmlcov-grouped") in cmd
        assert "--hierarchical" in cmd

    def test_genhtml_failure_prints_error(self, tmp_path: Path, capsys: object) -> None:
        mock_result = MagicMock(returncode=1)
        mock_result.stderr = b"some genhtml error"
        with (
            patch("scripts.run_tests.shutil.which", return_value="/usr/local/bin/genhtml"),
            patch("scripts.run_tests.subprocess.run", return_value=mock_result),
        ):
            _generate_grouped_html(tmp_path)  # should not raise

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert "genhtml failed" in captured.out
        assert "some genhtml error" in captured.out


# --- _open_coverage ---


class TestOpenCoverage:
    def test_opens_flat_html(self, tmp_path: Path) -> None:
        flat = tmp_path / "htmlcov" / "index.html"
        flat.parent.mkdir()
        flat.write_text("<html></html>")

        with patch("scripts.run_tests.webbrowser.open") as mock_open:
            _open_coverage(tmp_path)

        mock_open.assert_called_once_with(f"file://{flat}")

    def test_opens_grouped_html(self, tmp_path: Path) -> None:
        flat = tmp_path / "htmlcov" / "index.html"
        flat.parent.mkdir()
        flat.write_text("<html></html>")

        grouped = tmp_path / "htmlcov-grouped" / "index.html"
        grouped.parent.mkdir()
        grouped.write_text("<html></html>")

        with patch("scripts.run_tests.webbrowser.open") as mock_open:
            _open_coverage(tmp_path)

        assert mock_open.call_count == 2
        calls = [c[0][0] for c in mock_open.call_args_list]
        assert f"file://{flat}" in calls
        assert f"file://{grouped}" in calls


# --- _print_help ---


class TestPrintHelp:
    def test_prints_usage(self, capsys: object) -> None:
        _print_help()

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert "Scopes:" in captured.out
        assert "Examples:" in captured.out
        assert "Options:" in captured.out
        assert "--cov" in captured.out
        assert "default" in captured.out


# --- main ---


class TestPrintCoverageLocations:
    def test_prints_flat_html_path(self, tmp_path: Path, capsys: object) -> None:
        """Lines 195-197: prints flat HTML path even without grouped dir."""
        htmlcov = tmp_path / "htmlcov"
        htmlcov.mkdir()

        _print_coverage_locations(tmp_path)

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert str(tmp_path) in captured.out
        assert "Flat HTML:" in captured.out
        assert "Grouped HTML:" not in captured.out

    def test_prints_grouped_html_when_present(self, tmp_path: Path, capsys: object) -> None:
        """Lines 198-200: grouped dir exists, prints both paths."""
        htmlcov = tmp_path / "htmlcov"
        htmlcov.mkdir()
        grouped = tmp_path / "htmlcov-grouped"
        grouped.mkdir()

        _print_coverage_locations(tmp_path)

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert "Flat HTML:" in captured.out
        assert "Grouped HTML:" in captured.out
        assert str(grouped / "index.html") in captured.out


class TestMainFunction:
    def test_no_args_shows_help(self) -> None:
        result = main([])
        assert result == 0

    def test_default_scope(self) -> None:
        """Lines 275-304, 316: main() with default scope runs pytest with correct dirs."""
        mock_result = MagicMock(returncode=0)
        with patch("scripts.run_tests.subprocess.run", return_value=mock_result) as mock_run:
            rc = main(["default"])

        assert rc == 0
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        # Should contain pytest and the default test directories
        assert "-m" in cmd
        assert "pytest" in cmd
        assert "tests/core/" in cmd
        assert "tests/gui/" in cmd
        assert "tests/scripts/" in cmd

    def test_with_coverage_flag(self, tmp_path: Path) -> None:
        """Lines 289-314: --cov enables coverage processing after pytest."""
        mock_result = MagicMock(returncode=0)
        with (
            patch("scripts.run_tests.subprocess.run", return_value=mock_result),
            patch("scripts.run_tests._create_cov_dir", return_value=tmp_path) as mock_cov_dir,
            patch("scripts.run_tests._generate_lcov") as mock_lcov,
            patch("scripts.run_tests._generate_grouped_html") as mock_grouped,
            patch("scripts.run_tests._update_latest_symlink") as mock_symlink,
            patch("scripts.run_tests._print_coverage_locations") as mock_print_cov,
        ):
            rc = main(["core", "--cov"])

        assert rc == 0
        mock_cov_dir.assert_called_once()
        mock_lcov.assert_called_once_with(tmp_path)
        mock_grouped.assert_called_once_with(tmp_path)
        mock_symlink.assert_called_once_with(tmp_path)
        mock_print_cov.assert_called_once_with(tmp_path)

    def test_open_flag_implies_cov(self, tmp_path: Path) -> None:
        """Lines 278-279: --open implies --cov."""
        mock_result = MagicMock(returncode=0)
        with (
            patch("scripts.run_tests.subprocess.run", return_value=mock_result),
            patch("scripts.run_tests._create_cov_dir", return_value=tmp_path),
            patch("scripts.run_tests._generate_lcov"),
            patch("scripts.run_tests._generate_grouped_html"),
            patch("scripts.run_tests._update_latest_symlink"),
            patch("scripts.run_tests._print_coverage_locations"),
            patch("scripts.run_tests._open_coverage") as mock_open_cov,
        ):
            rc = main(["core", "--open"])

        assert rc == 0
        # --open implies --cov, so _open_coverage should be called
        mock_open_cov.assert_called_once_with(tmp_path)

    def test_invalid_scope_returns_1(self, capsys: object) -> None:
        """Lines 283-286: invalid scope prints error and returns 1."""
        rc = main(["nonexistent_scope"])

        assert rc == 1
        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert "no valid scopes" in captured.err


class TestMainDefaultArgv:
    """Test main() with None argv (uses sys.argv)."""

    def test_default_argv_shows_help(self) -> None:
        """main(None) with sys.argv=['run_tests.py'] shows help and returns 0."""
        with patch("sys.argv", ["run_tests.py"]):
            rc = main(None)
        assert rc == 0


class TestUpdateLatestSymlinkReplacesExisting:
    def test_replaces_existing_symlink(self, tmp_path: Path) -> None:
        """Line 150: existing symlink is replaced with new target."""
        old_target = tmp_path / "20260101T0000"
        old_target.mkdir()
        new_target = tmp_path / "20260303T1422"
        new_target.mkdir()

        latest = tmp_path / "latest"
        latest.symlink_to(old_target.name)
        assert latest.resolve() == old_target

        with patch("scripts.run_tests.COV_DIR", tmp_path):
            _update_latest_symlink(new_target)

        assert latest.is_symlink()
        assert latest.resolve() == new_target
