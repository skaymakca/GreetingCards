"""Tests for scripts/build_family_name_db/sources/smashew.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.build_family_name_db.sources.smashew import (
    _download_file,
    download_smashew_names,
    normalize,
)


class TestNormalize:
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("Smith", "smith"),
            ("JONES", "jones"),
            ("O'Brien", "obrien"),
            ("Müller", "muller"),
            ("García", "garcia"),
        ],
    )
    def test_normalize(self, input_name: str, expected: str) -> None:
        assert normalize(input_name) == expected


class TestDownloadFile:
    def test_returns_cached_content_when_exists(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "test.txt"
        cache_path.write_text("cached content", encoding="utf-8")

        with patch("scripts.build_family_name_db.sources.smashew.urlopen") as mock_urlopen:
            result = _download_file("https://example.com/file.txt", cache_path)
            mock_urlopen.assert_not_called()

        assert result == "cached content"

    def test_downloads_and_caches_when_missing(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "new.txt"
        content = "downloaded content"

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=content.encode("utf-8"))

        with patch("scripts.build_family_name_db.sources.smashew.urlopen", return_value=mock_resp):
            result = _download_file("https://example.com/file.txt", cache_path)

        assert result == content
        assert cache_path.exists()
        assert cache_path.read_text(encoding="utf-8") == content


class TestDownloadSmashewNames:
    def _make_mock_console(self) -> MagicMock:
        return MagicMock(spec=["print"])

    def test_parses_names_from_file(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        content = "Smith\nJones\nWilliams\n"

        with patch(
            "scripts.build_family_name_db.sources.smashew._download_file",
            return_value=content,
        ):
            result = download_smashew_names(console, tmp_path)

        assert "smith" in result
        assert "jones" in result
        assert "williams" in result

    def test_skips_names_shorter_than_2_chars(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        content = "A\nSmith\nB\n"

        with patch(
            "scripts.build_family_name_db.sources.smashew._download_file",
            return_value=content,
        ):
            result = download_smashew_names(console, tmp_path)

        assert "a" not in result
        assert "b" not in result
        assert "smith" in result

    def test_skips_comment_lines(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        content = "# This is a comment\nSmith\n"

        with patch(
            "scripts.build_family_name_db.sources.smashew._download_file",
            return_value=content,
        ):
            result = download_smashew_names(console, tmp_path)

        assert "smith" in result
        # The comment itself should not be a key
        keys = list(result.keys())
        assert not any(k.startswith("#") for k in keys)

    def test_download_error_warns_and_continues(self, tmp_path: Path) -> None:
        console = self._make_mock_console()

        def fake_download(url: str, path: Path) -> str:
            if "us.txt" in url:
                raise ConnectionError("network error")
            return "Smith\n"

        with patch(
            "scripts.build_family_name_db.sources.smashew._download_file",
            side_effect=fake_download,
        ):
            result = download_smashew_names(console, tmp_path)

        # Should still have results from other files
        assert isinstance(result, dict)

    def test_first_occurrence_wins(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        call_count = [0]

        def fake_download(url: str, path: Path) -> str:
            call_count[0] += 1
            # First file has "Smith", second has "SMITH"
            if call_count[0] == 1:
                return "Smith\n"
            return "SMITH\n"

        with patch(
            "scripts.build_family_name_db.sources.smashew._download_file",
            side_effect=fake_download,
        ):
            result = download_smashew_names(console, tmp_path)

        # First occurrence should win
        assert result.get("smith") == "Smith"
