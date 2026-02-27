"""Tests for scripts/dmg/readme.py."""

from __future__ import annotations

import pathlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.dmg.readme import _inline, _render_body, _rtf_escape, generate


class TestRtfEscape:
    def test_backslash_escaped(self) -> None:
        assert _rtf_escape("a\\b") == "a\\\\b"

    def test_open_brace_escaped(self) -> None:
        assert _rtf_escape("a{b") == "a\\{b"

    def test_close_brace_escaped(self) -> None:
        assert _rtf_escape("a}b") == "a\\}b"

    def test_pure_ascii_unchanged(self) -> None:
        assert _rtf_escape("Hello, World!") == "Hello, World!"

    def test_unicode_char_encoded(self) -> None:
        result = _rtf_escape("café")
        assert "\\u233?" in result  # é = U+00E9 = 233

    def test_unicode_char_high_codepoint(self) -> None:
        result = _rtf_escape("\u4e2d")  # 中
        assert "\\u20013?" in result  # 0x4E2D = 20013


class TestInline:
    def test_plain_text_unchanged(self) -> None:
        assert _inline("Hello world") == "Hello world"

    def test_bold_markers_converted(self) -> None:
        result = _inline("This is **bold** text")
        assert "{\\b bold}" in result
        assert "This is " in result
        assert " text" in result

    def test_multiple_bold_spans(self) -> None:
        result = _inline("**A** and **B**")
        assert result.count("{\\b ") == 2

    def test_no_bold_markers_plain(self) -> None:
        result = _inline("plain text")
        assert result == "plain text"


class TestRenderBody:
    def test_heading(self) -> None:
        result = _render_body("## My Heading")
        assert "My Heading" in result
        assert "\\b" in result

    def test_bullet_list(self) -> None:
        result = _render_body("- Item one\n- Item two")
        assert "Item one" in result
        assert "Item two" in result
        assert "\\li360" in result

    def test_numbered_list(self) -> None:
        result = _render_body("1. First item\n2. Second item")
        assert "1." in result
        assert "First item" in result
        assert "\\li360" in result

    def test_paragraph(self) -> None:
        result = _render_body("A plain paragraph.")
        assert "A plain paragraph." in result
        assert "\\par" in result

    def test_empty_lines_skipped(self) -> None:
        result = _render_body("Para one\n\nPara two")
        assert "Para one" in result
        assert "Para two" in result

    def test_mixed_content(self) -> None:
        md = "## Section\n\nA paragraph.\n\n- Bullet\n\n1. Numbered"
        result = _render_body(md)
        assert "Section" in result
        assert "A paragraph." in result
        assert "Bullet" in result
        assert "Numbered" in result


class TestGenerate:
    def _make_mock_image(self) -> MagicMock:
        mock_img = MagicMock()
        mock_img.convert.return_value = mock_img
        mock_img.resize.return_value = mock_img
        mock_img.save.side_effect = lambda buf, fmt: buf.write(b"\x89PNG\r\n\x1a\n")
        return mock_img

    def test_creates_rtfd_directory(self, tmp_path: Path) -> None:
        readme_md = tmp_path / "readme.md"
        readme_md.write_text("## Hello\n\nWelcome.", encoding="utf-8")

        icon_png = tmp_path / "icon.png"
        output_dir = tmp_path / "Read Me.rtfd"

        mock_img = self._make_mock_image()

        with (
            patch("scripts.dmg.readme._OUTPUT", output_dir),
            patch("scripts.dmg.readme._README_MD", readme_md),
            patch("scripts.dmg.readme._ICON_PNG", icon_png),
            patch("PIL.Image") as mock_image_mod,
        ):
            mock_image_mod.open.return_value = mock_img
            mock_image_mod.Resampling = MagicMock()
            result = generate("1.2.3")

        assert result == output_dir
        assert output_dir.is_dir()
        assert (output_dir / "TXT.rtf").exists()

    def test_version_string_in_rtf(self, tmp_path: Path) -> None:
        readme_md = tmp_path / "readme.md"
        readme_md.write_text("## Hello", encoding="utf-8")

        icon_png = tmp_path / "icon.png"
        output_dir = tmp_path / "Read Me.rtfd"

        mock_img = self._make_mock_image()

        with (
            patch("scripts.dmg.readme._OUTPUT", output_dir),
            patch("scripts.dmg.readme._README_MD", readme_md),
            patch("scripts.dmg.readme._ICON_PNG", icon_png),
            patch("PIL.Image") as mock_image_mod,
        ):
            mock_image_mod.open.return_value = mock_img
            mock_image_mod.Resampling = MagicMock()
            generate("9.8.7")

        rtf_content = (output_dir / "TXT.rtf").read_text(encoding="ascii", errors="replace")
        assert "9.8.7" in rtf_content
