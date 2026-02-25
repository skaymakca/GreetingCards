# Refactor main_window.py into Smaller Modules

## Context

`app/gui/main_window.py` is 1763 lines with 56 methods spanning 9+ responsibilities: GUI layout, toolbar/menu setup, file scanning/loading, PDF/OCR processing orchestration, AI batch processing, rename operations, card state management, filtering, and event handling. Too much processing code lives in this GUI file. The `app/gui/` directory is also flat (16 files, no subdirectories).

**Goal:** Reduce main_window.py to ~900-1000 lines across 4 phased commits, establishing a `processing/` subdirectory for background thread orchestration.

## Design Principles

1. **Delegation, not inheritance.** Extracted code goes into collaborator classes that receive a `MainWindow` reference. No mixins.
2. **Re-exports for backward compatibility.** Moved symbols get re-exported from `main_window.py` so test imports don't break. Cleanup later.
3. **`TYPE_CHECKING` guard for circular imports.** Collaborators use `from __future__ import annotations` + `if TYPE_CHECKING: from app.gui.main_window import MainWindow`.
4. **Each phase is independently committable.** All tests pass after each phase.

## Final `app/gui/` Structure

```
app/gui/
  (existing files unchanged)
  drop_target.py              NEW — Phase 1
  toolbar.py                  NEW — Phase 4
  processing/                 NEW — Phase 2
    __init__.py
    pdf_processor.py          NEW — Phase 2
    ai_processor.py           NEW — Phase 3
    rename_handler.py         NEW — Phase 4
  main_window.py              ~960 lines (down from 1763)
```

---

## Phase 1: Extract Standalone Utilities and Widgets (~190 lines)

Lowest risk — moves self-contained module-level code that has zero coupling to MainWindow methods.

### Moves

| What | From | To | Notes |
|------|------|----|-------|
| `_RateLimitGate` (19 lines) | main_window.py:44-62 | `app/core/ai_analyzer.py` | Pure async primitive, alongside `parse_retry_after`. Rename to `RateLimitGate`. |
| `_plural()` (3 lines) | main_window.py:65-67 | `app/gui/utils.py` | Simple string utility. |
| `_load_drop_background()` (29 lines) | main_window.py:70-98 | `app/gui/drop_target.py` (new) | PIL image loader for drop zone. |
| `_DropOverlay` class (97 lines) | main_window.py:102-198 | `app/gui/drop_target.py` (new) | Custom wx.Panel for drag-drop visual. |
| `FileDropTarget` class (34 lines) | main_window.py:1730-1763 | `app/gui/drop_target.py` (new) | wx.FileDropTarget subclass. |

### Re-exports in main_window.py
```python
from app.core.ai_analyzer import RateLimitGate as _RateLimitGate
from app.gui.drop_target import DropOverlay as _DropOverlay, FileDropTarget, load_drop_background as _load_drop_background
from app.gui.utils import plural as _plural
```

### Files
- **Create:** `app/gui/drop_target.py`
- **Modify:** `app/gui/main_window.py` (remove code, add re-exports), `app/gui/utils.py` (add `plural()`), `app/core/ai_analyzer.py` (add `RateLimitGate`)
- **Tests:** No changes needed — re-exports preserve all existing imports
- **Docs:** Update `docs/architecture/async-processing.md` (RateLimitGate location)

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 2: Extract PDF/OCR Processing Pipeline (~200 lines)

Moves background thread orchestration for PDF rendering and OCR into a processing subpackage.

### New class: `PdfProcessor` in `app/gui/processing/pdf_processor.py`

Receives `MainWindow` reference, accesses shared state via `self._window._cards_by_hash`, etc.

### Methods that move

| Method | Lines | Notes |
|--------|-------|-------|
| `_scan_for_pdfs()` | 756-772 | Pure Path utility — becomes `@staticmethod` |
| `_load_paths()` | 782-820 | File loading orchestration |
| `_start_processing()` | 984-1013 | Thread spawning |
| `_process_cards()` | 1015-1067 | ProcessPoolExecutor orchestration |
| `_worker_result_to_card()` | 1069-1104 | Data transformation — `@staticmethod` |
| `_update_processing_progress()` | 1106-1109 | Progress UI callback |
| `_derive_folders()` | 1111-1113 | Pure derivation |
| `_processing_complete()` | 1115-1141 | Post-processing UI updates |
| `_load_card_state_from_db()` | 1325-1361 | DB → CardResult sync — shared by AI too |

### Delegation wrappers remain on MainWindow
Thin one-liners like `def _start_processing(self, files=None): self._pdf_processor.start_processing(files)`. This preserves `patch.object(window, "_start_processing")` in tests.

### Files
- **Create:** `app/gui/processing/__init__.py`, `app/gui/processing/pdf_processor.py`
- **Modify:** `app/gui/main_window.py`
- **Tests:** No changes — delegation wrappers preserve test interface

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 3: Extract AI Batch Processing (~200 lines)

Moves async AI analysis orchestration — the semaphore, rate limit gate, retry logic, and progress reporting.

### New class: `AiProcessor` in `app/gui/processing/ai_processor.py`

### Methods that move

| Method | Lines | Notes |
|--------|-------|-------|
| `_ensure_api_key()` | 1271-1289 | API key validation/prompt |
| `_get_target_cards()` | 1291-1301 | Selection → card list |
| `_on_ai_request()` | 1303-1322 | Single-card AI from detail panel |
| `_start_ai_all()` | 1363-1406 | Thread spawning + progress dialog |
| `_run_ai_all()` | 1408-1415 | Thread entry point |
| `_run_ai_all_async()` | 1417-1509 | Core async batch with retry |
| `_update_ai_all_progress()` | 1511-1519 | Progress UI callback |
| `_ai_all_complete()` | 1521-1544 | Post-AI UI updates |
| `_on_clear_ai_results()` | 948-982 | Clear AI candidates dialog |

Uses `PdfProcessor.load_card_state_from_db()` (from Phase 2) and `RateLimitGate` (from Phase 1).

### Files
- **Create:** `app/gui/processing/ai_processor.py`
- **Modify:** `app/gui/main_window.py`
- **Tests:** No changes — delegation wrappers preserve test interface

### Verification
`make check && uv run pytest tests/ -x`

---

## Phase 4: Extract Rename Operations and Toolbar/Menu Construction (~280 lines)

### Group A: Rename → `app/gui/processing/rename_handler.py`

| Method | Lines |
|--------|-------|
| `_start_rename()` | 1546-1583 |
| `_remove_completed_results()` | 1586-1623 |

`_RESOLVED_MESSAGES` moves with `_remove_completed_results`.

### Group B: Toolbar/Menu → `app/gui/toolbar.py`

New class: `ToolbarManager` — builds toolbar and menu bar, manages tool/menu IDs.

| Method | Lines |
|--------|-------|
| `_setup_menu_bar()` | 264-373 |
| `_build_toolbar()` | 429-503 |
| `_enable_action_tools()` | 505-521 |
| `_refresh_toolbar_icons()` | 1665-1677 |
| `_on_update_action_menu()` | 1238-1265 |

**ID storage approach:** `ToolbarManager` writes tool/menu IDs directly onto `MainWindow` (e.g., `self._window._browse_id = ...`) to avoid updating every reference across MainWindow. This preserves all existing test access patterns like `window._toolbar.GetToolEnabled(window._reload_id)`.

### Files
- **Create:** `app/gui/processing/rename_handler.py`, `app/gui/toolbar.py`
- **Modify:** `app/gui/main_window.py`
- **Tests:** No changes expected

### Verification
`make check && uv run pytest tests/ -x`

---

## Summary

| Phase | Extracted | New Files | ~Lines Removed | main_window.py |
|-------|----------|-----------|---------------|----------------|
| 1 | Utilities + widgets | `drop_target.py` | 190 | ~1573 |
| 2 | PDF/OCR processing | `processing/pdf_processor.py` | 200 | ~1373 |
| 3 | AI batch processing | `processing/ai_processor.py` | 200 | ~1173 |
| 4 | Rename + toolbar | `processing/rename_handler.py`, `toolbar.py` | 280 | ~960 |

## Open Questions / Future Considerations

- Should `_reload_cards()` (100+ lines, very complex) move to `PdfProcessor` in Phase 2 or stay on MainWindow?
- Should filter pipeline methods (`_refresh_display`, `_apply_*_filters`) be extracted? They're tightly coupled to UI widgets.
- Should card interaction handlers (`_on_name_change`, `_on_remove_card`) be extracted?
- Test file `test_main_window.py` (2835 lines) may also need splitting after the refactor stabilizes.
- Re-export cleanup pass: once refactor is complete, update test imports to point to new locations and remove re-exports.

## Verification (after each phase)
1. `make check` — all static checks pass
2. `uv run pytest tests/ -x` — all tests pass
3. `uv run python main.py` — app launches, load cards, run AI, rename — no regressions
