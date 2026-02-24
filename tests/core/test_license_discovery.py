"""Tests for license discovery helpers."""

from pathlib import Path

import pytest

from app.core.license_discovery import (
    _build_reverse_deps,
    _categorize_packages,
    _display_name,
    _parse_uv_lock,
    _slug,
    load_config,
)
from app.core.license_models import (
    LicenseConfig,
    PackageCategory,
    PackageOverride,
    SystemDep,
)


class TestLoadConfig:
    """Tests for load_config()."""

    def test_normal_config(self, tmp_path):
        config_toml = tmp_path / "config.toml"
        config_toml.write_text(
            'exclude = ["bar"]\n\n'
            '[[system]]\nslug = "python"\ndisplay = "Python"\n'
            'version = "3.14"\nlicense_type = "PSF"\n\n'
            '[[package]]\nname = "foo"\ndisplay = "Foo Lib"\n'
            'category = "Runtime"\n',
            encoding="utf-8",
        )
        config = load_config(tmp_path)
        assert len(config.system_deps) == 1
        assert config.system_deps[0].slug == "python"
        assert "foo" in config.package_overrides
        assert "bar" in config.exclude

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path)

    def test_empty_file(self, tmp_path):
        config_toml = tmp_path / "config.toml"
        config_toml.write_text("", encoding="utf-8")
        config = load_config(tmp_path)
        assert config.system_deps == []
        assert config.package_overrides == {}
        assert config.exclude == set()


class TestSlugAndDisplay:
    """Tests for _slug() and _display_name()."""

    def test_slug_normalization(self):
        assert _slug("PyMuPDF") == "pymupdf"
        assert _slug("my_package") == "my-package"
        assert _slug("some.dotted") == "some-dotted"

    def test_display_name_override(self):
        overrides = {"foo": PackageOverride(name="foo", display="Foo Library")}
        assert _display_name("foo", overrides) == "Foo Library"

    def test_display_name_no_override(self):
        assert _display_name("foo", {}) == "foo"


class TestCategorizePackages:
    """Tests for _categorize_packages()."""

    def test_runtime_categorization(self):
        packages = [{"name": "anthropic", "version": "1.0", "deps": []}]
        config = LicenseConfig(system_deps=[])
        cats = _categorize_packages(packages, set(), config, {"anthropic"})
        assert cats["anthropic"] == PackageCategory.RUNTIME

    def test_dev_categorization(self):
        packages = [{"name": "pytest", "version": "9.0", "deps": []}]
        config = LicenseConfig(system_deps=[])
        cats = _categorize_packages(packages, {"pytest"}, config, set())
        assert cats["pytest"] == PackageCategory.DEVELOPMENT

    def test_transitive_categorization(self):
        packages = [{"name": "anyio", "version": "4.0", "deps": []}]
        config = LicenseConfig(system_deps=[])
        cats = _categorize_packages(packages, set(), config, set())
        assert cats["anyio"] == PackageCategory.TRANSITIVE


class TestParseUvLock:
    """Tests for _parse_uv_lock()."""

    def test_normal_lock(self, tmp_path):
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text(
            "version = 1\n\n"
            '[[package]]\nname = "foo"\nversion = "1.0.0"\n\n'
            '[[package]]\nname = "bar"\nversion = "2.0.0"\n'
            '[[package.dependencies]]\nname = "foo"\n',
            encoding="utf-8",
        )
        packages = _parse_uv_lock(lock_file)
        assert len(packages) == 2
        assert packages[0]["name"] == "foo"
        assert packages[0]["version"] == "1.0.0"
        assert packages[1]["deps"] == ["foo"]

    def test_empty_lock(self, tmp_path):
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text("version = 1\n", encoding="utf-8")
        packages = _parse_uv_lock(lock_file)
        assert packages == []

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _parse_uv_lock(tmp_path / "nonexistent.lock")


class TestBuildReverseDeps:
    """Tests for _build_reverse_deps()."""

    def test_direct_deps(self):
        packages = [
            {"name": "app", "version": "1.0", "deps": ["foo", "bar"]},
            {"name": "foo", "version": "1.0", "deps": []},
            {"name": "bar", "version": "1.0", "deps": []},
        ]
        reverse = _build_reverse_deps(packages)
        assert "app" in reverse["foo"]
        assert "app" in reverse["bar"]

    def test_no_deps(self):
        packages = [
            {"name": "standalone", "version": "1.0", "deps": []},
        ]
        reverse = _build_reverse_deps(packages)
        assert reverse == {}

    def test_circular(self):
        packages = [
            {"name": "a", "version": "1.0", "deps": ["b"]},
            {"name": "b", "version": "1.0", "deps": ["a"]},
        ]
        reverse = _build_reverse_deps(packages)
        assert "a" in reverse["b"]
        assert "b" in reverse["a"]
