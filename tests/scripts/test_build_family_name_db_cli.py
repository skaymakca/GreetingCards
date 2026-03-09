"""Tests for scripts/build_family_name_db/cli.py — default cache dir edge case."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.build_family_name_db.cli import main


class TestDefaultCacheDir:
    """When --cache-dir is not provided, main() uses a system temp directory."""

    @patch("scripts.build_family_name_db.cli.write_tsv")
    @patch("scripts.build_family_name_db.cli.apply_overrides")
    @patch("scripts.build_family_name_db.cli.merge_sources")
    @patch("scripts.build_family_name_db.cli.download_smashew_names")
    @patch("scripts.build_family_name_db.cli.extract_faker_names")
    @patch("scripts.build_family_name_db.cli.download_census")
    def test_default_cache_dir_uses_tempdir(
        self,
        mock_census: MagicMock,
        mock_faker: MagicMock,
        mock_smashew: MagicMock,
        mock_merge: MagicMock,
        mock_overrides: MagicMock,
        mock_write: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Without --cache-dir, a tempfile.mkdtemp directory is used and passed to downloaders."""
        mock_census.return_value = {}
        mock_faker.return_value = ({}, set())
        mock_smashew.return_value = {}
        mock_merge.return_value = []
        mock_overrides.return_value = []

        output = tmp_path / "out.tsv"

        with patch("scripts.build_family_name_db.cli.tempfile.mkdtemp") as mock_mkdtemp:
            fake_temp = tmp_path / "family_name_db_tmp"
            fake_temp.mkdir()
            mock_mkdtemp.return_value = str(fake_temp)

            main(["--output", str(output)])

        # tempfile.mkdtemp should have been called with the expected prefix
        mock_mkdtemp.assert_called_once_with(prefix="family_name_db_")

        # The temp dir should have been passed to census and smashew downloaders
        census_cache_arg = mock_census.call_args[0][1]
        assert census_cache_arg == fake_temp

        smashew_cache_arg = mock_smashew.call_args[0][1]
        assert smashew_cache_arg == fake_temp

    @patch("scripts.build_family_name_db.cli.write_tsv")
    @patch("scripts.build_family_name_db.cli.apply_overrides")
    @patch("scripts.build_family_name_db.cli.merge_sources")
    @patch("scripts.build_family_name_db.cli.download_smashew_names")
    @patch("scripts.build_family_name_db.cli.extract_faker_names")
    @patch("scripts.build_family_name_db.cli.download_census")
    def test_explicit_cache_dir_creates_and_uses_it(
        self,
        mock_census: MagicMock,
        mock_faker: MagicMock,
        mock_smashew: MagicMock,
        mock_merge: MagicMock,
        mock_overrides: MagicMock,
        mock_write: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With --cache-dir, the specified directory is created and used."""
        mock_census.return_value = {}
        mock_faker.return_value = ({}, set())
        mock_smashew.return_value = {}
        mock_merge.return_value = []
        mock_overrides.return_value = []

        cache = tmp_path / "my_cache"
        output = tmp_path / "out.tsv"

        main(["--output", str(output), "--cache-dir", str(cache)])

        # The explicit cache dir should exist (created by main)
        assert cache.exists()
        assert cache.is_dir()

        # The explicit dir should have been passed to census and smashew
        census_cache_arg = mock_census.call_args[0][1]
        assert census_cache_arg == cache

        smashew_cache_arg = mock_smashew.call_args[0][1]
        assert smashew_cache_arg == cache
