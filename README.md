# Greeting Card Analyzer

Scans holiday/greeting card PDFs, extracts family names via OCR and AI, and batch-renames the files.

## Features

- **PDF rendering** — renders all pages of each PDF using PyMuPDF for preview and analysis
- **Offline OCR** — extracts text from card images with Tesseract, then pattern-matches family names (e.g. "The Smiths", "Love, John & Jane Smith") at high/medium/low confidence levels
- **AI analysis** — sends page images to Claude's vision API for name extraction; available per-card or as a batch "AI All" operation
- **Caching** — OCR results, AI results, and manual edits are all persisted to a local SQLite database keyed by file content hash, so re-processing the same files is instant
- **Batch rename** — builds a rename plan (with duplicate/skip detection), shows a confirmation dialog, then renames files to `Holiday Cards Year - FamilyName Family.pdf` (or without "Family" suffix if checkbox is checked)
- **Per-file options** — checkbox to omit "Family" suffix from individual filenames (e.g., `Holiday Cards 2024 - Smith.pdf` instead of `Holiday Cards 2024 - Smith Family.pdf`)
- **Drag and drop** — drop a folder or PDF onto the window to load it
- **Keyboard navigation** — Up/Down to select cards, Left/Right to page through previews, Escape to defocus text entries
- **API key management** — prompts for the Anthropic API key on first AI use; key is saved to a plist in bundled mode or read from `.env` in dev mode

## Prerequisites

- Python 3.14
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (`brew install tesseract`)

## Quick Start

```bash
# 1. Create virtual environment and install dependencies
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
| `make setup` | Create venv and install production dependencies |
| `make setup-dev` | Install development dependencies (testing tools) |
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

### Requirements Files

The project uses separate requirements files:

- **`requirements.txt`** - Production dependencies (bundled in `.app`)
- **`requirements-dev.txt`** - Development tools (testing, etc.)
  - Automatically includes `requirements.txt` via `-r requirements.txt`
  - This keeps production and development dependencies in sync

### Setup

Create a virtualenv and install dependencies:

```bash
# Create venv
python3 -m venv .venv
source .venv/bin/activate

# Install production dependencies
pip install -r requirements.txt

# OR install development dependencies (includes production + testing tools)
pip install -r requirements-dev.txt
```

Create a `.env` file with your Anthropic API key (for AI analysis):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Run from source:

```bash
python main.py
```

Build the `.app` bundle (requires `pip install pyinstaller`):

```bash
pyinstaller -y --windowed --name="Greeting Cards" --collect-all tkinterdnd2 main.py
```

## Testing

The project uses **pytest** for testing with comprehensive test coverage of core functionality and GUI components.

### Quick Start

```bash
# Install dev dependencies (includes pytest and testing tools)
make setup-dev

# Run all tests
make test

# Run with coverage report
make test-cov
open htmlcov/index.html
```

### Test Organization

Tests are organized by component with clear markers:

```
tests/
├── conftest.py              # Shared fixtures (wx.App, mock frames)
├── core/
│   └── test_name_formatting.py   # Name parsing and formatting logic
└── gui/
    └── test_wx_utils.py          # wxPython utility functions
```

**Test markers:**
- `@pytest.mark.unit` - Fast unit tests (no GUI)
- `@pytest.mark.gui` - Tests requiring wx.App (GUI components)

### Running Tests

| Command | What it does |
|---------|--------------|
| `make test` | Run all tests with verbose output |
| `make test-cov` | Generate HTML coverage report |
| `make test-unit` | Run only unit tests (fast, no GUI) |
| `make test-gui` | Run only GUI tests |
| `pytest -k "mac_names"` | Run tests matching pattern |
| `pytest tests/core/test_name_formatting.py -v` | Run specific test file |

### Current Coverage

- **87 tests** covering name formatting, wxPython utilities, and GUI components
- **Core logic** (name_formatting.py): Comprehensive coverage of:
  - Plural name removal ("Smiths" → "Smith", preserves "Jones")
  - Mc/Mac prefix rules ("mcdonald" → "McDonald", "macintosh" → "Macintosh")
  - Apostrophe names ("o'brien" → "O'Brien")
  - Hyphenated names ("smith-jones" → "Smith-Jones")
  - Particles (van/von/de), suffixes (Jr./Sr./III), complex combinations
- **GUI utilities** (wx_utils.py): Color conversion, image handling, widget creation

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
| Dev (running `python main.py`) | Project root, next to `main.py` |
| Bundled (`.app`) | `~/Library/Application Support/GreetingCards/` |

**Automatic schema management:** The schema version is a hash computed from all model column definitions at startup. If the models change (columns added, removed, or altered), the hash changes and the database is automatically dropped and recreated. There is no manual migration step — the cache simply rebuilds on next use. This is safe because the database only contains derived/cached data, never source data.
