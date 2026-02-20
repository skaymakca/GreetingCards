# Project Instructions for Claude

## 🚫 CRITICAL: NO AUTO-COMMITS 🚫

**NEVER commit code without explicit user request.**

- ❌ Do NOT commit after completing tasks
- ❌ Do NOT commit after writing tests
- ❌ Do NOT commit after fixing bugs
- ✅ ONLY commit when user explicitly says "commit X"
- ✅ Keep track of changes to write good commit messages when asked
- ✅ Include `Fixes #N` or `Fixes #N, #M` in commit/PR messages when the work resolves GitHub issues

---

## 🚫 CRITICAL: DO NOT MODIFY GITHUB ISSUES 🚫

**NEVER create, close, or edit GitHub issues without explicit user permission.**

- ❌ Do NOT create new issues without being asked
- ❌ Do NOT close or modify existing issues without being asked
- ✅ ONLY manage issues when user explicitly asks you to
- Use `gh issue list` to view open issues

---

## ⚠️ CRITICAL: ALWAYS USE UV ⚠️

**NEVER use system Python or pip. ONLY use `uv run` for all commands.**

### Correct usage:
```bash
# ✅ CORRECT - Use uv run
uv run pytest tests/
uv run python main.py
uv add package-name

# ✅ CORRECT - Install/sync dependencies
uv sync              # all deps (including dev)
uv sync --no-dev     # production only

# ❌ WRONG - System Python (DO NOT USE)
python3 -m pytest tests/
python3 main.py
pip install package-name
.venv/bin/python main.py
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
```

### Rules:
- **ALWAYS** use `uv run` to execute Python commands
- **ALWAYS** use `uv add` to add new dependencies
- **NEVER** use `python3`, `pip`, or direct `.venv/bin/python` paths
- **NEVER** install packages outside uv's management
- If a command fails, check that you're using `uv run` first
- The venv directory is `.venv` (managed by uv, do not create manually)

---

## Project Overview

Greeting Cards - macOS app for organizing and renaming greeting card PDFs using OCR and AI.

### Tech Stack
- Python 3.14 (from python.org)
- wxPython for native macOS GUI
- PyMuPDF for PDF rendering
- Anthropic Claude API for AI analysis

### Key Notes
- macOS native widgets: use wx widgets without explicit bg colors
- Python 3.14: exception variables cleared after except block
- Always test both source version and app bundle when making UI changes

---

## Architecture Docs

When editing files in these areas, **read the corresponding doc first**, then **update the doc** if your changes alter the documented behavior.

| Files Being Edited | Read First |
|---|---|
| `app/gui/main_window.py` (filters, `_refresh_display`) | `docs/architecture/filter-pipeline.md` |
| `app/gui/filter_sidebar.py` | `docs/architecture/filter-pipeline.md` |
| `app/gui/main_window.py` (card loading, state, dedup) | `docs/architecture/card-data-model.md` |
| `app/models/card.py` | `docs/architecture/card-data-model.md` |
| `app/gui/review_panel.py` | `docs/architecture/review-panel.md` |
| `app/gui/main_window.py` (processing, AI, threads) | `docs/architecture/async-processing.md` |
| `app/core/ai_analyzer.py` | `docs/architecture/async-processing.md` |
| `app/core/name_extractor.py`, `app/core/name_formatting.py` | `docs/architecture/name-pipeline.md` |
| `app/core/database.py`, `app/core/renamer.py` | `docs/architecture/name-pipeline.md` |
| `app/gui/help_dialog.py` | `docs/architecture/help-system.md` |
| `help/**/*.html` | `docs/architecture/help-system.md` |
| `app/core/config.py`, `app/core/paths.py` | `docs/architecture/config-and-preferences.md` |
| `app/gui/settings_dialog.py` | `docs/architecture/config-and-preferences.md` |

### Test Count
When adding or removing tests, update the test count in `README.md` (search for "tests** covering") to match the actual number from `pytest` output.

### Keeping Docs in Sync

- **After modifying code:** If your changes affect control flow, data structures, callback contracts, or gotchas described in an architecture doc, update the doc in the same work session. Don't leave stale docs behind.
- **If docs contradict code:** The code is the source of truth. Update the doc to match. If the code seems wrong based on the doc's described intent, flag the discrepancy to the user before changing either — it may be an out-of-date doc or a misaligned implementation that needs discussion.
- **New subsystems:** If you add a major new subsystem (new panel, new processing pipeline, etc.), create a new doc in `docs/architecture/` and add it to the table above.

---

## Code Quality Audit Checklist

When asked to audit the codebase, check for these categories across all files in `app/` and `tests/`:

### What to Look For
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

### How to Run
Launch parallel Explore agents for each area:
- `app/core/` — all core modules
- `app/gui/main_window.py` — largest file, audit separately
- `app/gui/` (excluding main_window) — all other GUI modules
- `app/models/card.py` — data model
- `tests/` — coverage gap analysis (compare test files against source modules)
