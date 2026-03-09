# Card Data Model

CardResult lifecycle, content-based deduplication, and state management.

**Key files:** `app/models/card.py`, `app/core/card_store.py` (in-memory state), `app/core/services/factory.py` (service construction + wiring), `app/core/services/card_service.py` (mutations + DB persistence), `app/core/services/rename_service.py` (rename orchestration), `app/core/services/processing_service.py` (PDF processing orchestration), `app/core/services/ai_service.py` (AI batch orchestration), `app/core/database.py` (DB models)

## Core Data Structures

### CardResult (in-memory, runtime)

The primary object representing a loaded greeting card. Created during PDF processing, lives in `CardStore._cards_by_hash` (accessed via `MainWindow._card_store`).

Fields are organized into four sections. No prefix = domain model (the default majority); `ui_` prefix = view-only state (the exception).

```
CardResult
│
│ ── Identity ──
├── id: int                    # Monotonically increasing, unique per session
├── file_paths: list[Path]     # All paths with identical content (1+)
├── primary_path: Path         # First path discovered
├── file_hash: str             # SHA256 of file content
│
│ ── Name resolution (persisted to DB) ──
├── family_name: str           # Current best name (from DB candidate or manual)
├── confidence: Confidence     # HIGH | MEDIUM | LOW | MANUAL | NONE
├── method: str                # 'ocr' | 'ai' | 'manual' | 'missing'
├── candidates: list[CandidateInfo]  # All name candidates from DB
├── selected_candidate_id: int?      # Which candidate is active
├── manual_override: str       # User-typed name (overrides family_name in display)
├── remove_family: bool        # Omit "Family" suffix in filename
├── alternates: list[str]      # Alternative display name forms
│
│ ── Processing artifacts ──
├── ocr_text: str              # Raw OCR output
├── preview_image: PIL.Image   # First page render (for AI)
├── page_images: list[Image]   # All page renders
├── ai_analyzed: bool          # Has AI been run
├── error: str                 # Non-empty on processing failure
│
│ ── UI state (not persisted, GUI bookkeeping) ──
├── original_confidence: Confidence?  # Saved when manual edit starts; restored when candidate re-selected
│
│ ── Properties ──
└── @property pdf_path         # alias for primary_path
    @property display_name     # manual_override if set, else family_name
    @property filename         # primary_path.name
```

### Confidence Enum

| Value    | Color            | Meaning                        |
|----------|------------------|--------------------------------|
| `HIGH`   | Green (#34C759)  | Strong OCR pattern or AI match |
| `MEDIUM` | Orange (#FF9500) | Partial pattern match          |
| `LOW`    | Red (#FF3B30)    | Weak/fallback match            |
| `MANUAL` | Blue (#1E90FF)   | User manually entered name     |
| `NONE`   | Gray (#6E6E73)   | No name extracted yet          |

### CandidateInfo (from DB)

```
CandidateInfo
├── id: int            # DB primary key
├── family_name: str   # Cleaned name (smart_title_case applied)
├── method: str        # 'ocr' | 'ai'
└── confidence: str    # 'high' | 'medium' | 'low'
```

### CardState (DB query result)

Returned by `database.get_card_state()` — a snapshot of the card's DB state:

```
CardState
├── display_name: str
├── method: str
├── confidence: str
├── candidates: list[CandidateInfo]
├── remove_family: bool
└── selected_candidate_id: int?
```

## CardStore — Thread-Safe State Owner

`CardStore` (`app/core/card_store.py`) is the single source of truth for all in-memory card state. It owns the dictionaries, the threading lock, and provides query/mutation APIs:

```
CardStore
├── _cards_by_hash: dict[str, CardResult]    # hash → Card (1:1)
├── _id_to_card: dict[int, CardResult]       # session ID → Card
├── _hash_by_path: dict[Path, str]           # path → hash (many:1)
├── _mtime_by_path: dict[Path, float]        # path → mtime cache
├── _pdf_files: set[Path]                    # all registered paths
├── _processing_errors: list[ProcessingError] # failed PDFs (no card created)
├── _next_card_id: int                       # monotonic ID counter
└── _lock: threading.Lock                    # protects background worker mutations
```

**Queries** (main thread, no lock needed): `get_by_id()`, `get_by_hash()`, `get_all_cards()`, `find_by_filename()`, `has_path()`, `count`, `is_empty`, `error_count`, `get_processing_errors()`

**Derived queries:** `derive_folders()` — returns a sorted list of unique parent directories across all loaded cards. Used by the controller to populate the folder sidebar without exposing internal card data to the GUI layer.

**Mutations** (thread-safe via internal lock): `add_or_update()`, `register_new_pdfs()`, `unlink_path()`, `update_path_mapping()`, `clear()`

**Composite operations** (main thread): `filter_and_register(pdf_paths)` — filters out already-loaded paths, registers new ones, returns `(new_pdfs, skipped_pdfs)`. `compute_reload_diff(mtime_only)` — iterates loaded paths, detects deletions and content modifications, returns `(deleted_paths, modified_paths)` with side effects (unlinking deleted, detaching modified).

### Threading Model

CardStore uses a split locking strategy as an intentional design choice:

- **Main-thread reads are lock-free.** Query methods (`get_by_id()`, `get_by_hash()`, `get_all_cards()`, etc.) do not acquire `self._lock`. This relies on CPython's GIL guaranteeing atomicity for single dict operations (`__getitem__`, `__contains__`, `__len__`), so a main-thread read cannot see a partially-updated dict entry.
- **Background worker mutations use `self._lock`.** Methods like `add_or_update()` acquire the lock to ensure that multistep mutations (e.g., inserting into `_cards_by_hash` then `_id_to_card` then `_hash_by_path`) are atomic with respect to each other. Without the lock, two concurrent background workers could interleave their mutations.
- **Main-thread mutations are also lock-free.** `CardService` methods and composite operations like `compute_reload_diff()` run exclusively on the main thread. Since the GIL prevents concurrent execution with the background worker's locked section, these are safe without acquiring the lock.

**Risk: free-threaded Python (PEP 703).** If the project moves to a free-threaded build (no GIL), the lock-free read paths would become unsafe — concurrent dict reads during a background mutation could observe inconsistent state. The fix would be to acquire `self._lock` on read paths as well, or switch to a `threading.RWLock` pattern to avoid lock contention on the UI thread. This is a known trade-off: the current design prioritizes UI responsiveness over forward-compatibility with free-threaded builds.

## CardService — Mutations + DB Persistence

`CardService` (`app/core/services/card_service.py`) orchestrates card field mutations with database persistence. Each method combines in-memory updates on the CardResult with DB calls, ensuring the two stay in sync. Runs exclusively on the main (UI) thread.

```
CardService
├── reset()                              # Reset database + clear in-memory state
├── set_name(card_id, name)              # Manual name override + DB persist
├── select_candidate(card_id, cand_id)   # Select candidate + DB persist
├── select_candidate_by_rank(card_id, rank)  # By 1-based rank → CardResult | None (raises ValueError)
├── set_remove_family(card_id, value)    # Toggle flag + DB persist
├── clear_ai_results(cards)              # Delete AI data + reload from DB
├── clear_cards()                        # Clear all in-memory state (no DB reset)
├── unlink_path(path)                    # Remove path from tracking and its card
└── is_ai_eligible(card) [static]        # True if card can be sent for AI analysis
```

**`select_candidate_by_rank`** returns `CardResult` on success or `None` if the card is not found. Raises `ValueError` on invalid rank (out of range). Callers (e.g. the scripting bridge) catch `ValueError` to report the error.

**`is_ai_eligible`** checks that a card has no error and has at least one image (`page_images` or `preview_image`). Used by both the GUI AI button handler and the scripting bridge's `analyze` command to avoid duplicating eligibility logic.

**Why separate from CardStore:** CardStore is a pure in-memory container with thread-safety concerns (background PDF worker). CardService handles business operations that require database access and runs only on the main thread — no locking needed.

### Services Factory

`create_services()` (`app/core/services/factory.py`) centralizes dependency wiring. It creates a single `CardStore` and passes it to every service that needs it, returning a frozen `Services` dataclass. `MainWindow.__init__` calls `create_services()` instead of manually constructing each service and threading the store through them.

## RenameService — Rename Orchestration

`RenameService` (`app/core/services/rename_service.py`) consolidates rename execution and path-mapping updates that were previously duplicated in MainWindow and AppleEventsMixin.

```
RenameService
├── build_plan(cards, year) [static]            # Wrap build_rename_plan()
├── execute(plan)                               # Execute rename plan + update store path mappings
├── rename_card(card, name, year)               # Single-card rename for Apple Events scripting
├── get_completed_paths(results) [static]       # Resolved paths (wraps filter_completed_renames)
├── validate_year(year_str) [static]            # Wrap validate_year() for year input validation
├── INVALID_FILENAME_CHARS [class attr]         # Frozenset of invalid filename characters
```

`build_plan()` wraps `build_rename_plan()` so GUI callers don't import core naming internals directly. `execute()` calls `execute_rename_plan()` then updates `CardStore.update_path_mapping()` for each resolved result. `rename_card()` temporarily sets the card's `manual_override`, builds a plan, executes it, and rolls back on total failure.

`get_completed_paths()` wraps `filter_completed_renames()` so the GUI doesn't import `rename_filter` directly.

**Rename presentation helpers** (`summarize_plan`, `summarize_results`, `format_plan_summary`, `format_results_summary`, `filter_visible_results`, `get_plan_item_display`, `is_skip_status`) live in `app/gui/rename_display.py`, not in `RenameService`. They are standalone functions used by `RenameConfirmDialog` and `CompletionDialog`.

## ProcessingService — PDF Processing Orchestration

`ProcessingService` (`app/core/services/processing_service.py`) manages the `ProcessPoolExecutor` lifecycle and worker dispatch. Zero wxPython dependency — the caller wraps callbacks with `wx.CallAfter`.

```
ProcessingService
├── process_files(files, on_progress, on_complete)
│       # Runs synchronously in calling thread
│       # Caller is responsible for launching background thread
│       # Calls store.add_or_update() for each result
├── ingest_paths(paths)             # Scan paths for PDFs + register new ones → (new_pdfs, skipped_count)
├── compute_reload(mtime_only)      # Compute deleted/modified + register modified → (deleted, modified)
└── scan_for_pdfs(path) [static]    # Scan a file/directory for PDF files
```

## AIService — AI Batch Orchestration

`AIService` (`app/core/services/ai_service.py`) wraps the async AI batch pipeline so that GUI callers don't import `core.pipeline` internals. Zero wxPython dependency — the caller wraps callbacks with `wx.CallAfter`.

```
AIService
└── run_batch(cards, on_progress, on_complete) [static]
        # Runs asyncio.run() synchronously in calling thread
        # Caller is responsible for launching background thread
```

## Content-Based Deduplication

CardStore uses a two-level mapping:

```
_cards_by_hash: dict[str, CardResult]    # hash → Card (1:1)
_hash_by_path:  dict[Path, str]          # path → hash (many:1)
```

**Why:** Multiple PDF files can have identical content (copies in different folders). Rather than showing duplicates, the system detects this via SHA256 hash and groups them under one CardResult with multiple `file_paths`.

```
PDF A (/dir1/card.pdf)  ─┐
                          ├─ hash "abc123" → CardResult(file_paths=[A, B])
PDF B (/dir2/card.pdf)  ─┘
PDF C (/dir1/other.pdf)    ─ hash "def456" → CardResult(file_paths=[C])
```

### Dedup During Processing

In `CardStore.add_or_update()` (called from `ProcessingService.process_files()`):
1. Worker returns `file_hash` in result dict
2. If `file_hash` is `None` (processing error) → record a `ProcessingError`, return `(None, False)` — no card created
3. If hash already in `_cards_by_hash` → add path to existing card's `file_paths`
4. If hash is new → create new CardResult, assign next monotonic ID
5. Always update `_hash_by_path[pdf_path] = file_hash`

## Processing Errors

PDFs that fail processing (e.g. corrupt files, OCR failures) are tracked separately from successful cards. When `PdfWorkerResult.file_hash` is `None`, `CardStore.add_or_update()` does **not** create a `CardResult`. Instead, it appends a `ProcessingError(path, error)` to `_processing_errors`.

```python
@dataclass
class ProcessingError:
    path: Path
    error: str
```

This eliminates "ghost cards" — cards with no hash that cannot be looked up, deduplicated, or meaningfully displayed. The error count is available via `CardStore.error_count` and the full list via `get_processing_errors()`. The GUI appends the failure count to the processing-complete status message (e.g., "5 cards loaded (2 files failed)"). `clear()` resets the error list along with all other state.

## State Flow

```
PDF file on disk
    │
    ├─ compute_file_hash() → SHA256
    │
    ├─ get_card_state(hash) → check DB cache
    │   ├─ EXISTS: reprocess_candidates_from_raw(hash)
    │   │          → re-applies current cleaning logic to raw data
    │   │          → returns updated CardState
    │   │
    │   └─ NEW: render_all_pages() → PIL images
    │          extract_text_all_pages() → OCR text
    │          save_raw_ocr(hash, text) → persist raw
    │          reprocess_candidates_from_raw(hash) → parse + clean + auto-select
    │
    └─ CardStore.add_or_update() creates/updates CardResult with assigned ID
       → stored in _cards_by_hash[hash] and _id_to_card[id]
```

## Multi-Load Architecture

Cards accumulate from multiple sources. `_load_paths(paths, auto_process=True) -> int`:
- Calls `ProcessingService.ingest_paths()` to scan, filter, and register new PDFs
- Processes only new PDFs via `ProcessingService`
- Returns the count of new PDFs found (used by the scripting bridge)

`_clear_all()` resets everything — calls `CardService.clear_cards()`, resets sidebar, preview. Also triggered by the Clear toolbar button.

`CardService.clear_ai_results(cards)` performs scoped deletion of AI data for specific cards. Deletes `raw_ai_results` and AI candidates for the given hashes. For cards whose selected candidate was AI, automatically re-selects the best OCR candidate (using `_CONFIDENCE_ORDER`), or clears the selection if no OCR candidates remain. Manual entries (`selected_family_name`) are preserved.

### Reload

`_reload_cards(mtime_only=False) -> bool` re-checks all currently loaded paths without scanning folders for new files. Returns `True` if anything changed (files deleted or modified), `False` otherwise. The scripting bridge uses the return value to report whether a reload had any effect. It delegates to `ProcessingService.compute_reload()` (which wraps `CardStore.compute_reload_diff()` and `register_new_pdfs()`), running a diff against the `_hash_by_path` snapshot:

1. **Deleted files** (path no longer exists) — path is removed via `CardStore.unlink_path()`. If the card has no remaining paths, it's removed from `_cards_by_hash`.
2. **Modified files** (path exists, `compute_file_hash()` returns a different hash) — the path is detached from the old card (same cleanup as deletion), then added to a reprocessing list.
3. **Unchanged files** — skipped.

**mtime pre-filter:** Auto-reload (window re-activation) passes `mtime_only=True`, which compares `path.stat().st_mtime` against `CardStore.get_mtime_for_path()` before computing any hash. Files whose mtime hasn't changed are skipped entirely — a single `stat()` call per file instead of reading the full file content through SHA-256. Files with a changed mtime still fall through to hash comparison (mtime change doesn't guarantee content change). Manual reload (menu/toolbar) uses `mtime_only=False` (the default) and always hash-checks every file.

Modified files go through `_start_processing()`, where `CardStore.add_or_update()` handles hash convergence: if the new hash matches an existing card, the path merges into that card automatically. `add_or_update()` also records the mtime, keeping the mtime cache in sync.

Triggered by: File > Reload (Cmd+Shift+R), toolbar Reload button, or automatically on window re-activation (with a 2-second cooldown).

## Rename Flow

After renaming, `RenameService.execute()` calls `CardStore.update_path_mapping()` for each resolved result, updating `_hash_by_path`, `_mtime_by_path`, `_pdf_files`, and the card's `file_paths`.

### Post-Rename Selective Removal
After the completion dialog, `_remove_completed_results()` selectively cleans up:
- **Removed:** Paths from results with outcomes in `RESOLVED_OUTCOMES` (`RENAMED` or `ALREADY_CORRECT`) — these are resolved.
- **Kept:** Paths that failed (OS errors, race conditions) or had no name extracted (`skip_no_name`) / processing errors (`skip_error`).
- If removing a path leaves a card with no remaining `file_paths`, the card is deleted from `_cards_by_hash`.
- Folder list and display are refreshed; empty state overlay shows only if all cards are gone.

## Gotchas

- **CardResult.id is session-scoped:** IDs are monotonically increasing starting from 0 each session. They are NOT database IDs.
- **file_hash is the canonical key:** All DB operations use `file_hash`, not `id` or path. Cards survive renames because the hash doesn't change.
- **Savepoint in `_insert_candidates`:** Candidate insertion uses `session.begin_nested()` (a SAVEPOINT) around the add+flush. If a `UniqueConstraint` violation occurs, only the savepoint is rolled back — the outer session remains valid for subsequent queries. This avoids a full `session.rollback()` that would invalidate the session state.
- **display_name vs family_name:** `display_name` (property) returns `manual_override` if set, else `family_name`. Always use `display_name` for UI display.
- **original_confidence:** Saved when manual edit starts; restored when candidate re-selected. Prevents losing the OCR/AI confidence level. Not persisted to the database.
