"""Tests for scripts/dmg/cli.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestMain:
    def test_calls_generate_background(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"

        with (
            patch("scripts.dmg.cli.read_version", return_value="1.0.0"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path) as mock_bg,
            patch("scripts.dmg.cli._generate_readme", return_value=tmp_path / "readme.rtfd"),
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        mock_bg.assert_called_once()

    def test_calls_generate_readme(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.cli.read_version", return_value="2.0.0"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path),
            patch("scripts.dmg.cli._generate_readme", return_value=readme_path) as mock_readme,
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        mock_readme.assert_called_once_with("2.0.0")

    def test_calls_dmgbuild(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.cli.read_version", return_value="1.0.0"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path),
            patch("scripts.dmg.cli._generate_readme", return_value=readme_path),
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        mock_dmg.build_dmg.assert_called_once()

    def test_output_filename_uses_hyphens(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.cli.read_version", return_value="1.2.3"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path),
            patch("scripts.dmg.cli._generate_readme", return_value=readme_path),
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        call_kwargs = mock_dmg.build_dmg.call_args
        filename = call_kwargs.kwargs.get("filename") or call_kwargs[0][0]
        assert "Greeting-Cards-1.2.3.dmg" in filename
        assert "Greeting Cards -" not in filename

    def test_editable_flag_adds_udrw_format(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.cli.read_version", return_value="1.0.0"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path),
            patch("scripts.dmg.cli._generate_readme", return_value=readme_path),
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg", "--editable"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        call_kwargs = mock_dmg.build_dmg.call_args
        defines = call_kwargs.kwargs.get("defines") or call_kwargs[1].get("defines") or call_kwargs[0][3]
        assert defines.get("format") == "UDRW"

    def test_no_editable_flag_no_udrw(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.cli.read_version", return_value="1.0.0"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path),
            patch("scripts.dmg.cli._generate_readme", return_value=readme_path),
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        call_kwargs = mock_dmg.build_dmg.call_args
        defines = call_kwargs.kwargs.get("defines") or call_kwargs[1].get("defines")
        assert "format" not in (defines or {})

    def test_verify_signature_not_called_by_default(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.cli.read_version", return_value="1.0.0"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path),
            patch("scripts.dmg.cli._generate_readme", return_value=readme_path),
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("scripts.dmg.cli.verify_app_signature") as mock_verify,
            patch("sys.argv", ["dmg"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        mock_verify.assert_not_called()

    def test_verify_signature_called_with_flag(self, tmp_path: Path) -> None:
        bg_path = tmp_path / "background.png"
        readme_path = tmp_path / "Read Me.rtfd"

        with (
            patch("scripts.dmg.cli.read_version", return_value="1.0.0"),
            patch("scripts.dmg.cli._generate_background", return_value=bg_path),
            patch("scripts.dmg.cli._generate_readme", return_value=readme_path),
            patch("scripts.dmg.cli.dmgbuild") as mock_dmg,
            patch("scripts.dmg.cli.verify_app_signature") as mock_verify,
            patch("sys.argv", ["dmg", "--verify-signature"]),
        ):
            mock_dmg.build_dmg = MagicMock()
            from scripts.dmg.cli import main

            main()

        mock_verify.assert_called_once()


class TestVerifyAppSignature:
    def test_passes_when_codesign_succeeds(self, tmp_path: Path) -> None:
        bundle = tmp_path / "Test.app"
        bundle.mkdir()

        result = subprocess.CompletedProcess(args=["codesign"], returncode=0, stdout="", stderr="")
        with patch("scripts.dmg.cli.subprocess.run", return_value=result):
            from scripts.dmg.cli import verify_app_signature

            verify_app_signature(bundle)  # should not raise

    def test_exits_when_codesign_fails(self, tmp_path: Path) -> None:
        bundle = tmp_path / "Test.app"
        bundle.mkdir()

        result = subprocess.CompletedProcess(
            args=["codesign"],
            returncode=1,
            stdout="",
            stderr="code object is not signed at all",
        )
        with patch("scripts.dmg.cli.subprocess.run", return_value=result):
            from scripts.dmg.cli import verify_app_signature

            with pytest.raises(SystemExit, match="1"):
                verify_app_signature(bundle)
