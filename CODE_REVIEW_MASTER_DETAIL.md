# Code Review: wx_review_panel_master_detail.py

## 1. Magic Numbers / Constants Not Centralized

### Column Indices (HIGH PRIORITY)
**Lines 83, 113, 120, 122, 132, 431-433**
```python
# Current - magic numbers scattered throughout
def GetColumnCount(self): return 3
if col == 0:  # Confidence dot
elif col == 1:  # Filename
elif col == 2:  # Family name

# Should be:
class CardListModel:
    COL_DOT = 0
    COL_FILENAME = 1
    COL_FAMILY_NAME = 2
    COL_COUNT = 3
```

### UI Dimensions
**Lines 239, 248, 431-433, 450, 465**
```python
# Hardcoded values:
- Icon size: 9 (line 239)
- Button height: 28 (line 248)
- Column widths: 30, 280, 200 (lines 431-433)
- Min pane size: 100 (line 450)
- Height check: 100 (line 465)

# Should create constants or use existing Layout constants
```

### Confidence Symbols (HIGH PRIORITY)
**Lines 114-119**
```python
# Current - Unicode symbols hardcoded
if card.error: return "✕"
elif card.confidence == Confidence.NONE: return "⚠"
else: return "●"

# Should be centralized:
CONFIDENCE_SYMBOLS = {
    'error': "✕",
    'none': "⚠",
    'default': "●"
}
```

### Hardcoded Strings
**Lines 239, 255, 293, 298, 312, 318**
```python
- "#1D1D1F" - should use Color constant
- "Remove 'Family' from File Name" - UI string
- "Edit Card" - UI string
- Various candidate/placeholder strings
```

---

## 2. Repeated Code (Non-DRY)

### Card Lookup by ID (MEDIUM PRIORITY)
**Lines 66-68 vs 73-75**
```python
# Repeated enumeration pattern
for i, card in enumerate(self._cards):
    if card.id == card_id:
        # do something

# Should extract:
def _find_card_index(self, card_id: int) -> int | None:
    """Find index of card by ID."""
    for i, card in enumerate(self._cards):
        if card.id == card_id:
            return i
    return None
```

### Row Bounds Checking (MEDIUM PRIORITY)
**Lines 107-109 vs 135-137**
```python
# Repeated twice
row = self.ItemToObject(item)
if row < 0 or row >= len(self._cards):
    return ...

# Should extract:
def _get_card_from_item(self, item: dv.DataViewItem) -> CardResult | None:
    """Safely get card from DataViewItem."""
    row = self.ItemToObject(item)
    if 0 <= row < len(self._cards):
        return self._cards[row]
    return None
```

### Select First Card Logic (HIGH PRIORITY)
**Lines 591-596 vs 608-613**
```python
# Nearly identical in select_next_card() and select_prev_card()
if not current_item.IsOk():
    if self._model._cards:
        item = self._model.ObjectToItem(0)
        self._list_ctrl.Select(item)
        self._list_ctrl.EnsureVisible(item)
    return

# Should extract:
def _select_first_card(self):
    """Select first card if available."""
    if self._model._cards:
        item = self._model.ObjectToItem(0)
        self._list_ctrl.Select(item)
        self._list_ctrl.EnsureVisible(item)
```

### Enable/Disable Widget Logic (LOW PRIORITY)
**Lines 304-306 vs 314-321**
```python
# Repeated enable/disable patterns for same widgets
# Could extract to helper method
def _set_controls_enabled(self, enabled: bool):
    """Enable or disable all editing controls."""
    self._name_text.Enable(enabled)
    self._remove_family_check.Enable(enabled)
    self._candidates_choice.Enable(enabled)
    self._ai_btn.Enable(enabled)
```

---

## 3. Code Smells

### Unused Imports (HIGH PRIORITY)
**Lines 29-30**
```python
from typing import Callable, Optional  # Optional not used
from pathlib import Path  # Path not used
```

### Lazy Imports (MEDIUM PRIORITY)
**Lines 518, 527**
```python
# Database imports inside methods
def _handle_checkbox(self, card_id: int, new_value: bool):
    from app.core.database import update_remove_family  # BAD

def _handle_candidate(self, card_id: int, candidate_id: int):
    from app.core.database import select_candidate  # BAD

# Should be at top of file
```

### Dynamic Attribute Creation (MEDIUM PRIORITY)
**Line 287**
```python
# _candidate_map created in load_card(), not __init__
self._candidate_map = {}

# Should be initialized in __init__:
def __init__(self, ...):
    self._candidate_map: dict[str, int] = {}
```

### Unused Parameters (LOW PRIORITY)
**Line 622**
```python
def set_ai_button_state(self, card_id: int, state: str, text: str = "AI"):
    # 'text' parameter never used - remove or implement
```

### Complex Child Finding (MEDIUM PRIORITY)
**Lines 466-476**
```python
# Loops through children to find splitter
for child in self.GetChildren():
    if isinstance(child, wx.SplitterWindow):
        ...

# Should save reference in __init__:
self._splitter = wx.SplitterWindow(...)
```

### Long Chain of Conditionals (LOW PRIORITY)
**Lines 114-124, 141-157**
```python
# Multiple if/elif chains for confidence
if card.error: ...
elif card.confidence == Confidence.NONE: ...
elif card.confidence == Confidence.HIGH: ...
# etc.

# Consider dict mapping:
CONFIDENCE_COLORS = {
    (True, None): Color.ERROR,  # error=True
    (False, Confidence.NONE): Color.TEXT_SECONDARY,
    (False, Confidence.HIGH): Color.SUCCESS,
    # etc.
}
```

---

## 4. Un-Pythonic Code

### Private Attribute Access (HIGH PRIORITY)
**Lines 570, 593, 610, 627**
```python
# Accessing private attributes from outside class
self._model._card_order  # Line 570
self._model._cards  # Lines 593, 610
self._detail_panel._ai_btn  # Line 627

# Should provide public methods or properties:
@property
def card_order(self) -> list[int]:
    return self._card_order

def has_cards(self) -> bool:
    return len(self._cards) > 0
```

### List Building (LOW PRIORITY)
**Lines 92-93**
```python
# Current
for i in range(len(self._cards)):
    children.append(self.ObjectToItem(i))

# More Pythonic
children.extend(self.ObjectToItem(i) for i in range(len(self._cards)))
```

### Magic Numbers for Logic (MEDIUM PRIORITY)
**Line 351**
```python
if selection <= 0:  # Placeholder selected
    return

# Should use constant:
PLACEHOLDER_INDEX = 0
if selection <= PLACEHOLDER_INDEX:
```

---

## 5. Architectural Issues

### Separation of Concerns (HIGH PRIORITY)
**Lines 518-519, 527-549**
```python
# UI code directly calling database functions
from app.core.database import update_remove_family
update_remove_family(card.file_hash, new_value)

# Should use callback pattern or service layer
# Let the parent/controller handle database operations
```

### Direct Manipulation of Card Data (MEDIUM PRIORITY)
**Lines 329, 340, 532-535**
```python
# DetailPanel directly modifies CardResult objects
self._current_card.manual_override = new_name
self._current_card.remove_family = new_value
card.family_name = cand.family_name

# Should be immutable or use proper setters
# Or only modify through callbacks
```

---

## 6. Inconsistencies

### Callback Checking (LOW PRIORITY)
```python
# Some methods check callback before calling:
if self._on_name_change:
    self._on_name_change(...)

# Others just call:
self._on_select(card.id)  # Line 499

# Should be consistent
```

### Event Suppression (MEDIUM PRIORITY)
```python
# load_card() checks self._suppress_events
# But _on_ai() doesn't check it (line 362)
# Should be consistent across all event handlers
```

### Import Style (LOW PRIORITY)
```python
# Line 33: imports create_button but never uses it
# Line 34: uses load_sf_symbol
# Should remove unused imports
```

---

## 7. Documentation Issues

### Outdated Docstring (LOW PRIORITY)
**Line 1**
```python
"""Master-Detail Review Panel - Prototype.
# Should remove "Prototype" - this is production code
```

### Missing Type Hints (MEDIUM PRIORITY)
**Lines 85-86, 89-95, 97-103, etc.**
```python
# PyDataViewModel methods lack return type hints
def GetColumnType(self, col):  # -> str
def GetChildren(self, parent, children):  # -> int
```

---

## Priority Summary

### HIGH PRIORITY (Fix Now)
1. ✅ Define column index constants
2. ✅ Define confidence symbol constants
3. ✅ Extract repeated card lookup logic
4. ✅ Extract repeated "select first" logic
5. ✅ Remove unused imports
6. ✅ Fix private attribute access violations
7. ✅ Move database imports to top / remove DB coupling

### MEDIUM PRIORITY (Fix Soon)
1. Extract row bounds checking
2. Move lazy imports to top
3. Initialize _candidate_map in __init__
4. Save splitter reference instead of searching
5. Fix callback checking consistency
6. Add missing type hints

### LOW PRIORITY (Technical Debt)
1. Extract dimension constants
2. Extract UI string constants
3. Remove unused parameters
4. Use dict for confidence mapping
5. More Pythonic list building
6. Update docstring
7. Extract enable/disable helper
