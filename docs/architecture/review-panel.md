# Review Panel (Master-Detail)

Mac-native master-detail pattern using DataViewCtrl for the card list.

**Key file:** `app/gui/components/review_panel.py`

## Layout

```
┌───────────────────────────────────┐
│ Cards                    12 cards │  ← Header with count
├───────────────────────────────────┤
│ ● │ filename.pdf    │ Smith       │  ← Master list (DataViewCtrl)
│ ● │ card2.pdf       │ Johnson     │     Col 0: confidence dot (colored)
│ ⚠ │ unknown.pdf     │             │     Col 1: filename (blue if multi-path)
│ ✕ │ corrupt.pdf     │             │     Col 2: family name
├───────────────────────────────────┤
│ [Edit Card] [File Paths (2)]      │  ← Detail panel (tabbed notebook)
│                                   │
│ Family Name: [____________]       │     Tab 1: Edit — name, candidates,
│ Alternative Candidates: [▾]       │            AI button, remove-family
│ [✨ AI Analyze]  ☐ Remove Family  │
│                                   │     Tab 2: File Paths — locations list
└───────────────────────────────────┘
```

## Class Hierarchy

```
ReviewPanelMasterDetail (wx.Panel)     ← Public API (drop-in for original)
├── CardListModel (PyDataViewModel)    ← Data model for DataViewCtrl
└── DetailPanel (wx.Panel)             ← Edit controls for selected card
    └── wx.Notebook
        ├── Edit tab (always)
        └── File Paths tab (added/removed per card)
```

Note: The drop overlay (`DropOverlay`) is defined in `app/gui/components/drop_target.py` and imported into `main_window.py` as `_DropOverlay`. It covers the entire content area below the toolbar when no cards are loaded.

## CardListModel (PyDataViewModel)

Wraps a flat `list[CardResult]` for display in DataViewCtrl.

| Method                     | Purpose                                                            |
|----------------------------|--------------------------------------------------------------------|
| `load_cards(cards)`        | Replace all data, notify via `Cleared()`                           |
| `get_card_by_item(item)`   | DataViewItem → CardResult                                          |
| `get_item_by_card_id(id)`  | Card ID → DataViewItem                                             |
| `update_card(id, card)`    | Update one card, notify via `ItemChanged()`                        |
| `GetValue(item, col)`      | Returns dot symbol (col 0), filename (col 1), display_name (col 2) |
| `GetAttr(item, col, attr)` | Sets dot color by confidence; blue filename for multi-path cards   |

## DetailPanel

Shows edit controls for the currently selected card. Key behaviors:

- **_suppress_events flag:** Set during `load_card()` and `clear()` to prevent event handlers from firing while programmatically updating controls.
- **Name editing:** Blocks filesystem-invalid characters via `_on_name_char`. Text changes fire `_on_name_edit` → parent's `on_name_change` callback.
- **Candidates dropdown:** First entry is a placeholder ("Select from N candidates"). Selection fires `_on_candidate_select` callback with the candidate's DB id.
- **File Paths tab:** Dynamically added/removed. Shows all `file_paths` for the card, with home-relative display paths.

## Callback Contract

ReviewPanelMasterDetail receives these callbacks from MainWindow:

| Callback                        | Triggered By                     | What Happens                              |
|---------------------------------|----------------------------------|-------------------------------------------|
| `on_select(card_id)`            | List selection change            | MainWindow updates preview panel          |
| `on_name_change(card_id, name)` | User types in name field         | MainWindow saves to DB, debounces refresh |
| `on_card_edited(card_id)`       | Candidate selected from dropdown | MainWindow calls `_refresh_display()`     |
| `on_ai_request(card_id)`        | AI button clicked                | MainWindow starts background AI analysis  |

**Important:** The panel does NOT write to the database directly (except `_handle_checkbox` for `remove_family` and `_handle_candidate` for `select_candidate`). The parent MainWindow handles most DB writes and card state updates, then calls `update_card()` back on the panel.

## Selection Reset

`load_cards()` resets selection to none by default, but accepts a `preserve_selection=False` keyword argument to retain the current selection (used after AI updates that shouldn't interrupt the user's focus):

```python
def load_cards(self, cards, *, preserve_selection=False):
    self._model.load_cards(cards)
    if not preserve_selection:
        self._list_ctrl.UnselectAll()
        self._selected_card_ids = []
        self._detail_panel.clear()
        self._on_select(None)
```

Without `preserve_selection`, any change to the displayed list (search, filter, remove, rename, processing) clears selection. The user must click a card to select it after any list change. `_refresh_display()` calls `load_cards()` for all list changes, making this the single funnel for selection reset.

## Public API

| Method                                      | Purpose                                         |
|---------------------------------------------|-------------------------------------------------|
| `load_cards(cards)`                         | Full reload, resets selection to none           |
| `get_cards()`                               | Return cards in display order                   |
| `update_card(card_id, card)`                | Update single card (after AI analysis)          |
| `select_next_card()` / `select_prev_card()` | Keyboard navigation (collapses multi-selection) |
| `select_all()` / `select_none()`            | Cmd+A / Cmd+Shift+A                             |
| `set_ai_button_state(card_id, enabled)`     | Enable/disable AI button (bool)                 |

## Drag Highlight

When files are dragged over the window while cards are loaded, `MainWindow` calls `set_drag_highlight(True)` on the review panel. This draws a rounded-rect border (`Layout.HIGHLIGHT_WIDTH` px, `Color.ACCENT`, `Layout.HIGHLIGHT_RADIUS` corner radius) inside the panel edges via `EVT_PAINT`. When the drag leaves, `set_drag_highlight(False)` clears the border.

The drop overlay (empty state) is defined in `app/gui/components/drop_target.py` and managed by `main_window.py`, not in this panel.

## Keyboard Selection

`_on_key` (bound to `EVT_CHAR_HOOK`) handles all keyboard navigation:

| Key                   | Action                                                       |
|-----------------------|--------------------------------------------------------------|
| Up / Down             | Move to prev/next card (collapses multi-selection to single) |
| Shift+Up / Shift+Down | Extend selection up/down (`_extend_selection_up/down`)       |
| Other keys            | Passed through via `event.Skip()`                            |

Cmd+A (Select All) and Cmd+Shift+A (Select None) are handled by MainWindow's Edit menu bindings, calling `select_all()` / `select_none()`. Cmd+Delete (Remove) is also an Edit menu item, handled by `_on_remove_menu` in MainWindow.

## Gotchas

- **Model uses row indices as objects:** `ObjectToItem(row_index)` and `ItemToObject(item)` → row index. This means card ordering must match between `_cards` list and `_card_order`.
- **Detail panel manages its own notebook tabs:** The File Paths tab is dynamically added/removed, tracked by `_locations_tab_index`. After removing it, the index is set to `None`.
- **Sash gravity 1.0:** The master list gets all extra vertical space. The detail panel gets its minimum height. Initial sash position is set in `_on_panel_size` after first layout.
