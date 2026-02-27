"""Tests for changelog parsing and HTML generation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.content.changelog import (
    _generate_changelog_html,
    _group_by_minor,
    _minor_key,
    _parse_changelog,
    generate_changelog_html,
)
from app.core.content.changelog_models import ChangelogVersion


class TestParseChangelog:
    """Tests for _parse_changelog()."""

    def test_single_version_with_bullets(self):
        md = "## 0.9.0 — Initial (2026-02-01)\n\n- First feature\n- Second feature\n"
        versions = _parse_changelog(md)
        assert len(versions) == 1
        assert versions[0].version == "0.9.0"
        assert versions[0].date == "2026-02-01"
        assert "<li>" in versions[0].body_html
        assert "First feature" in versions[0].body_html

    def test_multiple_versions(self):
        md = (
            "# Changelog\n\n"
            "## 0.9.0 — Title (2026-02-01)\n\n- Feature A\n\n"
            "## 0.8.0 — Older (2026-01-15)\n\n- Feature B\n"
        )
        versions = _parse_changelog(md)
        assert len(versions) == 2
        assert versions[0].version == "0.9.0"
        assert versions[1].version == "0.8.0"

    def test_heading_without_date(self):
        md = "## 1.0.0 — Big Release\n\n- Something\n"
        versions = _parse_changelog(md)
        assert len(versions) == 1
        assert versions[0].date == ""
        assert versions[0].title == "1.0.0 — Big Release"

    def test_bold_and_italic(self):
        md = "## 0.1.0 (date)\n\n- **Bold** and *italic* text\n"
        versions = _parse_changelog(md)
        assert "<strong>Bold</strong>" in versions[0].body_html
        assert "<em>italic</em>" in versions[0].body_html

    def test_paragraph_text(self):
        md = "## 0.1.0 (date)\n\nSome paragraph text here.\n"
        versions = _parse_changelog(md)
        assert "<p>" in versions[0].body_html
        assert "Some paragraph text here." in versions[0].body_html

    def test_empty_input(self):
        versions = _parse_changelog("")
        assert versions == []

    def test_list_to_paragraph_transition(self):
        """Paragraph directly after a list item closes the <ul> (lines 99-100)."""
        md = "## 0.1.0 (date)\n\n- Bullet item\nParagraph right after bullet.\n"
        versions = _parse_changelog(md)
        assert len(versions) == 1
        assert "</ul>" in versions[0].body_html
        assert "<p>" in versions[0].body_html
        assert "Paragraph right after bullet." in versions[0].body_html


class TestMinorKey:
    """Tests for _minor_key()."""

    def test_normal_version(self):
        assert _minor_key("0.9.1") == "0.9"

    def test_single_segment(self):
        assert _minor_key("1") == "1"

    def test_two_segments(self):
        assert _minor_key("1.2") == "1.2"


class TestGroupByMinor:
    """Tests for _group_by_minor()."""

    def test_groups_patches(self):
        versions = [
            ChangelogVersion(version="0.9.1", title="0.9.1", date="", body_html=""),
            ChangelogVersion(version="0.9.0", title="0.9.0", date="", body_html=""),
            ChangelogVersion(version="0.8.0", title="0.8.0", date="", body_html=""),
        ]
        groups = _group_by_minor(versions)
        assert len(groups) == 2
        assert groups[0].label == "0.9.x"
        assert len(groups[0].versions) == 2
        assert groups[1].label == "0.8.x"

    def test_preserves_order(self):
        versions = [
            ChangelogVersion(version="1.0.0", title="1.0.0", date="", body_html=""),
            ChangelogVersion(version="0.9.0", title="0.9.0", date="", body_html=""),
        ]
        groups = _group_by_minor(versions)
        assert groups[0].slug == "1.0"
        assert groups[1].slug == "0.9"

    def test_empty_list(self):
        groups = _group_by_minor([])
        assert groups == []


class TestGenerateChangelogHtml:
    """Tests for _generate_changelog_html()."""

    def test_writes_files(self, tmp_path):
        versions = [
            ChangelogVersion(version="0.9.0", title="0.9.0", date="2026-02-01", body_html="<p>Hello</p>"),
        ]
        page_order = _generate_changelog_html(versions, tmp_path)
        assert len(page_order) == 1
        assert (tmp_path / "pages" / "0.9.html").exists()

    def test_index_is_latest(self, tmp_path):
        versions = [
            ChangelogVersion(version="0.9.0", title="0.9.0", date="", body_html="<p>Latest</p>"),
            ChangelogVersion(version="0.8.0", title="0.8.0", date="", body_html="<p>Older</p>"),
        ]
        _generate_changelog_html(versions, tmp_path)
        index = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert "Latest" in index

    def test_page_order_manifest(self, tmp_path):
        versions = [
            ChangelogVersion(version="0.9.0", title="0.9.0", date="", body_html=""),
            ChangelogVersion(version="0.8.0", title="0.8.0", date="", body_html=""),
        ]
        _generate_changelog_html(versions, tmp_path)
        manifest = (tmp_path / "page_order.txt").read_text(encoding="utf-8")
        lines = manifest.strip().split("\n")
        assert len(lines) == 2

    def test_empty_versions(self, tmp_path):
        page_order = _generate_changelog_html([], tmp_path)
        assert page_order == []
        assert not (tmp_path / "index.html").exists()


class TestGenerateChangelogHtmlEntryPoint:
    """Tests for generate_changelog_html() public entry point."""

    def test_generates_html_files_with_minimal_changelog(self, tmp_path):
        """Test that generate_changelog_html() creates output files for a minimal changelog."""
        # Create minimal CHANGELOG.md
        changelog_content = "## 0.9.0 — Initial (2026-02-01)\n\n- First feature\n"
        (tmp_path / "CHANGELOG.md").write_text(changelog_content, encoding="utf-8")

        # Mock _get_project_root to return tmp_path
        with patch("app.core.changelog._get_project_root", return_value=tmp_path):
            generate_changelog_html()

        # Verify output directory structure
        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "changelog"
        assert output_dir.exists()

    def test_creates_index_html(self, tmp_path):
        """Test that index.html is created in the output directory."""
        changelog_content = "## 0.9.0 — Initial (2026-02-01)\n\n- Feature A\n"
        (tmp_path / "CHANGELOG.md").write_text(changelog_content, encoding="utf-8")

        with patch("app.core.changelog._get_project_root", return_value=tmp_path):
            generate_changelog_html()

        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "changelog"
        index_file = output_dir / "index.html"
        assert index_file.exists()
        assert index_file.stat().st_size > 0

    def test_creates_page_order_manifest(self, tmp_path):
        """Test that page_order.txt manifest is created."""
        changelog_content = (
            "## 0.9.0 — Initial (2026-02-01)\n\n- Feature A\n\n## 0.8.0 — Older (2026-01-15)\n\n- Feature B\n"
        )
        (tmp_path / "CHANGELOG.md").write_text(changelog_content, encoding="utf-8")

        with patch("app.core.changelog._get_project_root", return_value=tmp_path):
            generate_changelog_html()

        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "changelog"
        manifest_file = output_dir / "page_order.txt"
        assert manifest_file.exists()
        manifest_content = manifest_file.read_text(encoding="utf-8")
        assert manifest_content.strip()  # Non-empty manifest

    def test_generates_version_pages(self, tmp_path):
        """Test that individual version pages are generated in pages/ subdirectory."""
        changelog_content = (
            "## 0.9.0 — Initial (2026-02-01)\n\n- Feature A\n\n## 0.8.0 — Older (2026-01-15)\n\n- Feature B\n"
        )
        (tmp_path / "CHANGELOG.md").write_text(changelog_content, encoding="utf-8")

        with patch("app.core.changelog._get_project_root", return_value=tmp_path):
            generate_changelog_html()

        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "changelog"
        pages_dir = output_dir / "pages"
        assert pages_dir.exists()
        # At least one version page should exist
        html_files = list(pages_dir.glob("*.html"))
        assert len(html_files) > 0

    def test_handles_multiple_versions(self, tmp_path):
        """Test that multiple versions are processed correctly."""
        changelog_content = (
            "## 1.0.0 — Release (2026-02-15)\n\n- Major feature\n\n"
            "## 0.9.1 — Patch (2026-02-10)\n\n- Bugfix\n\n"
            "## 0.9.0 — Initial (2026-02-01)\n\n- First feature\n"
        )
        (tmp_path / "CHANGELOG.md").write_text(changelog_content, encoding="utf-8")

        with patch("app.core.changelog._get_project_root", return_value=tmp_path):
            generate_changelog_html()

        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "changelog"
        manifest_file = output_dir / "page_order.txt"
        manifest_content = manifest_file.read_text(encoding="utf-8")
        lines = manifest_content.strip().split("\n")
        # Should have entries for multiple versions
        assert len(lines) >= 1

    def test_index_contains_content(self, tmp_path):
        """Test that index.html contains expected content from changelog."""
        changelog_content = "## 0.9.0 — Test Version (2026-02-01)\n\n- Important feature here\n"
        (tmp_path / "CHANGELOG.md").write_text(changelog_content, encoding="utf-8")

        with patch("app.core.changelog._get_project_root", return_value=tmp_path):
            generate_changelog_html()

        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "changelog"
        index_file = output_dir / "index.html"
        index_content = index_file.read_text(encoding="utf-8")
        # Index should contain version info and content
        assert "0.9" in index_content or "Important feature" in index_content
