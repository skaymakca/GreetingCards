# PyCharm Markdown Table Formatting

PyCharm's `MarkdownIncorrectTableFormatting` inspection enforces consistent column widths in Markdown tables. These rules were learned by diffing a file before and after PyCharm's "Reformat File" action.

## Rules

1. **Column width = longest cell content** — For each column, find the longest cell content (including the header). All cells in that column are padded with trailing spaces to match this width.

2. **Separator row matches** — The separator row (`|---|`) uses exactly `width + 2` dashes per column, where `width` is the content width from rule 1. The `+2` accounts for one space of padding on each side.

3. **Cell format** — Each cell is: `| ` + content + trailing spaces + ` |`. There is exactly one space between the pipe and the content, and one space between the trailing padding and the closing pipe.

4. **Left-aligned** — All content is left-aligned (padded on the right).

5. **Escaped pipes** — `\|` inside cell content is preserved and does not count as a column delimiter.

## Example

Before (flagged by PyCharm):

```markdown
| Command | What it does |
|---------|-------------|
| `load paths {path, ...}` | Load one or more folder or file paths into the app |
| `get status` | Return processing state |
| `reload` | Re-scan all currently loaded paths |
```

After (passes inspection):

```markdown
| Command                  | What it does                                       |
|--------------------------|----------------------------------------------------|
| `load paths {path, ...}` | Load one or more folder or file paths into the app |
| `get status`             | Return processing state                            |
| `reload`                 | Re-scan all currently loaded paths                 |
```

## Automation

`scripts/reformat_md_tables.py` processes all tables outside code blocks in a Markdown file:

```bash
uv run python -m scripts.reformat_md_tables path/to/file.md
```

Or use PyCharm's built-in "Reformat File" (Cmd+Option+L) on any `.md` file.
