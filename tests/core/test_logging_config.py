"""Tests for app.core.logging_config module."""

import logging

from app.core.logging_config import LOG_FORMAT


class TestLoggingConfig:
    """Tests for root logger configuration."""

    def test_log_format_contains_required_fields(self) -> None:
        """LOG_FORMAT includes timestamp, level, name, and message."""
        assert "%(asctime)s" in LOG_FORMAT
        assert "%(levelname)s" in LOG_FORMAT
        assert "%(name)s" in LOG_FORMAT
        assert "%(message)s" in LOG_FORMAT

    def test_root_logger_level(self) -> None:
        """Root logger should be configured at INFO level."""
        root = logging.getLogger()
        assert root.level <= logging.INFO
