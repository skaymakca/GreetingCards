# MainWindow Mixin Architecture

## Overview

`MainWindow` (the primary application class) uses **four mixins** to keep related functionality grouped in navigable files while preserving a single runtime class. All mixins live in `app/gui/main_window_mixins/`.

```
app/gui/main_window_mixins/
    __init__.py            # re-exports all 4 mixin classes
    _protocol.py           # MainWindowProtocol — structural interface for self-typing
    filter_mixin.py        # Group D — search/filter (9 methods)
    selection_mixin.py     # Group F — card selection/editing (7 methods)
    ai_mixin.py            # Group B — AI batch analysis (8 methods)
    apple_events_mixin.py  # Group A — Apple Events scripting bridge (16 methods)
app/gui/main_window.py     # Core class: inherits all 4 mixins, ~850 lines remaining
```

## Class Declaration

```python
class MainWindow(FilterMixin, SelectionMixin, AppleEventsMixin, AIMixin):
    ...
```

Python's MRO (method resolution order) means `MainWindow` owns the `__init__` and core infrastructure methods. Mixin methods are inherited and accessed on `self` as if they were defined directly on `MainWindow`.

---

## Typing Mechanism: `MainWindowProtocol`

Each mixin method uses `self: MainWindowProtocol` as its first argument instead of the implicit `self`. This lets pyright and mypy understand what attributes and methods are available at runtime, without making the mixins inherit from `MainWindow` (which would create a circular dependency).

```python
class FilterMixin:
    def _refresh_display(self: MainWindowProtocol) -> None:
        self._sidebar.update_category_counts(...)  # Pyright knows _sidebar exists
```

`MainWindowProtocol` (in `_protocol.py`) is a `typing.Protocol` that lists every attribute and method that mixins depend on. It has three categories:

1. **Attributes** — state owned by `MainWindow.__init__` (e.g. `_card_store`, `_card_service`, `_frame`, `_sidebar`)
2. **Core methods** — infrastructure that stays in `main_window.py` (e.g. `_set_empty_state`, `_start_processing`)
3. **Cross-mixin calls** — methods defined in one mixin but called by another (e.g. `_refresh_display` defined in `FilterMixin`, called by `SelectionMixin` and `AIMixin`)

### Why not plain `self`?

Using plain `self` would require each mixin to inherit from `MainWindow`, creating circular imports. Using `Protocol` keeps the typing lightweight and the dependency graph clean.

### Properties in mixins

Properties require `# type: ignore[misc]` on the decorator because pyright doesn't support `Protocol`-typed `self` on properties:

```python
@property
def is_processing(self: MainWindowProtocol) -> bool:  # type: ignore[misc]
    return bool(self._processing_files) ...
```

---

## Mixin Groups

### FilterMixin (`filter_mixin.py`) — Group D

Search field and sidebar filter logic.

| Method | Purpose |
|--------|---------|
| `_on_search_text` | Calls `_refresh_display` on every keystroke |
| `_on_search_cancel` | Clears search field and refreshes |
| `_on_category_filter_change` | Updates `_current_category_filters`, refreshes |
| `_on_folder_filter_change` | Updates `_current_folder_filters`, refreshes |
| `_refresh_display` | Cross-filtered pipeline: search → folder → category → UI update |
| `_has_active_filters` | Returns True when any filter is narrowing the view |
| `_get_search_filtered_cards` | Applies text search query |
| `_apply_folder_filters` | Applies folder sidebar filters to a card list |
| `_apply_category_filters` | Applies confidence/category sidebar filters |

`_refresh_display` is the central method that coordinates the cross-filter pipeline (see `filter-pipeline.md`).

### SelectionMixin (`selection_mixin.py`) — Group F

Card selection, name edits, card removal, and review panel callbacks. Delegates mutations to `CardService`.

| Method | Purpose |
|--------|---------|
| `_on_card_select` | Updates preview panel when a card is selected |
| `_on_name_change` | Delegates to `CardService.set_name()` + debounce timer |
| `_on_checkbox_toggle` | Callback from review panel — delegates to `CardService.set_remove_family()` |
| `_on_candidate_select` | Callback from review panel — delegates to `CardService.select_candidate()` |
| `_on_card_edited` | Handles discrete edits (e.g. candidate selection) |
| `_on_remove_card` | Removes a card via `CardStore` (non-destructive, no file deletion) |
| `_on_remove_menu` | Removes all selected cards (Edit > Remove) |
| `_on_update_remove_menu` | Enables/disables the Remove menu item |
| `_on_edit_debounce_fire` | Fires after 1-second idle to refresh sidebar counts |

### AIMixin (`ai_mixin.py`) — Group B

AI batch analysis workflow.

| Method | Purpose |
|--------|---------|
| `_on_clear_ai_results` | Prompts + delegates to `CardService.clear_ai_results()` |
| `_ensure_api_key` | Checks for API key, shows dialog if missing |
| `_get_target_cards` | Returns (cards, scope) based on selection state |
| `_on_ai_request` | Handles single-card AI button click (uses `CardService.is_ai_eligible`) |
| `_get_action_menu_label` | Builds dynamic menu label like "AI Analyze Selected (3)\tCtrl+Shift+I" |
| `_start_ai_all` | Entry point: validates, locks UI, starts background thread |
| `_run_ai_all` | Runs `run_ai_batch_async` on the background thread |
| `_update_ai_all_progress` | Progress callback (called via `wx.CallAfter`) |
| `_ai_all_complete` | Completion callback: unlocks UI, shows errors or success |

### AppleEventsMixin (`apple_events_mixin.py`) — Group A

Scripting bridge called from `app/core/apple_events.py` on the main thread.
Provides 2 properties (`is_processing`, `is_ai_running`) and 14 bridge methods.
Delegates mutations to `CardService` and queries to `CardStore`.

See [`docs/architecture/apple-events.md`](apple-events.md) for the full command
reference, JSON schemas, threading details, and test coverage breakdown.

---

## Test Patching

Tests must patch at the module where the function is **imported** (looked up at call time):

```python
# ✅ DB functions used by CardService — patch at card_service module level
patch("app.core.services.card_service.set_manual_name")
patch("app.core.services.card_service.select_candidate")
patch("app.core.services.card_service.update_remove_family")
patch("app.core.services.card_service.clear_ai_results")
patch("app.core.services.card_service.load_card_state_from_db")

# ✅ Functions imported directly by mixin modules
patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key")

# ✅ wx symbols — wx is the global module object
patch("app.gui.main_window.wx.MessageBox")

# ✅ Functions that stay in main_window.py
patch("app.gui.main_window.scan_for_pdfs")    # used by _load_paths
patch("app.gui.main_window.build_rename_plan")
patch("app.gui.main_window.RenameConfirmDialog")
```

**Key change:** Mixins no longer import DB functions directly. Instead they delegate to `self._card_service`, which imports the DB functions in `app/core/services/card_service.py`. Patches for DB operations must target `app.core.services.card_service.*`, not the mixin modules. Similarly, `load_paths_for_script` now delegates to `_load_paths` in `main_window.py`, so `scan_for_pdfs` patches target `app.gui.main_window`, not the apple events mixin.

---

## What Stays in `main_window.py`

The following groups remain in `app/gui/main_window.py` (~850 lines):

- `__init__` — creates `CardStore`, `CardService`, all widgets/state
- UI builders: `_build_ui`, `_build_content_area`, `_build_progress_strip`
- Progress strip management: `_show_progress_strip`, `_update_progress_strip`, `_hide_progress_strip`
- Drop target: `_setup_drop_target`, `_on_drop`, `_on_drag_over`, `_on_drag_leave`
- File loading: `_load_paths` (returns count), `_clear_all`, `_unlink_path`, `_reload_cards` (returns bool), `_get_year` (delegates state ops to `CardStore`)
- OCR processing: `_start_processing`, `_process_cards`, `_processing_complete` (delegates dedup to `CardStore.add_or_update`)
- Folder refresh: `_refresh_folders` — updates sidebar folders, syncs filter state, and refreshes display (replaces 3 inline occurrences)
- Rename workflow: `_start_rename`, `_remove_completed_results` (delegates path updates to `CardStore`)
- Dark mode: `_on_appearance_changed`, `_refresh_toolbar_icons`
- Keyboard/close handlers: `_on_key_press`, `_on_frame_activate`, `_on_close`
- `run()` — main event loop entry point
