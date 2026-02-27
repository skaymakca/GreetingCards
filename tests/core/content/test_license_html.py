"""Tests for app.core.content.license_html — HTML generation pipeline."""

from unittest.mock import patch

import app.core.content.license_sync as ls
from app.core.content.license_html import (
    _build_nav_items,
    _category_page_for,
    _linkify,
    get_page_order,
)
from app.core.content.license_models import PackageCategory


class TestLinkify:
    """Tests for _linkify()."""

    def test_plain_url(self):
        result = _linkify("Visit https://example.com for more info")
        assert '<a href="https://example.com">' in str(result)
        assert "Visit" in str(result)

    def test_no_url(self):
        result = _linkify("No URLs here")
        assert str(result) == "No URLs here"

    def test_html_escaping(self):
        result = _linkify("<script>alert('xss')</script>")
        assert "<script>" not in str(result)
        assert "&lt;script&gt;" in str(result)


class TestCategoryPageFor:
    """Tests for _category_page_for()."""

    def test_runtime(self):
        assert _category_page_for(PackageCategory.RUNTIME) == "runtime.html"

    def test_development(self):
        assert _category_page_for(PackageCategory.DEVELOPMENT) == "development.html"

    def test_transitive(self):
        assert _category_page_for(PackageCategory.TRANSITIVE) == "transitive.html"

    def test_unknown_category_fallback(self):
        """Unknown category falls back to transitive.html."""
        from unittest.mock import MagicMock

        fake_cat = MagicMock()
        assert _category_page_for(fake_cat) == "transitive.html"


class TestGetPageOrder:
    """Tests for get_page_order() and _build_nav_items()."""

    def test_returns_manifest_when_exists(self, tmp_path):
        manifest = tmp_path / "licenses" / "page_order.txt"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("index.html\nruntime.html\n", encoding="utf-8")
        result = get_page_order(tmp_path / "licenses")
        assert result == ["index.html", "runtime.html"]

    def test_fallback_when_no_manifest(self, tmp_path):
        """Falls back to hardcoded nav order when manifest is missing."""
        result = get_page_order(tmp_path)
        assert "index.html" in result
        assert "runtime.html" in result
        assert len(result) == 6

    def test_build_nav_items(self):
        items = _build_nav_items()
        assert len(items) == 6
        slugs = [item["slug"] for item in items]
        assert "index" in slugs
        assert "runtime" in slugs
        assert "transitive" in slugs


class TestGenerateLicensesHtml:
    """Tests for generate_licenses_html() and _write_html()."""

    def test_full_pipeline(self, tmp_path):
        """Integration test: generate_licenses_html() creates all HTML files."""
        # Set up directory structure
        source_dir = tmp_path / "content" / "licenses"
        source_dir.mkdir(parents=True)
        manual_dir = source_dir / "manual"
        manual_dir.mkdir()

        # Minimal config.toml
        (source_dir / "config.toml").write_text(
            '[[system]]\nslug = "python"\ndisplay = "Python"\nversion = "3.14"\nlicense_type = "PSF"\n',
            encoding="utf-8",
        )
        (manual_dir / "python.txt").write_text("Python Software Foundation License", encoding="utf-8")

        # Create a fake LICENSE file
        (tmp_path / "LICENSE").write_text("BSD 3-Clause License\n\nCopyright ...", encoding="utf-8")

        # Create uv.lock with minimal content
        lock_content = (
            "version = 1\n\n"
            '[[package]]\nname = "greeting-cards"\nversion = "0.9.0"\n\n'
            '[[package.dependencies]]\nname = "anthropic"\n\n'
            '[[package]]\nname = "anthropic"\nversion = "0.50.0"\n'
        )
        (tmp_path / "uv.lock").write_text(lock_content, encoding="utf-8")

        # Create pyproject.toml
        (tmp_path / "pyproject.toml").write_text("[dependency-groups]\ndev = []\n", encoding="utf-8")

        # Create fake site-packages with dist-info
        site_packages = tmp_path / "site-packages"
        site_packages.mkdir()
        dist_info = site_packages / "anthropic-0.50.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Name: anthropic\nVersion: 0.50.0\nLicense: MIT\n"
            "Project-URL: Homepage, https://github.com/anthropics/anthropic-sdk-python\n",
            encoding="utf-8",
        )
        (dist_info / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...", encoding="utf-8")

        build_dir = tmp_path / "_build" / "licenses"

        with (
            patch.object(ls, "__file__", str(tmp_path / "app" / "core" / "content" / "license_sync.py")),
            patch("app.core.content.license_sync._get_site_packages", return_value=site_packages),
        ):
            from app.core.content.license_html import generate_licenses_html

            generate_licenses_html()

        html_dir = tmp_path / "_build" / "runtime_content" / "html" / "licenses"
        assert html_dir.exists()
        assert (html_dir / "index.html").exists()
        assert (html_dir / "greeting-cards.html").exists()
        assert (html_dir / "system.html").exists()
        assert (html_dir / "runtime.html").exists()
        assert (html_dir / "development.html").exists()
        assert (html_dir / "transitive.html").exists()
        assert (html_dir / "page_order.txt").exists()

        # Verify index has package info
        index = (html_dir / "index.html").read_text(encoding="utf-8")
        assert "anthropic" in index.lower()

        # Verify greeting-cards page has app license
        gc = (html_dir / "greeting-cards.html").read_text(encoding="utf-8")
        assert "BSD 3-Clause" in gc

        # Verify system page has Python
        sys_page = (html_dir / "system.html").read_text(encoding="utf-8")
        assert "Python" in sys_page

        # Verify registry was created
        assert (build_dir / "registry.toml").exists()

    def test_regenerate_clears_old_html(self, tmp_path):
        """Re-running clears old html_dir via shutil.rmtree."""
        # Set up same structure
        source_dir = tmp_path / "content" / "licenses"
        source_dir.mkdir(parents=True)
        manual_dir = source_dir / "manual"
        manual_dir.mkdir()
        (source_dir / "config.toml").write_text(
            '[[system]]\nslug = "python"\ndisplay = "Python"\nversion = "3.14"\nlicense_type = "PSF"\n',
            encoding="utf-8",
        )
        (manual_dir / "python.txt").write_text("PSF License", encoding="utf-8")
        (tmp_path / "LICENSE").write_text("BSD 3-Clause", encoding="utf-8")
        (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[dependency-groups]\ndev = []\n", encoding="utf-8")

        site_packages = tmp_path / "site-packages"
        site_packages.mkdir()

        # Pre-create html_dir with a stale file
        html_dir = tmp_path / "_build" / "runtime_content" / "html" / "licenses"
        html_dir.mkdir(parents=True)
        stale = html_dir / "old_stale.html"
        stale.write_text("stale", encoding="utf-8")

        with (
            patch.object(ls, "__file__", str(tmp_path / "app" / "core" / "content" / "license_sync.py")),
            patch("app.core.content.license_sync._get_site_packages", return_value=site_packages),
        ):
            from app.core.content.license_html import generate_licenses_html

            generate_licenses_html()

        # Stale file should be gone
        assert not stale.exists()
        # Fresh files should exist
        assert (html_dir / "index.html").exists()

    def test_manual_text_file_and_missing_text(self, tmp_path):
        """Test manual text file path and missing text fallback."""
        source_dir = tmp_path / "content" / "licenses"
        source_dir.mkdir(parents=True)
        manual_dir = source_dir / "manual"
        manual_dir.mkdir()

        # Config with override that has license_type
        (source_dir / "config.toml").write_text(
            '[[system]]\nslug = "python"\ndisplay = "Python"\n'
            'version = "3.14"\nlicense_type = "PSF"\n\n'
            '[[package]]\nname = "anthropic"\nlicense_type = "MIT Override"\n'
            'homepage = "https://override.example.com"\n',
            encoding="utf-8",
        )
        (manual_dir / "python.txt").write_text("PSF License", encoding="utf-8")

        # anthropic has a manual text file
        (manual_dir / "anthropic.txt").write_text("Manual MIT License", encoding="utf-8")

        (tmp_path / "LICENSE").write_text("BSD 3-Clause", encoding="utf-8")

        # uv.lock with anthropic + a second package with no license text at all
        lock = (
            "version = 1\n\n"
            '[[package]]\nname = "greeting-cards"\nversion = "0.9.0"\n\n'
            '[[package.dependencies]]\nname = "anthropic"\n\n'
            '[[package.dependencies]]\nname = "nolicense"\n\n'
            '[[package]]\nname = "anthropic"\nversion = "0.50.0"\n\n'
            '[[package]]\nname = "nolicense"\nversion = "1.0.0"\n'
        )
        (tmp_path / "uv.lock").write_text(lock, encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[dependency-groups]\ndev = []\n", encoding="utf-8")

        site_packages = tmp_path / "site-packages"
        site_packages.mkdir()
        # No dist-info for anthropic — will fall back to manual
        # No dist-info for nolicense — no text at all → "License text not available."

        with (
            patch.object(ls, "__file__", str(tmp_path / "app" / "core" / "content" / "license_sync.py")),
            patch("app.core.content.license_sync._get_site_packages", return_value=site_packages),
        ):
            from app.core.content.license_html import generate_licenses_html

            generate_licenses_html()

        html_dir = tmp_path / "_build" / "runtime_content" / "html" / "licenses"
        runtime_html = (html_dir / "runtime.html").read_text(encoding="utf-8")
        # anthropic should use manual text file
        assert "Manual MIT License" in runtime_html
        # nolicense should show fallback text
        assert "License text not available" in runtime_html
