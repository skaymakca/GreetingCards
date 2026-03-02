"""Tests for scripts/run_tests.py — scope resolution and pytest arg building."""

from __future__ import annotations

from pathlib import Path

from scripts.run_tests import build_pytest_args, resolve_scopes

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
