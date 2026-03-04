"""Tests for scripts/reformat_md_tables.py."""

from __future__ import annotations

from pathlib import Path

from scripts.reformat_md_tables import _reformat_table, _split_table_row, process_file


class TestSplitTableRow:
    def test_basic(self) -> None:
        assert _split_table_row("| a | b | c |") == ["a", "b", "c"]

    def test_escaped_pipe(self) -> None:
        assert _split_table_row(r"| a \| b | c |") == [r"a \| b", "c"]


class TestReformatTable:
    def test_pads_columns(self) -> None:
        lines = [
            "| a | bb |",
            "|---|---|",
            "| ccc | d |",
        ]
        result = _reformat_table(lines)
        assert result == [
            "| a   | bb |",
            "|-----|----|",
            "| ccc | d  |",
        ]

    def test_single_row_unchanged(self) -> None:
        lines = ["| a | b |"]
        result = _reformat_table(lines)
        assert result == lines


class TestProcessFile:
    def test_reformats_table(self, tmp_path: Path) -> None:
        md = "# Title\n\n| a | b |\n|---|---|\n| ccc | d |\n\nEnd.\n"
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        assert "| a   | b |" in result
        assert "| ccc | d |" in result

    def test_skips_code_blocks(self, tmp_path: Path) -> None:
        md = "```\n| a | b |\n|---|---|\n| ccc | d |\n```\n"
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        # Table inside code block should be unchanged (not padded)
        assert "| a | b |" in result
        assert "| a   |" not in result

    def test_multiple_tables(self, tmp_path: Path) -> None:
        md = "| a | bb |\n|---|---|\n| c | d |\n\nText\n\n| xx | y |\n|---|---|\n| z | ww |\n"
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        # Both tables should be reformatted
        assert "| a | bb |" in result
        assert "| c | d  |" in result
        assert "| xx | y  |" in result
        assert "| z  | ww |" in result

    def test_table_at_end(self, tmp_path: Path) -> None:
        md = "Text\n\n| a | bb |\n|---|---|\n| ccc | d |"
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        assert "| a   | bb |" in result
        assert "| ccc | d  |" in result
