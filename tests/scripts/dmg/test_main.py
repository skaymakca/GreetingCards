"""Tests for scripts/dmg/__main__.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestReadVersion:
    def test_reads_version_from_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")

        with patch("scripts.dmg.__main__._ROOT", tmp_path):
            from scripts.dmg.__main__ import _read_version

            result = _read_version()

        assert result == "1.2.3"

    def test_reads_different_version(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "0.11.0"\n', encoding="utf-8")

        with patch("scripts.dmg.__main__._ROOT", tmp_path):
            from scripts.dmg.__main__ import _read_version

            result = _read_version()

        assert result == "0.11.0"


class TestMain:
    def test_calls_generate_background(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"

        with (
            patch("scripts.dmg.__main__._read_version", return_value="1.0.0"),
            patch("scripts.dmg.__main__._generate_background", return_value=bg_path) as mock_bg,
            patch("scripts.dmg.__main__._generate_readme", return_value=tmp_path / "readme.rtfd"),
            patch("scripts.dmg.__main__.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.__main__ import main

            main()

        mock_bg.assert_called_once()

    def test_calls_generate_readme(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.__main__._read_version", return_value="2.0.0"),
            patch("scripts.dmg.__main__._generate_background", return_value=bg_path),
            patch("scripts.dmg.__main__._generate_readme", return_value=readme_path) as mock_readme,
            patch("scripts.dmg.__main__.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.__main__ import main

            main()

        mock_readme.assert_called_once_with("2.0.0")

    def test_calls_dmgbuild(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.__main__._read_version", return_value="1.0.0"),
            patch("scripts.dmg.__main__._generate_background", return_value=bg_path),
            patch("scripts.dmg.__main__._generate_readme", return_value=readme_path),
            patch("scripts.dmg.__main__.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.__main__ import main

            main()

        mock_dmg.build_dmg.assert_called_once()

    def test_editable_flag_adds_udrw_format(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.__main__._read_version", return_value="1.0.0"),
            patch("scripts.dmg.__main__._generate_background", return_value=bg_path),
            patch("scripts.dmg.__main__._generate_readme", return_value=readme_path),
            patch("scripts.dmg.__main__.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg", "--editable"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.__main__ import main

            main()

        call_kwargs = mock_dmg.build_dmg.call_args
        defines = call_kwargs.kwargs.get("defines") or call_kwargs[1].get("defines") or call_kwargs[0][3]
        assert defines.get("format") == "UDRW"

    def test_no_editable_flag_no_udrw(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.__main__._read_version", return_value="1.0.0"),
            patch("scripts.dmg.__main__._generate_background", return_value=bg_path),
            patch("scripts.dmg.__main__._generate_readme", return_value=readme_path),
            patch("scripts.dmg.__main__.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.__main__ import main

            main()

        call_kwargs = mock_dmg.build_dmg.call_args
        defines = call_kwargs.kwargs.get("defines") or call_kwargs[1].get("defines")
        assert "format" not in (defines or {})
