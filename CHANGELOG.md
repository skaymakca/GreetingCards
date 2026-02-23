# Changelog

## 0.9.1 (in progress)

Polish, dark mode support, and fixes to the changelog viewer and build pipeline.

- Full dark mode support — the app automatically follows macOS appearance settings, including native UI elements, toolbar icons, and HTML viewers (Help, Changelog, Licenses)
- Fixed changelog sidebar navigation — clicking versions now works correctly
- Dates displayed as subheadings below version titles
- Simplified changelog build: pre-generated at build time, no runtime generation

## 0.9.0 — Stability & Developer Experience (2026-02-20)

Stability improvements, graceful error handling, and developer experience.

- Added "Clear AI Results" menu item to reset AI analysis for all loaded cards
- Graceful handling when Tesseract is not installed — warnings instead of crashes
- Unified configuration: bundle ignores environment variables for API key, reads only from preferences
- Auto-hide settings status label after brief display
- Constrained preferences dialog width for consistent appearance
- Migrated to uv package manager for faster, more reliable dependency management
- Added "What's New" changelog viewer under the Help menu

## 0.8.0 — Native macOS Interface (2026-02-19)

Complete GUI rewrite from tkinter to wxPython for a fully native macOS experience.

- Native toolbar with SF Symbol icons for all actions
- Filter sidebar with cross-filtered confidence counts and Option-click multi-select
- Master-detail review panel with editable name fields and candidate selection
- Multi-folder loading with content-based deduplication across locations
- Drag-and-drop overlay for adding files and folders
- AI model selection — choose between Haiku 4.5, Sonnet 4.6, or Opus 4.6 in Settings
- Built-in help system with 8 pages, cross-page search, and match navigation
- Native preferences editor with API key management
- File and Edit menus with standard macOS keyboard shortcuts
- Card removal via toolbar, menu, or right-click context menu
- Colored confidence legend in the filter sidebar

## 0.6.0 — Initial Release (2026-02-12)

First release of Greeting Cards — a macOS app for organizing and renaming greeting card PDFs using OCR and AI.

- PDF loading with drag-and-drop support
- OCR text extraction via Tesseract for offline name detection
- AI-powered name analysis using Claude's vision API
- Multi-page PDF preview with zoom and pan controls
- Keyboard navigation for card selection and preview paging
- SQLite caching of OCR results, AI analysis, and manual edits
- Settings dialog with API key management
- macOS app bundle via PyInstaller
