# Refactor main_window.py into Smaller Modules

## Context

`app/gui/main_window.py` is **1828 lines** with 58 methods spanning 9+ responsibilities. The `app/gui/` directory is flat (17 files, no subdirectories). Goal: reduce to ~960 lines across 5 phased commits, extracting GUI-free logic to `app/core/` and organizing `app/gui/` into semantic subpackages.

**Current state:** No phases implemented yet. Progress strip replaced modal dialog (new methods at lines 435-488). `_has_active_filters()` added at 654. `app/core/family_name/` subpackage validates the extraction pattern.

## Parallelization Strategy

- Phases 2, 3, 4 all modify `main_window.py` → **must be sequential** (merge conflicts)
- **Within each phase:** creating new modules + their tests can run in parallel; modifying main_window.py follows
- **Phase 1:** all 10 file moves + shim creation in one batch
- **Phase 5:** combines old Phases 5+6 (shim removal + test restructure) — shim removal and test moves can run in parallel

---

## Phase 1: Extract Standalone Utilities + Establish Subpackages (~195 lines)

### Extract from main_window.py

| What | Lines | To |
|------|-------|----|
| `_RateLimitGate` class | 44-63 | `app/core/rate_limit.py` → rename `RateLimitGate` |
| `_plural()` | 65-68 | `app/gui/utils.py` |
| `_load_drop_background()` | 70-100 | `app/gui/components/drop_target.py` |
| `_DropOverlay` class | 102-199 | `app/gui/components/drop_target.py` |
| `FileDropTarget` class | 1795-1828 | `app/gui/components/drop_target.py` |

### Move existing files into subpackages

| File | Destination |
|------|-------------|
| `filter_sidebar.py` | `components/filter_sidebar.py` |
| `review_panel.py` | `components/review_panel.py` |
| `preview_panel.py` | `components/preview_panel.py` |
| `html_viewer.py` | `components/html_viewer.py` |
| `api_key_dialog.py` | `dialogs/api_key.py` |
| `changelog_dialog.py` | `dialogs/changelog.py` |
| `dialogs.py` | `dialogs/common.py` |
| `help_dialog.py` | `dialogs/help.py` |
| `licenses_dialog.py` | `dialogs/licenses.py` |
| `settings_dialog.py` | `dialogs/settings.py` |

Each old location gets a one-line re-export shim. Removed in Phase 5.

### Parallel execution within Phase 1

```
Step 1 (parallel file creation):
  - app/gui/components/__init__.py
  - app/gui/dialogs/__init__.py
  - app/core/rate_limit.py
  - app/gui/components/drop_target.py
  - Add plural() to app/gui/utils.py

Step 2 (batch):
  - git mv all 10 files + create 10 shim files

Step 3 (sequential):
  - Modify main_window.py (remove extracted code, add re-imports)
  - Move RateLimitGate tests → tests/core/test_rate_limit.py
  - Update docs/architecture/async-processing.md
```

### Verification: `make check && uv run pytest tests/ -x`

---

## Phase 2: Extract PDF/OCR Processing (~200 lines)

### New: `app/core/card_processor.py`

| Method | Lines | New name |
|--------|-------|----------|
| `_scan_for_pdfs()` | 825-841 | `scan_for_pdfs()` |
| `_worker_result_to_card()` | 1137-1172 | `worker_result_to_card()` |
| `_derive_folders()` | 1178-1180 | `derive_folders()` |
| `_load_card_state_from_db()` | 1393-1429 | `load_card_state_from_db()` |
| Dedup logic from `_process_cards()` | 1106-1130 | `CardStore.ingest_result()` |

**Stays on MainWindow:** `_start_processing()`, `_process_cards()` (thread + wx.CallAfter), `_update_processing_progress()`, `_processing_complete()`, `_load_paths()`

### Parallel: Create `card_processor.py` + `test_card_processor.py` in parallel, then modify main_window.py

### Verification: `make check && uv run pytest tests/ -x`

---

## Phase 3: Extract AI Batch Processing (~200 lines)

### New: `app/core/ai_batch.py`

| Method | Lines | New name |
|--------|-------|----------|
| `_run_ai_all_async()` core logic | 1483-1575 | `run_ai_batch_async()` — takes progress callback |

Uses `RateLimitGate` from Phase 1. No wx imports.

**Stays on MainWindow:** `_ensure_api_key()`, `_get_target_cards()`, `_on_ai_request()`, `_start_ai_all()`, `_run_ai_all()`, `_update_ai_all_progress()`, `_ai_all_complete()`, `_on_clear_ai_results()`

### Parallel: Create `ai_batch.py` + `test_ai_batch.py` in parallel, then modify main_window.py

### Verification: `make check && uv run pytest tests/ -x`

---

## Phase 4: Extract Rename + Toolbar (~280 lines)

### Group A: `app/core/rename_executor.py`

| What | Lines |
|------|-------|
| `_remove_completed_results()` filtering logic | 1648-1685 → `filter_completed_renames()` |
| `_RESOLVED_MESSAGES` | 41 |

### Group B: `app/gui/components/toolbar.py` → `ToolbarManager` class

| Method | Lines |
|--------|-------|
| `_setup_menu_bar()` | 264-373 |
| `_build_toolbar()` | 490-564 |
| `_enable_action_tools()` | 566-582 |
| `_refresh_toolbar_icons()` | 1730-1744 |
| `_on_update_action_menu()` | 1304-1331 |

ToolbarManager writes IDs directly onto MainWindow to preserve test access patterns.

### Parallel: Create both new modules + tests in parallel, then modify main_window.py

### Verification: `make check && uv run pytest tests/ -x`

---

## Phase 5: Remove Shims + Restructure Tests + Coverage

Combined cleanup — no functional changes.

### Part A + B (parallel agents):
- **Agent 1:** Remove 10 shim files, update all imports in `app/` to canonical paths
- **Agent 2:** Move test files to mirror new `app/gui/` structure:
  - `tests/gui/components/` — test_filter_sidebar, test_review_panel, test_preview_panel, test_html_viewer, test_drop_target, test_toolbar, test_cursors, test_preview_cursor_behavior
  - `tests/gui/dialogs/` — test_api_key, test_changelog, test_common, test_help, test_licenses, test_settings

### Part C (after A+B): Split `test_main_window.py` (2879 lines) — keep only orchestration tests

### Part D (after C): Coverage analysis → fill gaps in extracted modules

### Verification: `make check && uv run pytest tests/ -x --cov=app` + update test count in README.md

---

## Summary

| Phase | What | main_window.py |
|-------|------|----------------|
| 1 | Utilities + widgets + subpackages | ~1633 lines |
| 2 | PDF/OCR processing → core | ~1433 lines |
| 3 | AI batch → core | ~1233 lines |
| 4 | Rename + toolbar | ~960 lines |
| 5 | Shims + test restructure + coverage | ~940 lines |

## What stays on MainWindow (not extracted)

- Progress strip methods (`_build/_show/_update/_hide_progress_strip`, 53 lines) — pure UI, tightly coupled to panel layout
- `_reload_cards()` (95 lines, 921-1015) — straddles GUI/core boundary
- Filter methods (`_refresh_display`, `_apply_*_filters`, `_has_active_filters`) — coupled to UI widgets
- Card interaction handlers (`_on_name_change`, `_on_remove_card`, `_on_card_edited`)

## Critical files

- `app/gui/main_window.py` (1828 lines) — modified in every phase
- `tests/gui/test_main_window.py` (2879 lines) — split in Phase 5
- `app/gui/utils.py` — receives `_plural()` in Phase 1
- `docs/architecture/async-processing.md` — update when RateLimitGate moves
