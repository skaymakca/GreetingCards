"""Tests for scripts/configure_release/keychain.py."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from scripts.configure_release.keychain import SigningIdentity, find_signing_identities


class TestFindSigningIdentities:
    """Test Keychain identity scanning."""

    @patch("scripts.configure_release.keychain.subprocess.run")
    def test_parses_multiple_identities(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            stdout=(
                "  1) AABBCCDD11223344556677889900AABBCCDD1122 "
                '"Developer ID Application: Test Corp (TEAMID1)"\n'
                "  2) 1122334455667788990011223344556677889900 "
                '"Apple Development: dev@example.com (TEAMID2)"\n'
                "  2 valid identities found\n"
            )
        )

        result = find_signing_identities()

        assert len(result) == 2
        assert result[0] == SigningIdentity(
            sha1="AABBCCDD11223344556677889900AABBCCDD1122",
            common_name="Developer ID Application: Test Corp (TEAMID1)",
        )
        assert result[1] == SigningIdentity(
            sha1="1122334455667788990011223344556677889900",
            common_name="Apple Development: dev@example.com (TEAMID2)",
        )

    @patch("scripts.configure_release.keychain.subprocess.run")
    def test_single_identity(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            stdout=(
                "  1) AABBCCDD11223344556677889900AABBCCDD1122 "
                '"Developer ID Application: Test Corp (TEAMID1)"\n'
                "  1 valid identities found\n"
            )
        )

        result = find_signing_identities()

        assert len(result) == 1
        assert result[0].common_name == "Developer ID Application: Test Corp (TEAMID1)"

    @patch("scripts.configure_release.keychain.subprocess.run")
    def test_no_identities(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="  0 valid identities found\n")

        result = find_signing_identities()

        assert result == []

    @patch("scripts.configure_release.keychain.subprocess.run")
    def test_subprocess_error_returns_empty(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "security")

        result = find_signing_identities()

        assert result == []
