"""Tests for scripts/reformat_md_tables.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.reformat_md_tables import _reformat_table, _split_table_row, main, process_file

from tests.scripts._reformat_table_data import (
    COVERAGE_ANALYSIS_AFTER,
    COVERAGE_ANALYSIS_BEFORE,
    QUALITY_AUDIT_AFTER,
    QUALITY_AUDIT_BEFORE,
)


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

    def test_table_interrupted_by_code_block(self, tmp_path: Path) -> None:
        md = "| a | bb |\n|---|---|\n| ccc | d |\n```\ncode here\n```\n"
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        # The partial table before the code block should be reformatted
        assert "| a   | bb |" in result
        assert "| ccc | d  |" in result
        # Code block content should remain intact
        assert "code here" in result

    def test_table_inside_code_block_with_surrounding_content(self, tmp_path: Path) -> None:
        """Table-like lines inside a fenced code block with surrounding prose are unchanged."""
        md = (
            "# Doc\n"
            "\n"
            "Real table:\n"
            "\n"
            "| short | verylongcolumn |\n"
            "|---|---|\n"
            "| a | b |\n"
            "\n"
            "Code example:\n"
            "\n"
            "````\n"
            "some code\n"
            "| short | verylongcolumn |\n"
            "|---|---|\n"
            "| a | b |\n"
            "more code\n"
            "````\n"
            "\n"
            "End.\n"
        )
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        lines = result.splitlines()
        # Real table outside code block should be reformatted (padded)
        assert "| short | verylongcolumn |" in lines
        assert "| a     | b              |" in lines
        # Table inside ```` code block should remain exactly as-is (not padded)
        code_block_start = lines.index("````")
        code_block_end = lines.index("````", code_block_start + 1)
        code_lines = lines[code_block_start + 1 : code_block_end]
        assert "| short | verylongcolumn |" in code_lines
        assert "| a | b |" in code_lines

    def test_table_at_end(self, tmp_path: Path) -> None:
        md = "Text\n\n| a | bb |\n|---|---|\n| ccc | d |"
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        assert "| a   | bb |" in result
        assert "| ccc | d  |" in result

    def test_table_immediately_after_code_block_end(self, tmp_path: Path) -> None:
        """Table starting right after ``` closing fence is reformatted normally.

        Exercises the flush path at lines 82-84 (closing fence) and ensures
        table accumulation resumes correctly after the code block ends.
        """
        md = (
            "```\n"
            "| raw | table |\n"
            "|---|---|\n"
            "| inside | code |\n"
            "```\n"
            "| short | verylongcolumn |\n"
            "|---|---|\n"
            "| a | b |\n"
        )
        f = tmp_path / "test.md"
        f.write_text(md)
        result = process_file(f)
        lines = result.splitlines()

        # Table inside code block must remain unformatted
        code_start = lines.index("```")
        code_end = lines.index("```", code_start + 1)
        code_lines = lines[code_start + 1 : code_end]
        assert "| raw | table |" in code_lines
        assert "| inside | code |" in code_lines

        # Table after code block must be reformatted (padded)
        after_code = lines[code_end + 1 :]
        assert "| short | verylongcolumn |" in after_code
        assert "| a     | b              |" in after_code


class TestMain:
    def test_no_args_exits(self) -> None:
        with patch.object(sys, "argv", ["reformat_md_tables"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_reformats_files(self, tmp_path: Path) -> None:
        md = "| a | bb |\n|---|---|\n| ccc | d |\n"
        f = tmp_path / "test.md"
        f.write_text(md)
        with patch.object(sys, "argv", ["reformat_md_tables", str(f)]):
            main()
        content = f.read_text()
        assert "| a   | bb |" in content
        assert "| ccc | d  |" in content


class TestEndToEnd:
    """End-to-end tests using real-world files reformatted by PyCharm."""

    @pytest.mark.parametrize(
        ("before", "after", "name"),
        [
            pytest.param(
                QUALITY_AUDIT_BEFORE,
                QUALITY_AUDIT_AFTER,
                "code-quality-audit.md",
                id="quality-audit",
            ),
            pytest.param(
                COVERAGE_ANALYSIS_BEFORE,
                COVERAGE_ANALYSIS_AFTER,
                "coverage-analysis.md",
                id="coverage-analysis",
            ),
        ],
    )
    def test_real_world_files(self, tmp_path: Path, before: str, after: str, name: str) -> None:
        """Script output matches PyCharm's reformat for real documents."""
        f = tmp_path / name
        f.write_text(before)
        assert process_file(f) == after

    def test_composite_with_edge_cases(self, tmp_path: Path) -> None:
        """Full document combining real tables with edge cases."""
        before = (
            "# Mixed Document\n"
            "\n"
            "## Real table (from coverage analysis)\n"
            "\n"
            "| Part | Tests Added | Coverage Impact |\n"
            "|---|---|---|\n"
            "| Exclusion config | 0 | Removes ~77 untestable lines from denominator |\n"
            "| `app/core/apple_events.py` | 7 | 69% -> ~78% |\n"
            "| **Total** | **~26 tests** | Project coverage: 94.6% -> **~96.5%** |\n"
            "\n"
            "Some prose between tables.\n"
            "\n"
            "## Code block table (must NOT be reformatted)\n"
            "\n"
            "```\n"
            "| a | bb |\n"
            "|---|---|\n"
            "| ccc | d |\n"
            "```\n"
            "\n"
            "## Table with escaped pipes\n"
            "\n"
            "| Pattern | Example |\n"
            "|---|---|\n"
            r"| pipe \| in cell | `echo foo \| bar` |"
            "\n"
            "\n"
            "## Another real table (from quality audit)\n"
            "\n"
            "| Tool | Command | Expected |\n"
            "|---|---|---|\n"
            "| pyright | `pyright app/ scripts/ main.py` | 0 errors, 0 warnings |\n"
            "| bandit | `uv run bandit -r app/ scripts/ -c pyproject.toml` | 0 issues |\n"
        )
        expected = (
            "# Mixed Document\n"
            "\n"
            "## Real table (from coverage analysis)\n"
            "\n"
            "| Part                       | Tests Added   | Coverage Impact                               |\n"
            "|----------------------------|---------------|-----------------------------------------------|\n"
            "| Exclusion config           | 0             | Removes ~77 untestable lines from denominator |\n"
            "| `app/core/apple_events.py` | 7             | 69% -> ~78%                                   |\n"
            "| **Total**                  | **~26 tests** | Project coverage: 94.6% -> **~96.5%**         |\n"
            "\n"
            "Some prose between tables.\n"
            "\n"
            "## Code block table (must NOT be reformatted)\n"
            "\n"
            "```\n"
            "| a | bb |\n"
            "|---|---|\n"
            "| ccc | d |\n"
            "```\n"
            "\n"
            "## Table with escaped pipes\n"
            "\n"
            "| Pattern         | Example           |\n"
            "|-----------------|-------------------|\n"
            r"| pipe \| in cell | `echo foo \| bar` |"
            "\n"
            "\n"
            "## Another real table (from quality audit)\n"
            "\n"
            "| Tool    | Command                                            | Expected             |\n"
            "|---------|----------------------------------------------------|----------------------|\n"
            "| pyright | `pyright app/ scripts/ main.py`                    | 0 errors, 0 warnings |\n"
            "| bandit  | `uv run bandit -r app/ scripts/ -c pyproject.toml` | 0 issues             |\n"
        )
        f = tmp_path / "composite.md"
        f.write_text(before)
        assert process_file(f) == expected
