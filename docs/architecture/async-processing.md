# Async Processing

ProcessPoolExecutor for PDF rendering + OCR, asyncio for AI batch, and thread-safety patterns.

**Key files:** `app/core/pdf_worker.py` (subprocess worker), `app/gui/main_window.py` (processing methods), `app/core/ai_analyzer.py`

## Architecture Overview

```
┌──────────────────────────────────────────────────┐
│                Main Thread (wx)                  │
│ UI events, wx.CallAfter callbacks, timer events  │
└────────┬─────────────────────────┬───────────────┘
         │                         │
   ┌─────▼───────┐          ┌─────▼────────┐
   │  Thread 1   │          │  Thread 2    │
   │ _process_   │          │ _run_ai_all  │
   │   cards()   │          │   asyncio    │
   └─────┬───────┘          └─────┬────────┘
         │                        │
 ┌───────▼──────────┐   ┌────────▼───────────┐
 │ ProcessPool      │   │ asyncio.Semaphore   │
 │   Executor       │   │  (3 concurrent)     │
 │ OCR_WORKERS      │   │ + _RateLimitGate    │
 └──────────────────┘   └────────────────────┘
```

## PDF Processing: ProcessPoolExecutor

### Entry Point: `_start_processing()`
1. Shows ProgressDialog, begins busy cursor
2. Spawns `threading.Thread(target=_process_cards)`

### Worker: `process_pdf_worker()` in `app/core/pdf_worker.py`
Runs in a **separate process** (via `ProcessPoolExecutor`). Must be module-level (not a method) for pickling. Lives in the core layer since it contains only core logic (PDF rendering, OCR, database ops, image serialization) with zero GUI dependencies.

Each worker:
1. `compute_file_hash()` → SHA256
2. `get_card_state()` → check DB cache
3. `render_all_pages()` → PIL images at 200 DPI
4. If new: `extract_text_all_pages()` → OCR via tesserocr (PSM AUTO, dict penalty 0.15), then `save_raw_ocr()`
5. `reprocess_candidates_from_raw()` (always — re-applies current cleaning)
6. Returns a `PdfWorkerResult` dataclass (pickled across process boundaries)

### Worker Count
`OCR_WORKERS = cpu_count()` (defined in `app/core/constants.py`). Pool is capped at `min(num_cards, OCR_WORKERS)` to avoid idle worker startup latency when processing fewer cards than CPUs.

### Image Serialization
PIL Images can't be pickled across processes. The worker serializes them as PNG bytes in `PdfWorkerResult`:
```python
# Worker side: PIL → PNG bytes (in PdfWorkerResult)
preview_buf = io.BytesIO()
images[0].save(preview_buf, format='PNG')
result.preview_image_bytes = preview_buf.getvalue()

# Main side: PNG bytes → PIL (in _worker_result_to_card)
card.preview_image = Image.open(io.BytesIO(wr.preview_image_bytes))
```

### Deduplication During Processing
In `_process_cards()` (background thread, receiving results):
- Hash already in `_cards_by_hash` → add path to existing card
- New hash → `_worker_result_to_card()` creates CardResult with next monotonic ID

### Reload: `_reload_cards()`

Reload re-checks loaded paths for modifications/deletions on the main thread (no background work for the diff phase). Modified files are handed to `_start_processing()` — the same ProcessPoolExecutor path used by initial loading. This means reload inherits all existing dedup, progress tracking, and state management.

**mtime fast pre-filter:** `_reload_cards()` accepts a `mtime_only` keyword argument. When `mtime_only=True` (the auto-reload path), each file's `st_mtime` is compared against `_mtime_by_path` before any hash is computed. Files with unchanged mtime are skipped entirely — a `stat()` call is ~1000x faster than reading and hashing the full file. Files with changed mtime still fall through to hash comparison. Manual reload (menu/toolbar) uses `mtime_only=False` and always hash-checks every file.

Auto-reload fires on `wx.EVT_ACTIVATE` (window re-activation) with a 2-second cooldown (`time.monotonic()`) to avoid rapid-fire reloads. Reload is also gated on the reload toolbar tool being enabled — processing disables it, which prevents concurrent reloads.

## AI Analysis

### Unified Path: `_start_ai_all()`
All AI analysis (single card, selected, or visible) flows through a single async batch path:

1. `_get_ai_target_cards()` determines scope: 2+ selected → "selected", else → all "visible" cards
2. Single card from detail panel AI button passes `cards=[card]` directly
3. Spawns `threading.Thread(target=_run_ai_all)`
4. Thread runs `asyncio.run(_run_ai_all_async())`
5. Async function uses `Semaphore(3)` for concurrent API calls via `analyze_card_with_ai_async()`
6. Each card processed as an async task via `asyncio.gather()`

The menu label and toolbar tooltip update dynamically based on scope:
- 0-1 selected: "AI Analyze Visible (N)"
- 2+ selected: "AI Analyze Selected (N)"
- Disabled: "AI Analyze"

### Retry and Rate Limit Coordination

Two layers of retry protect against transient API failures:

1. **SDK-level retry** (`_MAX_RETRIES = 4` in `ai_analyzer.py`): The Anthropic SDK retries 429, 408, 409, and ≥500 errors automatically with exponential backoff + jitter + `retry-after` header parsing. Configured via `AsyncAnthropic(max_retries=4)`.

2. **App-level retry** (in `_run_ai_all_async()`): After SDK retries are exhausted, each card gets one more attempt:
   - `RateLimitError` → pause the shared `_RateLimitGate`, retry once after pause
   - `APITimeoutError` / `APIConnectionError` → retry once after 2s delay
   - `AuthenticationError` → abort all (no retry)
   - Other exceptions → no retry

### `_RateLimitGate` (Thundering Herd Prevention)

```python
class _RateLimitGate:
    def __init__(self): self._resume_at = 0
    async def wait_if_paused(self): ...  # sleep until resume_at
    def pause(self, seconds): ...        # set resume_at = max(current, now + seconds)
```

When any task hits a rate limit, it calls `gate.pause(delay)` using the delay from `parse_retry_after()` (which reads `retry-after-ms` / `retry-after` headers, falling back to 10s). All tasks call `gate.wait_if_paused()` before acquiring the semaphore, so queued tasks won't immediately fire into another rate limit. Multiple pauses coalesce — only the longest remaining pause applies.

Safe without locks because asyncio is single-threaded — only one coroutine runs at a time between await points.

### Auth Abort Pattern
```python
auth_failed = asyncio.Event()

async def process_card(card):
    if auth_failed.is_set():
        return  # Skip remaining
    try:
        result = await analyze_card_with_ai_async(images)
    except AuthenticationError:
        auth_failed.set()  # Stop all remaining cards
```

On `AuthenticationError`, the event is set immediately. All pending tasks check the event before acquiring the semaphore AND after acquiring it (double-check pattern).

## Thread Safety: wx.CallAfter

**All UI updates from background threads MUST use `wx.CallAfter()`.**

```python
# In background thread:
wx.CallAfter(self._update_processing_progress, i + 1, total, card.filename)
wx.CallAfter(self._processing_complete)
wx.CallAfter(self._ai_all_complete, errors, aborted)
```

`wx.CallAfter` posts a callable to the wx event queue, ensuring it runs on the main thread during the next event loop iteration.

### Error Dialogs from Threads
```python
# Capture exception reference before it goes out of scope
wx.CallAfter(lambda: wx.MessageBox(msg, "AI Error", ...))
```

Note: Python 3.14 clears `except` variables after the block exits. If using lambdas, capture the message string before the lambda.

## Progress Dialog

Both PDF processing and AI batch use `ProgressDialog`:
- Created on main thread before spawning worker
- Updated via `wx.CallAfter` from background thread
- `_progress.finish()` called when complete
- Guard: `not self._progress.IsBeingDeleted()` prevents updates after dialog is destroyed

## Gotchas

- **spawn method:** `multiprocessing.set_start_method('spawn', force=True)` is required for PyInstaller-bundled apps (fork doesn't work with frozen modules).
- **Module-level worker:** `process_pdf_worker` is defined at module level in `app/core/pdf_worker.py`, not as a method. Methods can't be pickled for multiprocessing.
- **Semaphore(3):** Limits concurrent API calls. Combined with `_RateLimitGate` for cross-request coordination — the gate pauses all tasks before semaphore acquisition when a rate limit is hit.
- **asyncio.run() in thread:** Creates a new event loop in the background thread. The main thread's wx event loop is separate.
- **Busy cursor:** `wx.BeginBusyCursor()` / `wx.EndBusyCursor()` bracket processing. Guard: `if wx.IsBusy()` prevents double-end.
- **tesserocr C API:** Uses tesserocr (C++ bindings to Tesseract) instead of pytesseract (CLI wrapper). No binary path resolution needed — tesserocr links directly to libtesseract. Tessdata (`eng.traineddata`) is bundled in `_build/runtime_content/tessdata/` (dev) / `_runtime_content/tessdata/` (bundle) and the path is set deterministically via `_get_tessdata_path()` in `ocr_engine.py` (uses `sys._MEIPASS` when bundled, project root in dev).
