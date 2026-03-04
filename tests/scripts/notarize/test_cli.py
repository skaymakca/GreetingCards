"""Tests for scripts/notarize/cli.py."""

from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from scripts.notarize.cli import (
    check_status,
    fetch_history,
    fetch_log,
    load_submission_id,
    save_submission_id,
    staple,
    submit,
    verify,
)


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
            stdout="  id: abc-def-123\n  message: Successfully uploaded file\n",
            stderr="",
        )

        result = submit(tmp_path / "test.dmg", "TestProfile")
        assert result == "abc-def-123"

    @patch("scripts.notarize.cli.subprocess.run")
    def test_no_wait_flag(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        """submit() must NOT pass --wait (async workflow)."""
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  id: abc-123\n",
            stderr="",
        )

        submit(tmp_path / "test.dmg", "MyProfile")

        cmd = mock_run.call_args[0][0]
        assert "--wait" not in cmd

    @patch("scripts.notarize.cli.subprocess.run")
    def test_submit_calls_notarytool(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  id: abc-123\n",
            stderr="",
        )

        submit(tmp_path / "test.dmg", "MyProfile")

        cmd = mock_run.call_args[0][0]
        assert "notarytool" in cmd
        assert "submit" in cmd
        assert "--keychain-profile" in cmd
        assert "MyProfile" in cmd

    @patch("scripts.notarize.cli.subprocess.run")
    def test_missing_id_raises_system_exit(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  some output without an id\n",
            stderr="",
        )

        with pytest.raises(SystemExit):
            submit(tmp_path / "test.dmg", "TestProfile")


class TestSaveLoadSubmissionId:
    def test_round_trip(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "submission-id.txt"
        save_submission_id("abc-def-123", path)
        assert load_submission_id(path) == "abc-def-123"

    def test_creates_parent_dirs(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "deep" / "nested" / "submission-id.txt"
        save_submission_id("xyz-789", path)
        assert path.exists()
        assert load_submission_id(path) == "xyz-789"

    def test_missing_file_raises_error(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            load_submission_id(path)


class TestCheckStatus:
    @patch("scripts.notarize.cli.subprocess.run")
    def test_returns_status_string(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  id: abc-123\n  status: Accepted\n",
            stderr="",
        )

        result = check_status("abc-123", "TestProfile")
        assert result == "Accepted"

    @patch("scripts.notarize.cli.subprocess.run")
    def test_calls_notarytool_info(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="status: In Progress\n", stderr="")

        check_status("abc-123", "MyProfile")

        cmd = mock_run.call_args[0][0]
        assert "notarytool" in cmd
        assert "info" in cmd
        assert "abc-123" in cmd
        assert "--keychain-profile" in cmd
        assert "MyProfile" in cmd

    @patch("scripts.notarize.cli.subprocess.run")
    def test_dry_run_returns_none(self, mock_run: MagicMock) -> None:
        result = check_status("abc-123", "TestProfile", dry_run=True)
        assert result is None
        mock_run.assert_not_called()


class TestFetchLog:
    @patch("scripts.notarize.cli.subprocess.run")
    def test_calls_notarytool_log(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0)

        fetch_log("abc-123", "MyProfile")

        cmd = mock_run.call_args[0][0]
        assert "notarytool" in cmd
        assert "log" in cmd
        assert "abc-123" in cmd
        assert "--keychain-profile" in cmd

    @patch("scripts.notarize.cli.subprocess.run")
    def test_dry_run_skips(self, mock_run: MagicMock) -> None:
        fetch_log("abc-123", "TestProfile", dry_run=True)
        mock_run.assert_not_called()

    @patch("scripts.notarize.cli.subprocess.run")
    def test_log_not_available_exits_gracefully(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(69, ["xcrun", "notarytool", "log"])

        with pytest.raises(SystemExit, match="1"):
            fetch_log("abc-123", "TestProfile")


class TestFetchHistory:
    @patch("scripts.notarize.cli.subprocess.run")
    def test_calls_notarytool_history(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="  id: aaa-111\n", stderr="")

        fetch_history("MyProfile")

        cmd = mock_run.call_args[0][0]
        assert "notarytool" in cmd
        assert "history" in cmd
        assert "--keychain-profile" in cmd
        assert "MyProfile" in cmd

    @patch("scripts.notarize.cli.subprocess.run")
    def test_returns_first_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="  id: aaa-bbb-000\n  id: ccc-ddd-111\n  id: eee-fff-222\n",
            stderr="",
        )

        result = fetch_history("TestProfile")
        assert result == "aaa-bbb-000"

    @patch("scripts.notarize.cli.subprocess.run")
    def test_returns_none_when_no_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="No submissions found.\n", stderr="")

        result = fetch_history("TestProfile")
        assert result is None

    @patch("scripts.notarize.cli.subprocess.run")
    def test_dry_run_returns_none(self, mock_run: MagicMock) -> None:
        result = fetch_history("TestProfile", dry_run=True)
        assert result is None
        mock_run.assert_not_called()


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
    def test_submit_dry_run(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run", "submit"]),
            patch("scripts.notarize.cli.read_version", return_value="1.0.0"),
            patch("scripts.notarize.cli.dmg_path") as mock_dmg_path,
            patch("scripts.notarize.cli.submit", return_value=None) as mock_submit,
        ):
            mock_dmg_path.return_value = pathlib.Path("/fake/test.dmg")
            from scripts.notarize.cli import main

            main()

        mock_submit.assert_called_once()
        assert mock_submit.call_args.kwargs["dry_run"] is True

    def test_staple_dry_run(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run", "staple"]),
            patch("scripts.notarize.cli.read_version", return_value="1.0.0"),
            patch("scripts.notarize.cli.dmg_path") as mock_dmg_path,
            patch("scripts.notarize.cli.app_path") as mock_app_path,
            patch("scripts.notarize.cli.load_submission_id", return_value="abc-123"),
            patch("scripts.notarize.cli.check_status", return_value=None) as mock_status,
            patch("scripts.notarize.cli.staple") as mock_staple,
            patch("scripts.notarize.cli.verify") as mock_verify,
        ):
            mock_dmg_path.return_value = pathlib.Path("/fake/test.dmg")
            mock_app_path.return_value = pathlib.Path("/fake/Test.app")
            from scripts.notarize.cli import main

            main()

        mock_status.assert_called_once()
        mock_staple.assert_called_once()
        mock_verify.assert_called_once()

    def test_status_with_explicit_id(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run", "status", "--submission-id", "xyz-789"]),
            patch("scripts.notarize.cli.check_status", return_value=None) as mock_status,
        ):
            from scripts.notarize.cli import main

            main()

        assert mock_status.call_args[0][0] == "xyz-789"

    def test_log_subcommand(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run", "log", "--submission-id", "abc-123"]),
            patch("scripts.notarize.cli.fetch_log") as mock_log,
        ):
            from scripts.notarize.cli import main

            main()

        mock_log.assert_called_once()
        assert mock_log.call_args[0][0] == "abc-123"

    def test_custom_keychain_profile(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--keychain-profile", "CustomProfile", "--dry-run", "submit"]),
            patch("scripts.notarize.cli.read_version", return_value="1.0.0"),
            patch("scripts.notarize.cli.dmg_path") as mock_dmg_path,
            patch("scripts.notarize.cli.submit", return_value=None) as mock_submit,
        ):
            mock_dmg_path.return_value = pathlib.Path("/fake/test.dmg")
            from scripts.notarize.cli import main

            main()

        assert mock_submit.call_args[0][1] == "CustomProfile"

    def test_missing_dmg_errors_on_submit(self, tmp_path: pathlib.Path) -> None:
        fake_dmg = tmp_path / "dist" / "Greeting-Cards-1.0.0.dmg"

        with (
            patch("sys.argv", ["notarize", "submit"]),
            patch("scripts.notarize.cli.read_version", return_value="1.0.0"),
            patch("scripts.notarize.cli.dmg_path", return_value=fake_dmg),
            pytest.raises(SystemExit, match="1"),
        ):
            from scripts.notarize.cli import main

            main()

    def test_status_falls_back_to_history(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run", "status"]),
            patch("scripts.notarize.cli.load_submission_id", side_effect=FileNotFoundError),
            patch("scripts.notarize.cli.fetch_history", return_value="history-id-999") as mock_hist,
            patch("scripts.notarize.cli.save_submission_id") as mock_save,
            patch("scripts.notarize.cli.check_status", return_value=None) as mock_status,
        ):
            from scripts.notarize.cli import main

            main()

        mock_hist.assert_called_once()
        mock_save.assert_called_once_with("history-id-999")
        assert mock_status.call_args[0][0] == "history-id-999"

    def test_status_fallback_no_history_errors(self) -> None:
        with (
            patch("sys.argv", ["notarize", "--dry-run", "status"]),
            patch("scripts.notarize.cli.load_submission_id", side_effect=FileNotFoundError),
            patch("scripts.notarize.cli.fetch_history", return_value=None),
            pytest.raises(SystemExit, match="1"),
        ):
            from scripts.notarize.cli import main

            main()

    def test_no_subcommand_errors(self) -> None:
        with (
            patch("sys.argv", ["notarize"]),
            pytest.raises(SystemExit, match="2"),
        ):
            from scripts.notarize.cli import main

            main()
