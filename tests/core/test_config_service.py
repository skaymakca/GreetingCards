"""Tests for app.core.config_service module."""

from unittest.mock import patch

from app.core.config_service import ConfigService


class TestConfigService:
    """Verify ConfigService delegates to config module functions."""

    @patch("app.core.config_service.get_api_key", return_value="sk-test")
    def test_get_api_key(self, mock_get):
        assert ConfigService.get_api_key() == "sk-test"
        mock_get.assert_called_once()

    @patch("app.core.config_service.save_api_key")
    def test_save_api_key(self, mock_save):
        ConfigService.save_api_key("sk-new")
        mock_save.assert_called_once_with("sk-new")

    @patch("app.core.config_service.get_api_key", return_value="sk-test")
    def test_has_api_key_true(self, mock_get):
        assert ConfigService.has_api_key() is True

    @patch("app.core.config_service.get_api_key", return_value=None)
    def test_has_api_key_false(self, mock_get):
        assert ConfigService.has_api_key() is False

    @patch("app.core.config_service.get_ai_model", return_value="claude-sonnet-4-6")
    def test_get_ai_model(self, mock_get):
        assert ConfigService.get_ai_model() == "claude-sonnet-4-6"
        mock_get.assert_called_once()

    @patch("app.core.config_service.save_ai_model")
    def test_save_ai_model(self, mock_save):
        ConfigService.save_ai_model("claude-haiku-4-5")
        mock_save.assert_called_once_with("claude-haiku-4-5")
