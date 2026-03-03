# Greeting Cards

Scans holiday/greeting card PDFs, extracts family names via OCR and AI, and batch-renames the files.

## Features

- **Multi-source loading** — add PDF files or folders from multiple locations without clearing previous loads; cards
  accumulate across sessions
- **Auto-reload** — instantly detects external file changes (e.g., page rotation in Preview) when the app window is
  re-activated, using mtime comparison to skip unchanged files without reading their contents; also available via File >
  Reload (Cmd+Shift+R) or the toolbar Reload button; deleted files are removed, modified files are reprocessed
- **Content-based deduplication** — identical files at different locations are automatically detected (by content hash)
  and displayed as a single card with multiple file paths
- **PDF rendering** — renders all pages of each PDF using PyMuPDF for preview and analysis
- **Offline OCR** — extracts text from card images with Tesseract, then pattern-matches family names (e.g. "The
  Smiths", "Love, John & Jane Smith") at high/medium/low confidence levels
- **AI analysis** — sends page images to Claude's vision API for name extraction; available per-card, for selected
  cards (2+), or all visible cards via toolbar/menu; the label dynamically shows scope and count (e.g., "AI Analyze
  Visible (12)" or "AI Analyze Selected (3)"); choose between Haiku 4.5 (fast/cheap), Sonnet 4.6 (balanced, default),
  and Opus 4.6 (most capable) in Settings
- **Intelligent caching** — OCR results, AI results, and manual edits are persisted to a local SQLite database keyed by
  file content hash, so re-processing the same files (even from different locations) is instant
- **Smart batch rename** — builds a rename plan with per-directory duplicate detection, shows a confirmation dialog,
  then renames files to `Holiday Cards Year - FamilyName Family.pdf` (or without "Family" suffix if checkbox is checked)
- **Per-file options** — checkbox to omit "Family" suffix from individual filenames (e.g.,
  `Holiday Cards 2024 - Smith.pdf` instead of `Holiday Cards 2024 - Smith Family.pdf`)
- **Drag and drop** — drop files or folders (even multiple at once) onto the window to add them
- **Search and filter** — quick search by filename or family name; sidebar filters by confidence level with Option-click
  multi-select
- **Preview with zoom/pan** — scroll wheel zoom at cursor, Shift+Click zoom in, Option+Click zoom out, click-drag
  pan, +/− buttons, Fit button
- **Card removal** — remove cards via the Remove button, Edit > Remove (Cmd+Delete), or right-click context menu (
  non-destructive; files remain on disk)
- **Right-click context menu** — right-click a card row for Open, Reveal in Finder, and Remove; right-click name fields
  for Cut, Copy, Paste, Title Case, and Clear
- **Keyboard navigation** — Up/Down to select cards, Shift+Up/Down to extend selection, Cmd+A to select all, Left/Right
  to page through previews, Cmd+Delete to remove selected cards, Cmd+F to search, Cmd+O to open files, Cmd+Shift+R to
  reload, Cmd+Shift+I to AI analyze, Cmd+R to rename, Cmd+, for Settings, Escape to defocus
- **Help system** — built-in WebView help viewer with 9 pages, cross-page search with highlighted matches, and
  Previous/Next match navigation
- **Native macOS UI** — native toolbar, preferences editor (Cmd+,), About dialog, and system colors throughout
- **API key management** — prompts for the Anthropic API key on first AI use; key is saved to `preferences.plist`;
  source mode also reads `ANTHROPIC_API_KEY` env var (bundle ignores env var)
- **AI model selection** — choose between Claude Haiku 4.5, Sonnet 4.6, or Opus 4.6 in Settings; persisted to
  preferences plist; stale/outdated model IDs are auto-migrated to the current default

## Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- [pyright](https://github.com/microsoft/pyright) — type checking (`brew install pyright` or `npm i -g pyright`)
- [Tesseract](https://github.com/tesseract-ocr/tesseract) — required only for benchmark scripts (
  `brew install tesseract`)
- [lcov](https://github.com/linux-test-project/lcov) — grouped HTML coverage reports (optional; `brew install lcov`)

## Quick Start

```bash
# 1. Install dependencies (creates .venv automatically)
make setup

# 2. (Optional) Install development/testing tools
make setup-dev

# 3. Run the app
make run

# 4. (Optional) Run tests
make test T=default
```

## Make commands

Run `make help` to see all available commands.

| Command                | Description                                                                      |
|------------------------|----------------------------------------------------------------------------------|
| `make help`            | Show all available make commands                                                 |
| `make setup`           | Install production dependencies (creates venv automatically)                     |
| `make setup-dev`       | Install all dependencies including dev/testing tools                             |
| `make run`             | Run the app from source                                                          |
| `make test`            | Run tests (no args shows help; `make test T="core --cov -x"`)                    |
| `make tessdata`        | Download tessdata (eng.traineddata) for OCR                                      |
| `make content`         | Generate runtime content (HTML, data files, images)                              |
| `make licenses-sync`   | Sync license registry from uv.lock + .dist-info                                  |
| `make visual-test`     | Run visual test harness from source                                              |
| `make visual-test-app` | Build and run visual test harness as `.app` bundle (logs visible)                |
| `make dmg`             | Build the distributable DMG installer (→ `dist/Greeting Cards - X.Y.Z.dmg`)      |
| `make app`             | Build the macOS `.app` bundle (output: `dist/Greeting Cards.app`)                |
| `make app-run`         | Build and run the `.app` bundle with logs visible in terminal                    |
| `make icon`            | Generate `icon.icns` from `icon.png` (auto-run by build)                         |
| `make version`         | Print the current version                                                        |
| `make bump-patch`      | Bump patch version (e.g. 0.5.0 → 0.5.1)                                          |
| `make bump-minor`      | Bump minor version (e.g. 0.5.1 → 0.6.0)                                          |
| `make bump-major`      | Bump major version (e.g. 0.6.0 → 1.0.0)                                          |
| `make tag`             | Create git tag `vX.Y.Z` from current version                                     |
| `make tag-push`        | Push all tags to remote                                                          |
| `make check`           | Run all static checks (pyright + mypy + ruff lint + format + bandit)             |
| `make pyright`         | Run pyright type checking on app/ and scripts/                                   |
| `make mypy`            | Run mypy type checking on app/ and scripts/                                      |
| `make lint`            | Run ruff linter                                                                  |
| `make lint-fix`        | Run ruff linter with auto-fix                                                    |
| `make format`          | Format code with ruff                                                            |
| `make format-check`    | Check formatting without making changes                                          |
| `make security`        | Run bandit security scan on app/ and scripts/                                    |
| `make pycharm-inspect` | Run PyCharm CLI inspections (skipped if PyCharm is not installed)                |
| `make loc`             | Count lines of code in project files (excludes dependencies and build artifacts) |
| `make show-scripts`    | Show available script invocations without running them                           |
| `make docker-build`    | Build the Linux test image                                                       |
| `make docker-test`     | Run core + scripts tests in Linux container                                      |
| `make docker-shell`    | Interactive shell in Linux container                                             |
| `make clean`           | Remove `_build/` and `dist/` directories                                         |

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

# Run with coverage and open HTML reports in browser
make test T="default --cov --open"
```

### Test Organization

Tests are organized by component:

```
tests/
├── conftest.py                      # Shared fixtures (wx.App, mock frames, in-memory DB)
├── core/
│   ├── conftest.py                  # Core-specific fixtures
│   ├── test_apple_events.py         # Apple Events handler logic
│   ├── test_card_model.py           # Card data model
│   ├── test_card_store.py           # CardStore state management
│   ├── test_config.py               # Configuration and API key management
│   ├── test_database.py             # SQLite database operations
│   ├── test_paths.py                # Path resolution (dev vs bundle)
│   ├── test_platform.py             # Platform detection
│   ├── test_scripting_protocol.py   # AppleScript scripting protocol
│   ├── test_version.py              # Version string
│   ├── content/                     # 7 files: changelog, changelog_models, help_builder,
│   │                                #   license_html, license_models, license_sync, template_env
│   ├── naming/                      # 7 files: extractor, family_name_cleaning, family_name_data,
│   │                                #   family_name_formatting, filename_safety, rename_filter, renamer
│   ├── pipeline/                    # 7 files: ai_analyzer, ai_batch, card_processor, ocr_engine,
│   │                                #   pdf_renderer, pdf_worker, rate_limit
│   └── services/                    # 6 files: ai_service, card_service, config_service,
│                                    #   filter_service, processing_service, rename_service
├── gui/                             # 21 test files
│   ├── conftest.py                  # GUI-specific fixtures
│   ├── test_api_key_dialog.py       # API key prompt dialog
│   ├── test_appearance.py           # Dark/light mode appearance
│   ├── test_apple_events_bridge.py  # AppleScript bridge integration mocks
│   ├── test_changelog_dialog.py     # Changelog viewer dialog
│   ├── test_context_menu.py         # Right-click context menu
│   ├── test_cursors.py              # Cursor state management
│   ├── test_dialogs.py              # Progress, rename, completion dialogs
│   ├── test_drop_target.py          # Drag-and-drop target
│   ├── test_filter_sidebar.py       # Sidebar filters and multi-select
│   ├── test_help_dialog.py          # Help viewer and cross-page search
│   ├── test_html_viewer.py          # WebView HTML viewer component
│   ├── test_icons.py                # SF Symbol icon loading
│   ├── test_licenses_dialog.py      # Licenses viewer dialog
│   ├── test_main_window.py          # Main window integration
│   ├── test_preview_cursor_behavior.py # Preview cursor and modifier keys
│   ├── test_preview_panel.py        # Preview panel and zoom/pan
│   ├── test_review_panel.py         # Card list and detail panel
│   ├── test_settings_dialog.py      # Preferences editor
│   ├── test_styles.py               # Style constants
│   ├── test_toolbar.py              # Native toolbar buttons and state
│   └── test_utils.py                # wxPython utility functions
├── integration/
│   └── test_applescript.py          # End-to-end AppleScript integration (--run-integration)
└── scripts/
    ├── test_helpers.py              # script_output_dir lifecycle
    ├── test_run_tests.py            # test runner scopes and argument building
    ├── build_family_name_db/        # merger, unicode, Census/Faker/Smashew sources
    ├── dmg/                         # readme RTF, background PNG, dmgbuild orchestration
    ├── generate_diagnostic_cards/   # CLI argument parsing, PDF creation
    └── generate_sample_cards/       # models, display, pdf_composer, image_generator,
                                     #   spec_generator, cli; spec_generators/ sub-package
```

### Running Tests

| Command                                                             | What it does                       |
|---------------------------------------------------------------------|------------------------------------|
| `make test T=default`                                               | Run core + gui + scripts tests     |
| `make test T=all`                                                   | All tests including integration    |
| `make test T=core`                                                  | Run only core tests (fast, no GUI) |
| `make test T=gui`                                                   | Run only GUI tests                 |
| `make test T="gui scripts"`                                         | Combine multiple scopes            |
| `make test T="core -x"`                                             | Stop on first failure              |
| `make test T="core -k family_name"`                                 | Keyword filter                     |
| `make test T="default --cov"`                                       | All tests with coverage reports    |
| `make test T="default --cov --open"`                                | Coverage + open in browser         |
| `uv run pytest tests/core/naming/test_family_name_formatting.py -v` | Run specific test file             |

### Current Coverage

- **2376 tests** covering core logic, GUI components, and scripts
- **Core** (services/, pipeline/, naming/, content/ sub-packages + top-level): AI analysis, AI batch, AI service,
  Apple Events, card model, card processor, card service, card store, changelog, changelog models, config,
  config service, database, family name cleaning, family name data, family name formatting, filename safety,
  filter service, help builder, license HTML, license models, license sync, name extraction, OCR engine, paths,
  PDF rendering, PDF worker, platform, processing service, rate limit, rename service, renamer, rename filter,
  scripting protocol, template environment, version
- **GUI** (21 test files): API key dialog, Apple Events bridge, appearance, changelog dialog, context menu, cursors,
  dialogs, drop target, filter sidebar, help dialog, HTML viewer, icons, licenses dialog, main window, preview cursor
  behavior, preview panel, review panel, settings, styles, toolbar, utilities
- **Integration**: AppleScript end-to-end tests (requires `--run-integration`)
- **Scripts** (tests/scripts/): helpers, build_family_name_db (merger, Unicode, Census/Faker/Smashew sources), dmg
  (readme RTF, background PNG, dmgbuild orchestration), generate_diagnostic_cards (CLI), generate_sample_cards
  (models, display, pdf_composer, image_generator, spec_generator, cli, spec_generators/ sub-package)

### Adding Tests

When adding new functionality:

1. Add tests to appropriate file in `tests/core/` or `tests/gui/`
2. Mark tests with `@pytest.mark.unit` or `@pytest.mark.gui`
3. Run tests to verify: `make test`
4. Check coverage: `make test T="default --cov"`

See `tests/core/naming/test_family_name_formatting.py` for examples of comprehensive test organization with parameterization.

## Database

The app stores OCR results, AI results, and manual name edits in a SQLite database (`GreetingCards.sqlite`).

**Location by mode:**

| Mode                           | Path                                           |
|--------------------------------|------------------------------------------------|
| Dev (running `python main.py`) | `.local/` subdirectory of project root         |
| Bundled (`.app`)               | `~/Library/Application Support/GreetingCards/` |

**Automatic schema management:** The schema version is a hash computed from all model column definitions at startup. If
the models change (columns added, removed, or altered), the hash changes and the database is automatically dropped and
recreated. There is no manual migration step — the cache simply rebuilds on next use. This is safe because the database
only contains derived/cached data, never source data.

## Scripts

Utility and benchmark scripts live in `scripts/` (a Python package). Run them with `uv run python -m scripts.<name>`. All
script dependencies are included in the dev group — run `make setup-dev` first.

Output goes to `_build/script_output/` with timestamped directories (e.g., `20260223_2011-generate_sample_cards/`) so
runs don't overwrite each other. Empty output directories are automatically cleaned up if a script errors out before
writing any files.

### Sample Card Generator

`generate_sample_cards` creates a corpus of realistic greeting card PDFs for testing and demos. It uses a multiphase
async pipeline — unique family names, batched color schemes, LLM-generated subtitles, then per-card creative content —
with Claude generating card metadata and OpenAI's gpt-image-1.5 generating entire card images in the style of commercial
greeting cards (Shutterfly, Snapfish, Minted), with typography baked into the artwork. Generated images are temporary
and cleaned up after PDF creation.

```bash
# Default: 3 cards
uv run python -m scripts.generate_sample_cards

# 20 cards with capped text concurrency
uv run python -m scripts.generate_sample_cards --count=20 --text-concurrency=15
```

| Flag                     | Description                                                         |
|--------------------------|---------------------------------------------------------------------|
| `--count N`              | Number of cards to generate (default: 3)                            |
| `--ai-model MODEL`       | Claude model for metadata generation (default: `claude-sonnet-4-6`) |
| `--image-model MODEL`    | OpenAI image model (default: `gpt-image-1.5`)                       |
| `--image-concurrency N`  | Max concurrent OpenAI image requests (default: 5)                   |
| `--text-concurrency N`   | Max concurrent Claude spec-generation requests (default: 10)        |
| `--no-image-compression` | Embed images as lossless PNG instead of JPEG (Q75)                  |
| `--no-open`              | Don't open output folder when done                                  |

**Required API keys:** `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.

### Benchmarks

The benchmark scripts take a corpus directory (folder of PDF files) as a positional argument. The OCR benchmarks also
require the [Tesseract CLI](https://github.com/tesseract-ocr/tesseract) (`brew install tesseract` on macOS).

| Script                                 | Description                                                                                                                                                                                                       |
|----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `benchmark.ocr_configuration_quality`  | Exhaustive search of the Tesseract configuration space (192 configs) with optional AI scoring. Produces per-card and per-config HTML detail pages, a ranked summary, and CSV exports.                             |
| `benchmark.pre_processing_concurrency` | Measures how 6 Python concurrency models (sequential, threads, futures processes, asyncio threads/processes, mp.Queue) scale for the CPU-bound image preprocessing step across 3 pipelines (pillow, clahe, otsu). |
| `benchmark.ocr_concurrency`            | Measures how sequential, threads, and futures processes scale for the OCR step using a single configuration. Confirms that processes achieve near-linear scaling while threads are GIL-limited.                   |

```bash
# OCR configuration quality (AI scoring enabled by default)
uv run python -m scripts.benchmark.ocr_configuration_quality ~/Desktop/Cards

# Preprocessing concurrency
uv run python -m scripts.benchmark.pre_processing_concurrency ~/Desktop/Cards

# OCR concurrency (default config: tesserocr-default-200-3-pillow-0.15)
uv run python -m scripts.benchmark.ocr_concurrency ~/Desktop/Cards

# All scripts support --help, --no-open, and custom output dirs (-o)
```

Each benchmark generates a self-contained HTML report (with sorting, filtering, and heatmap coloring) and a CSV export
in `_build/script_output/`.

### Appearance Toggle

`dark_mode_cycler` switches macOS between dark and light mode every 5 seconds until interrupted with Ctrl-C.
Useful for testing live appearance change handling in the app.

```bash
uv run python -m scripts.dark_mode_cycler
```

### Diagnostic Card Generator

`generate_diagnostic_cards` generates PDF cards with specific family names for testing OCR accuracy.

```bash
uv run python -m scripts.generate_diagnostic_cards
```

### Profiling

`profiling` profiles the PDF processing pipeline and generates performance reports.

```bash
uv run python -m scripts.profiling ~/Desktop/Cards
```

### Family Name Database Builder

`build_family_name_db` builds the family name database from multiple sources (Census, Faker, Smashew).

```bash
uv run python -m scripts.build_family_name_db
```

### Markdown Table Formatter

`reformat_md_tables` reformats Markdown tables to pass PyCharm's `MarkdownIncorrectTableFormatting` inspection.

```bash
uv run python -m scripts.reformat_md_tables docs/**/*.md README.md CLAUDE.md
```

### DMG Installer

`dmg` builds the distributable macOS DMG installer from the current `.app` bundle.

```bash
uv run python -m scripts.dmg
```

This is also available as `make dmg`, which builds the `.app` bundle first if needed.

## IDE Setup (PyCharm)

The `.idea/` directory is committed with shared project settings:

- **Inspection profile** — custom dictionary, inline `# noinspection` suppressions for wxPython/SQLAlchemy false
  positives, and scope-based suppression for Markdown file reference warnings
- **Inspection scope** — "Markdown and Other Inspection Suppressions" disables `MarkdownUnresolvedFileReference` for
  `*.md` files, since help page links (`pages/*.html`) are resolved at build time, not on disk
- **Custom dictionary** — project-specific words (technical terms, proper names) to suppress spell-check false positives

User-specific files (`workspace.xml`, etc.) are excluded via `.idea/.gitignore`.

### CLI Inspections

You can run PyCharm inspections from the command line without opening the IDE:

```bash
make pycharm-inspect

# Override PyCharm location if needed
PYCHARM_APP="/custom/path/PyCharm.app" make pycharm-inspect
```

This launches PyCharm's headless inspection runner against the project using the shared `Project_Default` profile.
Results are written to `/tmp/pycharm-inspect-out/` as XML files. The target auto-detects PyCharm (Professional or
Community) in `~/Applications` (JetBrains Toolbox) first, then `/Applications`, and skips gracefully if neither is
found.

> **Note:** The CLI runner starts a full IDE instance in headless mode, so it takes a minute or two. Some inspections (
> e.g., Grazie grammar) may not produce results in headless mode. For the most complete results, use Code > Inspect Code
> inside the IDE.

> **Caveat:** The headless instance may reset your IDE theme to the default when you next launch PyCharm. This is a
> known side effect of running `inspect.sh`.

> **Tip:** If you're writing Markdown with file paths that should resolve on disk, temporarily re-enable
`MarkdownUnresolvedFileReference` in Settings > Editor > Inspections to catch broken links. The scope only suppresses it
> for the help content files where paths are intentionally unresolvable.

See [`docs/architecture/pycharm-inspections.md`](docs/architecture/pycharm-inspections.md) for the full suppression
inventory.

## Docker (Cross-Platform Testing)

Docker is used to run the test suite on Linux, verifying cross-platform compatibility for non-GUI code. This catches
platform-specific issues (e.g., path handling, Tesseract integration) that macOS-only testing would miss.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### Commands

| Command             | Description                                                    |
|---------------------|----------------------------------------------------------------|
| `make docker-build` | Build the Linux test image (Python 3.14-slim + Tesseract + uv) |
| `make docker-test`  | Run core + scripts tests in the Linux container                |
| `make docker-shell` | Open an interactive shell in the container for debugging       |

### What runs in the container

The container runs `tests/core/` and `tests/scripts/` — everything except GUI tests (`tests/gui/`) and macOS-specific
tests (`test_apple_events.py`). These are excluded because they depend on wxPython and macOS frameworks that aren't
available in a Linux container.

### Development workflow

Docker Compose mounts the project directory into the container, so code changes are reflected immediately without
rebuilding. An anonymous volume for `.venv` prevents the macOS virtual environment from leaking into the container.

```bash
# First time: build the image
make docker-build

# Iterate: edit code, then run tests
make docker-test

# Debug: get a shell inside the container
make docker-shell
```

See [`docs/architecture/docker-and-ci.md`](docs/architecture/docker-and-ci.md) for implementation details.

## Continuous Integration

CI runs on GitHub Actions (`.github/workflows/ci.yml`) with two jobs:

| Job     | Trigger                   | What it does                                                                         |
|---------|---------------------------|--------------------------------------------------------------------------------------|
| `check` | Every push (all branches) | Runs `make check` (pyright + mypy + ruff lint + format-check + bandit)               |
| `test`  | PRs to `main` only        | Static checks + `make app` build + full test suite with coverage (`make test T=...`) |

Both jobs run on `macos-26` runners with Python 3.14, uv, Tesseract, and lcov installed via a shared composite action
(`.github/actions/setup-build-env/action.yml`).

### Artifacts

Each job uploads downloadable artifacts:

- **`check` job:** `static-checks.log` — full output of all static analysis tools
- **`test` job:** `static-checks.log`, `test-results.log`, and the HTML coverage report (`_build/coverage/latest/`)

Artifacts are available from the Actions tab on GitHub for any workflow run.

See [`docs/architecture/docker-and-ci.md`](docs/architecture/docker-and-ci.md) for implementation details.
