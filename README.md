# Greeting Cards

Scans holiday/greeting card PDFs, extracts family names via OCR and AI, and batch-renames the files.

## Features

- **Multi-source loading** — add PDF files or folders from multiple locations without clearing previous loads; cards accumulate across sessions
- **Content-based deduplication** — identical files at different locations are automatically detected (by content hash) and displayed as a single card with multiple file paths
- **PDF rendering** — renders all pages of each PDF using PyMuPDF for preview and analysis
- **Offline OCR** — extracts text from card images with Tesseract, then pattern-matches family names (e.g. "The Smiths", "Love, John & Jane Smith") at high/medium/low confidence levels
- **AI analysis** — sends page images to Claude's vision API for name extraction; available per-card, for selected cards (2+), or all visible cards via toolbar/menu; the label dynamically shows scope and count (e.g., "AI Analyze Visible (12)" or "AI Analyze Selected (3)"); choose between Haiku 4.5 (fast/cheap), Sonnet 4.6 (balanced, default), and Opus 4.6 (most capable) in Settings
- **Intelligent caching** — OCR results, AI results, and manual edits are persisted to a local SQLite database keyed by file content hash, so re-processing the same files (even from different locations) is instant
- **Smart batch rename** — builds a rename plan with per-directory duplicate detection, shows a confirmation dialog, then renames files to `Holiday Cards Year - FamilyName Family.pdf` (or without "Family" suffix if checkbox is checked)
- **Per-file options** — checkbox to omit "Family" suffix from individual filenames (e.g., `Holiday Cards 2024 - Smith.pdf` instead of `Holiday Cards 2024 - Smith Family.pdf`)
- **Drag and drop** — drop files or folders (even multiple at once) onto the window to add them
- **Search and filter** — quick search by filename or family name; sidebar filters by confidence level with Option-click multi-select
- **Preview with zoom/pan** — scroll wheel zoom at cursor, Shift+Click zoom in, Option+Click zoom out, click-drag pan, +/− buttons, Fit button
- **Card removal** — remove cards via the Remove button, Edit > Remove (Cmd+Delete), or right-click context menu (non-destructive; files remain on disk)
- **Right-click context menu** — right-click a card row for Open, Reveal in Finder, and Remove; right-click name fields for Cut, Copy, Paste, Title Case, and Clear
- **Keyboard navigation** — Up/Down to select cards, Shift+Up/Down to extend selection, Cmd+A to select all, Left/Right to page through previews, Cmd+Delete to remove selected cards, Cmd+F to search, Cmd+O to open files, Cmd+Shift+I to AI analyze, Cmd+R to rename, Cmd+, for Settings, Escape to defocus
- **Help system** — built-in WebView help viewer with 8 pages, cross-page search with highlighted matches, and Previous/Next match navigation
- **Native macOS UI** — native toolbar, preferences editor (Cmd+,), About dialog, and system colors throughout
- **API key management** — prompts for the Anthropic API key on first AI use; key is saved to `preferences.plist`; source mode also reads `ANTHROPIC_API_KEY` env var (bundle ignores env var)
- **AI model selection** — choose between Claude Haiku 4.5, Sonnet 4.6, or Opus 4.6 in Settings; persisted to preferences plist; stale/outdated model IDs are auto-migrated to the current default

## Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Quick Start

```bash
# 1. Install dependencies (creates .venv automatically)
make setup

# 2. (Optional) Install development/testing tools
make setup-dev

# 3. Run the app
make run

# 4. (Optional) Run tests
make test
```

## Make commands

Run `make help` to see all available commands.

| Command | Description |
|---------|-------------|
| `make help` | Show all available make commands |
| `make setup` | Install production dependencies (creates venv automatically) |
| `make setup-dev` | Install all dependencies including dev/testing tools |
| `make run` | Run the app from source |
| `make test` | Run all tests |
| `make test-cov` | Run tests with coverage report (generates `htmlcov/index.html`) |
| `make test-unit` | Run unit tests only (fast, no GUI) |
| `make test-gui` | Run GUI tests only (requires wxPython) |
| `make test-watch` | Run tests on file changes (requires pytest-watch) |
| `make build` | Build the macOS `.app` bundle (output: `dist/Greeting Cards.app`) — alias for `make app` |
| `make app` | Build the macOS `.app` bundle (same as `make build`) |
| `make icon` | Generate `icon.icns` from `icon.png` (auto-run by build) |
| `make version` | Print the current version |
| `make bump-patch` | Bump patch version (e.g. 0.5.0 → 0.5.1) |
| `make bump-minor` | Bump minor version (e.g. 0.5.1 → 0.6.0) |
| `make bump-major` | Bump major version (e.g. 0.6.0 → 1.0.0) |
| `make tag` | Create git tag `vX.Y.Z` from current version |
| `make tag-push` | Push all tags to remote |
| `make loc` | Count lines of code in project files (excludes dependencies and build artifacts) |
| `make clean` | Remove `build/` and `dist/` directories |

## Manual setup and commands

### Dependencies

Dependencies are managed with [uv](https://docs.astral.sh/uv/) via `pyproject.toml`:

- **Production dependencies** — `[project.dependencies]`
- **Development/testing tools** — `[dependency-groups]` dev group

### Setup

Install dependencies (creates `.venv` automatically):

```bash
# Install production dependencies only
uv sync --no-dev

# OR install all dependencies (includes dev/testing tools)
uv sync
```

Set your Anthropic API key (for AI analysis) via environment variable or the Settings dialog (Cmd+,):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Run from source:

```bash
uv run python main.py
```

Build the `.app` bundle:

```bash
uv run pyinstaller -y "Greeting Cards.spec"
```

## Testing

The project uses **pytest** for testing with comprehensive test coverage of core functionality and GUI components.

### Quick Start

```bash
# Install all dependencies (includes pytest and testing tools)
make setup-dev

# Run all tests
make test

# Run with coverage report
make test-cov
open htmlcov/index.html
```

### Test Organization

Tests are organized by component:

```
tests/
├── conftest.py                      # Shared fixtures (wx.App, mock frames)
├── core/
│   ├── test_ai_analyzer.py          # AI analysis and error handling
│   ├── test_card_model.py           # Card data model
│   ├── test_config.py               # Configuration and API key management
│   ├── test_database.py             # SQLite database operations
│   ├── test_filename_sanitization.py # Filename safety checks
│   ├── test_name_extractor.py       # OCR text → name extraction
│   ├── test_name_formatting.py      # Name parsing and formatting logic
│   ├── test_ocr_engine.py           # OCR engine integration
│   ├── test_paths.py                # Path resolution (dev vs bundle)
│   ├── test_pdf_renderer.py         # PDF rendering
│   ├── test_renamer.py              # Rename plan and execution
│   └── test_version.py              # Version string
└── gui/
    ├── conftest.py                  # GUI-specific fixtures
    ├── test_api_key_dialog.py       # API key prompt dialog
    ├── test_context_menu.py         # Right-click context menu
    ├── test_dialogs.py              # Progress, rename, completion dialogs
    ├── test_filter_sidebar.py       # Sidebar filters and multi-select
    ├── test_help_dialog.py          # Help viewer and cross-page search
    ├── test_icons.py                # SF Symbol icon loading
    ├── test_main_window.py          # Main window integration
    ├── test_preview_cursor_behavior.py # Preview cursor and modifier keys
    ├── test_preview_panel.py        # Preview panel and zoom/pan
    ├── test_review_panel.py         # Card list and detail panel
    ├── test_settings_dialog.py      # Preferences editor
    ├── test_styles.py               # Style constants
    └── test_utils.py                # wxPython utility functions
```

### Running Tests

| Command | What it does |
|---------|--------------|
| `make test` | Run all tests with verbose output |
| `make test-cov` | Generate HTML coverage report |
| `make test-unit` | Run only unit tests (fast, no GUI) |
| `make test-gui` | Run only GUI tests |
| `uv run pytest -k "mac_names"` | Run tests matching pattern |
| `uv run pytest tests/core/test_name_formatting.py -v` | Run specific test file |

### Current Coverage

- **1187 tests** covering core logic and GUI components
- **Core** (14 test files): AI analysis, card model, config, database, filename sanitization, name extraction, name formatting, OCR engine, paths, PDF rendering, PDF worker, renamer, template environment, version
- **GUI** (14 test files): API key dialog, context menu, dialogs, filter sidebar, help system, icons, main window, preview cursor behavior, preview panel, review panel, settings, styles, utilities

### Adding Tests

When adding new functionality:
1. Add tests to appropriate file in `tests/core/` or `tests/gui/`
2. Mark tests with `@pytest.mark.unit` or `@pytest.mark.gui`
3. Run tests to verify: `make test`
4. Check coverage: `make test-cov`

See `tests/core/test_name_formatting.py` for examples of comprehensive test organization with parameterization.

## Database

The app stores OCR results, AI results, and manual name edits in a SQLite database (`GreetingCards.sqlite`).

**Location by mode:**

| Mode | Path |
|------|------|
| Dev (running `python main.py`) | `.local/` subdirectory of project root |
| Bundled (`.app`) | `~/Library/Application Support/GreetingCards/` |

**Automatic schema management:** The schema version is a hash computed from all model column definitions at startup. If the models change (columns added, removed, or altered), the hash changes and the database is automatically dropped and recreated. There is no manual migration step — the cache simply rebuilds on next use. This is safe because the database only contains derived/cached data, never source data.

## Scripts

Benchmark and analysis scripts live in `scripts/`. They take a corpus directory (folder of PDF files) as a positional argument.

> **Note:** Some scripts require packages beyond the standard runtime/dev dependencies (e.g. `pytesseract`, `tesserocr`, `opencv-python-headless`). Install any missing ones with `uv add --dev <package>`. Unavailable features are skipped gracefully.

| Script | Description |
|--------|-------------|
| `benchmark_ocr_configuration_quality.py` | Exhaustive search of the Tesseract configuration space (192 configs) with optional AI scoring. Produces per-card and per-config HTML detail pages, a ranked summary, and CSV exports. |
| `benchmark_pre_processing_concurrency.py` | Measures how 6 Python concurrency models (sequential, threads, futures processes, asyncio threads/processes, mp.Queue) scale for the CPU-bound image preprocessing step across 3 pipelines (pillow, clahe, otsu). |
| `benchmark_ocr_concurrency.py` | Measures how sequential, threads, and futures processes scale for the OCR step using a single configuration. Confirms that processes achieve near-linear scaling while threads are GIL-limited. |

### Usage

```bash
# OCR configuration quality (AI scoring enabled by default)
uv run python scripts/benchmark_ocr_configuration_quality.py ~/Desktop/Cards

# Preprocessing concurrency
uv run python scripts/benchmark_pre_processing_concurrency.py ~/Desktop/Cards

# OCR concurrency (default config: tesserocr-default-200-3-pillow-0.15)
uv run python scripts/benchmark_ocr_concurrency.py ~/Desktop/Cards

# All scripts support --help, --no-open, and custom output dirs (-o)
```

Each script generates a self-contained HTML report (with sorting, filtering, and heatmap coloring) and a CSV export in `_script_output/`.
