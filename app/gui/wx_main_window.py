"""wxPython Main Window for Greeting Cards application."""

import io
import wx
from pathlib import Path
from datetime import datetime
import threading
import asyncio

from app.gui import wx_styles
from app.gui.wx_preview_panel import PreviewPanel
from app.gui.wx_review_panel_master_detail import ReviewPanelMasterDetail
from app.gui.wx_filter_sidebar import FilterSidebar
from app.gui.wx_dialogs import ProgressDialog, RenameConfirmDialog, CompletionDialog, ErrorListDialog
from app.gui.wx_settings_dialog import show_settings_dialog
from app.gui.wx_help_dialog import show_help_dialog
from app.gui.wx_icons import load_sf_symbol
from app.gui.wx_api_key_dialog import show_api_key_dialog
from app.models.card import CardResult, Confidence
from app.core.pdf_renderer import render_all_pages
from app.core.ocr_engine import extract_text_all_pages
from app.core.ai_analyzer import analyze_card_with_ai, analyze_card_with_ai_async, format_ai_error
from app.core.config import get_api_key
from app.core.renamer import build_rename_plan, execute_rename_plan
from app.core.database import (
    compute_file_hash, get_card_state, save_raw_ocr, save_raw_ai,
    set_manual_name, reprocess_candidates_from_raw
)


def _process_pdf_worker(pdf_path_str: str) -> dict:
    """Worker function to process a single PDF in a separate process.

    Returns dict of results (serializable for multiprocessing).
    """
    from pathlib import Path
    from PIL import Image
    from app.core.pdf_renderer import render_all_pages
    from app.core.ocr_engine import extract_text_all_pages
    from app.core.database import (
        compute_file_hash, get_card_state, save_raw_ocr,
        reprocess_candidates_from_raw
    )
    from app.models.card import Confidence

    pdf_path = Path(pdf_path_str)
    result = {
        'pdf_path': pdf_path_str,
        'file_hash': None,
        'family_name': '',
        'confidence': 'none',
        'method': 'missing',
        'alternates': [],
        'candidates': [],
        'remove_family': False,
        'selected_candidate_id': None,
        'ocr_text': '',
        'error': None,
        # Store images as PNG bytes for pickling
        'preview_image_bytes': None,
        'page_images_bytes': [],
    }

    try:
        # Compute file hash
        file_hash = compute_file_hash(pdf_path)
        result['file_hash'] = file_hash

        # Check DB cache first
        card_state = get_card_state(file_hash)

        # Always render preview (needed for AI later)
        images = render_all_pages(pdf_path, dpi=200)
        if images:
            # Serialize images to bytes
            preview_buf = io.BytesIO()
            images[0].save(preview_buf, format='PNG')
            result['preview_image_bytes'] = preview_buf.getvalue()

            for img in images:
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                result['page_images_bytes'].append(buf.getvalue())

        if card_state:
            # Card exists - reprocess candidates from raw data with current cleaning logic
            reprocess_candidates_from_raw(file_hash)

            # Reload state after reprocessing
            card_state = get_card_state(file_hash)
            if card_state:
                result['family_name'] = card_state.display_name
                result['confidence'] = card_state.confidence
                result['alternates'] = [c.family_name for c in card_state.candidates]
                result['candidates'] = card_state.candidates
                result['remove_family'] = card_state.remove_family
                result['selected_candidate_id'] = card_state.selected_candidate_id
                result['method'] = card_state.method
        else:
            # New file - run OCR and save raw data
            if images:
                ocr_text = extract_text_all_pages(images)
                result['ocr_text'] = ocr_text

                # Save raw OCR
                save_raw_ocr(file_hash, ocr_text)

                # Process candidates from raw data
                reprocess_candidates_from_raw(file_hash)

                # Load state after processing
                card_state = get_card_state(file_hash)
                if card_state:
                    result['family_name'] = card_state.display_name
                    result['confidence'] = card_state.confidence
                    result['alternates'] = [c.family_name for c in card_state.candidates]
                    result['candidates'] = card_state.candidates
                    result['remove_family'] = card_state.remove_family
                    result['selected_candidate_id'] = card_state.selected_candidate_id
                    result['method'] = card_state.method

    except Exception as e:
        result['error'] = str(e)

    return result


class MainWindow:
    """Main application window with toolbar and content panels."""

    def __init__(self):
        # Create frame
        self._frame = wx.Frame(
            None,
            title="Greeting Cards",
            size=(wx_styles.Layout.WINDOW_WIDTH, wx_styles.Layout.WINDOW_HEIGHT)
        )
        self._frame.SetMinSize((800, 500))

        # State - Content-based deduplication (multi-load architecture)
        # Removed: self._folder (no root folder concept)
        self._next_card_id = 0  # Monotonically increasing ID counter
        self._cards_by_hash: dict[str, CardResult] = {}  # hash → Card (1:1)
        self._hash_by_path: dict[Path, str] = {}  # path → hash (many:1)
        self._pdf_files: list[Path] = []
        self._year = datetime.now().year - 1
        self._current_filters = ["all"]  # Current sidebar filters (can be multiple)

        # Build UI
        self._setup_menu_bar()
        self._build_ui()
        self._setup_drop_target()
        self._setup_keyboard_shortcuts()

        # Center and bind close event
        self._frame.Centre()
        self._frame.Bind(wx.EVT_CLOSE, self._on_close)

    def _get_card_by_id(self, card_id: int) -> CardResult | None:
        """Get card by ID (searches through hash-based storage).

        Args:
            card_id: Card ID to find

        Returns:
            CardResult if found, None otherwise
        """
        for card in self._cards_by_hash.values():
            if card.id == card_id:
                return card
        return None

    def _setup_menu_bar(self):
        """Create native macOS menu bar with File and Help menus."""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_OPEN, "Open...\tCtrl+O")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_CLOSE, "Close Window\tCtrl+W")
        file_menu.Append(wx.ID_EXIT, "Quit\tCtrl+Q")
        menubar.Append(file_menu, "&File")

        # Help menu
        help_menu = wx.Menu()
        help_menu.Append(wx.ID_HELP, "Greeting Cards Help")
        menubar.Append(help_menu, "&Help")

        self._frame.SetMenuBar(menubar)

        # Bind events
        self._frame.Bind(wx.EVT_MENU, lambda e: self._add_files_folders(), id=wx.ID_OPEN)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._frame.Close(), id=wx.ID_CLOSE)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._frame.Close(), id=wx.ID_EXIT)
        self._frame.Bind(wx.EVT_MENU, lambda e: show_help_dialog(self._frame), id=wx.ID_HELP)

    def _build_ui(self):
        """Assemble main UI layout with toolbar and three-column layout."""
        # Main panel for content
        self._panel = wx.Panel(self._frame)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Toolbar (custom panel for stability across tests and production)
        self._toolbar = self._build_toolbar()
        main_sizer.Add(self._toolbar, 0, wx.EXPAND)

        # Separator
        sep = wx.StaticLine(self._panel)
        main_sizer.Add(sep, 0, wx.EXPAND)

        # Info bar (initially hidden)
        self._info_bar = wx.InfoBar(self._panel)
        main_sizer.Add(self._info_bar, 0, wx.EXPAND)

        # Three-column content splitter
        splitter = self._build_content_area()
        main_sizer.Add(splitter, 1, wx.EXPAND)

        self._panel.SetSizer(main_sizer)

        # Apply toolbar icons and tooltips
        self._apply_toolbar_icons()
        self._apply_tooltips()

    def _build_toolbar(self) -> wx.Panel:
        """Build single-row toolbar panel with properly-sized icon buttons."""
        toolbar = wx.Panel(self._panel)
        toolbar.SetMinSize((-1, 50))  # Single row height
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Add Files/Folders button (larger for better visibility)
        self._browse_btn = wx.Button(toolbar, label="", size=(50, 40))
        self._browse_btn.Bind(wx.EVT_BUTTON, lambda e: self._add_files_folders())
        sizer.Add(self._browse_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, wx_styles.Layout.PAD)

        # Search control (no folder label - cards can be from multiple sources)
        self._search_ctrl = wx.SearchCtrl(toolbar, style=wx.TE_PROCESS_ENTER, size=(200, -1))
        self._search_ctrl.ShowSearchButton(True)
        self._search_ctrl.ShowCancelButton(True)
        self._search_ctrl.SetDescriptiveText("Filter cards...")
        self._search_ctrl.Bind(wx.EVT_TEXT, self._on_search_text)
        self._search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_cancel)
        sizer.Add(self._search_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 10)

        sizer.AddStretchSpacer()

        # Year controls
        year_label = wx.StaticText(toolbar, label="Year:")
        year_label.SetFont(wx_styles.Font.BODY())
        sizer.Add(year_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self._year_ctrl = wx.TextCtrl(toolbar, value=str(self._year), size=(60, -1))
        sizer.Add(self._year_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        # Action buttons (larger icons, proper spacing)
        self._ai_all_btn = wx.Button(toolbar, label="", size=(50, 40))
        self._ai_all_btn.Enable(False)
        self._ai_all_btn.Bind(wx.EVT_BUTTON, lambda e: self._start_ai_all())
        sizer.Add(self._ai_all_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, wx_styles.Layout.PAD)

        self._rename_btn = wx.Button(toolbar, label="", size=(50, 40))
        self._rename_btn.Enable(False)
        self._rename_btn.Bind(wx.EVT_BUTTON, lambda e: self._start_rename())
        sizer.Add(self._rename_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, wx_styles.Layout.PAD)

        self._clear_btn = wx.Button(toolbar, label="", size=(50, 40))
        self._clear_btn.Enable(False)
        self._clear_btn.Bind(wx.EVT_BUTTON, lambda e: self._clear_all())
        sizer.Add(self._clear_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, wx_styles.Layout.PAD)

        # Help and Settings
        self._help_btn = wx.Button(toolbar, label="", size=(50, 40))
        self._help_btn.Bind(wx.EVT_BUTTON, lambda e: show_help_dialog(self._frame))
        sizer.Add(self._help_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, wx_styles.Layout.PAD)

        self._settings_btn = wx.Button(toolbar, label="", size=(50, 40))
        self._settings_btn.Bind(wx.EVT_BUTTON, lambda e: show_settings_dialog(self._frame, on_db_reset=self._clear_all))
        sizer.Add(self._settings_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, wx_styles.Layout.PAD)

        toolbar.SetSizer(sizer)
        return toolbar

    def _apply_toolbar_icons(self):
        """Load and apply properly-sized SF Symbol icons to toolbar buttons."""
        icon_map = {
            "browse": ("folder.badge.plus", self._browse_btn),  # Add files/folders
            "ai_all": ("sparkles", self._ai_all_btn),
            "rename": ("pencil", self._rename_btn),
            "clear": ("xmark.circle", self._clear_btn),
            "help": ("questionmark.circle", self._help_btn),
            "settings": ("gearshape", self._settings_btn),
        }

        # Use larger 24pt icons for better visibility
        for key, (symbol_name, button) in icon_map.items():
            icon = load_sf_symbol(symbol_name, point_size=24, color_hex="#1D1D1F")
            if icon:
                button.SetBitmap(icon)
                button.SetBitmapCurrent(icon)

    def _apply_tooltips(self):
        """Add helpful tooltips to all toolbar controls."""
        self._browse_btn.SetToolTip("Add PDF files or folders to analyze (can add from multiple sources)")
        self._search_ctrl.SetToolTip("Filter cards by filename or family name")
        self._year_ctrl.SetToolTip("Year to use in renamed filenames (e.g., 2024)")
        self._ai_all_btn.SetToolTip("Analyze all loaded cards with AI to extract family names")
        self._rename_btn.SetToolTip("Rename all files based on detected family names")
        self._clear_btn.SetToolTip("Clear all loaded cards and reset the application")
        self._help_btn.SetToolTip("Show help and usage instructions")
        self._settings_btn.SetToolTip("Configure API key and application settings")

    def _on_search_text(self, event):
        """Filter cards as user types in search field."""
        filtered_cards = self._get_filtered_cards()
        self._review_panel.load_cards(filtered_cards)

    def _on_search_cancel(self, event):
        """Clear filter when cancel button clicked."""
        self._search_ctrl.SetValue("")
        filtered_cards = self._get_filtered_cards()
        self._review_panel.load_cards(filtered_cards)

    def _on_filter_change(self, filter_keys: list[str]):
        """Handle sidebar filter change (multi-select).

        Args:
            filter_keys: List of selected filters (e.g., ["high", "manual"])
        """
        self._current_filters = filter_keys
        filtered_cards = self._get_filtered_cards()
        self._review_panel.load_cards(filtered_cards)

    def _get_filtered_cards(self) -> list[CardResult]:
        """Get cards filtered by search query AND sidebar filters (multi-select)."""
        # Start with all cards (unique by content hash)
        cards = list(self._cards_by_hash.values())

        # Apply sidebar filters (OR logic - show cards matching ANY selected filter)
        if "all" not in self._current_filters:
            filtered = []
            for filter_key in self._current_filters:
                if filter_key == "manual":
                    filtered.extend([c for c in cards if c.confidence == Confidence.MANUAL])
                elif filter_key == "high":
                    filtered.extend([c for c in cards if c.confidence == Confidence.HIGH])
                elif filter_key == "needs_review":
                    filtered.extend([c for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW)])
                elif filter_key == "errors":
                    filtered.extend([c for c in cards if c.error or c.confidence == Confidence.NONE])

            # Remove duplicates (card might match multiple filters)
            cards = list({c.id: c for c in filtered}.values())

        # Then apply search query
        query = self._search_ctrl.GetValue().lower().strip()
        if query:
            cards = [
                c for c in cards
                if query in c.filename.lower() or query in c.family_name.lower()
            ]

        return sorted(cards, key=lambda c: c.filename.lower())

    def _build_content_area(self) -> wx.SplitterWindow:
        """Build three-column Mail.app style layout: [sidebar | review | preview]."""
        # Main splitter: [sidebar | content]
        main_splitter = wx.SplitterWindow(
            self._panel,
            style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH
        )

        # Left: Filter sidebar
        self._sidebar = FilterSidebar(main_splitter, on_filter=self._on_filter_change)

        # Right: Nested splitter for [review | preview]
        content_splitter = wx.SplitterWindow(
            main_splitter,
            style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH
        )

        # Review panel with callbacks
        self._review_panel = ReviewPanelMasterDetail(
            content_splitter,
            on_select=self._on_card_select,
            on_ai_request=self._on_ai_request,
            on_name_change=self._on_name_change,
        )

        # Preview panel
        self._preview_panel = PreviewPanel(content_splitter)

        # Split nested content splitter vertically
        content_splitter.SplitVertically(self._review_panel, self._preview_panel)
        content_splitter.SetSashGravity(1.0)
        content_splitter.SetMinimumPaneSize(200)

        # Split main splitter vertically (sidebar | content)
        main_splitter.SplitVertically(self._sidebar, content_splitter)
        main_splitter.SetMinimumPaneSize(150)

        # Set initial sash positions after layout
        wx.CallAfter(lambda: main_splitter.SetSashPosition(150))  # Sidebar width
        wx.CallAfter(lambda: content_splitter.SetSashPosition(
            wx_styles.Layout.WINDOW_WIDTH - 150 - wx_styles.Layout.PREVIEW_WIDTH
        ))

        return main_splitter

    def _setup_drop_target(self):
        """Enable drag-and-drop on the frame."""
        drop_target = FileDropTarget(self._on_drop)
        self._frame.SetDropTarget(drop_target)

    def _on_drop(self, paths: list[Path]):
        """Handle dropped files and/or folders (multi-select).

        Args:
            paths: List of dropped paths (files or folders)
        """
        # Add to existing cards (don't replace)
        self._load_paths(paths, auto_process=True)

    def _setup_keyboard_shortcuts(self):
        """Set up keyboard accelerators."""
        # Menu shortcuts (Cmd+O, Cmd+W, Cmd+Q) handled by menu bar

        # Add Cmd+F for search
        search_id = wx.NewIdRef()
        self._frame.Bind(wx.EVT_MENU, lambda e: self._search_ctrl.SetFocus(), id=search_id)
        accel_tbl = wx.AcceleratorTable([
            (wx.ACCEL_CMD, ord('F'), search_id)
        ])
        self._frame.SetAcceleratorTable(accel_tbl)

        # Navigation shortcuts
        self._frame.Bind(wx.EVT_CHAR_HOOK, self._on_key_press)

    def _on_key_press(self, event):
        """Handle key presses for navigation."""
        key = event.GetKeyCode()
        focus = self._frame.FindFocus()

        # Handle Escape key - clear search if search has focus
        if key == wx.WXK_ESCAPE:
            if focus == self._search_ctrl:
                self._search_ctrl.SetValue("")
                self._frame.SetFocus()
            else:
                self._frame.SetFocus()  # Defocus text entry
            return

        # Skip if focus is in text entry (except search handled above)
        if isinstance(focus, (wx.TextCtrl, wx.ComboBox, wx.Choice)):
            event.Skip()
            return

        if key == wx.WXK_UP:
            self._review_panel.select_prev_card()
        elif key == wx.WXK_DOWN:
            self._review_panel.select_next_card()
        elif key == wx.WXK_LEFT:
            self._preview_panel._prev_page()
        elif key == wx.WXK_RIGHT:
            self._preview_panel._next_page()
        else:
            event.Skip()

    def _scan_for_pdfs(self, path: Path) -> list[Path]:
        """Recursively scan path for PDFs.

        Args:
            path: File or directory path

        Returns:
            List of PDF paths (absolute, resolved)
        """
        import os

        if path.is_file():
            if path.suffix.lower() == '.pdf':
                return [path.resolve()]
            return []

        # Recursive directory scan
        pdf_paths = []
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_paths.append((Path(root) / file).resolve())

        return sorted(pdf_paths)

    def _add_files_folders(self):
        """Add PDF files or folders (unified picker - multi-load architecture)."""
        # Show file dialog for PDFs (supports multi-select)
        dlg = wx.FileDialog(
            self._frame,
            message="Add PDF Files or Folders",
            defaultDir=str(Path.home()),
            wildcard="PDF files (*.pdf)|*.pdf|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE
        )

        if dlg.ShowModal() == wx.ID_OK:
            paths = [Path(p) for p in dlg.GetPaths()]
            self._load_paths(paths, auto_process=True)

        dlg.Destroy()

    def _load_paths(self, paths: list[Path], auto_process: bool = True):
        """Load PDFs from multiple files/folders (accumulating, not replacing).

        Args:
            paths: List of file or folder paths
            auto_process: Whether to start processing immediately
        """
        # 1. Scan all paths for PDFs (recursive for folders)
        all_pdfs = []
        for path in paths:
            all_pdfs.extend(self._scan_for_pdfs(path))

        # 2. Filter out already-loaded paths (same path won't load twice)
        new_pdfs = []
        skipped_pdfs = []

        for pdf_path in all_pdfs:
            if pdf_path in self._hash_by_path:
                # This exact path is already loaded (regardless of content)
                skipped_pdfs.append(pdf_path)
            else:
                # New path - will process and check hash later
                new_pdfs.append(pdf_path)

        # 3. Update state (accumulate, don't replace)
        self._pdf_files.extend(new_pdfs)

        # 4. Show feedback
        if new_pdfs or skipped_pdfs:
            msg = f"Found {len(new_pdfs)} new PDF{'s' if len(new_pdfs) != 1 else ''}"
            if skipped_pdfs:
                msg += f", skipped {len(skipped_pdfs)} already loaded"
            self._show_info_message(msg, wx.ICON_INFORMATION)
        elif not all_pdfs:
            self._show_info_message("No PDF files found", wx.ICON_WARNING, duration_ms=0)

        # 5. Process new PDFs
        if new_pdfs and auto_process:
            # Process only the new PDFs, not all accumulated PDFs
            temp_pdf_files = self._pdf_files
            self._pdf_files = new_pdfs
            self._start_processing()
            # After processing starts, restore full list
            self._pdf_files = temp_pdf_files

    def _clear_all(self):
        """Clear all loaded cards (from all sources) and reset UI."""
        # Clear all state (multi-load architecture)
        self._cards_by_hash.clear()
        self._hash_by_path.clear()
        self._pdf_files = []
        self._next_card_id = 0

        self._review_panel.load_cards([])
        self._preview_panel.clear()
        self._sidebar.update_card_counts([])

        # Disable toolbar buttons
        self._ai_all_btn.Enable(False)
        self._rename_btn.Enable(False)
        self._clear_btn.Enable(False)

        # Clear search filter
        self._search_ctrl.SetValue("")

        # Reset sidebar filters
        self._current_filters = ["all"]
        self._sidebar.set_filters(["all"])

        # Show confirmation
        self._show_info_message("All cards cleared", wx.ICON_INFORMATION)

        # Dismiss any info bar messages
        self._info_bar.Dismiss()

    def _start_processing(self):
        """Start processing PDFs in background."""
        if not self._pdf_files:
            return

        # Show busy cursor
        wx.BeginBusyCursor()

        # Disable toolbar buttons
        self._rename_btn.Enable(False)
        self._ai_all_btn.Enable(False)

        # Don't clear existing cards (multi-load architecture - accumulate!)
        # Note: Card deduplication happens in _process_cards during processing

        # Show progress dialog
        total = len(self._pdf_files)
        self._progress = ProgressDialog(self._frame, "Processing Cards", total)
        self._progress.Show()

        # Start background thread
        thread = threading.Thread(target=self._process_cards, daemon=True)
        thread.start()

    def _process_cards(self):
        """Process PDFs using multiprocessing.Pool (runs in background thread)."""
        import multiprocessing
        from multiprocessing import Pool, cpu_count

        # Set spawn method for PyInstaller
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            pass  # Already set

        total = len(self._pdf_files)
        num_workers = max(1, cpu_count() // 2)
        pdf_paths_str = [str(p) for p in self._pdf_files]

        try:
            with Pool(num_workers) as pool:
                for i, result_dict in enumerate(pool.imap_unordered(_process_pdf_worker, pdf_paths_str)):
                    pdf_path = Path(result_dict['pdf_path'])
                    file_hash = result_dict['file_hash']

                    # Content-based deduplication: check if we already have this content
                    if file_hash in self._cards_by_hash:
                        # Duplicate content - add path to existing card
                        existing_card = self._cards_by_hash[file_hash]
                        if pdf_path not in existing_card.file_paths:
                            existing_card.file_paths.append(pdf_path)
                        card = existing_card
                    else:
                        # New content - create new card
                        card_id = self._next_card_id
                        self._next_card_id += 1

                        # Convert dict to CardResult
                        card = self._dict_to_card(result_dict, card_id)
                        self._cards_by_hash[file_hash] = card

                    # Always update path → hash mapping
                    self._hash_by_path[pdf_path] = file_hash

                    # Update UI (thread-safe with wx.CallAfter)
                    wx.CallAfter(self._update_processing_progress, i + 1, total, card.filename)

        except Exception as e:
            print(f"Multiprocessing error: {e}")
            # Fallback to sequential processing
            self._process_cards_sequential()
            return

        wx.CallAfter(self._processing_complete)

    def _dict_to_card(self, result_dict: dict, card_id: int) -> CardResult:
        """Convert result dict from worker to CardResult object with assigned ID."""
        from PIL import Image

        pdf_path = Path(result_dict['pdf_path'])
        card = CardResult(
            id=card_id,
            file_paths=[pdf_path],  # Initialize with single path
            primary_path=pdf_path
        )

        card.file_hash = result_dict['file_hash']
        card.family_name = result_dict['family_name']
        card.alternates = result_dict['alternates']
        card.candidates = result_dict.get('candidates', [])
        card.remove_family = result_dict.get('remove_family', False)
        card.selected_candidate_id = result_dict.get('selected_candidate_id')
        card.method = result_dict.get('method', 'missing')
        card.ocr_text = result_dict['ocr_text']

        try:
            card.confidence = Confidence(result_dict['confidence'])
        except ValueError:
            card.confidence = Confidence.NONE

        # Deserialize images from bytes
        if result_dict['preview_image_bytes']:
            card.preview_image = Image.open(io.BytesIO(result_dict['preview_image_bytes']))

        if result_dict['page_images_bytes']:
            card.page_images = [
                Image.open(io.BytesIO(img_bytes))
                for img_bytes in result_dict['page_images_bytes']
            ]

        if result_dict['error']:
            card.error = result_dict['error']
            card.confidence = Confidence.NONE

        return card

    def _process_cards_sequential(self):
        """Fallback: sequential processing if multiprocessing fails."""
        total = len(self._pdf_files)
        for i, pdf_path in enumerate(self._pdf_files):
            try:
                file_hash = compute_file_hash(pdf_path)

                # Content-based deduplication: check if we already have this content
                if file_hash in self._cards_by_hash:
                    # Duplicate content - add path to existing card
                    existing_card = self._cards_by_hash[file_hash]
                    if pdf_path not in existing_card.file_paths:
                        existing_card.file_paths.append(pdf_path)
                    # Update path → hash mapping
                    self._hash_by_path[pdf_path] = file_hash
                    wx.CallAfter(self._update_processing_progress, i + 1, total, pdf_path.name)
                    continue  # Skip to next file

                # New content - create new card
                card_id = self._next_card_id
                self._next_card_id += 1
                card = CardResult(
                    id=card_id,
                    file_paths=[pdf_path],
                    primary_path=pdf_path
                )
                card.file_hash = file_hash
                card_state = get_card_state(file_hash)

                images = render_all_pages(pdf_path, dpi=200)
                if images:
                    card.preview_image = images[0]
                    card.page_images = images

                if card_state:
                    # Card exists - reprocess from raw data
                    reprocess_candidates_from_raw(card.file_hash)
                    card_state = get_card_state(card.file_hash)
                else:
                    # New file - run OCR and save raw
                    ocr_text = extract_text_all_pages(images)
                    card.ocr_text = ocr_text
                    save_raw_ocr(card.file_hash, ocr_text)

                    # Process candidates from raw
                    reprocess_candidates_from_raw(card.file_hash)
                    card_state = get_card_state(card.file_hash)

                # Load card state
                if card_state:
                    card.family_name = card_state.display_name
                    try:
                        card.confidence = Confidence(card_state.confidence)
                    except ValueError:
                        card.confidence = Confidence.MEDIUM
                    card.alternates = [c.family_name for c in card_state.candidates]
                    card.candidates = card_state.candidates
                    card.remove_family = card_state.remove_family
                    card.selected_candidate_id = card_state.selected_candidate_id
                    card.method = card_state.method

            except Exception as e:
                card.error = str(e)
                card.confidence = Confidence.NONE

            # Store by hash and update path mapping
            self._cards_by_hash[card.file_hash] = card
            self._hash_by_path[pdf_path] = card.file_hash
            wx.CallAfter(self._update_processing_progress, i + 1, total, pdf_path.name)

        wx.CallAfter(self._processing_complete)

    def _update_processing_progress(self, current: int, total: int, name: str):
        """Update progress dialog from background thread."""
        if hasattr(self, "_progress") and not self._progress.IsBeingDeleted():
            self._progress.update_progress(current, f"Processing: {name}")

    def _processing_complete(self):
        """Called when processing finishes."""
        # End busy cursor
        if wx.IsBusy():
            wx.EndBusyCursor()

        if hasattr(self, "_progress") and not self._progress.IsBeingDeleted():
            self._progress.finish()

        # Update sidebar with card counts
        all_cards = list(self._cards_by_hash.values())
        self._sidebar.update_card_counts(all_cards)

        # Load cards into review panel (respects search and sidebar filters)
        filtered_cards = self._get_filtered_cards()
        self._review_panel.load_cards(filtered_cards)

        # Enable toolbar buttons
        self._rename_btn.Enable(True)
        self._ai_all_btn.Enable(True)
        self._clear_btn.Enable(True)

        # Show success message with auto-dismiss
        count = len(self._cards_by_hash)
        self._show_info_message(
            f"Processing complete: {count} card{'s' if count != 1 else ''} loaded",
            wx.ICON_INFORMATION
        )

    def _on_card_select(self, card_id: int):
        """Handle card selection - update preview panel."""
        card = self._get_card_by_id(card_id)
        if not card:
            return

        if card.error:
            self._preview_panel.show_error(card.error, card.filename)
        elif card.page_images:
            self._preview_panel.show_images(card.page_images, card.filename)
        elif card.preview_image:
            self._preview_panel.show_images([card.preview_image], card.filename)
        else:
            self._preview_panel.clear()

    def _on_name_change(self, card_id: int, new_name: str):
        """Handle manual name edit in review panel."""
        card = self._get_card_by_id(card_id)
        if not card:
            return

        # Update card object
        if new_name:
            # Save original confidence before marking as manual
            if card.confidence != Confidence.MANUAL:
                card.original_confidence = card.confidence
            card.confidence = Confidence.MANUAL
            card.method = "manual"
            card.family_name = new_name
            card.manual_override = new_name
            card.selected_candidate_id = None

            # Save to database
            if card.file_hash:
                set_manual_name(card.file_hash, new_name, card.remove_family)

        # Update review panel
        self._review_panel.update_card(card_id, card)

    def _ensure_api_key(self) -> bool:
        """Check for an API key; prompt the user if missing. Returns True if a key is available."""
        if get_api_key():
            return True

        # Show info bar with warning (no auto-dismiss for important warnings)
        self._show_info_message(
            "API key not configured. Click Settings to add your Anthropic API key.",
            wx.ICON_WARNING,
            duration_ms=0  # Don't auto-dismiss warnings
        )

        # Also show dialog for immediate action
        api_key = show_api_key_dialog(self._frame)
        if api_key is not None and get_api_key() is not None:
            self._info_bar.Dismiss()
            return True

        return False

    def _on_ai_request(self, card_id: int):
        """Handle AI button click for single card."""
        card = self._get_card_by_id(card_id)
        if not card or card.error:
            return

        if not self._ensure_api_key():
            return

        if not card.page_images and not card.preview_image:
            wx.MessageBox(
                "No preview image available for AI analysis.",
                "No Image",
                wx.OK | wx.ICON_WARNING,
                self._frame
            )
            return

        # Disable AI button
        self._review_panel.set_ai_button_state(card_id, "disabled", "...")

        # Start background thread
        thread = threading.Thread(target=self._run_ai_analysis, args=(card_id, card), daemon=True)
        thread.start()

    def _run_ai_analysis(self, card_id: int, card: CardResult):
        """Run AI analysis for single card (runs in background thread)."""
        try:
            # Check if we already have AI candidates
            card_state = get_card_state(card.file_hash) if card.file_hash else None
            has_ai_candidates = False
            if card_state:
                has_ai_candidates = any(c.method == 'ai' for c in card_state.candidates)

            if not has_ai_candidates:
                # Run AI analysis
                ai_images = card.page_images or [card.preview_image]
                result = analyze_card_with_ai(ai_images)

                if card.file_hash and result.best_name:
                    save_raw_ai(card.file_hash, result.best_name, result.alternates)

                    # Reprocess all candidates from raw data (includes new AI results)
                    reprocess_candidates_from_raw(card.file_hash)

            # Reload state after reprocessing
            if card.file_hash:
                card_state = get_card_state(card.file_hash)
                if card_state:
                    card.family_name = card_state.display_name
                    card.confidence = Confidence(card_state.confidence)
                    card.alternates = [c.family_name for c in card_state.candidates]
                    card.candidates = card_state.candidates
                    card.remove_family = card_state.remove_family
                    card.selected_candidate_id = card_state.selected_candidate_id
                    card.method = card_state.method
                    card.ai_analyzed = True
                    # Only clear manual override if user hasn't manually edited
                    if not card.manual_override or card.method != "manual":
                        card.manual_override = ""
                else:
                    card.ai_analyzed = True
            else:
                card.confidence = Confidence.NONE
                card.ai_analyzed = True

        except Exception as e:
            msg = format_ai_error(e)
            wx.CallAfter(lambda: wx.MessageBox(msg, "AI Error", wx.OK | wx.ICON_ERROR, self._frame))

        wx.CallAfter(self._ai_analysis_complete, card_id, card)

    def _ai_analysis_complete(self, card_id: int, card: CardResult):
        """Update UI after AI analysis completes."""
        self._review_panel.update_card(card_id, card)
        self._review_panel.set_ai_button_state(card_id, "normal", "AI")

    def _start_ai_all(self):
        """Start AI analysis for all cards."""
        if not self._cards_by_id:
            return

        if not self._ensure_api_key():
            return

        # Show busy cursor
        wx.BeginBusyCursor()

        # Disable toolbar buttons
        self._ai_all_btn.Enable(False)
        self._rename_btn.Enable(False)

        # Show progress
        total = len(self._cards_by_hash)
        self._progress = ProgressDialog(self._frame, "AI Analysis", total)
        self._progress.Show()

        # Start background thread
        thread = threading.Thread(target=self._run_ai_all, daemon=True)
        thread.start()

    def _run_ai_all(self):
        """Run async AI batch processing in background thread."""
        asyncio.run(self._run_ai_all_async())

    async def _run_ai_all_async(self):
        """Async batch AI processing with concurrency limit."""
        import anthropic

        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent API calls
        completed = 0
        total = len(self._cards_by_hash)
        auth_failed = asyncio.Event()
        errors: list[tuple[str, str]] = []

        async def process_card(card_id: int, card: CardResult):
            nonlocal completed

            if card.error or (not card.page_images and not card.preview_image):
                completed += 1
                wx.CallAfter(self._update_ai_all_progress, completed, total, card.filename, card_id, None)
                return

            # Skip remaining cards if auth already failed
            if auth_failed.is_set():
                completed += 1
                wx.CallAfter(self._update_ai_all_progress, completed, total, card.filename, card_id, None)
                return

            async with semaphore:
                # Re-check after acquiring semaphore
                if auth_failed.is_set():
                    completed += 1
                    wx.CallAfter(self._update_ai_all_progress, completed, total, card.filename, card_id, None)
                    return

                try:
                    # Check if we already have AI candidates
                    card_state = get_card_state(card.file_hash) if card.file_hash else None
                    has_ai_candidates = False
                    if card_state:
                        has_ai_candidates = any(c.method == 'ai' for c in card_state.candidates)

                    if not has_ai_candidates:
                        # Run AI analysis
                        ai_images = card.page_images or [card.preview_image]
                        result = await analyze_card_with_ai_async(ai_images)

                        if card.file_hash and result.best_name:
                            save_raw_ai(card.file_hash, result.best_name, result.alternates)

                            # Reprocess all candidates from raw data (includes new AI results)
                            reprocess_candidates_from_raw(card.file_hash)

                    # Reload state after reprocessing
                    if card.file_hash:
                        card_state = get_card_state(card.file_hash)
                        if card_state:
                            card.family_name = card_state.display_name
                            card.confidence = Confidence(card_state.confidence)
                            card.alternates = [c.family_name for c in card_state.candidates]
                            card.candidates = card_state.candidates
                            card.remove_family = card_state.remove_family
                            card.selected_candidate_id = card_state.selected_candidate_id
                            card.method = card_state.method
                            card.ai_analyzed = True
                            # Only clear manual override if user hasn't manually edited
                            if not card.manual_override or card.method != "manual":
                                card.manual_override = ""
                        else:
                            card.ai_analyzed = True
                    else:
                        card.ai_analyzed = True

                except anthropic.AuthenticationError as e:
                    auth_failed.set()
                    errors.append((card.filename, format_ai_error(e)))
                except Exception as e:
                    errors.append((card.filename, format_ai_error(e)))

                completed += 1
                wx.CallAfter(self._update_ai_all_progress, completed, total, card.filename, card_id, card)

        # Process all cards concurrently with semaphore limiting concurrency
        await asyncio.gather(*[process_card(card.id, card) for card in self._cards_by_hash.values()])

        aborted = auth_failed.is_set()
        wx.CallAfter(self._ai_all_complete, errors, aborted)

    def _update_ai_all_progress(self, completed: int, total: int, filename: str, card_id: int, card: CardResult | None):
        """Update progress during batch AI processing."""
        if hasattr(self, "_progress") and not self._progress.IsBeingDeleted():
            self._progress.update_progress(completed, f"AI analyzing: {filename}")

        if card is not None:
            self._review_panel.update_card(card_id, card)

    def _ai_all_complete(self, errors: list[tuple[str, str]], auth_aborted: bool = False):
        """Called when batch AI processing completes."""
        # End busy cursor
        if wx.IsBusy():
            wx.EndBusyCursor()

        if hasattr(self, "_progress") and not self._progress.IsBeingDeleted():
            self._progress.finish()

        # Enable toolbar buttons
        self._ai_all_btn.Enable(True)
        self._rename_btn.Enable(True)

        # Update sidebar counts (confidence levels may have changed)
        all_cards = list(self._cards_by_hash.values())
        self._sidebar.update_card_counts(all_cards)

        if errors:
            suffix = " (auth error)" if auth_aborted else " (with errors)"
            dialog = ErrorListDialog(self._frame, f"AI Analysis{suffix}", errors, auth_aborted)
            dialog.ShowModal()
            dialog.Destroy()
        else:
            # Show success message with auto-dismiss
            count = len(self._cards_by_hash)
            self._show_info_message(
                f"AI analysis complete: {count} card{'s' if count != 1 else ''} analyzed",
                wx.ICON_INFORMATION
            )

    def _start_rename(self):
        """Start rename workflow."""
        cards = self._review_panel.get_cards()
        year_str = self._year_ctrl.GetValue().strip()

        if not year_str:
            wx.MessageBox("Please enter a year.", "No Year", wx.OK | wx.ICON_WARNING, self._frame)
            return

        # Build rename plan
        plan = build_rename_plan(cards, year_str)

        # Show confirmation dialog
        dialog = RenameConfirmDialog(self._frame, plan, year_str)
        if dialog.ShowModal() == wx.ID_OK:
            # Execute rename
            results = execute_rename_plan(plan)

            # Show completion
            errors = sum(1 for r in results if not r.success)
            title = "Rename Complete" if not errors else "Rename Complete (with errors)"
            completion = CompletionDialog(self._frame, title, results)
            completion.ShowModal()
            completion.Destroy()

            # Clear everything
            self._clear_all()

        dialog.Destroy()

    def _show_info_message(self, message: str, icon=wx.ICON_INFORMATION, duration_ms: int = 4000):
        """Show info bar message with auto-dismiss.

        Args:
            message: Message to display
            icon: Icon to show (wx.ICON_INFORMATION, wx.ICON_WARNING, wx.ICON_ERROR)
            duration_ms: Time in milliseconds before auto-dismiss (0 = no auto-dismiss)
        """
        self._info_bar.ShowMessage(message, icon)

        if duration_ms > 0:
            # Auto-dismiss after delay
            wx.CallLater(duration_ms, lambda: self._info_bar.Dismiss() if not self._info_bar.IsBeingDeleted() else None)

    def _on_close(self, event):
        """Handle window close event."""
        self._frame.Destroy()

    def run(self):
        """Start the application event loop."""
        self._frame.Show()


class FileDropTarget(wx.FileDropTarget):
    """Custom drop target for files/folders (supports multi-select)."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def OnDropFiles(self, x, y, filenames):
        """Handle dropped files (can be multiple)."""
        if not filenames:
            return False

        paths = [Path(f) for f in filenames]
        wx.CallAfter(self._callback, paths)  # Pass list, not single path
        return True
