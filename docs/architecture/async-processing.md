# Async Processing

Multiprocessing for PDF rendering, asyncio for AI batch, and thread-safety patterns.

**Key files:** `app/gui/wx_main_window.py` (processing methods), `app/core/ai_analyzer.py`

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Main Thread (wx)                   │
│  UI events, wx.CallAfter callbacks, timer events     │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
     ┌─────▼──────┐            ┌──────▼──────┐
     │  Thread 1   │            │  Thread 2   │
     │ _process_   │            │ _run_ai_all │
     │   cards()   │            │  asyncio    │
     └─────┬──────┘            └──────┬──────┘
           │                          │
  ┌────────▼─────────┐      ┌────────▼─────────┐
  │ multiprocessing  │      │ asyncio.Semaphore │
  │     Pool         │      │   (3 concurrent)  │
  │  N/2 workers     │      │                   │
  └──────────────────┘      └───────────────────┘
```

## PDF Processing: Multiprocessing Pool

### Entry Point: `_start_processing()`
1. Shows ProgressDialog, begins busy cursor
2. Spawns `threading.Thread(target=_process_cards)`

### Worker: `_process_pdf_worker()` (module-level function)
Runs in a **separate process** (via `multiprocessing.Pool`). Must be module-level (not a method) for pickling.

Each worker:
1. `compute_file_hash()` → SHA256
2. `get_card_state()` → check DB cache
3. `render_all_pages()` → PIL images at 200 DPI
4. If cached: `reprocess_candidates_from_raw()` (re-applies current cleaning)
5. If new: `extract_text_all_pages()` → OCR, then save + reprocess
6. Returns a **plain dict** (not CardResult — must be picklable)

### Image Serialization
PIL Images can't be pickled across processes. The worker serializes them:
```python
# Worker side: PIL → PNG bytes
preview_buf = io.BytesIO()
images[0].save(preview_buf, format='PNG')
result['preview_image_bytes'] = preview_buf.getvalue()

# Main side: PNG bytes → PIL
card.preview_image = Image.open(io.BytesIO(result_dict['preview_image_bytes']))
```

### Deduplication During Processing
In `_process_cards()` (background thread, receiving results):
- Hash already in `_cards_by_hash` → add path to existing card
- New hash → `_dict_to_card()` creates CardResult with next monotonic ID

### Fallback
If `multiprocessing.Pool` fails (common in frozen apps), `_process_cards_sequential()` runs everything in the background thread directly.

## AI Analysis

### Single Card: `_on_ai_request()`
1. Checks API key via `_ensure_api_key()`
2. Disables AI button on the card
3. Spawns `threading.Thread(target=_run_ai_analysis)`
4. Worker calls `analyze_card_with_ai()` (sync Anthropic client)
5. Saves raw AI result to DB, reprocesses candidates
6. `wx.CallAfter(_ai_analysis_complete)` → updates UI

### Batch AI: `_start_ai_all()`
1. Spawns `threading.Thread(target=_run_ai_all)`
2. Thread runs `asyncio.run(_run_ai_all_async())`
3. Async function uses `Semaphore(3)` for 3 concurrent API calls
4. Each card processed as an async task via `asyncio.gather()`

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
- **Module-level worker:** `_process_pdf_worker` is defined at module level, not as a method. Methods can't be pickled for multiprocessing.
- **Semaphore(3):** Limits concurrent API calls to prevent rate limiting. The Anthropic API has per-account rate limits.
- **asyncio.run() in thread:** Creates a new event loop in the background thread. The main thread's wx event loop is separate.
- **Busy cursor:** `wx.BeginBusyCursor()` / `wx.EndBusyCursor()` bracket processing. Guard: `if wx.IsBusy()` prevents double-end.
