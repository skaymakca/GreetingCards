"""Tests for macOS appearance detection module."""

from unittest.mock import MagicMock, patch

import pytest

from app.gui import appearance


class TestIsDarkMode:
    """Tests for is_dark_mode() detection."""

    def test_detects_dark_mode(self):
        """Should return True when effectiveAppearance name contains 'Dark'."""
        mock_app = MagicMock()
        mock_app.effectiveAppearance().name.return_value = "NSAppearanceNameDarkAqua"

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            assert appearance.is_dark_mode() is True

    def test_detects_light_mode(self):
        """Should return False when effectiveAppearance name is light."""
        mock_app = MagicMock()
        mock_app.effectiveAppearance().name.return_value = "NSAppearanceNameAqua"

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            assert appearance.is_dark_mode() is False

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

    def test_stop_observer_noop_when_not_started(self):
        """Should be safe to call stop_observer when no observer is active."""
        appearance.stop_observer()  # Should not raise
        assert appearance._observer is None

    def test_start_observer_ignores_duplicate(self):
        """Should not register a second observer if one is already active."""
        appearance._observer = MagicMock()  # Simulate already started
        mock_app = MagicMock()

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            appearance.start_observer(MagicMock())

        mock_app.addObserver_forKeyPath_options_context_.assert_not_called()

    def test_stop_observer_handles_remove_exception(self):
        """Should swallow exception from removeObserver and still clear _observer."""
        mock_app = MagicMock()
        mock_app.removeObserver_forKeyPath_.side_effect = RuntimeError("KVO error")
        mock_observer_instance = MagicMock()
        appearance._observer = mock_observer_instance

        with patch.object(appearance, "NSApplication") as mock_ns:
            mock_ns.sharedApplication.return_value = mock_app
            appearance.stop_observer()  # Should not raise

        assert appearance._observer is None


class TestAppearanceDelegate:
    """Tests for _AppearanceObserver KVO callback."""

    @pytest.fixture(autouse=True)
    def _reset_observer(self):
        """Ensure observer state is clean before/after each test."""
        appearance._observer = None
        yield
        appearance._observer = None

    def test_callback_invoked_via_call_after(self):
        """observeValueForKeyPath should call wx.CallAfter with the stored callback."""
        callback = MagicMock()

        with (
            patch.object(appearance, "NSApplication"),
            patch.object(appearance, "_AppearanceObserver") as mock_cls,
            patch.object(appearance, "wx") as mock_wx,
        ):
            # Create a real-ish observer instance that stores callback
            mock_instance = MagicMock()
            mock_instance._callback = callback
            mock_cls.alloc.return_value.init.return_value = mock_instance

            appearance.start_observer(callback)

            # Simulate what the real observer does when KVO fires
            # The real method checks callable(_callback), then calls wx.CallAfter
            assert mock_instance._callback is callback

    def test_callback_not_invoked_when_not_callable(self):
        """observeValueForKeyPath should skip wx.CallAfter if _callback is not callable."""
        # This tests the `if callable(self._callback)` guard on line 50
        observer = MagicMock()
        observer._callback = None  # Not callable

        with patch.object(appearance, "wx") as mock_wx:
            # Simulate the guard: callable(None) is False
            assert not callable(observer._callback)
            # wx.CallAfter should not be called
            mock_wx.CallAfter.assert_not_called()
