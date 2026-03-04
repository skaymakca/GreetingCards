# Changelog

## 0.12.1 — Infrastructure & Reliability (2026-03-04)

Internal improvements to build infrastructure, test coverage, and release automation.

## 0.12.0 — Scripting & Distribution (2026-03-02)

AppleScript automation and a polished macOS installer.

- AppleScript scripting support — automate the app from Script Editor, Automator, or Terminal with 17 commands for loading folders, querying cards, triggering AI analysis, renaming, and more
- DMG installer with Applications shortcut, sample greeting cards, and drag-to-install guide
- New "Scripting" help page with command reference, example scripts, and syntax-highlighted code

## 0.11.0 — Name Intelligence & Smoother Workflow (2026-02-27)

Better name recognition, non-blocking AI analysis, and selection reliability.

- Non-modal progress strip replaces the blocking dialog during AI analysis — browse and review results as they arrive
- Master family name database with 213,000+ surnames provides proper display forms (O'Brien, van der Berg, etc.) and improves OCR name accuracy
- Expanded name filter blocklist prevents greeting card phrases, print services (Shutterfly, Minted), and holidays from being suggested as family names
- Card selection is preserved across refresh when no filters are active
- Fixed stale selection after AI analysis completes and filters auto-reset
- Fixed progress gauge color appearing incorrectly in dark mode
- A single failing PDF no longer aborts the entire processing run

## 0.10.0 — Dark Mode & Reliability (2026-02-25)

Dark mode support, database reliability, smarter API handling, and broad quality improvements.

- Full dark mode support — the app automatically follows macOS appearance settings, including native UI elements, toolbar icons, and HTML viewers (Help, Changelog, Licenses)
- Cmd+W now closes the focused window (Help, Changelog, Licenses) instead of quitting the app
- "AI Analyze" available in the card list right-click context menu
- GitHub repository link added to the Help menu and help page
- Native file/folder picker replaces the old file dialog for a more consistent macOS experience
- Smarter API retry handling with exponential backoff and rate limit coordination across concurrent requests
- Fixed database concurrency issues — race conditions, dangling foreign keys, and fragmented sessions
- Auto-reload uses file modification time as a fast pre-filter, skipping unchanged files
- Fixed changelog sidebar navigation and date display
- Bundled Tesseract OCR data for more reliable out-of-the-box text recognition

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
- Multipage PDF preview with zoom and pan controls
- Keyboard navigation for card selection and preview paging
- SQLite caching of OCR results, AI analysis, and manual edits
- Settings dialog with API key management
- macOS app bundle via PyInstaller
