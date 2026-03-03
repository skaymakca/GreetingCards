"""Tests for scripts/configure_release/cli.py."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from scripts.configure_release.cli import configure, main, show_diff, write_script
from scripts.configure_release.generator import ExistingConfig, ReleaseConfig, generate_script
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

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_no_developer_id_cert(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_APPLE_DEV]  # No "Developer ID Application:" cert
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        ui = _MockUI()
        config = configure(ui)

        assert config.signing_identity == _APPLE_DEV.common_name
        # No auto-default should be set
        assert ui.choose_calls[0][2] is None


class TestConfigureWithExisting:
    """Test re-run detection in configure()."""

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_with_existing_shows_keep_option(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_DEV_ID]
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        existing = ExistingConfig(signing_identity="Old Identity (OLD)")
        ui = _MockUI(choose_value=0)
        configure(ui, existing=existing)

        # The first option should be "Keep current: ..."
        options = ui.choose_calls[0][1]
        assert options[0] == "Keep current: Old Identity (OLD)"
        # Default should be 0 (the "Keep current" option)
        assert ui.choose_calls[0][2] == 0

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_keep_current_identity(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_DEV_ID]
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        existing = ExistingConfig(signing_identity="Old Identity (OLD)")
        ui = _MockUI(choose_value=0)  # Select "Keep current"
        config = configure(ui, existing=existing)

        assert config.signing_identity == "Old Identity (OLD)"

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_existing_new_selection(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_APPLE_DEV, _DEV_ID]
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        existing = ExistingConfig(signing_identity="Old Identity (OLD)")
        ui = _MockUI(choose_value=1)  # Select first real identity (index 1 = _APPLE_DEV)
        config = configure(ui, existing=existing)

        # Index 1 with "Keep current" prepended maps to identities[0] = _APPLE_DEV
        assert config.signing_identity == _APPLE_DEV.common_name

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_existing_profile_default(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_DEV_ID]
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        existing = ExistingConfig(keychain_profile="ExistingProfile")
        ui = _MockUI(choose_value=0, ask_value="ExistingProfile")
        configure(ui, existing=existing)

        # The ask() call should use the existing profile as default
        assert ui.ask_calls[0][1] == "ExistingProfile"

    @patch("scripts.configure_release.cli.find_signing_identities")
    def test_configure_no_existing_uses_default_profile(self, mock_find: object) -> None:
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.return_value = [_DEV_ID]
        mock_find.return_value = mock.return_value  # type: ignore[union-attr]

        ui = _MockUI()
        configure(ui)

        # Without existing config, default should be "GreetingCards"
        assert ui.ask_calls[0][1] == "GreetingCards"


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

    def test_write_script_overwrites_existing(self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
        output = tmp_path / "release-local.sh"
        output.write_text("#!/bin/bash\n# old content\n", encoding="utf-8")

        config = ReleaseConfig(signing_identity="New ID", keychain_profile="New")
        write_script(config, output_path=output)

        actual = output.read_text(encoding="utf-8")
        assert 'CODESIGN_IDENTITY="New ID"' in actual
        # Should show a diff, not "new file"
        captured = capsys.readouterr()
        assert "(new file)" not in captured.out


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

    def test_show_diff_context_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        old = "line1\nline2\nline3\n"
        new = "line1\nchanged\nline3\n"
        show_diff(old, new)

        captured = capsys.readouterr()
        # Should contain the @@ header and unchanged context lines
        assert "@@" in captured.out
        assert "line1" in captured.out
        assert "line3" in captured.out

    def test_show_diff_unchanged(self, capsys: pytest.CaptureFixture[str]) -> None:
        content = "same content\n"
        show_diff(content, content)

        captured = capsys.readouterr()
        assert "No changes" in captured.out


class TestMain:
    """Test the main() entry point."""

    @patch("scripts.configure_release.cli.write_script")
    @patch("scripts.configure_release.cli.configure")
    @patch("scripts.configure_release.cli.InteractiveInput")
    @patch("scripts.configure_release.cli.find_signing_identities")
    @patch("scripts.configure_release.cli._OUTPUT_PATH")
    def test_main_reads_existing_script(
        self,
        mock_path: MagicMock,
        mock_find: MagicMock,
        mock_interactive: MagicMock,
        mock_configure: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        # Simulate an existing release-local.sh
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = (
            'export CODESIGN_IDENTITY="Existing ID"\nKEYCHAIN_PROFILE="ExistingProfile"\n'
        )

        mock_configure.return_value = ReleaseConfig(signing_identity="Existing ID", keychain_profile="ExistingProfile")

        main()

        # configure() should receive an ExistingConfig with parsed values
        call_args = mock_configure.call_args
        existing_arg = call_args.kwargs.get("existing") or call_args[1].get("existing")
        assert existing_arg is not None
        assert existing_arg.signing_identity == "Existing ID"
        assert existing_arg.keychain_profile == "ExistingProfile"

    @patch("scripts.configure_release.cli.write_script")
    @patch("scripts.configure_release.cli.configure")
    @patch("scripts.configure_release.cli.InteractiveInput")
    @patch("scripts.configure_release.cli.find_signing_identities")
    @patch("scripts.configure_release.cli._OUTPUT_PATH")
    def test_main_no_existing_script(
        self,
        mock_path: MagicMock,
        mock_find: MagicMock,
        mock_interactive: MagicMock,
        mock_configure: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        mock_path.exists.return_value = False

        mock_configure.return_value = ReleaseConfig(signing_identity="New ID", keychain_profile="GreetingCards")

        main()

        # configure() should receive existing=None
        call_args = mock_configure.call_args
        existing_arg = call_args.kwargs.get("existing") or call_args[1].get("existing")
        assert existing_arg is None
