# Project Instructions for Claude

## 🚫 CRITICAL: NO AUTO-COMMITS 🚫

**NEVER commit code without explicit user request.**

- ❌ Do NOT commit after completing tasks
- ❌ Do NOT commit after writing tests
- ❌ Do NOT commit after fixing bugs
- ✅ ONLY commit when user explicitly says "commit X"
- ✅ Keep track of changes to write good commit messages when asked

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
