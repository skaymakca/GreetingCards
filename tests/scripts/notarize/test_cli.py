"""Tests for scripts/notarize/cli.py."""

from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from scripts.notarize.cli import staple, submit, verify


class TestSubmit:
    @patch("scripts.notarize.cli.subprocess.run")
    def test_dry_run_returns_none(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        result = submit(tmp_path / "test.dmg", "TestProfile", dry_run=True)
        assert result is None
        mock_run.assert_not_called()

    @patch("scripts.notarize.cli.subprocess.run")
    def test_parses_submission_id(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  id: abc-def-123\n  status: Accepted\n",
            stderr="",
        )

        result = submit(tmp_path / "test.dmg", "TestProfile")
        assert result == "abc-def-123"

    @patch("scripts.notarize.cli.subprocess.run")
    def test_failure_raises_system_exit(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  id: abc-def-123\n  status: Invalid\n",
            stderr="",
        )

        with pytest.raises(SystemExit):
            submit(tmp_path / "test.dmg", "TestProfile")

    @patch("scripts.notarize.cli.subprocess.run")
    def test_submit_calls_notarytool(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  id: abc-123\n  status: Accepted\n",
            stderr="",
        )

        submit(tmp_path / "test.dmg", "MyProfile")

        cmd = mock_run.call_args[0][0]
        assert "notarytool" in cmd
        assert "submit" in cmd
        assert "--keychain-profile" in cmd
        assert "MyProfile" in cmd
        assert "--wait" in cmd


class TestStaple:
    @patch("scripts.notarize.cli.subprocess.run")
    def test_staples_app_and_dmg(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        app = tmp_path / "Test.app"
        dmg = tmp_path / "Test.dmg"

        staple(app, dmg)

        assert mock_run.call_count == 2
        first_cmd = mock_run.call_args_list[0][0][0]
        second_cmd = mock_run.call_args_list[1][0][0]
        assert "stapler" in first_cmd
        assert str(app) in first_cmd
        assert str(dmg) in second_cmd

    @patch("scripts.notarize.cli.subprocess.run")
    def test_dry_run_skips(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        staple(tmp_path / "a.app", tmp_path / "a.dmg", dry_run=True)
        mock_run.assert_not_called()


class TestVerify:
    @patch("scripts.notarize.cli.subprocess.run")
    def test_calls_spctl(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        verify(tmp_path / "Test.app")

        cmd = mock_run.call_args[0][0]
        assert "spctl" in cmd
        assert "--assess" in cmd
        assert "--type" in cmd
        assert "execute" in cmd

    @patch("scripts.notarize.cli.subprocess.run")
    def test_dry_run_skips(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        verify(tmp_path / "Test.app", dry_run=True)
        mock_run.assert_not_called()


class TestMain:
    def test_dry_run_succeeds(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run"]),
            patch("scripts.notarize.cli.submit") as mock_submit,
            patch("scripts.notarize.cli.staple") as mock_staple,
            patch("scripts.notarize.cli.verify") as mock_verify,
        ):
            from scripts.notarize.cli import main

            main()

        mock_submit.assert_called_once()
        assert mock_submit.call_args.kwargs["dry_run"] is True
        mock_staple.assert_called_once()
        mock_verify.assert_called_once()

    def test_custom_keychain_profile(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run", "--keychain-profile", "CustomProfile"]),
            patch("scripts.notarize.cli.submit") as mock_submit,
            patch("scripts.notarize.cli.staple"),
            patch("scripts.notarize.cli.verify"),
        ):
            from scripts.notarize.cli import main

            main()

        assert mock_submit.call_args[0][1] == "CustomProfile"

    def test_missing_dmg_errors(self, tmp_path: pathlib.Path) -> None:
        """main() calls parser.error when DMG file doesn't exist."""
        fake_dmg = tmp_path / "dist" / "Greeting-Cards-1.0.0.dmg"

        with (
            patch("sys.argv", ["notarize"]),
            patch("scripts.notarize.cli.read_version", return_value="1.0.0"),
            patch("scripts.notarize.cli.dmg_path", return_value=fake_dmg),
            patch("scripts.notarize.cli.app_path", return_value=tmp_path / "Test.app"),
            pytest.raises(SystemExit, match="2"),
        ):
            from scripts.notarize.cli import main

            main()

    def test_missing_app_bundle_errors(self, tmp_path: pathlib.Path) -> None:
        """main() calls parser.error when app bundle doesn't exist."""
        # Create the DMG so it passes that check
        fake_dmg = tmp_path / "dist" / "Greeting-Cards-1.0.0.dmg"
        fake_dmg.parent.mkdir(parents=True)
        fake_dmg.write_bytes(b"dmg")

        fake_app = tmp_path / "dist" / "Greeting Cards.app"
        # Don't create the app bundle — it should fail

        with (
            patch("sys.argv", ["notarize"]),
            patch("scripts.notarize.cli.read_version", return_value="1.0.0"),
            patch("scripts.notarize.cli.dmg_path", return_value=fake_dmg),
            patch("scripts.notarize.cli.app_path", return_value=fake_app),
            pytest.raises(SystemExit, match="2"),
        ):
            from scripts.notarize.cli import main

            main()
