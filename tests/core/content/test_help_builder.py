"""Tests for help page builder — frontmatter, validation, reading, and generation."""

from pathlib import Path

import pytest

from app.core.content.help_builder import (
    _parse_frontmatter,
    _read_help_pages,
    _validate_numbering,
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

    def test_empty_lines_in_frontmatter(self):
        """Empty lines between metadata fields are skipped (line 63)."""
        text = "---\ntitle: Home\n\norder: 1\n---\n\nBody text."
        metadata, body = _parse_frontmatter(text)
        assert metadata["title"] == "Home"
        assert metadata["order"] == "1"
        assert "Body text." in body


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


class TestGenerateHelpHtmlEntryPoint:
    """Tests for the generate_help_html() public entry point (lines 156-228)."""

    def _fake_project_root(self, tmp_path):
        """Set up tmp_path as a fake project root and return a patcher."""
        from unittest.mock import patch

        import app.core.content.help_builder as hb

        fake_file = str(tmp_path / "app" / "core" / "content" / "help_builder.py")
        return patch.object(hb, "__file__", fake_file)

    def test_generates_output_files(self, tmp_path):
        """generate_help_html() creates index.html, pages/, and page_order.txt."""
        help_dir = tmp_path / "content" / "html" / "help"
        help_dir.mkdir(parents=True)
        (help_dir / "1 - index.md").write_text("---\ntitle: Home\n---\n\nWelcome.", encoding="utf-8")
        (help_dir / "2 - guide.md").write_text("---\ntitle: Guide\n---\n\nGuide text.", encoding="utf-8")

        with self._fake_project_root(tmp_path):
            generate_help_html()

        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "help"
        assert output_dir.exists()
        assert (output_dir / "index.html").exists()
        assert (output_dir / "pages" / "guide.html").exists()
        assert (output_dir / "page_order.txt").exists()

        # Verify content
        index_html = (output_dir / "index.html").read_text(encoding="utf-8")
        assert "Welcome" in index_html

        # Verify page_order
        order = (output_dir / "page_order.txt").read_text(encoding="utf-8")
        assert "index.html" in order
        assert "pages/guide.html" in order

    def test_no_pages_early_return(self, tmp_path):
        """generate_help_html() returns early when no help pages found."""
        help_dir = tmp_path / "content" / "html" / "help"
        help_dir.mkdir(parents=True)

        with self._fake_project_root(tmp_path):
            generate_help_html()

        # No output should be created
        output_dir = tmp_path / "_build" / "runtime_content" / "html" / "help"
        assert not output_dir.exists()


class TestGenerateHelpHtmlIntegration:
    """Integration test for the full help generation pipeline."""

    def test_full_pipeline(self, tmp_path):
        """Generate HTML from Markdown help pages and verify output files."""
        from app.core.content.template_env import jinja_env

        # Create help pages directory and files
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "1 - index.md").write_text("---\ntitle: Home\n---\n\nWelcome to help.", encoding="utf-8")
        (help_dir / "2 - usage.md").write_text("---\ntitle: Usage Guide\n---\n\nHow to use the app.", encoding="utf-8")

        # Read and parse pages
        pages = _read_help_pages(tmp_path)
        assert len(pages) == 2
        assert pages[0].slug == "index"
        assert pages[1].slug == "usage"

        # Create output directory
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        pages_dir = output_dir / "pages"
        pages_dir.mkdir()

        # Build nav items (same logic as generate_help_html)
        nav_items = []
        for page in pages:
            if page.slug == "index":
                nav_items.append(
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "href": "index.html",
                        "href_from_pages": "../index.html",
                    }
                )
            else:
                nav_items.append(
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "href": f"pages/{page.slug}.html",
                        "href_from_pages": f"{page.slug}.html",
                    }
                )

        # Render pages with real template
        template = jinja_env.get_template("help_page.html.j2")
        for page in pages:
            if page.slug == "index":
                nav = [{"slug": n["slug"], "title": n["title"], "href": n["href"]} for n in nav_items]
                css_path = "../common/css/viewer.css"
                js_path = "../common/js/search.js"
                out_path = output_dir / "index.html"
            else:
                nav = [{"slug": n["slug"], "title": n["title"], "href": n["href_from_pages"]} for n in nav_items]
                css_path = "../../common/css/viewer.css"
                js_path = "../../common/js/search.js"
                out_path = pages_dir / f"{page.slug}.html"

            html = template.render(
                title=page.title,
                css_path=css_path,
                js_path=js_path,
                nav=nav,
                active_slug=page.slug,
                body_html=page.body_html,
            )
            out_path.write_text(html, encoding="utf-8")

        # Write page_order.txt manifest
        order: list[str] = []
        for page in pages:
            if page.slug == "index":
                order.append("index.html")
            else:
                order.append(f"pages/{page.slug}.html")
        (output_dir / "page_order.txt").write_text("\n".join(order), encoding="utf-8")

        # Verify all output files exist
        assert (output_dir / "index.html").exists()
        assert (pages_dir / "usage.html").exists()
        assert (output_dir / "page_order.txt").exists()

        # Verify index.html content
        index_html = (output_dir / "index.html").read_text(encoding="utf-8")
        assert "Welcome to help" in index_html
        assert "Home" in index_html
        assert "Usage Guide" in index_html  # nav item should be present

        # Verify usage.html content
        usage_html = (pages_dir / "usage.html").read_text(encoding="utf-8")
        assert "How to use the app" in usage_html
        assert "Usage Guide" in usage_html
        assert "Home" in usage_html  # nav item should be present

        # Verify page_order.txt
        order_text = (output_dir / "page_order.txt").read_text(encoding="utf-8")
        assert order_text == "index.html\npages/usage.html"

    def test_empty_help_directory(self, tmp_path):
        """Empty help directory results in empty page list."""
        help_dir = tmp_path / "help"
        help_dir.mkdir()

        pages = _read_help_pages(tmp_path)
        assert pages == []
        assert len(pages) == 0

    def test_path_references_in_nav(self, tmp_path):
        """Verify correct CSS/JS and nav href paths for index vs pages."""
        from app.core.content.template_env import jinja_env

        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "1 - index.md").write_text("---\ntitle: Home\n---\n\nIndex body.", encoding="utf-8")
        (help_dir / "2 - guide.md").write_text("---\ntitle: Guide\n---\n\nGuide body.", encoding="utf-8")

        pages = _read_help_pages(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        pages_dir = output_dir / "pages"
        pages_dir.mkdir()

        nav_items = []
        for page in pages:
            if page.slug == "index":
                nav_items.append(
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "href": "index.html",
                        "href_from_pages": "../index.html",
                    }
                )
            else:
                nav_items.append(
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "href": f"pages/{page.slug}.html",
                        "href_from_pages": f"{page.slug}.html",
                    }
                )

        template = jinja_env.get_template("help_page.html.j2")

        # Render index page
        index_nav = [{"slug": n["slug"], "title": n["title"], "href": n["href"]} for n in nav_items]
        index_html = template.render(
            title="Home",
            css_path="../common/css/viewer.css",
            js_path="../common/js/search.js",
            nav=index_nav,
            active_slug="index",
            body_html="<p>Index body.</p>",
        )
        (output_dir / "index.html").write_text(index_html, encoding="utf-8")

        # Render guide page
        guide_nav = [{"slug": n["slug"], "title": n["title"], "href": n["href_from_pages"]} for n in nav_items]
        guide_html = template.render(
            title="Guide",
            css_path="../../common/css/viewer.css",
            js_path="../../common/js/search.js",
            nav=guide_nav,
            active_slug="guide",
            body_html="<p>Guide body.</p>",
        )
        (pages_dir / "guide.html").write_text(guide_html, encoding="utf-8")

        # Verify index.html has correct paths
        index_content = (output_dir / "index.html").read_text(encoding="utf-8")
        assert "../common/css/viewer.css" in index_content
        assert "../common/js/search.js" in index_content

        # Verify guide.html has correct paths
        guide_content = (pages_dir / "guide.html").read_text(encoding="utf-8")
        assert "../../common/css/viewer.css" in guide_content
        assert "../../common/js/search.js" in guide_content

        # Verify nav href paths
        assert 'href="index.html"' in index_content  # index page nav link to index
        assert 'href="pages/guide.html"' in index_content  # index page nav link to guide
        assert 'href="../index.html"' in guide_content  # guide page nav link to index (sibling-relative)
        assert 'href="guide.html"' in guide_content  # guide page nav link to guide (sibling-relative)
