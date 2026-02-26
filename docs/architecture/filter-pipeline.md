# Filter Pipeline

Cross-filtering, re-entrancy prevention, and auto-reset logic for the three-column layout.

**Key files:** `app/gui/main_window.py`, `app/gui/filter_sidebar.py`

## Layout Overview

```
┌──────────┬─────────────────┬──────────────┐
│ Sidebar  │  Review Panel   │   Preview    │
│          │  (master-detail)│   Panel      │
│ CONFID.  │                 │              │
│ ☑ All    │  DataViewCtrl   │   PDF page   │
│ ☐ Manual │  list + detail  │   images     │
│ ☐ High   │                 │              │
│ ☐ Review │                 │              │
│ ☐ Errors │                 │              │
│          │                 │              │
│ FOLDERS  │                 │              │
│ ☑ All    │                 │              │
│ ☐ dir_a  │                 │              │
│ ☐ dir_b  │                 │              │
└──────────┴─────────────────┴──────────────┘
```

## Filter Chain

Three independent filter axes are applied in sequence:

```
All cards (_cards_by_hash.values())
    │
    ├─ 1. Search filter  → _get_search_filtered_cards()
    │      Matches query against filename + family_name (case-insensitive)
    │
    ├─ 2. Folder filter  → _apply_folder_filters()
    │      "all_folders" = pass-through; else match card.file_paths parent dirs
    │
    └─ 3. Category filter → _apply_category_filters()
           "all" = pass-through; else match by Confidence enum values
           Sorted alphabetically by filename at the end
```

## Cross-Filtering Algorithm

Sidebar counts show how many cards **would** match each filter option given the other axis's current selection. This prevents misleading counts when both axes are active.

```
_refresh_display():
    search_cards = search-filtered cards

    # Cross-filtered counts:
    folder_filtered = apply_folder_filters(search_cards)   # for category counts
    category_filtered = apply_category_filters(search_cards) # for folder counts

    sidebar.update_category_counts(folder_filtered)   # counts reflect folder selection
    sidebar.update_folder_counts(category_filtered)    # counts reflect category selection
```

**Why:** If "High Confidence" is selected and folder A has 0 high-confidence cards, its count shows 0 and it gets disabled. Without cross-filtering, folder A would show its total card count, misleading the user.

## Re-Entrancy Prevention

`update_category_counts()` and `update_folder_counts()` may auto-reset internal sidebar state when all selected filters have zero count (e.g., user selected "High Confidence" but after folder filtering, no high cards remain).

The sidebar resets its own `_selected_*_filters` internally but does **not** fire callbacks. After count updates, `_refresh_display` syncs main window state from sidebar:

```python
# Sync filter state back (sidebar may have auto-reset)
self._current_category_filters = self._sidebar.get_selected_category_filters()
self._current_folder_filters = self._sidebar.get_selected_folder_filters()
```

This avoids re-entrant calls: sidebar mutates state silently, main window reads it once.

## Auto-Reset on Empty Display

After full filtering, if `display_cards` is empty but `search_cards` is non-empty, category checkboxes are reset to "All" while preserving folder selection and search text:

```python
if not display_cards and search_cards:
    self._current_category_filters = ["all"]
    self._sidebar.set_category_filters(["all"])
    # Recompute with reset filters...
```

This prevents the user from getting stuck with an empty list when the combination of filters produces no results.

## Finder-Style Click Behavior

Both category and folder sections share the same click logic (`_handle_check`):

| Action            | Behavior                                        |
|-------------------|-------------------------------------------------|
| Regular click     | Exclusive select (uncheck all others)           |
| Option+click      | Toggle multi-select (add/remove from selection) |
| Uncheck last item | Falls back to "All" automatically               |

## Debounce Timer

Manual name edits trigger `_on_name_change` which updates the card immediately but delays `_refresh_display` by 1 second via `_edit_debounce_timer`. Each keystroke restarts the timer. This prevents expensive filter recalculation on every character.

## Selection Preservation

`_refresh_display()` passes `preserve_selection=not self._has_active_filters()` to `load_cards()`. When no search, category filter, or folder filter is active, the previously selected card(s) are re-selected by ID after the list reloads. This prevents the user from losing their place when editing a card triggers a debounce refresh.

- **No filters active:** Selection is restored (card is guaranteed to be in the unfiltered list unless removed)
- **Filters active:** Selection clears (the card may have moved out of the filtered set, e.g., confidence changed from HIGH to MANUAL while filtering by HIGH)
- **Card removed:** Falls back to clearing selection
- **Multi-select:** All surviving cards are re-selected; detail panel clears (matches existing multi-select behavior)

`_has_active_filters()` checks: search text non-empty, category filter not "all", or folder filter not "all_folders".

## Gotchas

- **Tests must sync both axes:** When testing filters, set both `_current_category_filters` / `_current_folder_filters` on the main window AND call `sidebar.set_category_filters()` / `set_folder_filters()` to keep checkbox state aligned.
- **Sidebar counts disable checkboxes:** When a category/folder count hits 0, the checkbox is unchecked and disabled. The `_disabled_keys` set tracks these. If all selected keys become disabled, sidebar auto-resets to "All".
- **Folder section visibility:** Folder checkboxes only appear when cards come from 2+ distinct directories. `update_folders()` rebuilds from scratch (destroys and recreates checkboxes) and always resets to "all_folders".
- **Processing resets folders:** After `_processing_complete`, `update_folders()` is called first (creates checkboxes), then `_refresh_display()` populates counts. Must sync `_current_folder_filters` manually since `update_folders` doesn't fire callbacks.
