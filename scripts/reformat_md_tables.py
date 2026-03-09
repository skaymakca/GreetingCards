"""Reformat Markdown tables to PyCharm standards.

Pads all cells to consistent column widths so PyCharm's
MarkdownIncorrectTableFormatting inspection passes.
See docs/pycharm-table-formatting.md for the full rule set.

Usage::

    uv run python -m scripts.reformat_md_tables file1.md file2.md ...
"""

from __future__ import annotations

import sys
from pathlib import Path

# Sentinel for escaped pipes inside cell content
_PIPE_PLACEHOLDER = "\x00PIPE\x00"


def _split_table_row(line: str) -> list[str]:
    r"""Split a Markdown table row on unescaped pipes, handling \| inside cells."""
    # Replace escaped pipes with placeholder before splitting
    safe = line.replace("\\|", _PIPE_PLACEHOLDER)
    parts = safe.split("|")
    # Remove first and last empty parts from leading/trailing |
    return [c.strip().replace(_PIPE_PLACEHOLDER, "\\|") for c in parts[1:-1]]


def _reformat_table(lines: list[str]) -> list[str]:
    """Reformat a Markdown table block."""
    rows: list[list[str]] = []
    for line in lines:
        cells = _split_table_row(line)
        rows.append(cells)

    if len(rows) < 2:
        return lines

    num_cols = len(rows[0])

    # Find max width per column (skip separator row at index 1)
    max_widths = [0] * num_cols
    for i, row in enumerate(rows):
        if i == 1:  # separator
            continue
        for j in range(min(len(row), num_cols)):
            max_widths[j] = max(max_widths[j], len(row[j]))

    # Reformat
    result: list[str] = []
    for i, row in enumerate(rows):
        if i == 1:  # separator
            parts = "|"
            for w in max_widths:
                parts += "-" * (w + 2) + "|"
            result.append(parts)
        else:
            parts = "|"
            for j in range(num_cols):
                cell = row[j] if j < len(row) else ""
                parts += " " + cell.ljust(max_widths[j]) + " |"
            result.append(parts)

    return result


def process_file(filepath: Path) -> str:
    """Process a Markdown file, reformatting all tables outside code blocks."""
    lines = filepath.read_text().splitlines()

    result: list[str] = []
    in_code_block = False
    table_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Track code blocks (``` or ````)
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            if table_lines:
                result.extend(_reformat_table(table_lines))
                table_lines = []
            result.append(line)
            continue

        if in_code_block:
            if table_lines:
                result.extend(_reformat_table(table_lines))
                table_lines = []
            result.append(line)
            continue

        # Check if line is a table row
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(line)
        else:
            if table_lines:
                result.extend(_reformat_table(table_lines))
                table_lines = []
            result.append(line)

    if table_lines:
        result.extend(_reformat_table(table_lines))

    return "\n".join(result) + "\n"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python -m scripts.reformat_md_tables file1.md ...")
        sys.exit(1)

    for fp in sys.argv[1:]:
        path = Path(fp)
        output = process_file(path)
        path.write_text(output)
        print(f"Reformatted: {fp}")


if __name__ == "__main__":  # pragma: no cover — script entry point
    main()
