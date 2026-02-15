# Project Instructions for Claude

## 🚫 CRITICAL: NO AUTO-COMMITS 🚫

**NEVER commit code without explicit user request.**

- ❌ Do NOT commit after completing tasks
- ❌ Do NOT commit after writing tests
- ❌ Do NOT commit after fixing bugs
- ✅ ONLY commit when user explicitly says "commit X"
- ✅ Keep track of changes to write good commit messages when asked

---

## ⚠️ CRITICAL: ALWAYS USE VENV ⚠️

**NEVER use system Python. ONLY use the virtual environment.**

### Correct Python/pip usage:
```bash
# ✅ CORRECT - Use .venv Python
.venv/bin/python -m pytest tests/
.venv/bin/python main.py
.venv/bin/python -m pip install package-name

# ✅ CORRECT - Activate venv first
source .venv/bin/activate
python -m pytest tests/
python main.py

# ❌ WRONG - System Python (DO NOT USE)
python3 -m pytest tests/
python3 main.py
/usr/bin/python3 -m pip install package-name
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
```

### Rules:
- **ALWAYS** use `.venv/bin/python` for all Python commands
- **NEVER** use `python3`, `/usr/bin/python3`, or system Python paths
- **NEVER** install packages outside the venv
- If a command fails, check that you're using .venv Python first
- The venv directory is `.venv` (with leading dot)

---

## Project Overview

Greeting Cards - macOS app for organizing and renaming greeting card PDFs using OCR and AI.

### Tech Stack
- Python 3.14 (from python.org)
- wxPython (migrating from tkinter)
- PyMuPDF for PDF rendering
- Anthropic Claude API for AI analysis

### Active Work
- **Branch:** `wx`
- **Goal:** Migrate from tkinter to wxPython for native macOS appearance
- See `WX_MIGRATION_PLAN.md` for full migration plan

### Key Notes
- macOS native widgets: use ttk/wx widgets without explicit bg colors
- Python 3.14: exception variables cleared after except block
- Always test both source version and app bundle when making UI changes

---

## Architecture Docs

When editing files in these areas, **read the corresponding doc first**, then **update the doc** if your changes alter the documented behavior.

| Files Being Edited | Read First |
|---|---|
| `app/gui/wx_main_window.py` (filters, `_refresh_display`) | `docs/architecture/filter-pipeline.md` |
| `app/gui/wx_filter_sidebar.py` | `docs/architecture/filter-pipeline.md` |
| `app/gui/wx_main_window.py` (card loading, state, dedup) | `docs/architecture/card-data-model.md` |
| `app/models/card.py` | `docs/architecture/card-data-model.md` |
| `app/gui/wx_review_panel_master_detail.py` | `docs/architecture/review-panel.md` |
| `app/gui/wx_main_window.py` (processing, AI, threads) | `docs/architecture/async-processing.md` |
| `app/core/ai_analyzer.py` | `docs/architecture/async-processing.md` |
| `app/core/name_extractor.py`, `app/core/name_formatting.py` | `docs/architecture/name-pipeline.md` |
| `app/core/database.py`, `app/core/renamer.py` | `docs/architecture/name-pipeline.md` |

### Keeping Docs in Sync

- **After modifying code:** If your changes affect control flow, data structures, callback contracts, or gotchas described in an architecture doc, update the doc in the same work session. Don't leave stale docs behind.
- **If docs contradict code:** The code is the source of truth. Update the doc to match. If the code seems wrong based on the doc's described intent, flag the discrepancy to the user before changing either — it may be an out-of-date doc or a misaligned implementation that needs discussion.
- **New subsystems:** If you add a major new subsystem (new panel, new processing pipeline, etc.), create a new doc in `docs/architecture/` and add it to the table above.
