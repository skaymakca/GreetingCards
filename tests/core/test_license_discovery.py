"""Tests for license discovery helpers."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.license_discovery import (
    _build_nav_items,
    _build_reverse_deps,
    _categorize_packages,
    _category_page_for,
    _display_name,
    _extract_homepage,
    _extract_license_type,
    _find_dist_info,
    _find_license_file,
    _linkify,
    _parse_uv_lock,
    _read_existing_versions,
    _required_by_text,
    _slug,
    _write_registry_toml,
    get_page_order,
    load_config,
)
from app.core.license_models import (
    DiscoveredPackage,
    LicenseConfig,
    LicenseRegistry,
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


class TestRequiredByText:
    """Tests for _required_by_text()."""

    def test_runtime_returns_dash(self):
        result = _required_by_text("foo", PackageCategory.RUNTIME, {}, {})
        assert result == "\u2014"

    def test_transitive_with_parents(self):
        reverse = {"foo": {"bar", "baz"}}
        result = _required_by_text("foo", PackageCategory.TRANSITIVE, reverse, {})
        assert "bar" in result
        assert "baz" in result

    def test_transitive_no_parents(self):
        result = _required_by_text("foo", PackageCategory.TRANSITIVE, {}, {})
        assert result == "\u2014"


class TestCategoryPageFor:
    """Tests for _category_page_for()."""

    def test_runtime(self):
        assert _category_page_for(PackageCategory.RUNTIME) == "runtime.html"

    def test_development(self):
        assert _category_page_for(PackageCategory.DEVELOPMENT) == "development.html"

    def test_transitive(self):
        assert _category_page_for(PackageCategory.TRANSITIVE) == "transitive.html"

    def test_unknown_category_fallback(self):
        """Unknown category falls back to transitive.html (line 518)."""
        # Create a mock category value not in the mapping
        from unittest.mock import MagicMock

        fake_cat = MagicMock()
        assert _category_page_for(fake_cat) == "transitive.html"


class TestWriteRegistryToml:
    """Tests for _write_registry_toml()."""

    def test_writes_valid_toml(self, tmp_path):
        import tomllib

        registry = LicenseRegistry(
            uv_lock_hash="sha256:abc123",
            generated_at="2026-01-01T00:00:00+00:00",
            system_deps=[SystemDep(slug="python", display="Python", version="3.14", license_type="PSF", notes="")],
            packages=[
                DiscoveredPackage(
                    name="foo",
                    slug="foo",
                    display="Foo",
                    version="1.0",
                    license_type="MIT",
                    category=PackageCategory.RUNTIME,
                    required_by="\u2014",
                    text_file="texts/foo.txt",
                    homepage="https://foo.dev",
                ),
            ],
        )
        _write_registry_toml(tmp_path, registry)
        registry_path = tmp_path / "registry.toml"
        assert registry_path.exists()
        data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
        assert data["meta"]["uv_lock_hash"] == "sha256:abc123"
        assert len(data["package"]) == 1
        assert data["package"][0]["name"] == "foo"
        assert len(data["system"]) == 1


class TestFindDistInfo:
    """Tests for _find_dist_info()."""

    def test_finds_matching_dist_info(self, tmp_path):
        dist = tmp_path / "foo-1.0.dist-info"
        dist.mkdir()
        assert _find_dist_info(tmp_path, "foo") == dist

    def test_returns_none_when_not_found(self, tmp_path):
        assert _find_dist_info(tmp_path, "nonexistent") is None

    def test_no_version_in_dist_name(self, tmp_path):
        """dist-info name without a version digit uses full stem (line 157)."""
        dist = tmp_path / "mypkg.dist-info"
        dist.mkdir()
        assert _find_dist_info(tmp_path, "mypkg") == dist

    def test_normalizes_dashes_and_dots(self, tmp_path):
        dist = tmp_path / "my_package-2.0.dist-info"
        dist.mkdir()
        assert _find_dist_info(tmp_path, "my-package") == dist


class TestFindLicenseFile:
    """Tests for _find_license_file()."""

    def test_finds_license_in_licenses_subdir(self, tmp_path):
        licenses_dir = tmp_path / "licenses"
        licenses_dir.mkdir()
        (licenses_dir / "LICENSE").write_text("MIT License text", encoding="utf-8")
        assert _find_license_file(tmp_path) == "MIT License text"

    def test_finds_license_in_root(self, tmp_path):
        (tmp_path / "LICENSE.txt").write_text("BSD License", encoding="utf-8")
        assert _find_license_file(tmp_path) == "BSD License"

    def test_returns_none_when_no_license(self, tmp_path):
        assert _find_license_file(tmp_path) is None

    def test_fallback_to_any_file_in_licenses_dir(self, tmp_path):
        """Falls back to any file in licenses/ subdir when standard names don't match."""
        licenses_dir = tmp_path / "licenses"
        licenses_dir.mkdir()
        (licenses_dir / "NOTICE").write_text("Notice text", encoding="utf-8")
        assert _find_license_file(tmp_path) == "Notice text"


class TestExtractLicenseType:
    """Tests for _extract_license_type()."""

    def test_from_license_header(self, tmp_path):
        (tmp_path / "METADATA").write_text("License: MIT\n", encoding="utf-8")
        assert _extract_license_type(tmp_path) == "MIT"

    def test_from_classifier(self, tmp_path):
        (tmp_path / "METADATA").write_text(
            "License: UNKNOWN\nClassifier: License :: OSI Approved :: BSD License\n",
            encoding="utf-8",
        )
        assert _extract_license_type(tmp_path) == "BSD License"

    def test_no_metadata(self, tmp_path):
        assert _extract_license_type(tmp_path) == "Unknown"

    def test_see_license_fallback(self, tmp_path):
        (tmp_path / "METADATA").write_text("Name: foo\nVersion: 1.0\n", encoding="utf-8")
        assert _extract_license_type(tmp_path) == "See LICENSE file"


class TestExtractHomepage:
    """Tests for _extract_homepage()."""

    def test_from_project_url(self, tmp_path):
        (tmp_path / "METADATA").write_text("Project-URL: Homepage, https://example.com\n", encoding="utf-8")
        assert _extract_homepage(tmp_path) == "https://example.com"

    def test_from_home_page_field(self, tmp_path):
        (tmp_path / "METADATA").write_text("Home-page: https://old.example.com\n", encoding="utf-8")
        assert _extract_homepage(tmp_path) == "https://old.example.com"

    def test_no_metadata(self, tmp_path):
        assert _extract_homepage(tmp_path) == ""

    def test_unknown_home_page(self, tmp_path):
        (tmp_path / "METADATA").write_text("Home-page: UNKNOWN\n", encoding="utf-8")
        assert _extract_homepage(tmp_path) == ""


class TestCategorizePackagesOverride:
    """Tests for category config override (line 274)."""

    def test_config_override_changes_category(self):
        packages = [{"name": "foo", "version": "1.0", "deps": []}]
        overrides = {"foo": PackageOverride(name="foo", category="Runtime")}
        config = LicenseConfig(system_deps=[], package_overrides=overrides)
        cats = _categorize_packages(packages, set(), config, set())
        assert cats["foo"] == PackageCategory.RUNTIME


class TestReadExistingVersions:
    """Tests for _read_existing_versions()."""

    def test_reads_versions(self, tmp_path):
        import tomli_w

        data = {"package": [{"name": "foo", "version": "1.0"}, {"name": "bar", "version": "2.0"}]}
        (tmp_path / "registry.toml").write_bytes(tomli_w.dumps(data).encode("utf-8"))
        versions = _read_existing_versions(tmp_path)
        assert versions == {"foo": "1.0", "bar": "2.0"}

    def test_missing_file(self, tmp_path):
        assert _read_existing_versions(tmp_path) == {}


class TestGetPageOrder:
    """Tests for get_page_order() and _build_nav_items()."""

    def test_returns_manifest_when_exists(self, tmp_path):
        manifest = tmp_path / "licenses" / "page_order.txt"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("index.html\nruntime.html\n", encoding="utf-8")
        result = get_page_order(tmp_path / "licenses")
        assert result == ["index.html", "runtime.html"]

    def test_fallback_when_no_manifest(self, tmp_path):
        """Falls back to hardcoded nav order when manifest is missing (line 527)."""
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
    """Tests for generate_licenses_html() and _write_html() (lines 549-725)."""

    def test_full_pipeline(self, tmp_path):
        """Integration test: generate_licenses_html() creates all HTML files."""
        import app.core.license_discovery as ld

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
            patch.object(ld, "__file__", str(tmp_path / "app" / "core" / "license_discovery.py")),
            patch("app.core.license_discovery._get_site_packages", return_value=site_packages),
        ):
            from app.core.license_discovery import generate_licenses_html

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
        """Re-running clears old html_dir via shutil.rmtree (line 584)."""
        import app.core.license_discovery as ld

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
            patch.object(ld, "__file__", str(tmp_path / "app" / "core" / "license_discovery.py")),
            patch("app.core.license_discovery._get_site_packages", return_value=site_packages),
        ):
            from app.core.license_discovery import generate_licenses_html

            generate_licenses_html()

        # Stale file should be gone
        assert not stale.exists()
        # Fresh files should exist
        assert (html_dir / "index.html").exists()

    def test_manual_text_file_and_missing_text(self, tmp_path):
        """Test manual text file path (line 695) and missing text fallback (line 702)."""
        import app.core.license_discovery as ld

        source_dir = tmp_path / "content" / "licenses"
        source_dir.mkdir(parents=True)
        manual_dir = source_dir / "manual"
        manual_dir.mkdir()

        # Config with override that has license_type (line 412)
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
            patch.object(ld, "__file__", str(tmp_path / "app" / "core" / "license_discovery.py")),
            patch("app.core.license_discovery._get_site_packages", return_value=site_packages),
        ):
            from app.core.license_discovery import generate_licenses_html

            generate_licenses_html()

        html_dir = tmp_path / "_build" / "runtime_content" / "html" / "licenses"
        runtime_html = (html_dir / "runtime.html").read_text(encoding="utf-8")
        # anthropic should use manual text file
        assert "Manual MIT License" in runtime_html
        # nolicense should show fallback text
        assert "License text not available" in runtime_html
