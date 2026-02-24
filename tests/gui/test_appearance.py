"""Tests for macOS appearance detection module."""

from unittest.mock import MagicMock, patch

import pytest

from app.gui import appearance


class TestIsDarkMode:
    """Tests for is_dark_mode() detection."""

    @pytest.mark.unit
    def test_detects_dark_mode(self):
        """Should return True when effectiveAppearance name contains 'Dark'."""
        mock_app = MagicMock()
        mock_app.effectiveAppearance().name.return_value = "NSAppearanceNameDarkAqua"

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            assert appearance.is_dark_mode() is True

    @pytest.mark.unit
    def test_detects_light_mode(self):
        """Should return False when effectiveAppearance name is light."""
        mock_app = MagicMock()
        mock_app.effectiveAppearance().name.return_value = "NSAppearanceNameAqua"

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            assert appearance.is_dark_mode() is False

    @pytest.mark.unit
    def test_returns_false_on_error(self):
        """Should return False if AppKit call raises an exception."""
        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.side_effect = RuntimeError("no app")
            assert appearance.is_dark_mode() is False


class TestObserver:
    """Tests for start_observer / stop_observer lifecycle."""

    @pytest.fixture(autouse=True)
    def _reset_observer(self):
        """Ensure observer state is clean before/after each test."""
        appearance._observer = None
        yield
        appearance._observer = None

    @pytest.mark.unit
    def test_start_observer_registers_kvo(self):
        """Should call addObserver on NSApp with correct key path."""
        mock_app = MagicMock()
        callback = MagicMock()

        with (
            patch.object(appearance, "NSApplication") as mock_ns,
            patch.object(appearance, "_AppearanceObserver") as mock_cls,
        ):
            mock_ns.sharedApplication.return_value = mock_app
            mock_observer_instance = MagicMock()
            mock_cls.alloc.return_value.init.return_value = mock_observer_instance

            appearance.start_observer(callback)

            mock_app.addObserver_forKeyPath_options_context_.assert_called_once()
            args = mock_app.addObserver_forKeyPath_options_context_.call_args[0]
            assert args[0] is mock_observer_instance
            assert args[1] == "effectiveAppearance"

    @pytest.mark.unit
    def test_stop_observer_removes_kvo(self):
        """Should call removeObserver on NSApp."""
        mock_app = MagicMock()
        mock_observer_instance = MagicMock()
        appearance._observer = mock_observer_instance

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            appearance.stop_observer()

        mock_app.removeObserver_forKeyPath_.assert_called_once_with(mock_observer_instance, "effectiveAppearance")
        assert appearance._observer is None

    @pytest.mark.unit
    def test_stop_observer_noop_when_not_started(self):
        """Should be safe to call stop_observer when no observer is active."""
        appearance.stop_observer()  # Should not raise
        assert appearance._observer is None

    @pytest.mark.unit
    def test_start_observer_ignores_duplicate(self):
        """Should not register a second observer if one is already active."""
        appearance._observer = MagicMock()  # Simulate already started
        mock_app = MagicMock()

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            appearance.start_observer(MagicMock())

        mock_app.addObserver_forKeyPath_options_context_.assert_not_called()
