"""Tests for app/core/sparkle.py — Sparkle auto-update bridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core import sparkle


class TestInit:
    """init() behavior in various environments."""

    def setup_method(self) -> None:
        """Reset module state before each test."""
        sparkle.cleanup()

    def test_not_bundled_returns_false(self) -> None:
        """init() returns False when running from source (not bundled)."""
        with patch("app.core.paths.is_bundled", return_value=False):
            assert sparkle.init() is False

    def test_framework_not_found_returns_false(self) -> None:
        """init() returns False when Sparkle.framework is not present."""
        with (
            patch("app.core.paths.is_bundled", return_value=True),
            patch("app.core.sparkle._get_frameworks_path", return_value=None),
        ):
            assert sparkle.init() is False

    def test_framework_path_missing_returns_false(self, tmp_path) -> None:
        """init() returns False when Frameworks dir exists but Sparkle.framework doesn't."""
        with (
            patch("app.core.paths.is_bundled", return_value=True),
            patch("app.core.sparkle._get_frameworks_path", return_value=tmp_path),
        ):
            assert sparkle.init() is False

    def test_successful_init(self, tmp_path) -> None:
        """init() returns True when framework loads successfully."""
        framework_dir = tmp_path / "Sparkle.framework"
        framework_dir.mkdir()

        mock_controller = MagicMock()
        mock_updater = MagicMock()
        mock_controller.updater.return_value = mock_updater

        mock_class = MagicMock()
        mock_class.alloc.return_value.initWithStartingUpdater_updaterDelegate_userDriverDelegate_.return_value = (
            mock_controller
        )

        mock_bundle = MagicMock()
        mock_bundle.load.return_value = True

        mock_nsbundle = MagicMock()
        mock_nsbundle.bundleWithPath_.return_value = mock_bundle

        with (
            patch("app.core.paths.is_bundled", return_value=True),
            patch("app.core.sparkle._get_frameworks_path", return_value=tmp_path),
            patch.dict("sys.modules", {"Foundation": MagicMock(NSBundle=mock_nsbundle)}),
            patch("objc.lookUpClass", return_value=mock_class),
        ):
            assert sparkle.init() is True
            assert sparkle.is_available() is True

    def test_bundle_load_failure(self, tmp_path) -> None:
        """init() returns False when bundle.load() fails."""
        framework_dir = tmp_path / "Sparkle.framework"
        framework_dir.mkdir()

        mock_bundle = MagicMock()
        mock_bundle.load.return_value = False

        mock_nsbundle = MagicMock()
        mock_nsbundle.bundleWithPath_.return_value = mock_bundle

        with (
            patch("app.core.paths.is_bundled", return_value=True),
            patch("app.core.sparkle._get_frameworks_path", return_value=tmp_path),
            patch.dict("sys.modules", {"Foundation": MagicMock(NSBundle=mock_nsbundle)}),
        ):
            assert sparkle.init() is False


class TestCheckForUpdates:
    """check_for_updates() safety."""

    def setup_method(self) -> None:
        sparkle.cleanup()

    def test_noop_when_not_initialized(self) -> None:
        """check_for_updates() is a safe no-op when controller is None."""
        sparkle.check_for_updates()  # Should not raise

    def test_exception_is_caught(self) -> None:
        """Exception from controller.checkForUpdates_ is caught and logged."""
        mock_ctrl = MagicMock()
        mock_ctrl.checkForUpdates_.side_effect = RuntimeError("boom")
        sparkle._controller = mock_ctrl
        sparkle.check_for_updates()  # Should not raise
        sparkle._controller = None


class TestIsAvailable:
    """is_available() reflects init state."""

    def setup_method(self) -> None:
        sparkle.cleanup()

    def test_false_before_init(self) -> None:
        assert sparkle.is_available() is False

    def test_false_after_failed_init(self) -> None:
        with patch("app.core.paths.is_bundled", return_value=False):
            sparkle.init()
        assert sparkle.is_available() is False


class TestAutoCheckPreference:
    """get/set_auto_check_enabled() behavior."""

    def setup_method(self) -> None:
        sparkle.cleanup()

    def test_default_when_not_available(self) -> None:
        """Returns True when Sparkle is not available."""
        assert sparkle.get_auto_check_enabled() is True

    def test_set_noop_when_not_available(self) -> None:
        """set_auto_check_enabled() is a safe no-op when not available."""
        sparkle.set_auto_check_enabled(False)  # Should not raise

    def test_get_auto_check_exception_returns_true(self) -> None:
        """Exception from updater returns True as safe default."""
        mock_updater = MagicMock()
        mock_updater.automaticallyChecksForUpdates.side_effect = RuntimeError("boom")
        sparkle._updater = mock_updater
        assert sparkle.get_auto_check_enabled() is True
        sparkle._updater = None

    def test_set_auto_check_exception_is_caught(self) -> None:
        """Exception from updater.setAutomaticallyChecksForUpdates_ is caught."""
        mock_updater = MagicMock()
        mock_updater.setAutomaticallyChecksForUpdates_.side_effect = RuntimeError("boom")
        sparkle._updater = mock_updater
        sparkle.set_auto_check_enabled(False)  # Should not raise
        sparkle._updater = None


class TestStart:
    """start() behavior."""

    def setup_method(self) -> None:
        sparkle.cleanup()

    def test_noop_when_not_initialized(self) -> None:
        """start() is a safe no-op when controller is None."""
        sparkle.start()  # Should not raise

    def test_exception_is_caught(self) -> None:
        """Exception from controller.startUpdater() is caught and logged."""
        mock_ctrl = MagicMock()
        mock_ctrl.startUpdater.side_effect = RuntimeError("boom")
        sparkle._controller = mock_ctrl
        sparkle.start()  # Should not raise
        sparkle._controller = None


class TestGetFrameworksPath:
    """_get_frameworks_path() behavior."""

    def test_no_meipass_returns_none(self) -> None:
        """Returns None when not running as a PyInstaller bundle."""
        had = hasattr(sparkle.sys, "_MEIPASS")
        if had:
            saved = sparkle.sys._MEIPASS  # type: ignore[attr-defined]
            delattr(sparkle.sys, "_MEIPASS")
        try:
            assert sparkle._get_frameworks_path() is None
        finally:
            if had:
                sparkle.sys._MEIPASS = saved  # type: ignore[attr-defined]

    def test_with_meipass_returns_frameworks(self, tmp_path) -> None:
        """Returns Frameworks path when _MEIPASS is set and dir exists."""
        contents = tmp_path / "Contents"
        resources = contents / "Resources"
        resources.mkdir(parents=True)
        frameworks = contents / "Frameworks"
        frameworks.mkdir()

        with patch.object(sparkle.sys, "_MEIPASS", str(resources), create=True):
            result = sparkle._get_frameworks_path()
            assert result == frameworks

    def test_with_meipass_no_frameworks_dir(self, tmp_path) -> None:
        """Returns None when Frameworks directory doesn't exist."""
        contents = tmp_path / "Contents"
        resources = contents / "Resources"
        resources.mkdir(parents=True)

        with patch.object(sparkle.sys, "_MEIPASS", str(resources), create=True):
            assert sparkle._get_frameworks_path() is None


class TestCleanup:
    """cleanup() behavior."""

    def test_resets_state(self) -> None:
        """cleanup() resets module state."""
        sparkle.cleanup()
        assert sparkle.is_available() is False

    def test_safe_to_call_multiple_times(self) -> None:
        """cleanup() can be called multiple times safely."""
        sparkle.cleanup()
        sparkle.cleanup()
        assert sparkle.is_available() is False
