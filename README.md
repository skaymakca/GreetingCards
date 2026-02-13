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

## Make commands

Run `make help` to see all available commands.

| Command | Description |
|---------|-------------|
| `make help` | Show all available make commands |
| `make run` | Run the app from source |
| `make build` | Build the macOS `.app` bundle (output: `dist/Greeting Cards.app`) — alias for `make app` |
| `make app` | Build the macOS `.app` bundle (same as `make build`) |
| `make icon` | Generate `icon.icns` from `icon.png` (auto-run by build) |
| `make version` | Print the current version |
| `make bump-patch` | Bump patch version (e.g. 0.5.0 → 0.5.1) |
| `make bump-minor` | Bump minor version (e.g. 0.5.1 → 0.6.0) |
| `make bump-major` | Bump major version (e.g. 0.6.0 → 1.0.0) |
| `make loc` | Count lines of code in project files (excludes dependencies and build artifacts) |
| `make clean` | Remove `build/` and `dist/` directories |

## Manual setup and commands

Create a virtualenv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

## Database

The app stores OCR results, AI results, and manual name edits in a SQLite database (`GreetingCards.sqlite`).

**Location by mode:**

| Mode | Path |
|------|------|
| Dev (running `python main.py`) | Project root, next to `main.py` |
| Bundled (`.app`) | `~/Library/Application Support/GreetingCards/` |

**Automatic schema management:** The schema version is a hash computed from all model column definitions at startup. If the models change (columns added, removed, or altered), the hash changes and the database is automatically dropped and recreated. There is no manual migration step — the cache simply rebuilds on next use. This is safe because the database only contains derived/cached data, never source data.
