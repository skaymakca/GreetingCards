"""Tests for app.core.keychain module."""

import logging
from unittest.mock import patch

import pytest

from app.core.keychain import delete_api_key, get_api_key, save_api_key

# OSStatus constants
_errSecSuccess = 0
_errSecItemNotFound = -25300


class TestGetApiKey:
    """Tests for get_api_key()."""

    @patch("app.core.keychain.SecItemCopyMatching")
    def test_returns_key_when_found(self, mock_copy):
        mock_copy.return_value = (_errSecSuccess, b"sk-test-key")
        assert get_api_key() == "sk-test-key"

    @patch("app.core.keychain.SecItemCopyMatching")
    def test_returns_none_when_not_found(self, mock_copy):
        mock_copy.return_value = (_errSecItemNotFound, None)
        assert get_api_key() is None

    @patch("app.core.keychain.SecItemCopyMatching")
    def test_returns_none_when_result_empty(self, mock_copy):
        mock_copy.return_value = (_errSecSuccess, None)
        assert get_api_key() is None


class TestSaveApiKey:
    """Tests for save_api_key()."""

    @patch("app.core.keychain.SecItemAdd")
    @patch("app.core.keychain.SecItemUpdate")
    def test_inserts_new_key(self, mock_update, mock_add):
        mock_update.return_value = _errSecItemNotFound
        mock_add.return_value = (_errSecSuccess, None)
        save_api_key("sk-new-key")
        mock_add.assert_called_once()

    @patch("app.core.keychain.SecItemUpdate")
    def test_updates_existing_key(self, mock_update):
        mock_update.return_value = _errSecSuccess
        save_api_key("sk-updated-key")
        mock_update.assert_called_once()

    @patch("app.core.keychain.SecItemAdd")
    @patch("app.core.keychain.SecItemUpdate")
    def test_raises_on_failure(self, mock_update, mock_add):
        mock_update.return_value = _errSecItemNotFound
        mock_add.return_value = (-1, None)
        with pytest.raises(OSError, match="Failed to save API key"):
            save_api_key("sk-key")

    @patch("app.core.keychain.SecItemAdd")
    @patch("app.core.keychain.SecItemUpdate")
    def test_strips_whitespace(self, mock_update, mock_add):
        mock_update.return_value = _errSecItemNotFound
        mock_add.return_value = (_errSecSuccess, None)
        save_api_key("  sk-padded  ")
        # The value data in the add call should be stripped
        add_attrs = mock_add.call_args[0][0]
        from Security import kSecValueData  # type: ignore[import-untyped]

        assert add_attrs[kSecValueData] == b"sk-padded"


class TestDeleteApiKey:
    """Tests for delete_api_key()."""

    @patch("app.core.keychain.SecItemDelete")
    def test_succeeds(self, mock_delete):
        mock_delete.return_value = _errSecSuccess
        delete_api_key()
        mock_delete.assert_called_once()

    @patch("app.core.keychain.SecItemDelete")
    def test_ignores_not_found(self, mock_delete):
        mock_delete.return_value = _errSecItemNotFound
        delete_api_key()  # Should not raise

    @patch("app.core.keychain.SecItemDelete")
    def test_logs_error_on_failure(self, mock_delete, caplog):
        mock_delete.return_value = -1
        with caplog.at_level(logging.ERROR, logger="app.core.keychain"):
            delete_api_key()
        assert "Keychain delete failed" in caplog.text
