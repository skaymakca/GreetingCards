# Card Data Model

CardResult lifecycle, content-based deduplication, and state management.

**Key files:** `app/models/card.py`, `app/gui/main_window.py` (state management), `app/core/database.py` (DB models)

## Core Data Structures

### CardResult (in-memory, runtime)

The primary object representing a loaded greeting card. Created during PDF processing, lives in `MainWindow._cards_by_hash`.

```
CardResult
├── id: int                    # Monotonically increasing, unique per session
├── file_paths: list[Path]     # All paths with identical content (1+)
├── primary_path: Path         # First path discovered
├── file_hash: str             # SHA256 of file content
├── family_name: str           # Current best name (from DB candidate or manual)
├── confidence: Confidence     # HIGH | MEDIUM | LOW | MANUAL | NONE
├── method: str                # 'ocr' | 'ai' | 'manual' | 'missing'
├── candidates: list[CandidateInfo]  # All name candidates from DB
├── selected_candidate_id: int?      # Which candidate is active
├── manual_override: str       # User-typed name (overrides family_name in display)
├── original_confidence: Confidence?  # Saved before manual override
├── remove_family: bool        # Omit "Family" suffix in filename
├── preview_image: PIL.Image   # First page render (for AI)
├── page_images: list[Image]   # All page renders
├── ocr_text: str              # Raw OCR output
├── ai_analyzed: bool          # Has AI been run
├── error: str                 # Non-empty on processing failure
└── @property display_name     # manual_override if set, else family_name
    @property filename         # primary_path.name
    target_filename(year)      # "Holiday Cards {year} - {Name} Family.pdf"
```

### Confidence Enum

| Value | Color | Meaning |
|-------|-------|---------|
| `HIGH` | Green (#34C759) | Strong OCR pattern or AI match |
| `MEDIUM` | Orange (#FF9500) | Partial pattern match |
| `LOW` | Red (#FF3B30) | Weak/fallback match |
| `MANUAL` | Blue (#1E90FF) | User manually entered name |
| `NONE` | Gray (#6E6E73) | No name extracted yet |

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

## Content-Based Deduplication

The main window uses a two-level mapping:

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

In `_process_cards()`:
1. Worker returns `file_hash` in result dict
2. If hash already in `_cards_by_hash` → add path to existing card's `file_paths`
3. If hash is new → create new CardResult, assign next monotonic ID
4. Always update `_hash_by_path[pdf_path] = file_hash`

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
    ├─ Dict result → _dict_to_card() → CardResult with assigned ID
    │
    └─ CardResult stored in _cards_by_hash[hash]
```

## Multi-Load Architecture

Cards accumulate from multiple sources. `_load_paths()`:
- Scans paths recursively for PDFs
- Filters out already-loaded paths (by path, not hash)
- Appends to `_pdf_files`, does NOT clear existing cards
- Processes only new PDFs

`_clear_all()` resets everything — clears all state, sidebar, preview. Also triggered by the Clear toolbar button.

`clear_ai_results(file_hashes)` performs scoped deletion of AI data for specific cards. Deletes `raw_ai_results` and AI candidates for the given hashes. For cards whose selected candidate was AI, automatically re-selects the best OCR candidate (using `_CONFIDENCE_ORDER`), or clears the selection if no OCR candidates remain. Manual entries (`selected_family_name`) are preserved.

### Reload

`_reload_cards()` re-checks all currently loaded paths without scanning folders for new files. It runs a diff against the existing `_hash_by_path` snapshot:

1. **Deleted files** (path no longer exists) — path is removed from `_hash_by_path`, `_mtime_by_path`, `_pdf_files`, and the card's `file_paths`. If the card has no remaining paths, it's removed from `_cards_by_hash`.
2. **Modified files** (path exists, `compute_file_hash()` returns a different hash) — the path is detached from the old card (same cleanup as deletion), then added to a reprocessing list.
3. **Unchanged files** — skipped.

**mtime pre-filter:** Auto-reload (window re-activation) passes `mtime_only=True`, which compares `path.stat().st_mtime` against `_mtime_by_path` before computing any hash. Files whose mtime hasn't changed are skipped entirely — a single `stat()` call per file instead of reading the full file content through SHA-256. Files with a changed mtime still fall through to hash comparison (mtime change doesn't guarantee content change). Manual reload (menu/toolbar) uses `mtime_only=False` (the default) and always hash-checks every file.

Modified files go through `_start_processing()`, where the existing dedup logic in `_process_cards()` handles hash convergence: if the new hash matches an existing card, the path merges into that card automatically. `_process_cards()` also records `_mtime_by_path[path]` after each successful hash, keeping the mtime cache in sync.

Triggered by: File > Reload (Cmd+Shift+R), toolbar Reload button, or automatically on window re-activation (with a 2-second cooldown).

## Rename Flow

After renaming, `_hash_by_path` is updated to map new paths to the same hash:
```python
file_hash = self._hash_by_path.pop(result.old_path)
self._hash_by_path[result.new_path] = file_hash
```

### Post-Rename Selective Removal
After the completion dialog, `_remove_completed_results()` selectively cleans up:
- **Removed:** Paths from results with "Renamed" or "Already named correctly" status — these are resolved.
- **Kept:** Paths that failed (OS errors, race conditions) or had no name extracted (`skip_no_name`) / processing errors (`skip_error`).
- If removing a path leaves a card with no remaining `file_paths`, the card is deleted from `_cards_by_hash`.
- Folder list and display are refreshed; empty state overlay shows only if all cards are gone.

## Gotchas

- **CardResult.id is session-scoped:** IDs are monotonically increasing starting from 0 each session. They are NOT database IDs.
- **file_hash is the canonical key:** All DB operations use `file_hash`, not `id` or path. Cards survive renames because the hash doesn't change.
- **display_name vs family_name:** `display_name` (property) returns `manual_override` if set, else `family_name`. Always use `display_name` for UI display.
- **original_confidence:** Saved when user starts manual edit, restored when selecting a candidate from dropdown. Prevents losing the OCR/AI confidence level.
