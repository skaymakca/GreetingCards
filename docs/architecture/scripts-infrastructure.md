# Scripts Infrastructure Architecture

## Key Files

```
scripts/
  __init__.py              # Empty (makes scripts/ a Python package)
  helpers.py               # Shared utilities: output dirs, API key validation
  dark_mode_cycler.py      # Standalone: toggles macOS dark/light mode every 5s
  visual_test.py           # Visual test harness (standalone, not a package)

scripts/benchmark/
  __init__.py
  common.py                # Shared benchmark infrastructure (Config, OCR, HTML reports)
  ocr_concurrency.py       # OCR concurrency model comparison
  ocr_configuration_quality.py  # Tesseract config space exhaustive search
  pre_processing_concurrency.py # Preprocessing pipeline benchmarking

scripts/build_family_name_db/
  __init__.py
  __main__.py              # Entry point
  cli.py                   # Orchestration: download sources → merge → write TSV
  merger.py                # Normalize, merge, apply overrides, write TSV
  _unicode.py              # Unicode → ASCII mapping table
  sources/
    census.py              # US Census surname data downloader
    faker_names.py         # Faker library name extractor
    smashew.py             # smashew/NameDatabases GitHub downloader
  benchmark_compression.py # Benchmarks file format/compression options (not tested)

scripts/dmg/
  __init__.py
  __main__.py              # Entry point + orchestration (build app → create DMG via dmgbuild)
  background.py            # Generates gradient PNG background for DMG window
  readme.py                # Generates RTF readme for DMG (RTFD package)
  dmgbuild_settings.py     # dmgbuild configuration (window layout, icons)

scripts/generate_diagnostic_cards/
  __init__.py
  __main__.py              # Entry point
  cli.py                   # CLI: create PDFs with fixed family name text for OCR testing

scripts/generate_sample_cards/
  __init__.py
  __main__.py              # Entry point
  cli.py                   # CLI: top-level orchestration and argument parsing
  models.py                # Dataclasses: CardSpec, ImageSpec, GenerationJob
  display.py               # Rich live-table progress display
  pdf_composer.py          # Assembles final PDF from generated image + metadata
  image_generator.py       # OpenAI image API calls with rate limiting and retry
  spec_generator.py        # Multiphase async pipeline: names → schemes → subtitles → content
  spec_generators/
    card_content.py        # Claude: per-card creative content generation
    color_schemes.py       # Claude: batched color scheme generation
    constants.py           # Static lists (themes, styles, occasions)
    family_names.py        # Claude: unique family name selection
    formatting.py          # Deterministic field assignment from spec
    subtitles.py           # Claude: batched subtitle generation
    utils.py               # JSON extraction from LLM responses

scripts/profiling/
  __init__.py
  __main__.py              # Entry point
  cli.py                   # Profiles PDF processing pipeline with pyinstrument
```

## Package Structure

Scripts are organized as Python packages runnable via `python -m scripts.<name>`:

```bash
uv run python -m scripts.generate_sample_cards --count=5
uv run python -m scripts.benchmark.ocr_concurrency ~/Desktop/Cards
```

Each script package follows the same pattern:
1. `__main__.py` imports and calls `main()` from the package's CLI module
2. The CLI module defines `main()` as the sync entry point
3. For async scripts, `main()` calls `asyncio.run(async_main())`

**Exceptions:** `scripts/dmg/` puts orchestration directly in `__main__.py` (no separate `cli.py`). `scripts/benchmark/` has no `__main__.py` — its scripts are standalone modules run individually (e.g., `python -m scripts.benchmark.ocr_concurrency`).

This structure allows scripts to be multi-file packages while remaining invocable as modules.

## Output Directory Convention

All script output goes to `_build/script_output/` with timestamped subdirectories:

```
_build/script_output/
  20260225_1425-generate_sample_cards/
  20260225_1510-ocr_configuration_quality/
  20260225_1515-ocr_concurrency/
```

**Format:** `YYYYMMDD_HHMM-<script_name>/`

### `script_output_dir()` Context Manager

Defined in `scripts/helpers.py`. Manages the lifecycle of output directories:

```python
with script_output_dir("generate_sample_cards") as output_dir:
    # output_dir is a Path like _build/script_output/20260225_1425-generate_sample_cards/
    # Generate files into output_dir...
```

**Behavior:**
- Creates the timestamped directory on entry
- Yields the `Path` for use inside the block
- **On exception:** removes the directory if it's empty (no partial output left behind)
- **On success:** keeps the directory as-is

## CLI Conventions

### Common Flags

All scripts support:
- `--no-open` — don't open the output folder in Finder when done
- `--help` — standard argparse help

### Positional Arguments

- Benchmark scripts take a corpus directory (folder of PDF files) as a required positional argument

### `validate_api_keys()` Pattern

Scripts that call external APIs validate required environment variables before starting:

```python
def validate_api_keys() -> bool:
    """Check for ANTHROPIC_API_KEY and OPENAI_API_KEY."""
    # Returns False with error message if keys are missing
```

This runs early in `main()` to fail fast with a clear message rather than mid-pipeline.

## Rich Progress Display

Scripts use the [Rich](https://rich.readthedocs.io/) library for terminal output:

- **`Console`** — styled print output, status messages, error formatting
- **`Live`** — auto-refreshing display for progress tables (used in `generate_sample_cards` at 10 Hz)
- **`Table`** — structured status tables with per-task rows showing status, spinners, elapsed time
- **Spinners** — embedded in table cells via Rich markup for active tasks

Pattern for live table updates:

```python
with Live(build_status_table(jobs), refresh_per_second=10) as live:
    while not all_done:
        live.update(build_status_table(jobs))
        await asyncio.sleep(0.1)
```

### Logging with `RichHandler`

Scripts that use `Live` tables and also need Python `logging` (e.g., for API error diagnostics) should use `RichHandler` from `rich.logging`, initialized with the **same `Console` instance** used by `Live`. This lets Rich coordinate output — log messages render above the live table instead of corrupting it.

```python
from rich.logging import RichHandler

console = Console(highlight=False)
logging.basicConfig(
    level=logging.WARNING,
    handlers=[RichHandler(console=console, show_path=False, show_time=False)],
)
```

**Log levels:**
- **WARNING** — API errors, retry attempts (e.g., OpenAI `images.edit` failures with exception type and message)
- **INFO** — Diagnostic signals (e.g., extra text Claude included around JSON responses)

The root handler is set to WARNING, with `scripts.generate_sample_cards` set to INFO:

```python
logging.getLogger("scripts.generate_sample_cards").setLevel(logging.INFO)
```

**Convention:** Use `console.print()` for user-facing status messages. Use `log.warning()` for API errors and retries. Use `log.info()` for diagnostic breadcrumbs (e.g., chatty LLM responses). Benchmark scripts use `console.print()` exclusively since they don't have background async tasks that need structured error logging.

## Async Patterns

### Entry Point

```python
def main() -> None:
    asyncio.run(async_main())
```

### Semaphore-Gated Concurrency

Limits concurrent API calls to avoid overwhelming rate limits:

```python
semaphore = asyncio.Semaphore(concurrency)

async def process_item(item):
    async with semaphore:
        return await api_call(item)

results = await asyncio.gather(*[process_item(i) for i in items])
```

### `RateLimitGate` for API Rate Limits

A coordination mechanism that pauses all concurrent tasks when any task hits a rate limit (defined in `generate_sample_cards/image_generator.py`):

- **No locks needed** — asyncio is single-threaded (cooperative multitasking)
- `pause(seconds)` — sets a monotonic resume timestamp
- `wait_if_paused(job)` — sleeps with countdown display if the gate is active
- Prevents thundering herd: tasks still queue through the semaphore after the gate lifts
- Parses `retry-after-ms` and `retry-after` response headers, falls back to 10 seconds

## Benchmark Infrastructure

**File:** `scripts/benchmark/common.py` (~660 lines)

Shared utilities used across all three benchmark scripts.

### Config Dataclass

Represents a Tesseract OCR configuration:
- Fields: `library`, `tessdata`, `dpi`, `psm`, `preprocess`, `dict_penalty`
- Properties: `name`, `short_name`, `slug` (for filenames)
- Factory: `from_short_name(s)` for deserialization

### tessdata Management

- Auto-downloads `tessdata_best` (high-accuracy LSTM models) on first run
- Detects system tessdata (Homebrew/default paths)
- `ensure_tessdata_best()` — downloads if missing, caches in project dir
- `get_tessdata_path(tessdata)` — resolves to absolute path for subprocess

### PDF Rendering & Preprocessing

- `render_all_pages(pdf_path, dpi)` — PyMuPDF rendering with DPI-aware zoom capping
- `autocrop_whitespace(image)` — trims white borders with configurable threshold
- Three preprocessing pipelines (`PREPROCESS_FNS`):
  - `pillow` — grayscale → autocontrast → sharpen (production pipeline)
  - `clahe` — CLAHE + denoising + adaptive threshold (OpenCV)
  - `otsu` — Otsu threshold + sharpen (OpenCV)

### OCR Engines

Two engines (`OCR_FNS`):
- `pytesseract` — subprocess-based Tesseract wrapper
- `tesserocr` — C++ API binding (faster, no subprocess overhead)

### HTML Report Scaffolding

Self-contained HTML reports with:
- Dark mode-aware CSS (prefers-color-scheme)
- Sortable table headers (JavaScript click handlers)
- Heatmap coloring for quartile-based cell highlighting
- Text expansion for long OCR output samples
- Filter dropdowns for multi-dimensional results

### Job Generation

`build_jobs(pdf_paths, concurrency_level, min_repeats)` ensures sufficient work for benchmarking:
- Total jobs >= max(n_files * min_repeats, 2 * concurrency_level)
- Distributes work evenly across files

### Statistics

- `mean_std(values)` — returns (mean, standard_deviation)
- `fmt_mean_std(mean, std)` — formatted string "M +/- S"

---

## Testing

### Test directory

`tests/scripts/` mirrors the `scripts/` directory structure. Each sub-package has its own `tests/scripts/<name>/` directory with `__init__.py` and focused test modules.

### What's tested

Scripts with pure logic or mockable I/O:

- **`scripts/helpers.py`** — `_make_output_dir` timestamped dir creation; `script_output_dir` keeps non-empty dirs on error, removes empty dirs, re-raises
- **`scripts/build_family_name_db/`** — `_unicode.py` mapping table; `merger.py` normalize/ascii_fold/merge_sources/apply_overrides/write_tsv/`_sanity_check`; all three source downloaders (census, faker_names, smashew) with in-memory zip/network mocks
- **`scripts/dmg/`** — `readme.py` RTF generation (escape, inline bold, body rendering, RTFD package); `background.py` gradient and PNG generation; `__main__.py` version reading and `dmgbuild` orchestration
- **`scripts/generate_diagnostic_cards/cli.py`** — `_create_diagnostic_pdf` fitz mock; `main()` argument parsing
- **`scripts/generate_sample_cards/`** — `models.py` dataclasses; `display.py` Rich table layout; `pdf_composer.py` fitz page creation; `image_generator.py` rate limiting, retry, prompt building, OpenAI API; `spec_generator.py` full pipeline; `cli.py` API key validation and card processing
- **`scripts/generate_sample_cards/spec_generators/`** — `utils.py` JSON extraction; `constants.py` list integrity; `formatting.py` deterministic field assignment; `family_names.py`, `color_schemes.py`, `subtitles.py`, `card_content.py` — all Anthropic API calls mocked

### What's NOT tested and why

| Script | Reason |
|---|---|
| `scripts/benchmark/` | Requires a real PDF corpus and OCR engines (tesseract/OpenCV); measurement tools, not business logic |
| `scripts/profiling/` | Requires real PDF files and pyinstrument; measures performance, not correctness |
| `scripts/visual_test.py` | Is itself a testing tool for manual GUI inspection |
| `scripts/dark_mode_cycler.py` | Trivial macOS utility — a single `osascript` call in a loop |
| `scripts/build_family_name_db/cli.py` | Integration orchestrator that downloads real Census/GitHub data; individual sources and merger are tested in isolation |
| `scripts/build_family_name_db/benchmark_compression.py` | Benchmarking utility for file format selection |

### API mocking

All Anthropic and OpenAI calls are mocked via `unittest.mock.patch` + `AsyncMock`. No tests hit real APIs or the network. The standard mock pattern:

```python
mock_msg = MagicMock()
mock_msg.content = [MagicMock(text='["Smith", "Jones"]')]
mock_client = MagicMock()
mock_client.messages.create = AsyncMock(return_value=mock_msg)
```

For sequential multi-phase responses (spec generator pipeline), pass a list to `side_effect`:
```python
mock_client.messages.create = AsyncMock(side_effect=[names_msg, schemes_msg, subtitles_msg, *content_msgs])
```

### Makefile targets

- `make test-scripts` — run `tests/scripts/` only (fast, ~1s)
- `make test-cov` — full suite with coverage for both `app/` and `scripts/`
