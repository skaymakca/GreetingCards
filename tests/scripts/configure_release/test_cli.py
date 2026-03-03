"""Tests for scripts/configure_release/cli.py."""

from __future__ import annotations

import pathlib
from unittest.mock import patch

import pytest
from scripts.configure_release.cli import configure, show_diff, write_script
from scripts.configure_release.generator import ReleaseConfig, generate_script
from scripts.configure_release.keychain import SigningIdentity
from scripts.configure_release.ui import UserInput

_DEV_ID = SigningIdentity(
    sha1="AABBCCDD11223344556677889900AABBCCDD1122",
    common_name="Developer ID Application: Test Corp (TEAM123)",
)
_APPLE_DEV = SigningIdentity(
    sha1="1122334455667788990011223344556677889900",
    common_name="Apple Development: dev@example.com (TEAM456)",
)


class _MockUI:
    """Test double for UserInput."""

    def __init__(self, choose_value: int = 0, ask_value: str = "GreetingCards") -> None:
        self.choose_value = choose_value
        self.ask_value = ask_value
        self.choose_calls: list[tuple[str, list[str], int | None]] = []
        self.ask_calls: list[tuple[str, str]] = []

    def choose(self, prompt: str, options: list[str], default: int | None = None) -> int:
        self.choose_calls.append((prompt, options, default))
        return self.choose_value if self.choose_value is not None else (default or 0)

    def ask(self, prompt: str, default: str = "") -> str:
        self.ask_calls.append((prompt, default))
        return self.ask_value

    def confirm(self, prompt: str, default: bool = True) -> bool:
        return default


# Verify _MockUI satisfies the UserInput protocol
_mock_ui_check: UserInput = _MockUI()


class TestConfigure:
    """Test the configure() orchestrator."""

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_selects_developer_id_by_default(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_APPLE_DEV, _DEV_ID]
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        ui = _MockUI()
        config = configure(ui)

        assert config.signing_identity == _APPLE_DEV.common_name
        # The default index should point to the Developer ID cert (index 1)
        assert ui.choose_calls[0][2] == 1

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_no_identities_exits(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = []
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        ui = _MockUI()
        with pytest.raises(SystemExit):
            configure(ui)

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_custom_profile(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_DEV_ID]
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        ui = _MockUI(ask_value="CustomProfile")
        config = configure(ui)

        assert config.keychain_profile == "CustomProfile"


class TestWriteScript:
    """Test file writing and permissions."""

    def test_write_script_creates_executable_file(self, tmp_path: pathlib.Path) -> None:
        config = ReleaseConfig(signing_identity="Test ID", keychain_profile="Test")
        output = tmp_path / "release-local.sh"

        write_script(config, output_path=output)

        assert output.exists()
        mode = output.stat().st_mode
        assert mode & 0o111  # executable bits set

    def test_write_script_content_matches_generator(self, tmp_path: pathlib.Path) -> None:
        config = ReleaseConfig(signing_identity="Test ID", keychain_profile="Test")
        output = tmp_path / "release-local.sh"

        write_script(config, output_path=output)

        expected = generate_script(config)
        actual = output.read_text(encoding="utf-8")
        assert actual == expected


class TestShowDiff:
    """Test colored diff output."""

    def test_show_diff_new_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        show_diff(None, "line1\nline2\n")

        captured = capsys.readouterr()
        assert "(new file)" in captured.out
        assert "+ line1" in captured.out
        assert "+ line2" in captured.out

    def test_show_diff_changed_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        show_diff("old line\n", "new line\n")

        captured = capsys.readouterr()
        assert "-old line" in captured.out
        assert "+new line" in captured.out

    def test_show_diff_unchanged(self, capsys: pytest.CaptureFixture[str]) -> None:
        content = "same content\n"
        show_diff(content, content)

        captured = capsys.readouterr()
        assert "No changes" in captured.out
