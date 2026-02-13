# wxPython Migration Plan

**Status:** In Progress
**Current Phase:** Phase 3 - Complex Dialogs (COMPLETE)
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

## Phase 4: Context Menu & Icons (Day 8)

### Tasks
- [ ] Migrate `context_menu.py` → `app/gui/wx_context_menu.py`
  - [ ] wx.Menu with copy/paste/select all
  - [ ] Bind to wx.EVT_CONTEXT_MENU
  - [ ] Test on text controls
- [ ] Update `icons.py` for wxPython
  - [ ] Load SF Symbols as wx.Bitmap
  - [ ] Test icon rendering
  - [ ] Consider wx.ArtProvider for standard icons

---

## Phase 5: Preview Panel (Days 9-11)

**Goal:** Image viewer with zoom and pan

### Tasks
- [ ] Create `app/gui/wx_preview_panel.py`
- [ ] Basic image display
  - [ ] wx.Panel with custom painting or wx.StaticBitmap
  - [ ] PIL Image → wx.Bitmap conversion
- [ ] Zoom functionality
  - [ ] Mouse wheel zoom (wx.EVT_MOUSEWHEEL)
  - [ ] Zoom in/out buttons
  - [ ] Fit to window
- [ ] Pan functionality
  - [ ] Click and drag (wx.EVT_LEFT_DOWN, wx.EVT_MOTION)
  - [ ] wx.ScrolledWindow or manual offset
- [ ] Navigation toolbar
  - [ ] Previous/Next page buttons
  - [ ] Page counter display
- [ ] Test with multi-page PDFs

**Challenges:**
- Canvas drawing → wx.DC or wx.GraphicsContext
- Mouse event coordination
- Performance with large images

---

## Phase 6: Review Panel (Days 12-15)

**Goal:** Scrollable card list with editable rows

### Tasks
- [ ] Create `app/gui/wx_review_panel.py`
- [ ] Choose implementation approach
  - [ ] Research: wx.ListCtrl vs wx.grid.Grid vs wx.lib.scrolledpanel
  - [ ] Decision: Recommended wx.lib.scrolledpanel
- [ ] Create `ReviewRow` as wx.Panel
  - [ ] wx.StaticBitmap (confidence dot)
  - [ ] wx.StaticText (filename)
  - [ ] wx.TextCtrl (editable name)
  - [ ] wx.CheckBox (remove family suffix)
  - [ ] wx.Choice (candidates dropdown)
  - [ ] wx.Button (AI button)
- [ ] Row layout with wx.BoxSizer
- [ ] Selection handling
  - [ ] Click to select (highlight row)
  - [ ] Keyboard navigation (up/down arrows)
  - [ ] Scroll to selected row
- [ ] Dynamic row creation/destruction
- [ ] Event handlers
  - [ ] Name edit callback
  - [ ] Candidate selection callback
  - [ ] Checkbox toggle callback
  - [ ] AI button click callback
- [ ] Test with real greeting card data

**Challenges:**
- Selection highlighting (custom background painting)
- Keyboard navigation between rows
- Scroll performance with many cards
- Dynamic widget creation

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

---

## Notes

- Keep this file updated as phases complete
- Check off tasks with `[x]` when done
- Add notes and lessons learned
- Track blockers and solutions
