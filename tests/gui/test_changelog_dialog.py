"""Tests for changelog parsing and HTML generation."""

from pathlib import Path

import pytest

from app.core.changelog import (
    _generate_changelog_html,
    _group_by_minor,
    _parse_changelog,
)
from app.core.changelog_models import ChangelogGroup, ChangelogVersion

# --- CHANGELOG.md file tests ---


class TestChangelogFileExists:
    """Tests that CHANGELOG.md exists and has valid content."""

    def _get_changelog_path(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"

    def test_changelog_exists(self):
        md_path = self._get_changelog_path()
        assert md_path.exists(), f"CHANGELOG.md not found at {md_path}"

    def test_changelog_has_version_headings(self):
        md_path = self._get_changelog_path()
        text = md_path.read_text(encoding="utf-8")
        assert "## 0." in text, "CHANGELOG.md must have version headings"

    def test_changelog_has_top_heading(self):
        md_path = self._get_changelog_path()
        text = md_path.read_text(encoding="utf-8")
        assert text.startswith("# "), "CHANGELOG.md should start with a top-level heading"


# --- Parse changelog tests ---


class TestParseChangelog:
    """Tests for _parse_changelog()."""

    SAMPLE_MD = """# Changelog

## 0.9.0 (in progress)

Stability improvements and bug fixes.

- Added "Clear AI Results" menu item
- Graceful Tesseract handling

## 0.8.0 — Native macOS Interface (2026-02-19)

Complete GUI rewrite for native macOS.

- Native toolbar with SF Symbol icons
- Filter sidebar with counts

## 0.6.0 — Initial Release (2026-02-12)

First release of the app.

- PDF loading with drag-and-drop
- OCR text extraction
"""

    def test_returns_list_of_changelog_versions(self):
        result = _parse_changelog(self.SAMPLE_MD)
        assert isinstance(result, list)
        assert all(isinstance(v, ChangelogVersion) for v in result)

    def test_correct_number_of_versions(self):
        result = _parse_changelog(self.SAMPLE_MD)
        assert len(result) == 3

    def test_version_tags_extracted(self):
        result = _parse_changelog(self.SAMPLE_MD)
        versions = [v.version for v in result]
        assert versions == ["0.9.0", "0.8.0", "0.6.0"]

    def test_titles_stripped_of_date(self):
        result = _parse_changelog(self.SAMPLE_MD)
        assert "(in progress)" not in result[0].title
        assert "(2026-02-19)" not in result[1].title
        assert "(2026-02-12)" not in result[2].title

    def test_titles_have_descriptive_text(self):
        result = _parse_changelog(self.SAMPLE_MD)
        assert "0.9.0" in result[0].title
        assert "Native macOS Interface" in result[1].title
        assert "Initial Release" in result[2].title

    def test_date_field_extracted(self):
        result = _parse_changelog(self.SAMPLE_MD)
        assert result[0].date == "in progress"
        assert result[1].date == "2026-02-19"
        assert result[2].date == "2026-02-12"

    def test_date_empty_when_no_parentheses(self):
        md = "## 1.0.0 — Title\n\nSome text.\n"
        result = _parse_changelog(md)
        assert result[0].date == ""
        assert result[0].title == "1.0.0 — Title"

    def test_body_html_contains_list_items(self):
        result = _parse_changelog(self.SAMPLE_MD)
        assert "<li>" in result[0].body_html
        assert "Clear AI Results" in result[0].body_html

    def test_body_html_contains_paragraphs(self):
        result = _parse_changelog(self.SAMPLE_MD)
        assert "<p>" in result[0].body_html
        assert "Stability improvements" in result[0].body_html

    def test_bold_formatting(self):
        md = "## 1.0.0\n\nA **bold** word.\n"
        result = _parse_changelog(md)
        assert "<strong>bold</strong>" in result[0].body_html

    def test_italic_formatting(self):
        md = "## 1.0.0\n\nAn *italic* word.\n"
        result = _parse_changelog(md)
        assert "<em>italic</em>" in result[0].body_html

    def test_empty_input(self):
        assert _parse_changelog("") == []

    def test_no_versions(self):
        assert _parse_changelog("# Changelog\n\nSome text.\n") == []

    def test_parses_real_changelog(self):
        md_path = Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"
        text = md_path.read_text(encoding="utf-8")
        result = _parse_changelog(text)
        assert len(result) >= 3
        assert result[0].version == "0.9.1"

    def test_html_entities_escaped(self):
        md = '## 1.0.0\n\nUse <html> & "quotes".\n'
        result = _parse_changelog(md)
        assert "&lt;html&gt;" in result[0].body_html
        assert "&amp;" in result[0].body_html

    def test_version_parts_larger_than_ten(self):
        md = "## 1.10.100\n\nBig version.\n"
        result = _parse_changelog(md)
        assert result[0].version == "1.10.100"


# --- Group by minor tests ---


class TestGroupByMinor:
    """Tests for _group_by_minor()."""

    def test_groups_same_minor(self):
        versions = [
            ChangelogVersion("0.9.1", "0.9.1", "in progress", "<p>A</p>"),
            ChangelogVersion("0.9.0", "0.9.0 — Title", "2026-02-20", "<p>B</p>"),
        ]
        groups = _group_by_minor(versions)
        assert len(groups) == 1
        assert groups[0].label == "0.9.x"
        assert groups[0].slug == "0.9"
        assert len(groups[0].versions) == 2

    def test_different_minors_separate_groups(self):
        versions = [
            ChangelogVersion("0.9.0", "0.9.0", "", "<p>A</p>"),
            ChangelogVersion("0.8.0", "0.8.0", "", "<p>B</p>"),
        ]
        groups = _group_by_minor(versions)
        assert len(groups) == 2
        assert groups[0].slug == "0.9"
        assert groups[1].slug == "0.8"

    def test_preserves_order(self):
        versions = [
            ChangelogVersion("1.10.0", "1.10.0", "", "<p>A</p>"),
            ChangelogVersion("1.2.0", "1.2.0", "", "<p>B</p>"),
        ]
        groups = _group_by_minor(versions)
        assert groups[0].slug == "1.10"
        assert groups[1].slug == "1.2"

    def test_empty_input(self):
        assert _group_by_minor([]) == []


# --- Generate HTML tests ---


class TestGenerateChangelogHtml:
    """Tests for _generate_changelog_html()."""

    @pytest.fixture
    def versions(self):
        """Two versions in same minor group + one in another."""
        return [
            ChangelogVersion("0.9.1", "0.9.1", "in progress", "<p>Latest changes.</p><ul><li>Feature A</li></ul>"),
            ChangelogVersion("0.9.0", "0.9.0 — Stability", "2026-02-20", "<p>Stability improvements.</p>"),
            ChangelogVersion(
                "0.8.0", "0.8.0 — Native UI", "2026-02-19", "<p>GUI rewrite.</p><ul><li>Feature B</li></ul>"
            ),
        ]

    def test_returns_page_order(self, versions, tmp_path):
        page_order = _generate_changelog_html(versions, tmp_path)
        assert page_order == ["pages/0.9.html", "pages/0.8.html"]
        assert "index.html" not in page_order

    def test_one_page_per_minor(self, versions, tmp_path):
        """Two 0.9.x versions should produce one page, not two."""
        _generate_changelog_html(versions, tmp_path)
        assert (tmp_path / "pages" / "0.9.html").exists()
        assert (tmp_path / "pages" / "0.8.html").exists()
        # No per-patch files
        assert not (tmp_path / "pages" / "0.9.1.html").exists()
        assert not (tmp_path / "pages" / "0.9.0.html").exists()

    def test_creates_index_html(self, versions, tmp_path):
        _generate_changelog_html(versions, tmp_path)
        assert (tmp_path / "index.html").exists()

    def test_pages_have_sidebar(self, versions, tmp_path):
        _generate_changelog_html(versions, tmp_path)
        for name in ["index.html", "pages/0.9.html", "pages/0.8.html"]:
            content = (tmp_path / name).read_text()
            assert 'class="sidebar"' in content
            assert 'class="content"' in content

    def test_sidebar_labels_use_x_suffix(self, versions, tmp_path):
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.9.html").read_text()
        assert ">0.9.x<" in content
        assert ">0.8.x<" in content

    def test_pages_have_active_link(self, versions, tmp_path):
        _generate_changelog_html(versions, tmp_path)
        for name in ["pages/0.9.html", "pages/0.8.html"]:
            content = (tmp_path / name).read_text()
            assert 'class="active"' in content

    def test_index_contains_latest_version(self, versions, tmp_path):
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "index.html").read_text()
        assert "Latest changes." in content
        assert "0.9.1" in content

    def test_grouped_page_has_both_versions(self, versions, tmp_path):
        """The 0.9.x page should contain both 0.9.1 and 0.9.0 content."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.9.html").read_text()
        assert "0.9.1" in content
        assert "0.9.0" in content
        assert "Latest changes." in content
        assert "Stability improvements." in content

    def test_grouped_page_has_divider(self, versions, tmp_path):
        """Multiple versions in one group should be separated by an hr."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.9.html").read_text()
        assert 'class="version-divider"' in content

    def test_single_version_page_has_no_divider(self, versions, tmp_path):
        """A group with one version should not have an hr."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.8.html").read_text()
        assert 'class="version-divider"' not in content

    def test_all_versions_use_h1(self, versions, tmp_path):
        """Every version in a group gets h1."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.9.html").read_text()
        assert "<h1>0.9.1</h1>" in content
        assert "<h1>0.9.0" in content

    def test_pages_reference_shared_css(self, versions, tmp_path):
        """Pages should reference the shared viewer.css via relative path."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.9.html").read_text()
        assert "viewer.css" in content

    def test_pages_include_search_js(self, versions, tmp_path):
        """Pages should include the search.js script."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.9.html").read_text()
        assert "search.js" in content

    def test_page_hrefs_are_sibling_relative(self, versions, tmp_path):
        """Page sidebar hrefs must be sibling-relative (no pages/ prefix)."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.8.html").read_text()
        assert 'href="0.9.html"' in content
        assert 'href="0.8.html"' in content
        assert 'href="pages/' not in content

    def test_index_hrefs_are_child_relative(self, versions, tmp_path):
        """Index sidebar hrefs must be child-relative (pages/ prefix)."""
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "index.html").read_text()
        assert 'href="pages/0.9.html"' in content
        assert 'href="pages/0.8.html"' in content

    def test_pages_have_version_date(self, versions, tmp_path):
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "pages" / "0.8.html").read_text()
        assert 'class="version-date"' in content
        assert "2026-02-19" in content

    def test_index_has_version_date(self, versions, tmp_path):
        _generate_changelog_html(versions, tmp_path)
        content = (tmp_path / "index.html").read_text()
        assert 'class="version-date"' in content
        assert "in progress" in content
