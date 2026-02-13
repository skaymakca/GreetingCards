# wxPython Migration Plan

**Status:** In Progress
**Current Phase:** Phase 6 - Review Panel (COMPLETE)
**Branch:** `wx`
**Start Date:** 2026-02-13

---

## Overview

Migrating Greeting Cards App from tkinter to wxPython for better native macOS integration, modern APIs, and improved maintainability.

**Total GUI Code:** 2,722 lines across 9 files
**Estimated Duration:** 28 days (4 weeks)
**Strategy:** Incremental bottom-up migration

---

## Phase 1: Setup & Foundation (Days 1-2)

**Goal:** Get wxPython running alongside tkinter

### Tasks
- [x] Install wxPython: `pip install wxPython`
- [x] Create `app/gui/wx_styles.py`
  - [x] Port `Color` class to wx.Colour
  - [x] Port `Font` class to wx.Font factory methods
  - [x] Port `Layout` class dimensions
- [x] Create `app/gui/wx_utils.py`
  - [x] PIL → wx.Bitmap conversion helper
  - [x] Hex color → wx.Colour helper
  - [x] Common widget factory functions
- [x] Create `main_wx.py` test harness
- [x] Verify wxPython runs on macOS

---

## Phase 2: Simple Dialogs (Days 3-4)

**Goal:** Migrate standalone dialogs

### Tasks
- [x] Migrate `api_key_dialog.py` → `app/gui/wx_api_key_dialog.py`
  - [x] wx.Dialog with wx.TextCtrl (password mode)
  - [x] OK/Cancel buttons
  - [x] Test standalone
- [x] Create `app/gui/wx_dialogs.py`
- [x] Migrate `ProgressDialog`
  - [x] Use wx.ProgressDialog or custom wx.Gauge
  - [x] Test with mock progress updates
- [x] Migrate `CompletionDialog`
  - [x] wx.Dialog with wx.ListCtrl
  - [x] Test with mock rename results

---

## Phase 3: Complex Dialogs (Days 5-7) ✅ COMPLETE

### Tasks
- [x] Migrate `help_dialog.py` → `app/gui/wx_help_dialog.py`
  - [x] wx.html.HtmlWindow with native HTML rendering
  - [x] Format help text as HTML
  - [x] Test scrolling
- [x] Migrate `settings_dialog.py` → `app/gui/wx_settings_dialog.py`
  - [x] Single dialog with About/API Key/Database sections
  - [x] API key input and validation
  - [x] Version display with git commit hash
  - [x] Database rebuild functionality
- [x] Migrate `RenameConfirmDialog`
  - [x] wx.dataview.DataViewCtrl with custom TableModel
  - [x] Color-coded status rows using GetAttr()
  - [x] Test with mock rename plan
- [x] Migrate `ErrorListDialog`
  - [x] DataViewCtrl with TableModel (consistent with RenameConfirm)
  - [x] Test with mock errors
- [x] Update `CompletionDialog` to match RenameConfirmDialog style
  - [x] Converted from ListCtrl to DataViewCtrl
  - [x] Same layout pattern as other dialogs
- [x] **Bonus:** Mac-native alignment
  - [x] Consistent 20px left margins throughout all dialogs
  - [x] Use AddSpacer() for explicit vertical spacing
  - [x] Remove panel wrappers, use system backgrounds
- [x] **Bonus:** TableModel utility tests
  - [x] Comprehensive test coverage (25 tests)
  - [x] All PyDataViewModel methods tested

---

## Phase 4: Context Menu & Icons (Day 8) ✅ COMPLETE

### Tasks
- [x] Create `app/gui/wx_icons.py`
  - [x] Adapt SF Symbol loader to return wx.Bitmap instead of PhotoImage
  - [x] PNG byte stream → wx.Image → wx.Bitmap conversion
  - [x] Retina/@2x display support (automatic scaling)
  - [x] Same PyObjC backend, caching, and graceful fallback
- [x] Create `app/gui/wx_context_menu.py`
  - [x] wx.Menu with Cut/Copy/Paste/Title Case/Clear
  - [x] SF Symbol icons in menu items (using load_sf_symbol)
  - [x] Bind to wx.EVT_CONTEXT_MENU
  - [x] Fixed accelerator format (Cmd+X instead of ⌘X)
  - [x] Test on TextCtrl in dialogs
- [x] **Bonus:** Comprehensive test coverage
  - [x] 28 tests for wx_icons.py (Level 1, 2, and 3)
    - [x] SF Symbol loading and caching
    - [x] Color handling
    - [x] Edge cases
    - [x] Integration tests (icons in dialogs)
  - [x] 19 tests for wx_context_menu.py (Level 1, 2, and 3)
    - [x] Context menu setup and icon loading
    - [x] Clipboard operations (Cut/Copy/Paste)
    - [x] Text transformations (Title Case/Clear)
    - [x] Edge cases (Unicode, long text, multiple controls)
    - [x] Integration tests (context menu in dialogs)
- [x] **Total:** 47 tests, all passing

---

## Phase 5: Preview Panel (Days 9-11) ✅ COMPLETE

**Goal:** Image viewer with zoom and pan

### Tasks
- [x] Create `app/gui/wx_preview_panel.py`
- [x] Basic image display
  - [x] wx.Panel with custom painting (EVT_PAINT with wx.PaintDC)
  - [x] PIL Image → wx.Bitmap conversion using wx_utils
  - [x] Placeholder text when no images loaded
  - [x] Error message display with warning icon
- [x] Zoom functionality
  - [x] Mouse wheel zoom (wx.EVT_MOUSEWHEEL)
  - [x] Zoom in/out/fit buttons
  - [x] Intelligent fit mode (scales to canvas, max 1:1)
  - [x] Zoom percentage label
  - [x] Min/Max zoom limits (0.1x to 10x)
  - [x] Modifier key zoom (Shift+Click, Ctrl/Cmd+Click)
- [x] Pan functionality
  - [x] Click and drag (wx.EVT_LEFT_DOWN, wx.EVT_MOTION)
  - [x] Manual offset tracking with bitmap caching
  - [x] Cursor changes (sizing cursor during drag)
- [x] Navigation toolbar
  - [x] Previous/Next page buttons
  - [x] Page counter display (1 / 3 format)
  - [x] Smart button enable/disable based on page bounds
- [x] Multi-page support
  - [x] Show_images() accepts list of PIL Images
  - [x] Page navigation resets zoom and pan
  - [x] Backward-compatible show_image() for single image
- [x] Comprehensive test suite
  - [x] 26 unit tests (Level 1: initialization, state, controls)
  - [x] Integration tests (Level 2: zoom, pan, navigation)
  - [x] UI integration tests (Level 3: dialogs, multi-page)
  - [x] All tests passing
- [x] Test harness integration
  - [x] Added Preview Panel Test button to main_wx.py
  - [x] Sample image generators (single and multi-page)
  - [x] Error display test

**Architecture:**
- wx.Panel with EVT_PAINT for custom drawing (not wx.StaticBitmap)
- Bitmap caching for performance (render once per zoom/pan change)
- Paint approach for placeholder/error (cleaner than fixed positioning)
- Full control over image positioning with pan offsets
- Public API matches tkinter version exactly for drop-in replacement

---

## Phase 6: Review Panel (Days 12-15) ✅ COMPLETE

**Goal:** Card list with editing controls

**Decision:** Pivoted from scrollable rows to master-detail pattern (Mac-native Mail.app / Finder style)

### Tasks
- [x] Create `app/gui/wx_review_panel_master_detail.py`
- [x] Choose implementation approach
  - [x] Research: Scrollable ReviewRow panels vs Master-Detail pattern
  - [x] Decision: Master-Detail with wx.dataview.DataViewCtrl (Mac-native NSTableView)
  - [x] Rationale: Better macOS integration, cleaner architecture, easier to test
- [x] Implement `CardListModel` (PyDataViewModel)
  - [x] 3 columns: confidence dot (●/⚠/✕), filename, family name
  - [x] Color-coded rows based on confidence level
  - [x] Notification methods for external updates
- [x] Implement `DetailPanel` (Edit controls for selected card)
  - [x] Name text input with live editing
  - [x] "Remove 'Family' from File Name" checkbox
  - [x] Candidate dropdown with placeholder
  - [x] AI button with SF Symbol icon (sparkles, 9pt, 28px height)
- [x] Implement `ReviewPanelMasterDetail` (SplitterWindow layout)
  - [x] Master (top): DataViewCtrl with card list
  - [x] Detail (bottom): Edit controls for selected card
  - [x] SetSashGravity(1.0) to give space to master list
- [x] Selection handling
  - [x] Click to select card
  - [x] Keyboard navigation (up/down arrows)
  - [x] Auto-scroll to selection
  - [x] Update detail panel on selection
- [x] Event callbacks
  - [x] on_select: Card selected in list
  - [x] on_name_change: Name edited manually
  - [x] on_remove_family_change: Checkbox toggled
  - [x] on_candidate_select: Candidate chosen from dropdown
  - [x] on_ai_generate: AI button clicked
- [x] Public API matches original ReviewPanel
  - [x] Drop-in replacement (same method signatures)
  - [x] Backward-compatible for main window integration
- [x] Comprehensive test suite
  - [x] 61 tests for master-detail panel
  - [x] CardListModel tests (22): columns, values, colors, updates
  - [x] ReviewPanelMasterDetail tests (39): initialization, selection, navigation, callbacks
  - [x] DetailPanel tests (5): candidates, controls, AI button
  - [x] Edge cases (5): empty list, invalid selection, state transitions
  - [x] All tests passing
- [x] Remove old scrollable implementation
  - [x] Deleted `app/gui/wx_review_panel.py`
  - [x] Deleted `tests/gui/test_wx_review_panel.py` (47 old tests)
  - [x] Removed test button from main_wx.py
- [x] Code quality review
  - [x] Created `CODE_REVIEW_MASTER_DETAIL.md`
  - [x] Documented magic numbers, code smells, DRY violations
  - [x] Deferred refactoring until app completion

**Architecture:**
- **Master-Detail Pattern** (Mac-native, like Mail.app)
- **DataViewCtrl** (uses NSTableView on macOS) for performant native list
- **PyDataViewModel** for custom data source (no widget creation per row)
- **Single DetailPanel** (edit one card at a time, cleaner than 100+ controls)
- **SplitterWindow** for resizable master/detail split
- **Callback-based** (parent/controller pattern, UI doesn't call database directly)

**Why Master-Detail?**
- Native macOS pattern (Mail, Finder, System Preferences)
- More performant (one set of controls vs N*6 widgets per card)
- Easier to test (mock data model, verify callbacks)
- Better separation of concerns (CardListModel vs DetailPanel)
- Cleaner architecture (no dynamic widget creation)

**Button Sizing Notes:**
- AI button: 9pt SF Symbol icon, 28px height for proper scaling
- Testing progression: 12pt→16pt→11pt→9pt to find native-looking size

---

## Phase 7: Main Window (Days 16-20)

**Goal:** Tie everything together

### Tasks
- [ ] Create `app/gui/wx_main_window.py`
- [ ] Main window structure
  - [ ] wx.Frame as application window
  - [ ] Set window size and title
- [ ] Menu bar
  - [ ] wx.MenuBar for native macOS menus
  - [ ] File menu: Open Folder, Exit
  - [ ] Help menu: Show Help, About
  - [ ] Bind menu events
- [ ] Toolbar
  - [ ] Folder picker button
  - [ ] Year text input
  - [ ] Process, Rename, Clear buttons
  - [ ] Layout with wx.BoxSizer
- [ ] Split layout
  - [ ] wx.SplitterWindow for preview/review split
  - [ ] Add wx_preview_panel to left
  - [ ] Add wx_review_panel to right
  - [ ] Set sash position
- [ ] Drag-and-drop
  - [ ] Create wx.FileDropTarget
  - [ ] Handle folder drops
  - [ ] Handle file drops
  - [ ] Parse macOS path format
- [ ] State management
  - [ ] Load cards from folder
  - [ ] Track current selection
  - [ ] Update preview on selection
- [ ] Async operations
  - [ ] Keep current threading model
  - [ ] wx.CallAfter for UI updates from threads
  - [ ] Progress dialogs during processing
- [ ] Integration testing
  - [ ] Full workflow: load → process → review → rename
  - [ ] Test all button actions
  - [ ] Test keyboard shortcuts

**Challenges:**
- Coordinating preview and review panel state
- Thread-safe UI updates
- Drag-and-drop edge cases
- State synchronization

---

## Phase 8: Integration & Polish (Days 21-25)

### Tasks
- [ ] Keyboard shortcuts
  - [ ] wx.AcceleratorTable setup
  - [ ] Cmd+O: Open folder
  - [ ] Cmd+Q: Quit
  - [ ] Arrow keys: Navigate cards
  - [ ] Return: Focus next field
- [ ] Native macOS integration
  - [ ] Verify menu bar is native (not in window)
  - [ ] Test with macOS dark mode
  - [ ] Verify Retina/high-DPI rendering
  - [ ] Test full-screen mode
- [ ] Drag-and-drop refinement
  - [ ] Test with spaces in paths
  - [ ] Test with multiple folder drops
  - [ ] Error handling for invalid paths
  - [ ] Permission errors
- [ ] Error handling
  - [ ] Replace all tk.messagebox with wx.MessageBox
  - [ ] Test error dialogs
  - [ ] Verify error messages are clear
- [ ] Styling consistency
  - [ ] Verify colors match in light mode
  - [ ] Verify colors match in dark mode
  - [ ] Check font sizes and spacing
  - [ ] Test window resizing behavior
- [ ] Performance testing
  - [ ] Test with 100+ cards
  - [ ] Memory profiling (PIL images)
  - [ ] Identify bottlenecks
  - [ ] Optimize if needed

---

## Phase 9: PyInstaller Bundle (Days 26-27)

### Tasks
- [ ] Update `Greeting Cards.spec`
  - [ ] Add wxPython to hiddenimports
  - [ ] Add wx hooks if needed
  - [ ] Bundle wx resources
  - [ ] Update imports list
- [ ] Build .app bundle
  - [ ] Run `make build`
  - [ ] Verify bundle builds successfully
- [ ] Test .app bundle
  - [ ] Launch from Finder
  - [ ] Test all features in bundled app
  - [ ] Verify icon displays
  - [ ] Check for missing dependencies
  - [ ] Test on fresh user account
- [ ] Code signing
  - [ ] Ad-hoc signing for local use
  - [ ] (Optional) Developer ID for distribution
- [ ] Notarization (if distributing)

**Challenges:**
- wxPython bundling quirks
- Missing resources or dependencies
- Code signing issues

---

## Phase 10: Cleanup & Documentation (Day 28)

### Tasks
- [ ] Remove tkinter code
  - [ ] Delete `app/gui/main_window.py` (old)
  - [ ] Delete `app/gui/preview_panel.py` (old)
  - [ ] Delete `app/gui/review_panel.py` (old)
  - [ ] Delete all old dialog files
  - [ ] Delete `app/gui/context_menu.py` (old)
- [ ] Rename wx files
  - [ ] `wx_main_window.py` → `main_window.py`
  - [ ] `wx_preview_panel.py` → `preview_panel.py`
  - [ ] `wx_review_panel.py` → `review_panel.py`
  - [ ] `wx_dialogs.py` → `dialogs.py`
  - [ ] `wx_styles.py` → `styles.py`
  - [ ] Update all imports
- [ ] Remove tkinter dependencies
  - [ ] Remove `tkinter` from imports
  - [ ] Remove `tkinterdnd2` from requirements
  - [ ] Update `requirements.txt`
- [ ] Update `main.py`
  - [ ] Import from wx modules
  - [ ] Test final version
- [ ] Documentation
  - [ ] Update README with wxPython info
  - [ ] Note Python and wxPython versions
  - [ ] Update screenshots if needed
- [ ] Final testing
  - [ ] Complete workflow test
  - [ ] Test .app bundle
  - [ ] Verify no regressions
- [ ] Merge to main
  - [ ] Commit all changes on wx branch
  - [ ] Test thoroughly
  - [ ] Merge wx → main
  - [ ] Tag new version
  - [ ] Push to remote

---

## Key Differences: tkinter → wxPython

| Feature | tkinter | wxPython |
|---------|---------|----------|
| Widgets | `tk.Frame`, `ttk.Button` | `wx.Panel`, `wx.Button` |
| Layout | `pack()`, `grid()`, `place()` | `wx.BoxSizer`, `wx.GridSizer` |
| Events | `bind("<Button-1>", ...)` | `Bind(wx.EVT_LEFT_DOWN, ...)` |
| Dialogs | `messagebox.showinfo(...)` | `wx.MessageBox(...)` |
| Images | `PhotoImage`, `ImageTk.PhotoImage` | `wx.Bitmap`, `wx.Image` |
| Canvas | `tk.Canvas` | `wx.DC`, `wx.GraphicsContext` |
| Menus | `tk.Menu` | `wx.MenuBar`, `wx.Menu` |
| Styles | `ttk.Style().configure()` | Native or `wx.SystemSettings` |

---

## Risk Mitigation

- ✅ **Business logic untouched** - All `app/core/*` stays the same
- ✅ **Parallel development** - Keep both tk and wx versions working
- ✅ **Incremental testing** - Test each phase before proceeding
- ✅ **Rollback plan** - wx branch can be abandoned if needed
- ✅ **Version control** - Git tracks all changes

---

## Why wxPython?

- ✅ Modern & actively maintained
- ✅ True native widgets on macOS
- ✅ Better APIs, more Pythonic
- ✅ Rich widget set (Grid, HTML viewer, etc.)
- ✅ Comprehensive documentation
- ✅ Built-in high-DPI/Retina support
- ✅ Used by professional apps (Blender, Audacity)

---

## Progress Log

### 2026-02-13
- Created migration plan
- Created wx branch
- **Phase 1 Complete:**
  - Installed wxPython 4.2.5
  - Created `wx_styles.py` (Color, Font factory methods, Layout)
  - Created `wx_utils.py` (PIL conversion, color helpers, widget factories, dialogs)
  - Created `main_wx.py` test harness
  - Verified wxPython working on macOS
  - Note: Font class uses factory methods to avoid wx.App requirement at import time
- **Phase 2 Complete:**
  - Migrated API Key Dialog with password input
  - Migrated Progress Dialog with wx.Gauge
  - Migrated Completion Dialog with wx.ListCtrl (later upgraded to DataViewCtrl)
  - Added test buttons to main_wx.py harness
  - Built and tested app bundle versions
- **Phase 3 Complete:**
  - Created `wx_help_dialog.py` using wx.html.HtmlWindow for native HTML rendering
  - Created `wx_settings_dialog.py` with About, API Key, and Database sections
  - Implemented `TableModel` class (PyDataViewModel) for colored table rows
  - Created `RenameConfirmDialog` using DataViewCtrl with colored status rows
  - Created `ErrorListDialog` using DataViewCtrl pattern
  - Refactored `CompletionDialog` to match RenameConfirm style
  - Applied Mac-native alignment: consistent 20px margins, AddSpacer() for spacing
  - Created comprehensive tests for TableModel (25 tests, all passing)
  - All 112 tests passing (46 core + 25 TableModel + 41 other GUI)
  - Created CLAUDE.md with project instructions
- **Phase 4 Complete:**
  - Created `wx_icons.py` - SF Symbol loader returning wx.Bitmap instead of PhotoImage
    - PNG byte stream → wx.Image → wx.Bitmap conversion with Retina/@2x support
    - 6pt icons with Small scale for native-looking menu icons
    - Module-level constants for NSImage parameters
    - Helper function `load_menu_icon()` for DRY menu icon loading
    - Caching by (name, size, color, scale) for performance
  - Created `wx_context_menu.py` - Native-style context menu
    - Cut/Copy/Paste using native wx.ID_CUT/COPY/PASTE for perfect macOS appearance
    - Title Case and Clear with SF Symbol icons (textformat.abc, xmark.circle)
    - Dict comprehension with walrus operator for icon loading
    - Graceful fallback when SF Symbols unavailable
  - Comprehensive code quality improvements:
    - Removed dead code (_cut, _copy, _paste functions - native IDs handle these)
    - Added type hints for all functions
    - Extracted magic numbers to module constants
    - Created color parsing helper function (_hex_to_rgb)
    - Fixed exception handling (specific exceptions vs bare except)
  - Test coverage:
    - 24 tests for wx_icons.py (SF Symbol loading, caching, color handling, edge cases, integration)
    - 16 tests for wx_context_menu.py (setup, clipboard ops, text transforms, edge cases, integration)
    - All 40 Phase 4 tests passing, total test count now 159
  - Fixed SF Symbols test dialog layout (proper spacing, larger button)
  - Updated CLAUDE.md with correct venv path (.venv not venv)
- **Phase 5 Complete:**
  - Created `wx_preview_panel.py` - Multi-page zoomable pannable PDF preview
    - wx.Panel with EVT_PAINT for custom drawing (full control over positioning)
    - Bitmap caching for performance (_bitmap_cache rendered once per state change)
    - Intelligent fit mode: scales to canvas size, never exceeds 1:1
    - Zoom: Fit/+/- buttons, scroll wheel, Shift+Click, Ctrl/Cmd+Click
    - Pan: Click and drag with offset tracking, sizing cursor during drag
    - Multi-page: Previous/Next buttons, page counter (1 / 3 format)
    - Smart controls: buttons enable/disable based on state (images loaded, page bounds)
    - Placeholder and error display: painted in _on_paint (cleaner than fixed positioning)
    - Text wrapping for error messages using _wrap_text helper
  - Public API matches tkinter version:
    - show_images(images, filename) - Display list of PIL Images
    - show_image(image, filename) - Backward-compatible single image
    - clear() - Reset state and clear display
    - show_error(message, filename) - Display error with warning icon
  - Test coverage:
    - 26 tests for wx_preview_panel.py
    - Level 1: Initialization, show/clear, error handling, control states
    - Level 2: Zoom in/out/fit, page navigation, zoom limits, label updates
    - Level 3: Dialog integration, multi-page navigation, state transitions
    - All 26 Phase 5 tests passing
  - Updated main_wx.py test harness:
    - Added "Preview Panel Test" button
    - Sample image generators (single and multi-page with PIL ImageDraw)
    - Load/Clear/Error test buttons
  - Total test count now 185 (159 + 26)
- **Phase 6 Complete:**
  - Created `wx_review_panel_master_detail.py` - Master-detail pattern (Mac-native)
    - CardListModel: PyDataViewModel with 3 columns (dot, filename, family)
    - DetailPanel: Single set of controls for selected card (name, checkbox, dropdown, AI button)
    - ReviewPanelMasterDetail: SplitterWindow layout (master top, detail bottom)
    - SetSashGravity(1.0) gives space to master list
    - AI button: 9pt sparkles icon, 28px height for native appearance
  - Public API matches original ReviewPanel:
    - Drop-in replacement with same method signatures
    - Callbacks for all interactions (selection, name change, checkbox, candidate, AI)
    - Keyboard navigation (up/down arrows)
    - select_card_by_id(), select_next_card(), select_prev_card() methods
  - Test coverage:
    - 61 tests for master-detail panel
    - Level 1: CardListModel (22 tests) - columns, values, colors, notifications
    - Level 2: ReviewPanelMasterDetail (39 tests) - init, selection, navigation, callbacks
    - Level 3: DetailPanel (5 tests) - candidates, controls, AI button
    - Edge cases (5 tests) - empty list, invalid selection, state transitions
    - All 61 tests passing
  - Deleted old scrollable implementation:
    - Removed `app/gui/wx_review_panel.py` (old scrollable rows approach)
    - Removed `tests/gui/test_wx_review_panel.py` (47 old tests)
    - Removed test button from main_wx.py
  - Code quality review:
    - Created `CODE_REVIEW_MASTER_DETAIL.md` documenting issues for future refactoring
    - HIGH priority: magic numbers (column indices, confidence symbols), private attribute access, DB coupling
    - MEDIUM priority: repeated code, lazy imports, dynamic attributes
    - LOW priority: hardcoded dimensions, unused parameters
    - Deferred refactoring until app completion
  - Architecture decision:
    - Chose master-detail over scrollable ReviewRow panels
    - Rationale: More performant (one control set vs N*6 widgets), native macOS pattern, easier to test
  - Button sizing journey: 12pt→16pt→11pt→9pt icon sizes to find native appearance
  - Total test count now 287 (226 before Phase 6 + 61 new master-detail tests)

---

## Notes

- Keep this file updated as phases complete
- Check off tasks with `[x]` when done
- Add notes and lessons learned
- Track blockers and solutions
