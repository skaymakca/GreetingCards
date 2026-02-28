# Scripts Infrastructure Architecture

## Key Files

```
scripts/
  __init__.py              # Empty (makes scripts/ a Python package)
  helpers.py               # Shared utilities: output dirs, API key validation
  visual_test.py           # Visual test harness (standalone, not a package)

scripts/<name>/            # Each script is a sub-package
  __init__.py              # Empty
  __main__.py              # Entry point: enables `python -m scripts.<name>`

scripts/benchmark/
  __init__.py              # Empty
  common.py                # Shared benchmark infrastructure (Config, OCR, HTML reports)
  ocr_concurrency.py       # OCR concurrency model comparison
  ocr_configuration_quality.py  # Tesseract config space exhaustive search
  pre_processing_concurrency.py # Preprocessing pipeline benchmarking
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
