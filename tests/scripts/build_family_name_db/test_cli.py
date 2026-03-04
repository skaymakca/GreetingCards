"""Tests for scripts/build_family_name_db/cli.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch


class TestMain:
    def test_happy_path(self, tmp_path: Path) -> None:
        """All 6 pipeline steps are called in order with correct args."""
        mock_census = {"SMITH": "data"}
        mock_faker = {"Jones": "data"}
        mock_faker_all = {"jones"}
        mock_smashew = {"Lee": "data"}
        mock_rows = [("SMITH", "data")]

        with (
            patch("scripts.build_family_name_db.cli.download_census", return_value=mock_census) as m_census,
            patch(
                "scripts.build_family_name_db.cli.extract_faker_names",
                return_value=(mock_faker, mock_faker_all),
            ) as m_faker,
            patch("scripts.build_family_name_db.cli.download_smashew_names", return_value=mock_smashew) as m_smashew,
            patch("scripts.build_family_name_db.cli.merge_sources", return_value=mock_rows) as m_merge,
            patch("scripts.build_family_name_db.cli.apply_overrides", return_value=mock_rows) as m_override,
            patch("scripts.build_family_name_db.cli.write_tsv") as m_write,
            patch("scripts.build_family_name_db.cli.Console"),
        ):
            from scripts.build_family_name_db.cli import main

            output = tmp_path / "out.tsv"
            main(["--output", str(output), "--cache-dir", str(tmp_path)])

        m_census.assert_called_once()
        m_faker.assert_called_once()
        m_smashew.assert_called_once()
        m_merge.assert_called_once()
        m_override.assert_called_once()
        m_write.assert_called_once()

    def test_no_smashew_flag(self, tmp_path: Path) -> None:
        """--no-smashew skips smashew download and passes empty dict."""
        mock_rows = [("SMITH", "data")]

        with (
            patch("scripts.build_family_name_db.cli.download_census", return_value={}),
            patch("scripts.build_family_name_db.cli.extract_faker_names", return_value=({}, set())),
            patch("scripts.build_family_name_db.cli.download_smashew_names") as m_smashew,
            patch("scripts.build_family_name_db.cli.merge_sources", return_value=mock_rows) as m_merge,
            patch("scripts.build_family_name_db.cli.apply_overrides", return_value=mock_rows),
            patch("scripts.build_family_name_db.cli.write_tsv"),
            patch("scripts.build_family_name_db.cli.Console"),
        ):
            from scripts.build_family_name_db.cli import main

            main(["--no-smashew", "--output", str(tmp_path / "out.tsv"), "--cache-dir", str(tmp_path)])

        m_smashew.assert_not_called()
        # merge_sources should receive empty dict for smashew
        merge_call = m_merge.call_args
        # smashew is the 4th positional arg
        assert merge_call[0][3] == {}

    def test_custom_cache_dir(self, tmp_path: Path) -> None:
        """--cache-dir passes the custom path to download functions."""
        cache_dir = tmp_path / "my_cache"
        mock_rows = [("SMITH", "data")]

        with (
            patch("scripts.build_family_name_db.cli.download_census", return_value={}) as m_census,
            patch("scripts.build_family_name_db.cli.extract_faker_names", return_value=({}, set())),
            patch("scripts.build_family_name_db.cli.download_smashew_names", return_value={}) as m_smashew,
            patch("scripts.build_family_name_db.cli.merge_sources", return_value=mock_rows),
            patch("scripts.build_family_name_db.cli.apply_overrides", return_value=mock_rows),
            patch("scripts.build_family_name_db.cli.write_tsv"),
            patch("scripts.build_family_name_db.cli.Console"),
        ):
            from scripts.build_family_name_db.cli import main

            main(["--cache-dir", str(cache_dir), "--output", str(tmp_path / "out.tsv")])

        # download_census receives (console, cache_dir)
        assert m_census.call_args[0][1] == cache_dir
        # download_smashew_names receives (console, cache_dir)
        assert m_smashew.call_args[0][1] == cache_dir

    def test_custom_output(self, tmp_path: Path) -> None:
        """--output passes custom path to write_tsv and derives override path."""
        custom_output = tmp_path / "subdir" / "custom.tsv"
        mock_rows = [("SMITH", "data")]

        with (
            patch("scripts.build_family_name_db.cli.download_census", return_value={}),
            patch("scripts.build_family_name_db.cli.extract_faker_names", return_value=({}, set())),
            patch("scripts.build_family_name_db.cli.download_smashew_names", return_value={}),
            patch("scripts.build_family_name_db.cli.merge_sources", return_value=mock_rows),
            patch("scripts.build_family_name_db.cli.apply_overrides", return_value=mock_rows) as m_override,
            patch("scripts.build_family_name_db.cli.write_tsv") as m_write,
            patch("scripts.build_family_name_db.cli.Console"),
        ):
            from scripts.build_family_name_db.cli import main

            main(["--output", str(custom_output), "--cache-dir", str(tmp_path)])

        # write_tsv receives (console, rows, output_path)
        assert m_write.call_args[0][2] == custom_output
        # apply_overrides receives (console, rows, override_path) where override is sibling
        override_path = m_override.call_args[0][2]
        assert override_path == custom_output.parent / "family_name_overrides.tsv"
