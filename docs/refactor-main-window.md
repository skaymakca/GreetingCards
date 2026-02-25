# Refactor main_window.py into Smaller Modules

## Context

`app/gui/main_window.py` is 1763 lines with 56 methods spanning 9+ responsibilities: GUI layout, toolbar/menu setup, file scanning/loading, PDF/OCR processing orchestration, AI batch processing, rename operations, card state management, filtering, and event handling. Too much processing code lives in this GUI file. The `app/gui/` directory is also flat (16 files, no subdirectories), making it hard to understand what's a component, what's a dialog, and what's infrastructure.

**Goal:** Reduce main_window.py to ~900-1000 lines across 6 phased commits, with proper separation of concerns: GUI-free processing logic goes to `app/core/`, the `app/gui/` directory gets organized into semantic subpackages, and only window-level orchestration remains in `main_window.py`.

## Design Principles

1. **Delegation, not inheritance.** Extracted code goes into collaborator classes that receive a `MainWindow` reference (for GUI orchestrators) or are standalone (for core logic). No mixins.
2. **Re-exports for backward compatibility.** Moved symbols get re-exported from their original location so test imports don't break. Cleanup in Phase 5.
3. **`TYPE_CHECKING` guard for circular imports.** Collaborators use `from __future__ import annotations` + `if TYPE_CHECKING: from app.gui.main_window import MainWindow`.
4. **Each phase is independently committable.** All tests pass after each phase.
5. **Core vs GUI separation.** If a CLI could reuse it, it belongs in `app/core/`. The `app/gui/` package organizes by role: components, dialogs, infrastructure.

## Final `app/gui/` Structure

```
app/gui/
  main_window.py              ~960 lines (down from 1763)
  appearance.py               System appearance detection (dark mode KVO)
  context_menu.py             Context menu builder
  icons.py                    Icon loading and caching
  styles.py                   Colors, layout constants
  utils.py                    Shared GUI utilities

  components/                 Panels and widgets composed by the main window
    __init__.py
    drop_target.py            NEW — Drop overlay + file drop target (from main_window)
    filter_sidebar.py         MOVED — Filter sidebar panel
    html_viewer.py            MOVED — Reusable HTML viewer window
    preview_panel.py          MOVED — PDF preview panel
    review_panel.py           MOVED — Card review/detail panel
    toolbar.py                NEW — Toolbar and menu bar builder (from main_window)

  dialogs/                    Modal and standalone dialog windows
    __init__.py
    api_key.py                MOVED (was api_key_dialog.py)
    changelog.py              MOVED (was changelog_dialog.py)
    common.py                 MOVED (was dialogs.py — shared helpers like ProgressDialog)
    help.py                   MOVED (was help_dialog.py)
    licenses.py               MOVED (was licenses_dialog.py)
    settings.py               MOVED (was settings_dialog.py)
```

```
app/core/
  (existing files)
  rate_limit.py               NEW — Phase 1  (RateLimitGate)
  card_processor.py           NEW — Phase 2  (PDF scanning, dedup, worker→card conversion)
  ai_batch.py                 NEW — Phase 3  (async batch AI orchestration, retry, rate limit coordination)
  rename_executor.py          NEW — Phase 4  (rename plan execution, result filtering)
```

### Why reorganize `app/gui/`?

The flat directory with 16 files gives no signal about what each module does. Someone new to the codebase has to open files to understand whether `html_viewer.py` is a reusable component or a dialog. The three-way split makes the architecture self-documenting:

- **`components/`** — Panels and widgets that the main window (or other windows) compose together. These are the building blocks of the UI.
- **`dialogs/`** — Modal or standalone windows that appear transiently. Grouped together because they share patterns (show/hide lifecycle, parent window reference, result collection).
- **Top-level `app/gui/`** — The main window itself plus infrastructure modules (appearance, icons, styles, utils, context_menu) that don't fit neatly into components or dialogs.

### What goes where?

| Destination | Criteria | Examples |
|---|---|---|
| `app/core/` | No wx imports, no UI callbacks. A CLI could use this. | Rate limiting, PDF scanning, card dedup, batch AI retry logic, rename execution |
| `app/gui/components/` | wx panels/widgets composed into windows | Drop overlay, toolbar, filter sidebar, review panel, preview panel, HTML viewer |
| `app/gui/dialogs/` | Modal or standalone dialog windows | API key, changelog, help, licenses, settings, shared dialog helpers |
| `app/gui/main_window.py` | Window-level wiring: thread spawning, progress dialogs, `wx.CallAfter` callbacks, UI state transitions | `_start_processing()`, `_start_ai_all()`, progress/completion handlers |

---

## Phase 1: Extract Standalone Utilities and Widgets (~190 lines)

Lowest risk — moves self-contained module-level code that has zero coupling to MainWindow methods. Also establishes the `components/` and `dialogs/` subpackages by moving existing files.

### Extracted from main_window.py

| What | From | To | Notes |
|------|------|----|-------|
| `_RateLimitGate` (19 lines) | main_window.py:44-62 | `app/core/rate_limit.py` (new) | Pure async primitive, no wx dependency. Rename to `RateLimitGate`. A CLI batch tool would use the same gating. |
| `_plural()` (3 lines) | main_window.py:65-67 | `app/gui/utils.py` | Simple string utility. |
| `_load_drop_background()` (29 lines) | main_window.py:70-98 | `app/gui/components/drop_target.py` (new) | PIL image loader for drop zone. |
| `_DropOverlay` class (97 lines) | main_window.py:102-198 | `app/gui/components/drop_target.py` (new) | Custom wx.Panel for drag-drop visual. |
| `FileDropTarget` class (34 lines) | main_window.py:1730-1763 | `app/gui/components/drop_target.py` (new) | wx.FileDropTarget subclass. |

### Reorganize existing files

Move existing modules into `components/` and `dialogs/` subpackages:

| File | Moves to | Notes |
|------|----------|-------|
| `filter_sidebar.py` | `components/filter_sidebar.py` | |
| `review_panel.py` | `components/review_panel.py` | |
| `preview_panel.py` | `components/preview_panel.py` | |
| `html_viewer.py` | `components/html_viewer.py` | |
| `api_key_dialog.py` | `dialogs/api_key.py` | Rename: drop `_dialog` suffix |
| `changelog_dialog.py` | `dialogs/changelog.py` | Rename: drop `_dialog` suffix |
| `dialogs.py` | `dialogs/common.py` | Shared helpers (ProgressDialog, etc.) |
| `help_dialog.py` | `dialogs/help.py` | Rename: drop `_dialog` suffix |
| `licenses_dialog.py` | `dialogs/licenses.py` | Rename: drop `_dialog` suffix |
| `settings_dialog.py` | `dialogs/settings.py` | Rename: drop `_dialog` suffix |

Each moved module gets a re-export from the old location (a one-line file: `from app.gui.components.filter_sidebar import *`) to avoid breaking imports during the refactor. These shims are removed in Phase 5.

### Re-exports in main_window.py
```python
from app.core.rate_limit import RateLimitGate as _RateLimitGate
from app.gui.components.drop_target import DropOverlay as _DropOverlay, FileDropTarget, load_drop_background as _load_drop_background
from app.gui.utils import plural as _plural
```

### Files
- **Create:** `app/core/rate_limit.py`, `app/gui/components/__init__.py`, `app/gui/components/drop_target.py`, `app/gui/dialogs/__init__.py`
- **Move:** 10 existing files into `components/` and `dialogs/` (see table above)
- **Create shims:** One-line re-export files at the old locations for backward compatibility
- **Modify:** `app/gui/main_window.py` (remove extracted code, add re-exports), `app/gui/utils.py` (add `plural()`)
- **Tests:** Move `RateLimitGate` tests from `test_main_window.py` to `tests/core/test_rate_limit.py`. All other tests continue working via re-export shims.
- **Docs:** Update `docs/architecture/async-processing.md` (RateLimitGate location)

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 2: Extract PDF/OCR Processing Pipeline (~200 lines)

Separates GUI-free processing logic (scanning, dedup, worker→card conversion) into `app/core/`, keeping only thread spawning and UI callbacks in main_window.

### New module: `app/core/card_processor.py`

Pure functions and a stateful `CardStore` class — no wx imports, no UI callbacks.

| What moves to `app/core/card_processor.py` | Lines | Notes |
|---|---|---|
| `_scan_for_pdfs()` | 756-772 | Pure Path utility → standalone function `scan_for_pdfs()` |
| `_worker_result_to_card()` | 1069-1104 | Data transformation → standalone function `worker_result_to_card()` |
| `_derive_folders()` | 1111-1113 | Pure derivation → standalone function `derive_folders()` |
| `_load_card_state_from_db()` | 1325-1361 | DB → CardResult sync → standalone function `load_card_state_from_db()` |
| Dedup logic from `_process_cards()` | 1039-1061 | The `with self._state_lock` block → `CardStore.ingest_result()` method |

### What stays on MainWindow (GUI orchestration)

| Method | Why it stays |
|---|---|
| `_start_processing()` | `wx.BeginBusyCursor()`, `ProgressDialog`, thread spawning |
| `_process_cards()` | Thread entry point calling `ProcessPoolExecutor` + `wx.CallAfter` for progress |
| `_update_processing_progress()` | `wx.CallAfter` target, touches `ProgressDialog` |
| `_processing_complete()` | UI state transitions (enable tools, close dialog) |
| `_load_paths()` | Touches `_hash_by_path`, `_mtime_by_path`, calls `_start_processing` |

But `_process_cards()` now delegates to `CardStore.ingest_result()` for the dedup/storage logic rather than doing it inline.

### Files
- **Create:** `app/core/card_processor.py`
- **Modify:** `app/gui/main_window.py` (simplify `_process_cards`, delegate to core functions)
- **Tests:** Add `tests/core/test_card_processor.py` for the extracted functions

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 3: Extract AI Batch Processing (~200 lines)

Moves the async AI orchestration — semaphore, rate limit gate, retry logic — into `app/core/`. The core module takes a callback protocol for progress reporting, making it reusable from a CLI.

### New module: `app/core/ai_batch.py`

Contains the async batch processing logic. No wx imports. Uses a callback/protocol for progress reporting.

| What moves to `app/core/ai_batch.py` | Lines | Notes |
|---|---|---|
| `_run_ai_all_async()` core logic | 1417-1509 | Async batch with retry → `run_ai_batch_async()`. Takes a progress callback instead of calling `wx.CallAfter` directly. |
| Rate limit + retry coordination | (within above) | Uses `RateLimitGate` from Phase 1 |

### What stays on MainWindow (GUI orchestration)

| Method | Why it stays |
|---|---|
| `_ensure_api_key()` | Shows wx dialog for API key input |
| `_get_target_cards()` | Reads selection state from `_review_panel` |
| `_on_ai_request()` | Single-card AI from detail panel button |
| `_start_ai_all()` | `wx.BeginBusyCursor()`, `ProgressDialog`, thread spawning |
| `_run_ai_all()` | Thread entry point, `asyncio.run()`, `wx.CallAfter` on error |
| `_update_ai_all_progress()` | Touches `ProgressDialog` and `_review_panel` |
| `_ai_all_complete()` | UI state transitions |
| `_on_clear_ai_results()` | Shows wx confirmation dialog |

But `_run_ai_all_async()` now delegates to `app.core.ai_batch.run_ai_batch_async()` passing a progress callback, rather than containing the retry/gating logic inline.

### Files
- **Create:** `app/core/ai_batch.py`
- **Modify:** `app/gui/main_window.py` (simplify `_run_ai_all_async`)
- **Tests:** Add `tests/core/test_ai_batch.py` for retry/gating logic

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 4: Extract Rename Operations and Toolbar/Menu Construction (~280 lines)

### Group A: Rename → `app/core/rename_executor.py`

The rename execution logic (plan building, result filtering) is GUI-free and belongs in core.

| What moves | Lines | Notes |
|---|---|---|
| `_remove_completed_results()` result-filtering logic | 1586-1623 | The path-removal and card-cleanup logic → `filter_completed_renames()` |
| `_RESOLVED_MESSAGES` | 41 | Moves with the filtering logic |

`_start_rename()` stays on MainWindow — it shows a confirmation dialog and calls `execute_rename_plan()` (already in `app/core/renamer.py`).

### Group B: Toolbar/Menu → `app/gui/components/toolbar.py`

New class: `ToolbarManager` — builds toolbar and menu bar, manages tool/menu IDs.

| Method | Lines |
|---|---|
| `_setup_menu_bar()` | 264-373 |
| `_build_toolbar()` | 429-503 |
| `_enable_action_tools()` | 505-521 |
| `_refresh_toolbar_icons()` | 1665-1677 |
| `_on_update_action_menu()` | 1238-1265 |

**ID storage approach:** `ToolbarManager` writes tool/menu IDs directly onto `MainWindow` (e.g., `self._window._browse_id = ...`) to avoid updating every reference across MainWindow. This preserves all existing test access patterns like `window._toolbar.GetToolEnabled(window._reload_id)`.

### Files
- **Create:** `app/core/rename_executor.py`, `app/gui/components/toolbar.py`
- **Modify:** `app/gui/main_window.py`
- **Tests:** Add `tests/core/test_rename_executor.py`. No GUI test changes (delegation wrappers preserve test interface).

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 5: Remove Compatibility Shims and Clean Up Imports

After all extractions are stable and tested, remove every re-export and compatibility shim added in Phases 1-4. This is a dedicated cleanup commit — no functional changes, only import paths change.

### Steps

1. **Remove re-export shim files** — delete the one-line forwarding modules left at old locations (e.g., the old `app/gui/filter_sidebar.py` that just re-exports from `app/gui/components/filter_sidebar`).
2. **Remove re-exports in `main_window.py`** — delete every `from ... import ... as _...` shim added during the refactor.
3. **Update all imports project-wide** — repoint every import to the canonical new location:
   - `app.gui.filter_sidebar` → `app.gui.components.filter_sidebar`
   - `app.gui.review_panel` → `app.gui.components.review_panel`
   - `app.gui.api_key_dialog` → `app.gui.dialogs.api_key`
   - `_RateLimitGate` → `app.core.rate_limit.RateLimitGate`
   - (etc. for all moved symbols)
4. **Search for stale references** — `grep` for every old import path to ensure nothing is missed.
5. **Verify no dead imports remain** — `make check` (ruff catches unused imports).

### Rules
- **No functional changes.** Only import paths change.
- **No re-exports survive.** Every symbol has exactly one canonical import path.

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 6: Restructure Tests and Close Coverage Gaps

With the source tree reorganized, the test suite should mirror the new structure. This phase restructures test files to match the source layout, then analyzes coverage to find gaps introduced or revealed by the refactor.

### Step 1: Restructure test files

Reorganize `tests/gui/` to mirror `app/gui/`:

```
tests/gui/
  components/
    test_drop_target.py         NEW or moved from test_main_window.py
    test_filter_sidebar.py      MOVED
    test_html_viewer.py         MOVED
    test_preview_panel.py       MOVED
    test_review_panel.py        MOVED
    test_toolbar.py             NEW or moved from test_main_window.py
    test_preview_cursor_behavior.py  MOVED
    test_cursors.py             MOVED
  dialogs/
    test_api_key.py             MOVED (was test_api_key_dialog.py)
    test_changelog.py           MOVED (was test_changelog_dialog.py)
    test_common.py              MOVED (was test_dialogs.py)
    test_help.py                MOVED (was test_help_dialog.py)
    test_licenses.py            MOVED (was test_licenses_dialog.py)
    test_settings.py            MOVED (was test_settings_dialog.py)
  test_main_window.py           Slimmed — only tests for MainWindow orchestration
  test_appearance.py
  test_context_menu.py
  test_icons.py
  test_styles.py
  test_utils.py
```

New core test files from Phases 1-4 should already be in place:
- `tests/core/test_rate_limit.py`
- `tests/core/test_card_processor.py`
- `tests/core/test_ai_batch.py`
- `tests/core/test_rename_executor.py`

### Step 2: Split `test_main_window.py`

`test_main_window.py` is 2835 lines — the largest test file. After Phases 1-4 extracted code into new modules (with their own test files), the monolithic test file should be split:

- Tests for extracted components (drop target, toolbar) move to `tests/gui/components/`.
- Tests for core logic (rate limiting, card processing, AI batch, rename) should already be in `tests/core/` from earlier phases.
- What remains in `test_main_window.py` should be pure integration/orchestration tests: thread spawning, progress dialog lifecycle, UI state transitions, event handler wiring.

### Step 3: Coverage analysis

Run coverage and identify gaps:

```bash
uv run pytest tests/ --cov=app --cov-report=html
```

Focus on:
- **Newly extracted modules** (`rate_limit.py`, `card_processor.py`, `ai_batch.py`, `rename_executor.py`) — verify each public function/method has direct unit tests, not just indirect coverage through integration tests.
- **Edge cases exposed by extraction** — when logic moves from a large method to a standalone function, edge cases that were implicitly tested via the larger flow may now lack direct coverage.
- **Error paths in retry/gating logic** — the AI batch retry, rate limit coordination, and auth failure abort paths should have dedicated tests now that they're isolated.
- **Component boundaries** — verify that each component's public interface (the methods MainWindow calls) is tested independently, not only through MainWindow integration tests.

### Step 4: Add missing tests

Write tests to close the gaps found in Step 3. Prioritize:
1. Extracted core functions that only had indirect coverage before
2. Error/edge-case paths in retry and rate limiting
3. Component boundary tests (e.g., `ToolbarManager` enable/disable, `CardStore.ingest_result` dedup behavior)

### Verification
`make check && uv run pytest tests/ -x --cov=app`

Update test count in `README.md`.

---

## Summary

| Phase | What | New/Changed Files | main_window.py |
|-------|------|-------------------|----------------|
| 1 | Extract utilities + widgets; establish `components/` and `dialogs/` | `core/rate_limit.py`, `gui/components/drop_target.py`, move 10 files | ~1573 lines |
| 2 | Extract PDF/OCR processing to core | `core/card_processor.py` | ~1373 lines |
| 3 | Extract AI batch processing to core | `core/ai_batch.py` | ~1173 lines |
| 4 | Extract rename + toolbar | `core/rename_executor.py`, `gui/components/toolbar.py` | ~960 lines |
| 5 | Remove all shims and re-exports | Delete shim files, update all imports | ~940 lines |
| 6 | Restructure tests + close coverage gaps | Reorganize `tests/gui/`, split `test_main_window.py`, add tests | ~940 lines |

## Open Questions / Future Considerations

- Should `_reload_cards()` (100+ lines, very complex) move to `PdfProcessor` or stay on MainWindow?
- Should filter pipeline methods (`_refresh_display`, `_apply_*_filters`) be extracted? They're tightly coupled to UI widgets.
- Should card interaction handlers (`_on_name_change`, `_on_remove_card`) be extracted?

## Verification (after each phase)
1. `make check` — all static checks pass
2. `uv run pytest tests/ -x` — all tests pass
3. `uv run python main.py` — app launches, load cards, run AI, rename — no regressions
