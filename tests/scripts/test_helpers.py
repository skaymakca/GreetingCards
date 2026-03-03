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
