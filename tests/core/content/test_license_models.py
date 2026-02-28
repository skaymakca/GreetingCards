"""Tests for app.core.license_models module."""

from app.core.content.license_models import (
    BundledDep,
    DiscoveredPackage,
    LicenseConfig,
    LicenseRegistry,
    PackageCategory,
    PackageOverride,
)


class TestPackageCategory:
    """Tests for PackageCategory enum."""

    def test_runtime(self):
        assert PackageCategory.RUNTIME.value == "Runtime"

    def test_development(self):
        assert PackageCategory.DEVELOPMENT.value == "Development"

    def test_transitive(self):
        assert PackageCategory.TRANSITIVE.value == "Transitive"

    def test_all_values(self):
        assert len(PackageCategory) == 3


class TestBundledDep:
    """Tests for BundledDep dataclass."""

    def test_construction(self):
        dep = BundledDep(
            slug="python",
            display="Python",
            version="3.14",
            license_type="PSF",
            notes="Runtime",
            url="https://python.org",
        )
        assert dep.slug == "python"
        assert dep.display == "Python"
        assert dep.url == "https://python.org"

    def test_url_default_empty(self):
        dep = BundledDep(
            slug="tesseract", display="Tesseract", version="5.0", license_type="Apache-2.0", notes="OCR engine"
        )
        assert dep.url == ""


class TestPackageOverride:
    """Tests for PackageOverride dataclass."""

    def test_construction(self):
        o = PackageOverride(name="wxPython")
        assert o.name == "wxPython"
        assert o.display == ""
        assert o.category == ""
        assert o.license_type == ""
        assert o.homepage == ""
        assert o.notes == ""

    def test_with_overrides(self):
        o = PackageOverride(name="wxPython", display="wxPython (Phoenix)", category="Runtime", license_type="wxWindows")
        assert o.display == "wxPython (Phoenix)"
        assert o.category == "Runtime"


class TestLicenseConfig:
    """Tests for LicenseConfig dataclass."""

    def test_construction(self):
        dep = BundledDep(slug="python", display="Python", version="3.14", license_type="PSF", notes="")
        config = LicenseConfig(bundled_deps=[dep])
        assert len(config.bundled_deps) == 1
        assert config.package_overrides == {}
        assert config.exclude == set()

    def test_with_overrides_and_exclude(self):
        config = LicenseConfig(
            bundled_deps=[],
            package_overrides={"wx": PackageOverride(name="wx")},
            exclude={"test-pkg"},
        )
        assert "wx" in config.package_overrides
        assert "test-pkg" in config.exclude


class TestDiscoveredPackage:
    """Tests for DiscoveredPackage dataclass."""

    def test_construction(self):
        pkg = DiscoveredPackage(
            name="anyio",
            slug="anyio",
            display="anyio",
            version="4.0",
            license_type="MIT",
            category=PackageCategory.TRANSITIVE,
            required_by="httpx",
            text_file="texts/anyio.txt",
        )
        assert pkg.name == "anyio"
        assert pkg.category == PackageCategory.TRANSITIVE
        assert pkg.homepage == ""
        assert pkg.license_text == ""


class TestLicenseRegistry:
    """Tests for LicenseRegistry dataclass."""

    def test_construction(self):
        dep = BundledDep(slug="python", display="Python", version="3.14", license_type="PSF", notes="")
        pkg = DiscoveredPackage(
            name="anyio",
            slug="anyio",
            display="anyio",
            version="4.0",
            license_type="MIT",
            category=PackageCategory.RUNTIME,
            required_by="direct",
            text_file="texts/anyio.txt",
        )
        reg = LicenseRegistry(
            uv_lock_hash="abc123",
            generated_at="2026-02-23",
            bundled_deps=[dep],
            packages=[pkg],
        )
        assert reg.uv_lock_hash == "abc123"
        assert len(reg.bundled_deps) == 1
        assert len(reg.packages) == 1
