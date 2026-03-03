"""Tests for scripts/helpers.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_make_output_dir_creates_timestamped_dir(tmp_path: Path) -> None:
    from scripts.helpers import _make_output_dir

    with patch("scripts.helpers.SCRIPT_OUTPUT_ROOT", tmp_path):
        result = _make_output_dir("my_script")

    assert result.exists()
    assert result.is_dir()
    # Name format: YYYYMMDDThhmm-my_script
    assert result.name.endswith("-my_script")
    prefix = result.name.split("-")[0]
    assert len(prefix) == 13  # YYYYMMDDThhmm
    assert prefix[8] == "T"


def test_make_output_dir_creates_under_root(tmp_path: Path) -> None:
    from scripts.helpers import _make_output_dir

    with patch("scripts.helpers.SCRIPT_OUTPUT_ROOT", tmp_path):
        result = _make_output_dir("test")

    assert result.parent == tmp_path


def test_script_output_dir_yields_path(tmp_path: Path) -> None:
    from scripts.helpers import script_output_dir

    with patch("scripts.helpers.SCRIPT_OUTPUT_ROOT", tmp_path), script_output_dir("my_script") as output_dir:
        assert output_dir.exists()
        assert output_dir.is_dir()


def test_script_output_dir_keeps_non_empty_dir_on_success(tmp_path: Path) -> None:
    from scripts.helpers import script_output_dir

    with patch("scripts.helpers.SCRIPT_OUTPUT_ROOT", tmp_path), script_output_dir("my_script") as output_dir:
        (output_dir / "file.txt").write_text("content")

    assert output_dir.exists()


def test_script_output_dir_keeps_non_empty_dir_on_exception(tmp_path: Path) -> None:
    from scripts.helpers import script_output_dir

    captured_dir: Path | None = None
    try:
        with patch("scripts.helpers.SCRIPT_OUTPUT_ROOT", tmp_path), script_output_dir("my_script") as output_dir:
            captured_dir = output_dir
            (output_dir / "file.txt").write_text("content")
            raise ValueError("test error")
    except ValueError:
        pass

    # Non-empty directory must be kept even after exception
    assert captured_dir is not None
    assert captured_dir.exists()


def test_script_output_dir_removes_empty_dir_on_exception(tmp_path: Path) -> None:
    from scripts.helpers import script_output_dir

    captured_dir: Path | None = None
    try:
        with patch("scripts.helpers.SCRIPT_OUTPUT_ROOT", tmp_path), script_output_dir("my_script") as output_dir:
            captured_dir = output_dir
            raise ValueError("test error")
    except ValueError:
        pass

    # Empty directory must be cleaned up on exception
    assert captured_dir is not None
    assert not captured_dir.exists()


def test_script_output_dir_reraises_exception(tmp_path: Path) -> None:
    from scripts.helpers import script_output_dir

    with (
        patch("scripts.helpers.SCRIPT_OUTPUT_ROOT", tmp_path),
        pytest.raises(RuntimeError, match="boom"),
        script_output_dir("my_script"),
    ):
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# PROJECT_ROOT
# ---------------------------------------------------------------------------


def test_project_root_is_absolute() -> None:
    from scripts.helpers import PROJECT_ROOT

    assert PROJECT_ROOT.is_absolute()


def test_project_root_contains_pyproject_toml() -> None:
    from scripts.helpers import PROJECT_ROOT

    assert (PROJECT_ROOT / "pyproject.toml").exists()


# ---------------------------------------------------------------------------
# read_version()
# ---------------------------------------------------------------------------


def test_read_version_returns_string() -> None:
    from scripts.helpers import read_version

    version = read_version()
    assert isinstance(version, str)
    # Should look like a semver string (digits and dots)
    parts = version.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


# ---------------------------------------------------------------------------
# app_path()
# ---------------------------------------------------------------------------


def test_app_path_ends_with_app_bundle() -> None:
    from scripts.helpers import app_path

    result = app_path()
    assert result.name == "Greeting Cards.app"
    assert result.parent.name == "dist"


# ---------------------------------------------------------------------------
# dmg_path()
# ---------------------------------------------------------------------------


def test_dmg_path_with_explicit_version() -> None:
    from scripts.helpers import dmg_path

    result = dmg_path("1.2.3")
    assert result.name == "Greeting-Cards-1.2.3.dmg"
    assert result.parent.name == "dist"


def test_dmg_path_without_version_reads_pyproject() -> None:
    from scripts.helpers import dmg_path, read_version

    version = read_version()
    result = dmg_path()
    assert result.name == f"Greeting-Cards-{version}.dmg"
