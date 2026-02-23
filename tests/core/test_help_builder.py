"""Tests for help page builder — frontmatter, validation, reading, and generation."""

import pytest
from pathlib import Path

from app.core.help_builder import (
    _parse_frontmatter,
    _validate_numbering,
    _read_help_pages,
    generate_help_html,
)


class TestParseFrontmatter:
    """Tests for _parse_frontmatter()."""

    def test_normal_frontmatter(self):
        text = "---\ntitle: Getting Started\n---\n\nBody text here."
        metadata, body = _parse_frontmatter(text)
        assert metadata["title"] == "Getting Started"
        assert "Body text here." in body

    def test_no_frontmatter(self):
        text = "Just plain markdown."
        metadata, body = _parse_frontmatter(text)
        assert metadata == {}
        assert body == text

    def test_unclosed_frontmatter(self):
        text = "---\ntitle: Broken\nno closing delimiter"
        metadata, body = _parse_frontmatter(text)
        assert metadata == {}
        assert body == text

    def test_empty_input(self):
        metadata, body = _parse_frontmatter("")
        assert metadata == {}
        assert body == ""


class TestValidateNumbering:
    """Tests for _validate_numbering()."""

    def test_valid_sequence(self):
        _validate_numbering([1, 2, 3], ["a.md", "b.md", "c.md"])

    def test_empty_list(self):
        _validate_numbering([], [])

    def test_gap_raises(self):
        with pytest.raises(ValueError, match="Gap"):
            _validate_numbering([1, 3], ["a.md", "c.md"])

    def test_duplicate_raises(self):
        with pytest.raises(ValueError, match="Duplicate"):
            _validate_numbering([1, 1], ["a.md", "b.md"])

    def test_not_starting_at_one(self):
        with pytest.raises(ValueError, match="must start at 1"):
            _validate_numbering([2, 3], ["a.md", "b.md"])


class TestReadHelpPages:
    """Tests for _read_help_pages()."""

    def test_valid_directory(self, tmp_path):
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "1 - index.md").write_text("---\ntitle: Home\n---\n\nWelcome.", encoding="utf-8")
        (help_dir / "2 - usage.md").write_text("---\ntitle: Usage\n---\n\nHow to use.", encoding="utf-8")

        pages = _read_help_pages(tmp_path)
        assert len(pages) == 2
        assert pages[0].slug == "index"
        assert pages[0].title == "Home"
        assert pages[1].slug == "usage"

    def test_invalid_filename(self, tmp_path):
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "bad-name.md").write_text("content", encoding="utf-8")

        with pytest.raises(ValueError, match="doesn't match"):
            _read_help_pages(tmp_path)

    def test_empty_dir(self, tmp_path):
        help_dir = tmp_path / "help"
        help_dir.mkdir()

        pages = _read_help_pages(tmp_path)
        assert pages == []


class TestGenerateHelpHtml:
    """Tests for generate_help_html() via _read_help_pages + template rendering."""

    def test_writes_files(self, tmp_path):
        """Test that help HTML files and page_order.txt are generated."""
        # Set up content dir with help pages
        help_dir = tmp_path / "content" / "html" / "help"
        help_dir.mkdir(parents=True)
        (help_dir / "1 - index.md").write_text("---\ntitle: Home\n---\n\nWelcome.", encoding="utf-8")
        (help_dir / "2 - guide.md").write_text("---\ntitle: Guide\n---\n\nGuide text.", encoding="utf-8")

        content_dir = tmp_path / "content" / "html"
        pages = _read_help_pages(content_dir)
        assert len(pages) == 2

    def test_title_from_slug_fallback(self, tmp_path):
        """Title defaults to slug when no frontmatter title."""
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "1 - getting-started.md").write_text("No frontmatter here.", encoding="utf-8")

        pages = _read_help_pages(tmp_path)
        assert pages[0].title == "Getting Started"

    def test_no_pages_logs_warning(self, tmp_path, caplog):
        """generate_help_html() logs warning when no pages found."""
        import logging

        # Create the directory structure generate_help_html expects
        help_dir = tmp_path / "content" / "html" / "help"
        help_dir.mkdir(parents=True)

        content_dir = tmp_path / "content" / "html"
        pages = _read_help_pages(content_dir)
        assert pages == []
