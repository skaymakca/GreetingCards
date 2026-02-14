# Multi-Load Architecture Plan

## Overview
Enable continuous loading of PDFs from multiple folders/files without clearing previous loads. Content-based deduplication ensures files with identical content are represented by a single Card object, even when they exist at multiple paths. Per-directory rename conflict resolution handles files across different locations.

## Key Architectural Principles

### 1. Content-Based Deduplication
- **One Card per unique file content** (identified by hash)
- **Hash → Card is 1:1** (each unique hash has exactly one Card)
- **Path → Hash is many:1** (multiple paths can share same hash)
- **Card tracks multiple paths** (Card.file_paths is a list)

### 2. Path Tracking
- Same path won't load twice (path-level deduplication on load)
- Same content at different paths → merged into one Card
- User sees one card in list, but can view all locations in detail panel

### 3. Unified Rename Logic
- Single function handles both preflight check and execution
- Groups file paths by directory
- Detects conflicts per-directory
- Re-checks before each rename (race condition protection)
- Updates all file paths in Card object after rename

### 4. Progressive Disclosure
- Card list shows cards with multiple paths in blue text
- Detail panel has collapsible section for file locations
- Auto-expands when 2+ paths exist

---

## Current vs. Desired Behavior

### Current (Single Folder):
```
1. Browse → Select folder → Clear all previous cards
2. Load PDFs from folder
3. Display folder path in UI: "/Users/name/Desktop/cards"
4. Rename: Check dupes within that folder
5. Clear: Reset to empty state
```

### Desired (Multi-Load):
```
1. Add Files/Folders → Select multiple files and/or folders
2. Recursively scan for PDFs, skip already-loaded paths
3. NO folder path in UI (cards from multiple sources)
4. Accumulate cards from all loads
5. Rename: Check dupes PER TARGET DIRECTORY
6. Clear: Remove ALL loaded cards (from any source)
```

---

## Architecture Changes

### 1. Data Model Changes

**Current:**
```python
self._folder: Path | None = None  # Single root folder
self._cards_by_id: dict[int, CardResult] = {}  # Cards indexed by ID
```

**New (Content-Based Deduplication):**
```python
# Remove _folder completely (no root folder concept)
self._cards_by_hash: dict[str, CardResult] = {}  # Hash → Card (1:1 mapping)
self._hash_by_path: dict[Path, str] = {}  # Path → Hash (many:1 mapping)
self._next_card_id: int = 0  # Monotonic ID counter
```

**Key Invariants:**
- **One Card per unique file content** (identified by hash)
- **One hash per Card** (hash → Card is 1:1)
- **Multiple paths can share same hash** (path → hash is many:1)
- **Card tracks all paths with same content** (via file_paths list)

**CardResult Changes:**
```python
@dataclass
class CardResult:
    id: int
    file_paths: list[Path]  # NEW: Multiple paths with same content
    primary_path: Path  # First path found (for backward compatibility)
    family_name: str
    confidence: Confidence
    # ... other fields ...

    @property
    def pdf_path(self) -> Path:
        """Backward compatibility - returns primary path."""
        return self.primary_path

    @property
    def filename(self) -> str:
        """Filename from primary path."""
        return self.primary_path.name
```

**Database:**
```python
# file_hash = hash of file CONTENT (not path)
# Multiple paths with same content → same hash → same Card → same DB cache
# Database cache is shared across all paths with identical content
```

---

### 2. UI Changes

#### Toolbar Changes:

**REMOVE:**
```
[Browse...] /Users/name/Desktop/cards
```

**ADD:**
```
[Add Files/Folders...]   [or use SF Symbol: folder.badge.plus]
```

**Keep:**
```
[Search]  [Year: 2025]  [AI All] [Rename All] [Clear] [Help] [Settings]
```

#### Open Dialog - Native Mac Multi-Select:

```python
# Support BOTH files and folders in ONE dialog
dlg = wx.FileDialog(
    self._frame,
    message="Add PDF Files or Folders",
    defaultDir=str(Path.home()),
    wildcard="PDF files (*.pdf)|*.pdf|All files (*.*)|*.*",
    style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE
)

# ALSO support folder selection:
dir_dlg = wx.DirDialog(
    self._frame,
    message="Add Folder (recursive)",
    style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST
)

# OR: Use native Mac file picker that handles both
# Need to investigate best wx approach for "files + folders" picker
```

**Alternative (simpler):** Two buttons or menu:
- "Add PDFs..." → File picker (multi-select PDFs)
- "Add Folder..." → Folder picker (recursive scan)

---

### 3. Loading Logic

#### Recursive Folder Scanning:

```python
def _scan_for_pdfs(self, path: Path) -> list[Path]:
    """Recursively scan path for PDFs.

    Args:
        path: File or directory path

    Returns:
        List of PDF paths (absolute)
    """
    if path.is_file():
        if path.suffix.lower() == '.pdf':
            return [path.resolve()]
        return []

    # Recursive directory scan
    pdf_paths = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_paths.append(Path(root) / file)

    return pdf_paths
```

#### Deduplication by Path (Same Path Won't Load Twice):

```python
def _load_paths(self, paths: list[Path], auto_process: bool = True):
    """Load PDFs from multiple files/folders.

    Args:
        paths: List of file or folder paths
        auto_process: Whether to start processing immediately
    """
    # 1. Scan all paths for PDFs (recursive)
    all_pdfs = []
    for path in paths:
        all_pdfs.extend(self._scan_for_pdfs(path))

    # 2. Filter out already-loaded paths (same path won't load twice)
    new_pdfs = []
    skipped_pdfs = []

    for pdf_path in all_pdfs:
        abs_path = pdf_path.resolve()
        if abs_path in self._hash_by_path:
            # This exact path is already loaded (regardless of content)
            skipped_pdfs.append(abs_path)
        else:
            # New path - will process and check hash later
            new_pdfs.append(abs_path)

    # 3. Update state
    self._pdf_files.extend(new_pdfs)  # Accumulate, don't replace

    # 4. Show feedback
    if new_pdfs or skipped_pdfs:
        msg = f"Found {len(new_pdfs)} new PDF{'s' if len(new_pdfs) != 1 else ''}"
        if skipped_pdfs:
            msg += f", skipped {len(skipped_pdfs)} already loaded"
        self._show_info_message(msg, wx.ICON_INFORMATION)

    # 5. Process new PDFs
    if new_pdfs and auto_process:
        self._start_processing(new_pdfs)  # Pass specific PDFs, not all
```

#### Processing Changes:

```python
def _start_processing(self, pdf_paths: list[Path] = None):
    """Process specific PDFs (not all).

    Args:
        pdf_paths: PDFs to process, or None for all in self._pdf_files
    """
    if pdf_paths is None:
        pdf_paths = self._pdf_files

    # Don't clear existing cards!
    # self._cards_by_id.clear()  # REMOVE THIS

    # Process only new PDFs
    # Add to existing cards
```

#### Processing Complete (Content-Based Dedup):

```python
def _processing_complete(self, processed_items: list[tuple[Path, CardResult]]):
    """Called when processing finishes.

    Args:
        processed_items: List of (path, card_result) tuples from processor
    """
    # Track duplicates found
    new_cards = 0
    existing_cards_updated = 0

    for path, card in processed_items:
        file_hash = card.file_hash  # Calculated during processing

        # Check if we already have this content
        if file_hash in self._cards_by_hash:
            # DUPLICATE CONTENT - Add path to existing card
            existing_card = self._cards_by_hash[file_hash]
            if path not in existing_card.file_paths:
                existing_card.file_paths.append(path)
                existing_cards_updated += 1
        else:
            # NEW CONTENT - Create new card
            card.file_paths = [path]  # Initialize with first path
            card.primary_path = path
            self._cards_by_hash[file_hash] = card
            new_cards += 1

        # Always update path → hash mapping
        self._hash_by_path[path] = file_hash

    # Show feedback about duplicates
    if existing_cards_updated > 0:
        msg = f"Loaded {new_cards} new card{'s' if new_cards != 1 else ''}"
        msg += f", found {existing_cards_updated} duplicate{'s' if existing_cards_updated != 1 else ''}"
        self._show_info_message(msg, wx.ICON_INFORMATION)

    # Update sidebar counts (all unique cards)
    all_cards = list(self._cards_by_hash.values())
    self._sidebar.update_card_counts(all_cards)

    # Reload filtered view
    filtered_cards = self._get_filtered_cards()
    self._review_panel.load_cards(filtered_cards)
```

---

### 4. Rename Logic Changes

#### RenameOperation Dataclass:

```python
@dataclass
class RenameOperation:
    """Represents a single file rename operation."""
    directory: Path                  # Target directory
    original_filename: str           # Original filename (e.g., "card.pdf")
    final_filename: str              # Final filename (e.g., "2024_Smith_Family.pdf")
    status: RenameStatus             # READY, DUPLICATE, SKIP, etc.
    result: RenameResult | None = None  # Set after execution

@dataclass
class RenameStatus:
    """Status codes for rename operations."""
    READY = "ready"                  # Ready to rename
    DUPLICATE = "duplicate"          # Would create duplicate (added number)
    SKIP = "skip"                    # User chose to skip
    UNCHANGED = "unchanged"          # Same name, no rename needed

@dataclass
class RenameResult:
    """Result of executing a rename operation."""
    SUCCESS = "success"              # Renamed successfully
    COLLISION = "collision"          # Target file exists (race condition)
    ERROR = "error"                  # Other error (permissions, file not found, etc.)
    error_message: str | None = None # Error details if failed
```

#### Unified Rename Function (Preflight + Execute):

```python
def process_renames(
    cards: list[CardResult],
    year: str,
    execute: bool = False
) -> list[RenameOperation]:
    """Process rename operations for all file paths across all cards.

    This function handles BOTH preflight checking and actual execution.
    Call with execute=False to preview, execute=True to perform renames.

    Args:
        cards: Cards to rename (each may have multiple file paths)
        year: Year string for filename generation
        execute: If True, perform renames; if False, just plan

    Returns:
        List of RenameOperation objects (one per file path)
    """
    operations = []

    # Group all file paths by directory
    paths_by_dir: dict[Path, list[tuple[CardResult, Path]]] = {}

    for card in cards:
        for file_path in card.file_paths:
            directory = file_path.parent
            if directory not in paths_by_dir:
                paths_by_dir[directory] = []
            paths_by_dir[directory].append((card, file_path))

    # Process each directory separately
    for directory, card_path_pairs in paths_by_dir.items():
        # Track original and new filenames in THIS directory
        original_names = {fp.name for _, fp in card_path_pairs}
        new_names_used = set()

        # Get existing files in directory (for collision detection)
        existing_files = {f.name for f in directory.glob("*.pdf")}

        for card, file_path in card_path_pairs:
            # Generate new filename
            new_name = generate_filename(card, year)

            # Check for duplicates in this directory
            if new_name in new_names_used or (new_name in existing_files and new_name not in original_names):
                # Collision - add number suffix
                base, ext = new_name.rsplit(".", 1)
                counter = 2
                while f"{base}_{counter}.{ext}" in new_names_used or f"{base}_{counter}.{ext}" in existing_files:
                    counter += 1
                new_name = f"{base}_{counter}.{ext}"
                status = RenameStatus.DUPLICATE
            elif new_name == file_path.name:
                # No change needed
                status = RenameStatus.UNCHANGED
            else:
                # Ready to rename
                status = RenameStatus.READY

            new_names_used.add(new_name)

            # Create operation
            op = RenameOperation(
                directory=directory,
                original_filename=file_path.name,
                final_filename=new_name,
                status=status
            )

            # Execute if requested
            if execute and status != RenameStatus.UNCHANGED:
                old_path = directory / file_path.name
                new_path = directory / new_name

                # CRITICAL: Re-check right before rename (race condition protection)
                if new_path.exists() and new_path != old_path:
                    op.result = RenameResult.COLLISION
                    op.error_message = f"Target file exists (created after preflight): {new_name}"
                else:
                    try:
                        old_path.rename(new_path)
                        op.result = RenameResult.SUCCESS

                        # Update card's file_paths list
                        idx = card.file_paths.index(file_path)
                        card.file_paths[idx] = new_path

                    except FileNotFoundError:
                        op.result = RenameResult.ERROR
                        op.error_message = f"File not found: {old_path}"
                    except PermissionError as e:
                        op.result = RenameResult.ERROR
                        op.error_message = f"Permission denied: {e}"
                    except Exception as e:
                        op.result = RenameResult.ERROR
                        op.error_message = str(e)

            operations.append(op)

    return operations
```

#### Current Rename Flow:
```python
# 1. Get all cards
cards = self._review_panel.get_cards()

# 2. Build rename plan (single directory)
plan = build_rename_plan(cards, year_str)

# 3. Show confirmation
dialog = RenameConfirmDialog(self._frame, plan, year_str)

# 4. Execute renames
results = execute_rename_plan(plan)
```

#### New Rename Flow (Unified Function):

```python
# 1. Get all cards
cards = self._review_panel.get_cards()

# 2. Preflight check (execute=False)
operations = process_renames(cards, year_str, execute=False)

# 3. Show confirmation dialog
dialog = RenameConfirmDialog(self._frame, operations, year_str)
if dialog.ShowModal() != wx.ID_OK:
    return

# 4. Execute renames (execute=True)
results = process_renames(cards, year_str, execute=True)

# 5. Show results
self._show_rename_results(results)
```


---

### 5. Rename Confirmation Dialog Changes

**Current:**
```
Rename 25 files?

old_name1.pdf → 2024_Smith_Family.pdf
old_name2.pdf → 2024_Jones_Family.pdf
...
```

**New (Consume RenameOperation List):**
```python
class RenameConfirmDialog(wx.Dialog):
    """Confirm rename operations before executing."""

    def __init__(self, parent, operations: list[RenameOperation], year: str):
        """
        Args:
            parent: Parent window
            operations: List of RenameOperation objects (from process_renames)
            year: Year string
        """
        # Group by directory for display
        ops_by_dir = {}
        for op in operations:
            if op.directory not in ops_by_dir:
                ops_by_dir[op.directory] = []
            ops_by_dir[op.directory].append(op)

        # Count total files
        total_files = len(operations)
        total_dirs = len(ops_by_dir)

        # Build display text
        title = f"Rename {total_files} file{'s' if total_files != 1 else ''} across {total_dirs} director{'ies' if total_dirs != 1 else 'y'}?"
        # ... rest of implementation
```

**Visual:**
```
Rename 25 files across 3 directories?

/Users/name/Desktop/cards_2024:
  old_name1.pdf → 2024_Smith_Family.pdf ✓
  old_name2.pdf → 2024_Jones_Family.pdf ✓

/Users/name/Downloads:
  card.pdf → 2024_Anderson_Family.pdf (duplicate #2) ⚠️

/Users/name/Documents/greeting_cards:
  scan001.pdf → 2024_Wilson_Family.pdf ✓
  scan002.pdf → 2024_Wilson_Family_2.pdf (duplicate #2) ⚠️

✓ Ready (22)  ⚠️ Duplicates (3)  − Unchanged (0)

[Cancel] [Rename All]
```

---

### 6. Clear Behavior

**Current:**
```python
def _clear_all(self):
    self._folder = None
    self._folder_label.SetLabel("No folder selected")
    self._cards_by_id.clear()
```

**New (Hash-Based):**
```python
def _clear_all(self):
    """Clear ALL loaded cards (from all sources)."""
    self._cards_by_hash.clear()  # Clear hash → card mapping
    self._hash_by_path.clear()   # Clear path → hash mapping
    self._pdf_files.clear()
    self._next_card_id = 0

    # Update UI
    self._review_panel.load_cards([])
    self._preview_panel.clear()
    self._sidebar.update_card_counts([])

    # Show confirmation
    self._show_info_message("All cards cleared", wx.ICON_INFORMATION)
```

---

### 7. Drag & Drop Changes

**Current:**
```python
def _on_drop(self, path: Path):
    """Handle dropped file or folder."""
    if path.is_dir():
        self._load_folder(path, auto_process=True)  # Replaces existing
    elif path.is_file() and path.suffix.lower() == ".pdf":
        self._load_folder(path.parent, auto_process=True)  # Replaces existing
```

**New:**
```python
def _on_drop(self, paths: list[Path]):
    """Handle dropped files and/or folders (multi-select).

    Args:
        paths: List of dropped paths (files or folders)
    """
    # Add to existing cards (don't replace)
    self._load_paths(paths, auto_process=True)
```

**Need to update FileDropTarget:**
```python
class FileDropTarget(wx.FileDropTarget):
    def OnDropFiles(self, x, y, filenames):
        """Handle dropped files (can be multiple)."""
        if not filenames:
            return False

        paths = [Path(f) for f in filenames]
        wx.CallAfter(self._callback, paths)  # Pass list, not single path
        return True
```

---

### 8. Card Display Changes

#### Card List Table Header Fix:

```python
# Change column header from "Filename" to "File Name"
self._list.AppendTextColumn("File Name", width=300)  # Was: "Filename"
```

#### Visual Indicator for Multiple Paths:

When a card has multiple file paths (duplicates), show the filename in **blue text** in the card list:

```python
# In DataViewCtrl item rendering
if len(card.file_paths) > 1:
    # Set filename text color to blue
    item.SetTextColour(wx.Colour(0, 122, 255))  # macOS system blue
```

#### Detail Panel - File Locations Section:

Add a collapsible disclosure section at the bottom of the edit panel to show all file paths.

**Visual (Collapsed - Single Path):**
```
┌─────────────────────────────────────┐
│ Family Name: [Smith            ]    │
│ ☐ Remove "Family"                   │
│ Candidates: [Smiths         ▾]      │
│ [✨ AI Analyze]                     │
│                                     │
│ ▶ File Location                     │ ← Collapsed by default
└─────────────────────────────────────┘
```

**Visual (Expanded - Multiple Paths):**
```
┌─────────────────────────────────────┐
│ Family Name: [Smith            ]    │
│ ☐ Remove "Family"                   │
│ Candidates: [Smiths         ▾]      │
│ [✨ AI Analyze]                     │
│                                     │
│ ▼ File Locations (3 copies)        │ ← Auto-expand when 2+ paths
│ ┌─────────────────────────────────┐ │
│ │ Desktop/cards_2024/card.pdf     │ │ ← Primary path (first)
│ │ Downloads/card.pdf              │ │
│ │ Documents/scans/card_copy.pdf   │ │
│ └─────────────────────────────────┘ │
│ ℹ️ These files have identical       │
│   content (same hash).              │
└─────────────────────────────────────┘
```

**Implementation:**

```python
# Add to detail panel (below AI button)
self._locations_pane = wx.CollapsiblePane(
    detail_panel,
    label="File Location",
    style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE
)

pane_window = self._locations_pane.GetPane()
pane_sizer = wx.BoxSizer(wx.VERTICAL)

# List of file paths
self._locations_list = wx.dataview.DataViewListCtrl(
    pane_window,
    style=wx.dataview.DV_NO_HEADER | wx.dataview.DV_SINGLE | wx.dataview.DV_ROW_LINES
)
self._locations_list.AppendTextColumn("", width=400)
self._locations_list.SetMinSize((-1, 80))  # Compact height
pane_sizer.Add(self._locations_list, 1, wx.EXPAND | wx.ALL, 5)

# Info text (for multiple paths)
self._duplicate_info = wx.StaticText(
    pane_window,
    label="ℹ️ These files have identical content (same hash)."
)
self._duplicate_info.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
pane_sizer.Add(self._duplicate_info, 0, wx.ALL, 5)

pane_window.SetSizer(pane_sizer)

# Update when card changes
def update_locations(card: CardResult):
    """Update file locations section."""
    num_paths = len(card.file_paths)

    # Update label
    if num_paths == 1:
        self._locations_pane.SetLabel("File Location")
        self._locations_pane.Collapse()  # Collapse for single path
        self._duplicate_info.Hide()
    else:
        self._locations_pane.SetLabel(f"File Locations ({num_paths} copies)")
        self._locations_pane.Expand()  # Auto-expand for multiple paths
        self._duplicate_info.Show()

    # Populate list
    self._locations_list.DeleteAllItems()
    for path in card.file_paths:
        # Show relative path from home if possible
        try:
            rel_path = path.relative_to(Path.home())
            display_path = str(rel_path)
        except ValueError:
            display_path = str(path)

        self._locations_list.AppendItem([display_path])

    # Highlight primary path (first one)
    if num_paths > 0:
        self._locations_list.SelectRow(0)
```

**Behavior:**
- **1 path:** Collapsed by default, label "File Location"
- **2+ paths:** Auto-expand, label "File Locations (N copies)", show info message
- **Paths displayed:** Relative to home directory when possible (cleaner)
- **Primary path:** First in list (highlighted)

---

## Implementation Strategy

### Phase 1: Core Data Structure & Content Deduplication (Day 1)
**Goal:** Implement hash-based deduplication with multiple paths per card

1. Update `CardResult` dataclass:
   - Add `file_paths: list[Path]` field
   - Add `primary_path: Path` field
   - Add `pdf_path` property for backward compatibility
2. Replace `_cards_by_id` with `_cards_by_hash` in main window
3. Add `_hash_by_path` dictionary for path tracking
4. Remove `_folder` state variable
5. Update `_clear_all()` to clear both hash dicts
6. Write unit tests for content-based dedup

**Files:**
- `app/models/card.py` (CardResult dataclass)
- `app/gui/wx_main_window.py`
- `tests/models/test_card.py`
- `tests/gui/test_wx_main_window.py`

### Phase 2: Loading Logic with Hash-Based Dedup (Day 1-2)
**Goal:** Support loading multiple sources with content deduplication

1. Implement `_scan_for_pdfs(path)` (recursive)
2. Rename `_load_folder()` → `_load_paths(paths)`
3. Update `_processing_complete()` to merge duplicate content:
   - Calculate file hash during processing
   - If hash exists, add path to existing card
   - If hash new, create new card
4. Add "X new, Y duplicates" feedback
5. Update `_start_processing()` to handle partial sets
6. Write tests for recursive scanning and hash dedup

**Files:**
- `app/gui/wx_main_window.py`
- `app/processors/pdf_processor.py` (ensure hash calculation)
- New: `app/core/path_scanner.py` (recursive scanner)
- `tests/core/test_path_scanner.py`
- `tests/gui/test_wx_main_window.py`

### Phase 3: UI Changes (Day 2)
**Goal:** Update toolbar, card list, and detail panel

1. **Toolbar:**
   - Remove folder label
   - Replace "Browse" → "Add Files/Folders"
   - Update tooltips and help text

2. **Card List:**
   - Change "Filename" → "File Name" header
   - Add blue text color for cards with multiple paths
   - Update all references to iterate over `_cards_by_hash.values()`

3. **Detail Panel:**
   - Add wx.CollapsiblePane for file locations
   - Add DataViewListCtrl to show all paths
   - Auto-expand when 2+ paths
   - Show info message for duplicates

4. **Dialogs:**
   - Update file dialog for multi-select PDFs
   - Add folder selection option
   - Update drag & drop for multiple items

**Files:**
- `app/gui/wx_main_window.py`
- `app/gui/wx_review_panel_master_detail.py`
- `app/gui/wx_help_dialog.py`
- `tests/gui/test_wx_review_panel_master_detail.py`

### Phase 4: Unified Rename Function (Day 3)
**Goal:** Single function for preflight + execution

1. Create `RenameOperation` and `RenameStatus` dataclasses
2. Implement `process_renames(cards, year, execute)` function:
   - Group all file paths by directory
   - Detect duplicates per directory
   - Execute if `execute=True`
   - Race condition protection (re-check before rename)
   - Update card.file_paths after successful rename
3. Update `RenameConfirmDialog` to consume `RenameOperation` list
4. Update rename flow in main window:
   - Call with execute=False for preview
   - Show dialog
   - Call with execute=True to perform
5. Write comprehensive rename tests

**Files:**
- `app/core/renamer.py` (unified function)
- `app/gui/wx_dialogs.py` (RenameConfirmDialog)
- `tests/core/test_renamer.py`

### Phase 5: Testing & Polish (Day 3-4)
**Goal:** Comprehensive testing and edge cases

1. Test multi-load (folder + folder + files)
2. Test content-based deduplication (same file, different paths)
3. Test rename across directories (multiple paths per card)
4. Test race condition handling
5. Test drag & drop multiple items
6. Test disclosure pane (collapse/expand)
7. Test blue text indicator for multi-path cards
8. Update all existing tests
9. Integration testing (full workflow)

**Files:**
- All test files
- Manual testing checklist

---

## Edge Cases & Considerations

### 1. Same File, Different Locations (Content-Based Dedup)
**Scenario:** Copy of same PDF in two folders

```
/Users/name/Desktop/card.pdf (hash: abc123)
/Users/name/Downloads/card.pdf (hash: abc123)
```

**Behavior:**
- **ONE card** (same content hash)
- Card.file_paths = [Desktop/card.pdf, Downloads/card.pdf]
- Appears ONCE in card list (filename shown in blue to indicate multiple copies)
- Editing card (family name, etc.) applies to ALL copies
- Renaming affects ALL copies (each in its own directory)
- DB cache shared (same hash)

**Why This Matters:**
- User sees duplicate content only once
- Edit once, applies to all copies
- Cleaner UI (fewer rows in table)
- Can still see all file locations in detail panel

### 2. Symbolic Links
**Scenario:** Symlink to PDF

```
/Users/name/Desktop/card.pdf → /Users/name/Archive/card.pdf
```

**Behavior:**
- `Path.resolve()` follows symlinks
- Only ONE card created (same resolved path)
- Deduplication works correctly

### 3. Files Renamed While Loaded
**Scenario:** User renames file in Finder while app has it loaded

**Behavior:**
- Card still references old path
- Rename operation will fail (file not found)
- Report error, skip that card
- Consider: Add "Refresh" button to re-scan paths?

### 4. Files Deleted While Loaded
**Scenario:** User deletes file in Finder

**Behavior:**
- Card remains in list (in-memory state)
- Rename fails (file not found)
- AI analysis fails (can't read file)
- Consider: Visual indicator for missing files?

### 5. Very Large Number of Cards
**Scenario:** Load 1000+ PDFs from multiple folders

**Behavior:**
- Processing may take time → progress dialog ✓
- Card list performance → DataViewCtrl handles well ✓
- Rename might be slow → show progress ✓
- Memory usage → PIL images cached, may need cleanup

**Optimization:**
- Lazy load images (only when selected)
- Clear image cache when card deselected
- Paginate card list (if >1000 cards)

---

## Additional Features to Consider

### 1. Remove Individual Cards
**UI:** Right-click → "Remove from List" (doesn't delete file)

```python
def _remove_card(self, card_id: int):
    """Remove card from loaded set (doesn't delete file)."""
    card = self._cards_by_id.pop(card_id, None)
    if card:
        self._cards_by_path.pop(card.pdf_path.resolve(), None)
        # Update UI
```

### 2. Reload/Refresh Paths
**UI:** Button to re-scan all loaded paths

```python
def _refresh_all_paths(self):
    """Re-scan all loaded paths for changes."""
    paths = list(self._cards_by_path.keys())
    # Remove cards for missing files
    # Re-process any changed files
```

### 3. Show Path in UI
**Option:** Add directory column to card list
**Option:** Show full path in tooltip
**Option:** Show in detail panel

### 4. Save/Load Workspace
**Feature:** Save loaded paths to file, reload later

```python
def _save_workspace(self, filepath: Path):
    """Save current loaded paths."""
    workspace = {
        'paths': [str(p) for p in self._cards_by_path.keys()],
        'year': self._year
    }
    json.dump(workspace, filepath.open('w'))

def _load_workspace(self, filepath: Path):
    """Reload saved workspace."""
    workspace = json.load(filepath.open())
    paths = [Path(p) for p in workspace['paths']]
    self._load_paths(paths)
```

### 5. Clear Button Confirmation
**Safety:** Confirm before clearing 100+ cards

```python
def _clear_all(self):
    if len(self._cards_by_id) > 10:
        dlg = wx.MessageDialog(
            self._frame,
            f"Clear all {len(self._cards_by_id)} loaded cards?",
            "Confirm Clear",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        )
        if dlg.ShowModal() != wx.ID_YES:
            return
    # ... clear logic
```

---

## Design Decisions

### Multiple File Paths Display (APPROVED)

**Chosen: Tab-Based Interface (wx.Notebook)**

After user feedback requesting a native tab control approach:

- **Mac-Native Pattern:** wx.Notebook provides native macOS tab appearance
- **Progressive Disclosure:** File Paths tab only shown for multi-path cards (2+ paths)
- **Clean Separation:** Edit controls and file locations in separate tab views
- **Tab Structure:**
  - **Edit Tab** (always present): Family name, candidates, AI button, checkbox
  - **File Paths Tab** (conditional): File paths list + duplicate info
- **Visual Indicators:**
  - Blue text in card list filename when multiple paths exist
  - Tab label shows count: "File Paths (N)"
- **Single-Path Cards:** Only Edit tab shown (no tab overhead)
- **Multi-Path Cards:** Both Edit and File Paths tabs available

**Implementation:** wx.Notebook with Edit panel always present, File Paths tab dynamically added/removed based on path count. DataViewListCtrl shows file locations with duplicate hash info message.

---

## Questions for Alignment

1. **File Dialog:** Two separate buttons ("Add PDFs" + "Add Folder") or one unified picker?
   - **Recommendation:** Two buttons for clarity

2. **Remove Individual Cards:** Right-click menu item to remove from loaded set?
   - **Recommendation:** Yes, useful for cleanup (doesn't delete file)

3. **Missing Files:** Show warning icon in list or just fail at rename?
   - **Recommendation:** Fail at rename with clear error (keep UI simple)

4. **Workspace Save/Load:** Save/load loaded paths to file?
   - **Recommendation:** Later (v2.0 feature, nice to have)

5. **Clear Confirmation:** Always confirm or only for large sets?
   - **Recommendation:** Only if >10 cards (avoid annoyance)

---

## Risk Assessment

### Low Risk:
- ✅ Adding `_cards_by_path` (simple dict)
- ✅ Recursive folder scanning (straightforward)
- ✅ UI button changes (cosmetic)

### Medium Risk:
- ⚠️ Path deduplication (need thorough testing)
- ⚠️ Accumulating cards (existing tests may break)
- ⚠️ Drag & drop multi-select (need to test)

### High Risk:
- 🔴 Per-directory rename logic (complex, critical)
- 🔴 Race condition handling (timing sensitive)
- 🔴 Rename dialog UI (needs redesign)

### Mitigation:
- Comprehensive unit tests at each phase
- Manual testing with edge cases
- Incremental rollout (can revert phases)

---

## Success Criteria

1. ✅ Load PDFs from multiple folders without clearing
2. ✅ Skip already-loaded paths automatically (same path won't load twice)
3. ✅ Merge duplicate content (same file at different paths → one card)
4. ✅ Show meaningful feedback ("X new, Y duplicates, Z skipped")
5. ✅ Card list shows multiple-path cards with blue text indicator
6. ✅ Detail panel disclosure section shows all file locations
7. ✅ Rename works correctly across directories (all paths per card)
8. ✅ Unified rename function handles preflight + execution
9. ✅ No file collisions or race conditions
10. ✅ Clear removes all cards from any source
11. ✅ All existing features still work (AI, filters, search)
12. ✅ Tests pass (unit + integration)
13. ✅ "File Name" header (not "Filename") in card list

---

## Timeline Estimate

- **Phase 1 (Data Structure & Hash Dedup):** 6-8 hours (CardResult changes, hash-based dicts)
- **Phase 2 (Loading Logic with Content Merge):** 8-10 hours (recursive scan, hash dedup, merge logic)
- **Phase 3 (UI Changes):** 6-8 hours (toolbar, card list, detail panel disclosure)
- **Phase 4 (Unified Rename Function):** 10-12 hours (complex per-directory logic, race protection)
- **Phase 5 (Testing & Polish):** 8-10 hours (content dedup tests, multi-path tests, integration)

**Total:** 38-48 hours (~5-6 days)

**Why More Complex:**
- Content-based deduplication adds complexity to loading and processing
- Card.file_paths list requires careful tracking and updates
- Unified rename function must handle multiple paths per card
- Detail panel disclosure UI is new component
- More edge cases to test (duplicate content scenarios)

---

## Next Steps

1. **Review this plan** - Confirm we're aligned on logic
2. **Approve implementation strategy** - Any changes needed?
3. **Start Phase 1** - Data structure changes
4. **Incremental testing** - Test after each phase

Ready to proceed?
