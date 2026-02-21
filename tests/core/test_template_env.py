"""Tests for app.core.template_env module."""

from pathlib import Path

from app.core.template_env import jinja_env, get_page_order


class TestJinjaEnv:
    """Tests for the shared Jinja2 environment."""

    def test_env_has_autoescape(self):
        assert jinja_env.autoescape is True

    def test_env_can_load_templates(self):
        """Environment can find templates in content/html/templates/."""
        templates = jinja_env.loader.list_templates()
        assert len(templates) > 0

    def test_env_has_trim_blocks(self):
        assert jinja_env.trim_blocks is True

    def test_env_has_lstrip_blocks(self):
        assert jinja_env.lstrip_blocks is True


class TestGetPageOrder:
    """Tests for get_page_order()."""

    def test_reads_manifest(self, tmp_path: Path):
        manifest = tmp_path / "page_order.txt"
        manifest.write_text("index.html\npages/foo.html\npages/bar.html\n")
        result = get_page_order(tmp_path)
        assert result == ["index.html", "pages/foo.html", "pages/bar.html"]

    def test_skips_blank_lines(self, tmp_path: Path):
        manifest = tmp_path / "page_order.txt"
        manifest.write_text("index.html\n\npages/foo.html\n\n")
        result = get_page_order(tmp_path)
        assert result == ["index.html", "pages/foo.html"]

    def test_fallback_when_missing(self, tmp_path: Path):
        result = get_page_order(tmp_path)
        assert result == ["index.html"]

    def test_empty_manifest(self, tmp_path: Path):
        manifest = tmp_path / "page_order.txt"
        manifest.write_text("")
        result = get_page_order(tmp_path)
        assert result == []
