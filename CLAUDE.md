# Project Instructions for Claude

## 🚫 CRITICAL: NO AUTO-COMMITS 🚫

**NEVER commit code without explicit user request.**

- ❌ Do NOT commit after completing tasks
- ❌ Do NOT commit after writing tests
- ❌ Do NOT commit after fixing bugs
- ✅ ONLY commit when user explicitly says "commit X"
- ✅ Keep track of changes to write good commit messages when asked
- ✅ Include `Fixes #N` or `Fixes #N, #M` in commit/PR messages when the work resolves GitHub issues
- ✅ **Always commit ALL unstaged changes** — never do partial/selective commits unless explicitly told to. Tests run against the full working tree, so partial commits can leave broken states in the history.

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
| `app/gui/help_dialog.py`, `app/core/help_builder.py` | `docs/architecture/help-system.md` |
| `content/html/help/*.md` | `docs/architecture/help-system.md` |
| `app/gui/html_viewer.py`, `content/html/common/js/search.js` | `docs/architecture/html-viewer.md` |
| `app/core/changelog.py`, `app/core/changelog_models.py` | `docs/architecture/changelog-viewer.md` |
| `app/gui/changelog_dialog.py`, `content/html/templates/changelog_page.html.j2` | `docs/architecture/changelog-viewer.md` |
| `app/core/license_models.py`, `app/core/license_discovery.py` | `docs/architecture/licenses-viewer.md` |
| `app/gui/licenses_dialog.py`, `content/html/templates/licenses_*.html.j2` | `docs/architecture/licenses-viewer.md` |
| `content/licenses/config.toml`, `content/licenses/manual/*` | `docs/architecture/licenses-viewer.md` |
| `CHANGELOG.md` | `CLAUDE.md` (changelog conventions below) |
| `app/core/config.py`, `app/core/paths.py` | `docs/architecture/config-and-preferences.md` |
| `app/gui/settings_dialog.py` | `docs/architecture/config-and-preferences.md` |

### Test Count
When adding or removing tests, update the test count in `README.md` (search for "tests** covering") to match the actual number from `pytest` output.

### Keeping Docs in Sync

- **After modifying code:** If your changes affect control flow, data structures, callback contracts, or gotchas described in an architecture doc, update the doc in the same work session. Don't leave stale docs behind.
- **If docs contradict code:** The code is the source of truth. Update the doc to match. If the code seems wrong based on the doc's described intent, flag the discrepancy to the user before changing either — it may be an out-of-date doc or a misaligned implementation that needs discussion.
- **New subsystems:** If you add a major new subsystem (new panel, new processing pipeline, etc.), create a new doc in `docs/architecture/` and add it to the table above.

### Changelog Conventions

`CHANGELOG.md` is user-facing (not developer-facing). When updating it:

- **Audience:** End users, not developers
- **Format:** Summary sentence(s) first, then bullets
- **Language:** Plain language — describe *what changed*, not *how*
- **Grouping:** Each `major.minor` version gets its own `## ` entry with date; patch versions fold into their parent
- **When to update:** When making user-visible changes
- **Build step:** `make html-content` regenerates HTML from the markdown; `make app` runs this automatically

### License Sync

After adding or updating packages with `uv add`, run `make licenses-sync` to update the license registry and extract new license texts. Then run `make html-content` to regenerate the HTML.

---

## Code Quality Audit

When asked to audit the codebase, follow the checklist in [`docs/code-quality-audit.md`](docs/code-quality-audit.md).

---

## Pre-Commit Checks

Before committing, run these checks and fix any issues:

| Command | Purpose | Expected |
|---------|---------|----------|
| `uv run pyright app/` | Static type checking (strict structural types) | 0 errors, 0 warnings |
| `uv run mypy app/` | Static type checking (nominal types, plugin-based) | 0 new errors (baseline has import-untyped warnings) |
| `uv run pytest tests/ -x` | Run all tests | All pass |

**pyright** (`pyrightconfig.json`): Catches structural type errors, unused imports, unreachable code. Zero-warning baseline.

**mypy** (no config file yet): Catches nominal type mismatches, SQLAlchemy plugin issues. Has existing `import-untyped` warnings for wx/tesserocr/fitz — don't increase the count.
