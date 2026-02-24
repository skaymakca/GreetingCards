# Code Quality Audit Checklist

When asked to audit the codebase, check for these categories across all files in `app/` and `tests/`.

**Include** the `scripts/benchmark_*.py` files in type checking (`pyright scripts/`, `mypy scripts/`). They are standalone analysis tools, so they are excluded from app test-coverage analysis but should still pass static checks.

## What to Look For
1. **Missing tests** — public methods/functions without tests, untested error paths, shallow happy-path-only coverage
2. **Unused code** — dead imports, unreachable code paths, unused functions/variables
3. **Missing type annotations** — functions missing `-> None` or return types, untyped parameters
4. **Repeated code** — duplicate logic across files that should be extracted to shared helpers
5. **Unpythonic patterns** — `dict.__init__(self)` instead of `super().__init__()`, `lambda: Path()` instead of `Path`, `count == 0` instead of `not count`, etc.
6. **Magic constants** — hardcoded strings, pixel values, colors, or numbers that should be named constants
7. **Hardcoded colors** — `wx.Colour(...)` literals that duplicate values in `app/gui/styles.py`
8. **print() instead of logging** — use `logging.getLogger(__name__)` instead
9. **Incomplete logic** — missing else branches, unhandled empty/None cases, no input validation
10. **Bugs and logic errors** — race conditions, off-by-one errors, unbounded loops, case-sensitivity mismatches, stale state after mutations, silent exception swallowing that hides real failures
11. **Stale Makefile** — targets referencing outdated paths, wrong Python versions, missing new entry points, or commands that no longer match the project structure
12. **License registry gaps** — run `make licenses-sync`, then check `content/licenses/registry.toml` for: missing license text files, empty homepage URLs, "Unknown" license types, platform-specific packages that should be in the `exclude` list in `content/licenses/config.toml`
13. **Redundant license config entries** — `content/licenses/config.toml` `[[package]]` entries should only exist when they override auto-discovered values (e.g. a different display name, homepage URL, license type, or category). Remove entries where `display` matches the package `name` and no other fields are set — the fallback in `_display_name()` already returns the package name

## Static Type Checking

Run both **pyright** and **mypy** on the codebase and review all errors and warnings:

```bash
uv run pyright app/
uv run mypy app/
```

For each diagnostic, determine whether to:
- **Fix the code** — if the checker found a real bug or a type that should be tightened
- **Add a suppression comment** (`# type: ignore[code]` or `# pyright: ignore[code]`) — if the diagnostic is a false positive or an intentional pattern (e.g. `sys._MEIPASS`, wxPython stubs)

**Before applying any suppression comments**, summarize every suppression to the user with:
1. The file, line, and diagnostic code
2. What the checker is complaining about
3. Why suppression (rather than a fix) is the right call

Wait for user approval before adding suppressions. The user may decide to fix the code, file an upstream bug, or handle it differently.

## PyCharm Inspections

Always attempt to run PyCharm inspections on all Python files in `main.py`, `app/**/*.py`, and `scripts/*.py` via the JetBrains MCP server. See the "PyCharm Inspections (MCP)" section in `CLAUDE.md` for details.

If the MCP server is unavailable (PyCharm not running, plugin not installed, tool calls fail), note the reason in the audit report and continue — do not fail the overall audit.

## How to Run
Launch parallel Explore agents for each area:
- `app/core/` — all core modules
- `app/gui/main_window.py` — largest file, audit separately
- `app/gui/` (excluding main_window) — all other GUI modules
- `app/models/card.py` — data model
- `tests/` — coverage gap analysis (compare test files against source modules)
