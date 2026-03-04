"""Tests for scripts/run_tests.py — scope resolution and pytest arg building."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.run_tests import (
    _create_cov_dir,
    _generate_grouped_html,
    _generate_lcov,
    _parse_args,
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


# --- main ---


class TestMainFunction:
    def test_no_args_shows_help(self) -> None:
        result = main([])
        assert result == 0
