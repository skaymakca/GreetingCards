"""Tests for the licenses system (discovery, registry, viewer)."""

from pathlib import Path
from unittest.mock import patch

import pytest
import wx

from app.core.license_discovery import (
    _build_reverse_deps,
    _categorize_packages,
    _category_page_for,
    _display_name,
    _extract_homepage,
    _extract_license_type,
    _find_dist_info,
    _find_license_file,
    _get_licenses_dir,
    _parse_uv_lock,
    _slug,
    generate_licenses_html,
    get_page_order,
    load_config,
    sync_registry,
)
from app.core.license_models import (
    DiscoveredPackage,
    LicenseConfig,
    LicenseRegistry,
    PackageCategory,
    PackageOverride,
    SystemDep,
)
from app.core.paths import get_runtime_content_path
from app.gui.html_viewer import _viewer_refs
from app.gui.licenses_dialog import show_licenses

# --- Shared fixtures ---


@pytest.fixture
def licenses_window(wx_app, wx_frame):
    """Open licenses window and yield it; destroy on teardown."""
    _viewer_refs.pop("licenses", None)
    show_licenses(wx_frame)
    ref = _viewer_refs.get("licenses")
    window = ref() if ref else None
    yield window
    if window and not window.IsBeingDeleted():
        window.Destroy()
    _viewer_refs.pop("licenses", None)


@pytest.fixture
def sample_config():
    """A minimal LicenseConfig for testing."""
    return LicenseConfig(
        system_deps=[
            SystemDep(
                slug="python",
                display="Python",
                version="3.14",
                license_type="PSF License 2.0",
                notes="Bundled",
                url="https://python.org",
            ),
        ],
        package_overrides={
            "anthropic": PackageOverride(name="anthropic", display="Anthropic SDK"),
            "pymupdf": PackageOverride(name="pymupdf", display="PyMuPDF"),
        },
    )


def _get_licenses_base_path() -> Path:
    """Helper to get the licenses base path for tests."""
    return get_runtime_content_path("html/licenses")


# --- Path tests ---


class TestGetLicensesBasePath:
    """Tests for licenses base path resolution."""

    def test_returns_path_object(self):
        result = _get_licenses_base_path()
        assert isinstance(result, Path)

    def test_path_exists_in_dev_mode(self):
        result = _get_licenses_base_path()
        assert result.exists(), f"Licenses HTML directory not found at {result}"

    def test_path_ends_with_licenses(self):
        result = _get_licenses_base_path()
        assert str(result).endswith("html/licenses")


# --- Config tests ---


class TestLoadConfig:
    """Tests for config.toml loading."""

    def test_loads_config(self):
        config = load_config(_get_licenses_dir())
        assert isinstance(config, LicenseConfig)

    def test_has_package_overrides(self):
        config = load_config(_get_licenses_dir())
        assert "anthropic" in config.package_overrides
        assert config.package_overrides["anthropic"].display == "Anthropic SDK"

    def test_has_system_deps(self):
        config = load_config(_get_licenses_dir())
        slugs = {sd.slug for sd in config.system_deps}
        assert "python" in slugs
        assert "tesseract" in slugs

    def test_system_deps_have_urls(self):
        config = load_config(_get_licenses_dir())
        urls = {sd.slug: sd.url for sd in config.system_deps}
        assert urls["python"] == "https://python.org"
        assert "tesseract" in urls["tesseract"]


# --- Registry tests ---


class TestSyncRegistry:
    """Tests for registry sync."""

    def test_sync_returns_registry(self):
        registry = sync_registry()
        assert isinstance(registry, LicenseRegistry)

    def test_registry_has_packages(self):
        registry = sync_registry()
        assert len(registry.packages) > 30

    def test_registry_has_system_deps(self):
        registry = sync_registry()
        assert len(registry.system_deps) >= 2

    def test_registry_has_hash(self):
        registry = sync_registry()
        assert registry.uv_lock_hash.startswith("sha256:")

    def test_registry_toml_written(self):
        sync_registry()
        assert (_get_licenses_dir() / "registry.toml").exists()

    def test_texts_dir_has_files(self):
        sync_registry()
        texts_dir = _get_licenses_dir() / "texts"
        assert texts_dir.exists()
        txt_files = list(texts_dir.glob("*.txt"))
        assert len(txt_files) > 20

    def test_packages_have_homepages(self):
        registry = sync_registry()
        with_homepage = [p for p in registry.packages if p.homepage]
        assert len(with_homepage) > 20


# --- Generation tests ---


class TestGenerateLicensesHtml:
    """Tests for license HTML generation."""

    def test_generation_creates_index(self):
        base = _get_licenses_base_path()
        assert (base / "index.html").exists()

    def test_shared_css_exists(self):
        """Shared viewer.css should exist in the common directory."""
        project_root = Path(__file__).resolve().parent.parent.parent
        assert (project_root / "_runtime_content" / "html" / "common" / "css" / "viewer.css").exists()

    def test_generation_creates_greeting_cards_page(self):
        base = _get_licenses_base_path()
        assert (base / "greeting-cards.html").exists()

    def test_generation_creates_system_page(self):
        base = _get_licenses_base_path()
        assert (base / "system.html").exists()

    def test_generation_creates_category_pages(self):
        base = _get_licenses_base_path()
        for page in ("runtime.html", "development.html", "transitive.html"):
            assert (base / page).exists(), f"Missing category page: {page}"

    def test_no_pages_subdir(self):
        """New structure is flat — no pages/ subdirectory."""
        base = _get_licenses_base_path()
        assert not (base / "pages").exists()


# --- Content tests ---


class TestLicenseContentFiles:
    """Tests that all generated pages have correct structure."""

    def test_all_pages_exist(self):
        base = _get_licenses_base_path()
        page_order = get_page_order(_get_licenses_base_path())
        for rel_path in page_order:
            assert (base / rel_path).exists(), f"Missing: {rel_path}"

    def test_pages_reference_shared_css(self):
        """Pages should reference the shared viewer.css."""
        base = _get_licenses_base_path()
        content = (base / "index.html").read_text()
        assert "viewer.css" in content

    def test_pages_contain_sidebar(self):
        base = _get_licenses_base_path()
        page_order = get_page_order(_get_licenses_base_path())
        for rel_path in page_order:
            content = (base / rel_path).read_text()
            assert 'class="sidebar"' in content, f"No sidebar in {rel_path}"
            assert 'class="content"' in content, f"No content in {rel_path}"

    def test_each_page_marks_itself_active(self):
        base = _get_licenses_base_path()
        page_order = get_page_order(_get_licenses_base_path())
        for rel_path in page_order:
            content = (base / rel_path).read_text()
            assert content.count('class="active"') == 1, f"Expected 1 active link in {rel_path}"

    def test_index_has_tables(self):
        base = _get_licenses_base_path()
        content = (base / "index.html").read_text()
        assert "<table>" in content
        assert "Python Packages" in content
        assert "System Dependencies" in content
        assert "Greeting Cards" in content

    def test_index_has_dependency_type_explanations(self):
        base = _get_licenses_base_path()
        content = (base / "index.html").read_text()
        assert "Dependency Types" in content
        for label in ("Runtime", "Development", "Transitive", "System"):
            assert label in content, f"Missing explanation for {label}"

    def test_index_has_runtime_deps(self):
        base = _get_licenses_base_path()
        content = (base / "index.html").read_text()
        # Check that key runtime deps appear
        assert "Anthropic SDK" in content
        assert "Pillow" in content or "pillow" in content

    def test_index_links_use_category_anchors(self):
        """Index table should link to category_page#slug, not individual pages."""
        base = _get_licenses_base_path()
        content = (base / "index.html").read_text()
        assert 'href="runtime.html#anthropic"' in content
        assert 'href="transitive.html#' in content

    def test_index_has_homepage_links(self):
        base = _get_licenses_base_path()
        content = (base / "index.html").read_text()
        assert "&nearr;" in content

    def test_category_pages_have_anchors(self):
        """Category pages should have id= anchor tags for each package."""
        base = _get_licenses_base_path()
        content = (base / "runtime.html").read_text()
        assert 'id="anthropic"' in content

    def test_category_pages_have_hr_dividers(self):
        """Multiple entries should be separated by hr.version-divider."""
        base = _get_licenses_base_path()
        content = (base / "runtime.html").read_text()
        assert 'class="version-divider"' in content

    def test_category_pages_have_pre_blocks(self):
        base = _get_licenses_base_path()
        for page in ("runtime.html", "system.html", "greeting-cards.html"):
            content = (base / page).read_text()
            assert "<pre>" in content, f"No <pre> in {page}"

    def test_category_pages_have_homepage_links(self):
        base = _get_licenses_base_path()
        content = (base / "runtime.html").read_text()
        assert "&nearr;" in content

    def test_greeting_cards_uses_repo_license(self):
        base = _get_licenses_base_path()
        content = (base / "greeting-cards.html").read_text()
        assert "Sukru N. Kaymakcalan" in content

    def test_system_page_has_python_and_tesseract(self):
        base = _get_licenses_base_path()
        content = (base / "system.html").read_text()
        assert 'id="python"' in content
        assert 'id="tesseract"' in content
        assert "Python Software Foundation" in content


# --- Page order tests ---


class TestPageOrder:
    """Tests for dynamic page order."""

    def test_index_is_first(self):
        page_order = get_page_order(_get_licenses_base_path())
        assert page_order[0] == "index.html"

    def test_has_category_pages(self):
        page_order = get_page_order(_get_licenses_base_path())
        assert len(page_order) == 6  # index + greeting-cards + system + 3 category
        assert "runtime.html" in page_order
        assert "development.html" in page_order
        assert "transitive.html" in page_order
        assert "greeting-cards.html" in page_order

    def test_all_html(self):
        page_order = get_page_order(_get_licenses_base_path())
        assert all(p.endswith(".html") for p in page_order)


# --- Utility function tests ---


class TestSlug:
    def test_lowercase(self):
        assert _slug("PyMuPDF") == "pymupdf"

    def test_underscores_to_hyphens(self):
        assert _slug("typing_extensions") == "typing-extensions"

    def test_dots_to_hyphens(self):
        assert _slug("foo.bar") == "foo-bar"


class TestDisplayName:
    def test_override(self):
        overrides = {
            "anthropic": PackageOverride(name="anthropic", display="Anthropic SDK"),
            "pymupdf": PackageOverride(name="pymupdf", display="PyMuPDF"),
        }
        assert _display_name("anthropic", overrides) == "Anthropic SDK"
        assert _display_name("pymupdf", overrides) == "PyMuPDF"

    def test_no_override(self):
        assert _display_name("certifi", {}) == "certifi"


class TestCategoryPageFor:
    def test_runtime(self):
        assert _category_page_for(PackageCategory.RUNTIME) == "runtime.html"

    def test_development(self):
        assert _category_page_for(PackageCategory.DEVELOPMENT) == "development.html"

    def test_transitive(self):
        assert _category_page_for(PackageCategory.TRANSITIVE) == "transitive.html"


class TestCategorizePackages:
    def test_runtime_deps(self, sample_config):
        pkgs = [
            {"name": "greeting-cards", "version": "0.8.0", "deps": ["anthropic", "pillow"]},
            {"name": "anthropic", "version": "1.0", "deps": []},
            {"name": "pillow", "version": "10.0", "deps": []},
        ]
        cats = _categorize_packages(
            pkgs,
            set(),
            sample_config,
            runtime_deps={"anthropic", "pillow"},
        )
        assert cats["anthropic"] == PackageCategory.RUNTIME
        assert cats["pillow"] == PackageCategory.RUNTIME

    def test_dev_deps(self, sample_config):
        pkgs = [
            {"name": "pytest", "version": "9.0", "deps": []},
        ]
        cats = _categorize_packages(
            pkgs,
            {"pytest"},
            sample_config,
            runtime_deps=set(),
        )
        assert cats["pytest"] == PackageCategory.DEVELOPMENT

    def test_transitive_deps(self, sample_config):
        pkgs = [
            {"name": "idna", "version": "3.0", "deps": []},
        ]
        cats = _categorize_packages(
            pkgs,
            set(),
            sample_config,
            runtime_deps=set(),
        )
        assert cats["idna"] == PackageCategory.TRANSITIVE


class TestBuildReverseDeps:
    def test_simple_reverse(self):
        pkgs = [
            {"name": "httpx", "version": "1.0", "deps": ["httpcore"]},
            {"name": "httpcore", "version": "1.0", "deps": []},
        ]
        reverse = _build_reverse_deps(pkgs)
        assert "httpx" in reverse["httpcore"]


class TestParseUvLock:
    def test_parses_packages(self, tmp_path):
        lock_content = """
version = 1

[[package]]
name = "foo"
version = "1.0.0"
dependencies = [
    { name = "bar" },
]

[[package]]
name = "bar"
version = "2.0.0"
"""
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text(lock_content)
        result = _parse_uv_lock(lock_file)
        assert len(result) == 2
        assert result[0]["name"] == "foo"
        assert result[0]["version"] == "1.0.0"
        assert result[0]["deps"] == ["bar"]
        assert result[1]["deps"] == []


# --- Dataclass tests ---


class TestLicenseModels:
    """Tests for license dataclasses."""

    def test_package_category_values(self):
        assert PackageCategory.RUNTIME.value == "Runtime"
        assert PackageCategory.DEVELOPMENT.value == "Development"
        assert PackageCategory.TRANSITIVE.value == "Transitive"
        assert len(PackageCategory) == 3

    def test_system_dep_creation(self):
        sd = SystemDep(
            slug="python",
            display="Python",
            version="3.14",
            license_type="PSF",
            notes="bundled",
            url="https://python.org",
        )
        assert sd.slug == "python"
        assert sd.url == "https://python.org"

    def test_package_override_creation(self):
        po = PackageOverride(name="anthropic", display="Anthropic SDK")
        assert po.name == "anthropic"
        assert po.display == "Anthropic SDK"
        assert po.category == ""

    def test_discovered_package_default_text(self):
        dp = DiscoveredPackage(
            name="foo",
            slug="foo",
            display="Foo",
            version="1.0",
            license_type="MIT",
            category=PackageCategory.RUNTIME,
            required_by="\u2014",
            text_file="texts/foo.txt",
        )
        assert dp.license_text == ""
        assert dp.homepage == ""

    def test_license_registry_fields(self):
        registry = LicenseRegistry(
            uv_lock_hash="sha256:abc",
            generated_at="2026-01-01T00:00:00",
            system_deps=[],
            packages=[],
        )
        assert registry.uv_lock_hash.startswith("sha256:")


# --- Manual text file tests ---


class TestManualTextFiles:
    """Tests for committed manual license texts."""

    def test_python_txt_exists(self):
        path = _get_licenses_dir() / "manual" / "python.txt"
        assert path.exists()
        content = path.read_text()
        assert "Python Software Foundation" in content

    def test_tesseract_txt_exists(self):
        path = _get_licenses_dir() / "manual" / "tesseract.txt"
        assert path.exists()
        content = path.read_text()
        assert "Apache" in content


# --- WebView window tests ---


class TestLicensesWebViewWindow:
    """Tests for the WebView licenses window."""

    def test_window_creation(self, licenses_window):
        assert licenses_window is not None
        assert licenses_window.GetTitle() == "Open-Source Licenses"

    def test_singleton_reuse(self, licenses_window):
        with (
            patch.object(licenses_window, "Raise") as mock_raise,
            patch.object(licenses_window, "IsBeingDeleted", return_value=False),
        ):
            show_licenses(licenses_window.GetParent())
            mock_raise.assert_called_once()

    def test_creates_new_after_close(self, wx_app, wx_frame):
        _viewer_refs.pop("licenses", None)
        show_licenses(wx_frame)
        ref = _viewer_refs.get("licenses")
        window = ref() if ref else None
        window.Destroy()
        _viewer_refs.pop("licenses", None)

        show_licenses(wx_frame)
        ref2 = _viewer_refs.get("licenses")
        second_window = ref2() if ref2 else None
        assert second_window is not None
        second_window.Destroy()
        _viewer_refs.pop("licenses", None)


# --- License extraction tests ---


class TestFindLicenseFile:
    """Tests for _find_license_file()."""

    def test_finds_license_in_licenses_subdir(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        licenses_dir = dist_info / "licenses"
        licenses_dir.mkdir()
        (licenses_dir / "LICENSE").write_text("MIT License text")
        assert _find_license_file(dist_info) == "MIT License text"

    def test_finds_license_in_dist_info_root(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "LICENSE.txt").write_text("BSD License text")
        assert _find_license_file(dist_info) == "BSD License text"

    def test_prefers_licenses_subdir_over_root(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "LICENSE").write_text("root license")
        licenses_dir = dist_info / "licenses"
        licenses_dir.mkdir()
        (licenses_dir / "LICENSE").write_text("subdir license")
        assert _find_license_file(dist_info) == "subdir license"

    def test_falls_back_to_any_file_in_licenses_dir(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        licenses_dir = dist_info / "licenses"
        licenses_dir.mkdir()
        (licenses_dir / "NOTICE").write_text("Notice text")
        assert _find_license_file(dist_info) == "Notice text"

    def test_returns_none_when_no_license(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        assert _find_license_file(dist_info) is None

    def test_skips_pyc_files_in_licenses_dir(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        licenses_dir = dist_info / "licenses"
        licenses_dir.mkdir()
        (licenses_dir / "cache.pyc").write_bytes(b"\x00")
        assert _find_license_file(dist_info) is None


class TestExtractLicenseType:
    """Tests for _extract_license_type()."""

    def test_extracts_license_field(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nVersion: 1.0\nLicense: MIT\n")
        assert _extract_license_type(dist_info) == "MIT"

    def test_extracts_from_classifier(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Name: foo\nVersion: 1.0\nClassifier: License :: OSI Approved :: BSD License\n"
        )
        assert _extract_license_type(dist_info) == "BSD License"

    def test_returns_see_license_when_no_info(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nVersion: 1.0\n")
        assert _extract_license_type(dist_info) == "See LICENSE file"

    def test_returns_unknown_when_no_metadata(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        assert _extract_license_type(dist_info) == "Unknown"

    def test_ignores_unknown_license_value(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nVersion: 1.0\nLicense: UNKNOWN\n")
        assert _extract_license_type(dist_info) == "See LICENSE file"


class TestExtractHomepage:
    """Tests for _extract_homepage()."""

    def test_extracts_project_url_homepage(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nProject-URL: Homepage, https://example.com\n")
        assert _extract_homepage(dist_info) == "https://example.com"

    def test_extracts_project_url_repository(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nProject-URL: Repository, https://github.com/x/y\n")
        assert _extract_homepage(dist_info) == "https://github.com/x/y"

    def test_falls_back_to_home_page_field(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nHome-page: https://old-style.com\n")
        assert _extract_homepage(dist_info) == "https://old-style.com"

    def test_returns_empty_when_no_url(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nVersion: 1.0\n")
        assert _extract_homepage(dist_info) == ""

    def test_returns_empty_when_no_metadata(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        assert _extract_homepage(dist_info) == ""

    def test_ignores_unknown_home_page(self, tmp_path):
        dist_info = tmp_path / "foo-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: foo\nHome-page: UNKNOWN\n")
        assert _extract_homepage(dist_info) == ""
