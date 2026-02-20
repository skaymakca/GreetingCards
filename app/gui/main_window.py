"""wxPython Main Window for Greeting Cards application."""

import asyncio
import io
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import wx
import wx.adv

logger = logging.getLogger(__name__)

from app.gui import styles
from app.core.constants import PDF_DPI, AI_CONCURRENCY
from app.gui.styles import Color, Font, Layout
from app.gui.preview_panel import PreviewPanel
from app.gui.review_panel import ReviewPanelMasterDetail
from app.gui.filter_sidebar import FilterSidebar
from app.gui.dialogs import ProgressDialog, RenameConfirmDialog, CompletionDialog, ErrorListDialog
from app.gui.settings_dialog import create_preferences_editor, get_commit_hash
from app.gui.help_dialog import show_help
from app.gui.icons import load_sf_symbol, load_menu_icon
from app.gui.api_key_dialog import show_api_key_dialog
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
    from app.core.constants import PDF_DPI

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
        images = render_all_pages(pdf_path, dpi=PDF_DPI)
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
        else:
            # New file - run OCR and save raw data
            if images:
                ocr_text = extract_text_all_pages(images)
                result['ocr_text'] = ocr_text
                save_raw_ocr(file_hash, ocr_text)
                reprocess_candidates_from_raw(file_hash)

        # Load state after processing/reprocessing
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


def _load_drop_background() -> wx.Bitmap | None:
    """Load and process the drop target background image.

    Applies Brightness(0.75) and Color(0.5) via PIL, returns wx.Bitmap.
    """
    try:
        from PIL import Image, ImageEnhance

        # Resolve path for both dev and bundled app
        if getattr(sys, '_MEIPASS', None):
            img_path = Path(sys._MEIPASS) / "Drop Target Background.png"
        else:
            img_path = Path(__file__).resolve().parent.parent.parent / "Drop Target Background.png"

        if not img_path.exists():
            return None

        img = Image.open(img_path).convert("RGBA")
        img = ImageEnhance.Brightness(img).enhance(0.75)
        img = ImageEnhance.Color(img).enhance(0.5)

        # Convert PIL → wx.Bitmap
        width, height = img.size
        wx_img = wx.Image(width, height)
        wx_img.SetData(img.convert("RGB").tobytes())
        wx_img.SetAlpha(img.getchannel("A").tobytes())
        return wx_img.ConvertToBitmap()
    except Exception:
        return None


class _DropOverlay(wx.Panel):
    """Full content-area drop overlay with background image and drop zone hint."""

    def __init__(self, parent):
        super().__init__(parent)
        self._bg_source = _load_drop_background()
        self._bg_scaled: wx.Bitmap | None = None
        self._bg_cache_size: tuple[int, int] = (0, 0)
        self._drag_active = False
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_drag_active(self, on: bool) -> None:
        """Toggle blue drag-active border."""
        if self._drag_active == on:
            return
        self._drag_active = on
        self.Refresh()

    def _on_size(self, event: wx.SizeEvent) -> None:
        self._bg_scaled = None  # Invalidate cache
        self.Refresh()
        event.Skip()

    def _scale_bg(self, target_w: int, target_h: int) -> wx.Bitmap | None:
        """Scale bg image to fit target size (contain), caching result."""
        if self._bg_source is None:
            return None
        if self._bg_scaled and self._bg_cache_size == (target_w, target_h):
            return self._bg_scaled

        src_w = self._bg_source.GetWidth()
        src_h = self._bg_source.GetHeight()
        if src_w == 0 or src_h == 0 or target_w == 0 or target_h == 0:
            return None

        # Scale to fit (contain) within target
        scale = min(target_w / src_w, target_h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)

        img = self._bg_source.ConvertToImage()
        img = img.Scale(new_w, new_h, wx.IMAGE_QUALITY_HIGH)

        self._bg_scaled = img.ConvertToBitmap()
        self._bg_cache_size = (target_w, target_h)
        return self._bg_scaled

    def _on_paint(self, event: wx.PaintEvent) -> None:
        dc = wx.PaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        if not gc:
            return

        w, h = self.GetSize()

        # If drag active, draw solid blue border at panel edges
        if self._drag_active:
            inset = Layout.HIGHLIGHT_INSET
            edge_path = gc.CreatePath()
            edge_path.AddRoundedRectangle(inset, inset, w - inset * 2, h - inset * 2, Layout.HIGHLIGHT_RADIUS)
            gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(Color.ACCENT).Width(Layout.HIGHLIGHT_WIDTH)))
            gc.SetBrush(wx.NullBrush)
            gc.StrokePath(edge_path)

        # Background image at ~50% of overlay area, centered in overlay
        img_area_w = int(w * 0.5)
        img_area_h = int(h * 0.5)
        bg = self._scale_bg(img_area_w, img_area_h)
        if bg:
            bw = bg.GetWidth()
            bh = bg.GetHeight()
            img_x = (w - bw) / 2
            img_y = (h - bh) / 2 - h * 0.06  # Shift up slightly for text room
            gc.DrawBitmap(bg, img_x, img_y, bw, bh)
            img_bottom = img_y + bh
        else:
            img_bottom = h * 0.5

        # Text halfway between image bottom and overlay bottom
        text_center_y = (img_bottom + h) / 2

        # Primary text
        primary = "Drop PDF files or folders here"
        gc.SetFont(Font.BODY(), Color.TEXT_SECONDARY)
        tw, th = gc.GetTextExtent(primary)[:2]
        tx = (w - tw) / 2
        ty = text_center_y - th - 2
        gc.DrawText(primary, tx, ty)

        # Secondary text
        secondary = "or use File \u2192 Open (\u2318O)"
        gc.SetFont(Font.SMALL(), Color.TEXT_SECONDARY)
        tw2, th2 = gc.GetTextExtent(secondary)[:2]
        tx2 = (w - tw2) / 2
        ty2 = text_center_y + 2
        gc.DrawText(secondary, tx2, ty2)


class MainWindow:
    """Main application window with toolbar and content panels."""

    def __init__(self):
        # Create frame
        self._frame = wx.Frame(
            None,
            title="Greeting Cards",
            size=(styles.Layout.WINDOW_WIDTH, styles.Layout.WINDOW_HEIGHT)
        )
        self._frame.SetMinSize(Layout.MIN_FRAME_SIZE)

        # State - Content-based deduplication (multi-load architecture)
        self._next_card_id = 0  # Monotonically increasing ID counter
        self._cards_by_hash: dict[str, CardResult] = {}  # hash → Card (1:1)
        self._hash_by_path: dict[Path, str] = {}  # path → hash (many:1)
        self._pdf_files: list[Path] = []
        self._year = datetime.now().year - 1
        self._current_category_filters = ["all"]  # Current sidebar category filters
        self._current_folder_filters = ["all_folders"]  # Current sidebar folder filters

        # Preferences editor (lazy-init)
        self._prefs_editor = None
        self._progress: ProgressDialog | None = None

        # Debounce timer for name edits (fires _refresh_display after user stops typing)
        self._edit_debounce_timer = wx.Timer(self._frame)
        self._frame.Bind(wx.EVT_TIMER, self._on_edit_debounce_fire, self._edit_debounce_timer)

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

    def _setup_menu_bar(self) -> None:
        """Create native macOS menu bar with File, Edit, and Help menus."""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_OPEN, "Open...\tCtrl+O")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_PREFERENCES, "Settings...\tCtrl+,")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_CLOSE, "Close Window\tCtrl+W")
        file_menu.Append(wx.ID_EXIT, "Quit\tCtrl+Q")
        menubar.Append(file_menu, "&File")

        # Edit menu
        edit_menu = wx.Menu()

        self._find_menu_id = wx.NewIdRef()
        find_item = edit_menu.Append(self._find_menu_id, "Find...\tCtrl+F")
        find_icon = load_menu_icon("magnifyingglass")
        if find_icon:
            find_item.SetBitmap(find_icon)

        edit_menu.AppendSeparator()

        select_all_item = edit_menu.Append(wx.ID_SELECTALL, "Select All\tCtrl+A")
        select_all_icon = load_menu_icon("checkmark.circle")
        if select_all_icon:
            select_all_item.SetBitmap(select_all_icon)

        self._select_none_id = wx.NewIdRef()
        select_none_item = edit_menu.Append(self._select_none_id, "Select None\tCtrl+Shift+A")
        select_none_icon = load_menu_icon("circle")
        if select_none_icon:
            select_none_item.SetBitmap(select_none_icon)

        edit_menu.AppendSeparator()

        self._remove_menu_id = wx.NewIdRef()
        remove_item = edit_menu.Append(self._remove_menu_id, "Remove\tCtrl+Backspace")
        remove_icon = load_menu_icon("minus.circle")
        if remove_icon:
            remove_item.SetBitmap(remove_icon)

        menubar.Append(edit_menu, "&Edit")

        # Help menu
        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "About Greeting Cards")
        help_menu.AppendSeparator()
        help_menu.Append(wx.ID_HELP, "Greeting Cards Help")
        menubar.Append(help_menu, "&Help")

        self._frame.SetMenuBar(menubar)

        # Bind events
        self._frame.Bind(wx.EVT_MENU, lambda e: self._show_about(), id=wx.ID_ABOUT)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._add_files_folders(), id=wx.ID_OPEN)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._show_preferences(), id=wx.ID_PREFERENCES)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._frame.Close(), id=wx.ID_CLOSE)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._frame.Close(), id=wx.ID_EXIT)
        self._frame.Bind(wx.EVT_MENU, lambda e: show_help(self._frame), id=wx.ID_HELP)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._search_ctrl.SetFocus(), id=self._find_menu_id)
        self._frame.Bind(wx.EVT_MENU, self._on_select_all, id=wx.ID_SELECTALL)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._review_panel.select_none(), id=self._select_none_id)
        self._frame.Bind(wx.EVT_MENU, self._on_remove_menu, id=self._remove_menu_id)
        self._frame.Bind(wx.EVT_UPDATE_UI, self._on_update_remove_menu, id=self._remove_menu_id)

    def _on_select_all(self, event: wx.CommandEvent) -> None:
        """Handle Select All — route to text field if focused, else select all cards."""
        focus = self._frame.FindFocus()
        if isinstance(focus, wx.TextCtrl):
            focus.SelectAll()
        else:
            self._review_panel.select_all()

    def _show_preferences(self) -> None:
        """Show the native macOS Preferences editor."""
        if self._prefs_editor is None:
            self._prefs_editor = create_preferences_editor(on_db_reset=self._clear_all)
        self._prefs_editor.Show(self._frame)

    def _show_about(self) -> None:
        """Show the native macOS About dialog."""
        info = wx.adv.AboutDialogInfo()
        info.SetName("Greeting Cards")
        info.SetCopyright("(c) 2026")
        # Do not call SetIcon() — it forces the generic About box on macOS.
        # The native About panel automatically uses the app bundle icon
        # from Contents/Resources/icon.icns via CFBundleIconFile in Info.plist.
        # Only set the commit hash as the version — the native About panel
        # already shows CFBundleShortVersionString from Info.plist as the main version.
        commit = get_commit_hash()
        if commit:
            info.SetVersion(commit)
        wx.adv.AboutBox(info)

    def _build_ui(self) -> None:
        """Assemble main UI layout with toolbar and three-column layout."""
        # Main panel for content
        self._panel = wx.Panel(self._frame)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Toolbar (wx.ToolBar for proper tool semantics)
        self._build_toolbar()
        main_sizer.Add(self._toolbar, 0, wx.EXPAND)

        # Three-column content splitter
        self._content_splitter = self._build_content_area()
        main_sizer.Add(self._content_splitter, 1, wx.EXPAND)

        # Drop overlay (shown when no cards loaded — covers entire content area)
        self._drop_overlay = _DropOverlay(self._panel)
        main_sizer.Add(self._drop_overlay, 1, wx.EXPAND)

        # Initially show overlay, hide content
        self._content_splitter.Hide()

        self._panel.SetSizer(main_sizer)

    def _build_toolbar(self) -> None:
        """Build toolbar with SF Symbol icons."""
        toolbar = wx.ToolBar(self._panel, style=wx.TB_HORIZONTAL | wx.TB_NODIVIDER)
        toolbar.SetToolBitmapSize(wx.Size(Layout.TOOLBAR_ICON_SIZE, Layout.TOOLBAR_ICON_SIZE))

        # Add Files tool
        browse_bmp = load_sf_symbol("folder.badge.plus", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        self._browse_id = toolbar.AddTool(
            wx.ID_ANY, "Add Files", browse_bmp,
            shortHelp="Add PDF files or folders to analyze (can add from multiple sources)"
        ).GetId()

        toolbar.AddSeparator()

        # AI Analyze tool
        ai_bmp = load_sf_symbol("sparkles", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        self._ai_all_id = toolbar.AddTool(
            wx.ID_ANY, "AI Analyze", ai_bmp,
            shortHelp="Analyze all loaded cards with AI to extract family names"
        ).GetId()
        toolbar.EnableTool(self._ai_all_id, False)

        # Rename tool
        rename_bmp = load_sf_symbol("pencil", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        self._rename_id = toolbar.AddTool(
            wx.ID_ANY, "Rename", rename_bmp,
            shortHelp="Rename all files based on detected family names"
        ).GetId()
        toolbar.EnableTool(self._rename_id, False)

        # Clear tool
        clear_bmp = load_sf_symbol("xmark.circle", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        self._clear_id = toolbar.AddTool(
            wx.ID_ANY, "Clear", clear_bmp,
            shortHelp="Clear all loaded cards and reset the application"
        ).GetId()
        toolbar.EnableTool(self._clear_id, False)

        toolbar.AddSeparator()

        # Year controls
        year_label = wx.StaticText(toolbar, label="Year:")
        year_label.SetFont(styles.Font.BODY())
        toolbar.AddControl(year_label)
        self._year_ctrl = wx.TextCtrl(toolbar, value=str(self._year), size=(Layout.YEAR_WIDTH, -1))
        self._year_ctrl.SetToolTip("Year to use in renamed file names (e.g., 2024)")
        toolbar.AddControl(self._year_ctrl)

        toolbar.AddStretchableSpace()

        # Search control
        self._search_ctrl = wx.SearchCtrl(toolbar, style=wx.TE_PROCESS_ENTER, size=(Layout.SEARCH_WIDTH, -1))
        self._search_ctrl.ShowSearchButton(True)
        self._search_ctrl.ShowCancelButton(True)
        self._search_ctrl.SetDescriptiveText("Filter cards...")
        self._search_ctrl.SetToolTip("Filter cards by file name or family name")
        self._search_ctrl.Bind(wx.EVT_TEXT, self._on_search_text)
        self._search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_cancel)
        toolbar.AddControl(self._search_ctrl)

        toolbar.Realize()
        self._toolbar = toolbar

        # Bind tool events
        self._frame.Bind(wx.EVT_TOOL, lambda e: self._add_files_folders(), id=self._browse_id)
        self._frame.Bind(wx.EVT_TOOL, lambda e: self._start_ai_all(), id=self._ai_all_id)
        self._frame.Bind(wx.EVT_TOOL, lambda e: self._start_rename(), id=self._rename_id)
        self._frame.Bind(wx.EVT_TOOL, lambda e: self._clear_all(), id=self._clear_id)

    def _on_search_text(self, event: wx.CommandEvent) -> None:
        """Filter cards as user types in search field."""
        self._refresh_display()

    def _on_search_cancel(self, event: wx.CommandEvent) -> None:
        """Clear filter when cancel button clicked."""
        self._search_ctrl.ChangeValue("")
        self._refresh_display()

    def _on_category_filter_change(self, filter_keys: list[str]) -> None:
        """Handle sidebar category filter change.

        Args:
            filter_keys: List of selected category filters (e.g., ["high", "manual"])
        """
        self._current_category_filters = filter_keys
        self._refresh_display()

    def _on_folder_filter_change(self, filter_keys: list[str]) -> None:
        """Handle sidebar folder filter change.

        Args:
            filter_keys: List of selected folder filters (e.g., ["all_folders"] or ["/path/to/dir"])
        """
        self._current_folder_filters = filter_keys
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh sidebar counts and cards table using cross-filtered pipeline.

        Re-entrancy-free: sidebar count updates may auto-reset internal filter
        state (e.g. when all selected categories go to zero count). We sync
        MainWindow's filter state from sidebar after count updates, then
        recompute display. If display is still empty but search has results,
        auto-reset checkbox filters (keep search text).
        """
        search_cards = self._get_search_filtered_cards()

        # First pass: compute cross-filtered counts
        folder_filtered = self._apply_folder_filters(search_cards)
        category_filtered = self._apply_category_filters(search_cards)
        self._sidebar.update_category_counts(folder_filtered)
        self._sidebar.update_folder_counts(category_filtered)

        # Sync filter state back (sidebar may have auto-reset empty categories/folders)
        self._current_category_filters = self._sidebar.get_selected_category_filters()
        self._current_folder_filters = self._sidebar.get_selected_folder_filters()

        # Recompute display with synced filters
        folder_filtered = self._apply_folder_filters(search_cards)
        display_cards = self._apply_category_filters(folder_filtered)

        # Auto-reset checkbox filters when display is empty but cards exist
        if not display_cards and search_cards:
            self._current_category_filters = ["all"]
            self._current_folder_filters = self._sidebar.get_selected_folder_filters()
            self._sidebar.set_category_filters(["all"])
            self._sidebar.set_folder_filters(self._current_folder_filters)
            # Recompute with reset filters
            folder_filtered = self._apply_folder_filters(search_cards)
            display_cards = self._apply_category_filters(folder_filtered)
            # Update counts to reflect reset state
            self._sidebar.update_category_counts(folder_filtered)
            self._sidebar.update_folder_counts(display_cards)

        self._review_panel.load_cards(display_cards)

        # Toggle overlay vs content area based on whether any cards exist at all
        self._set_empty_state(not self._cards_by_hash)

    def _get_search_filtered_cards(self) -> list[CardResult]:
        """Get cards filtered by search query only."""
        cards = list(self._cards_by_hash.values())
        query = self._search_ctrl.GetValue().lower().strip()
        if query:
            cards = [
                c for c in cards
                if query in c.filename.lower() or query in c.family_name.lower()
            ]
        return cards

    def _apply_folder_filters(self, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar folder filters to a card list."""
        if "all_folders" in self._current_folder_filters:
            return cards
        folder_set = set(self._current_folder_filters)
        return [c for c in cards if any(str(p.parent) in folder_set for p in c.file_paths)]

    def _apply_category_filters(self, cards: list[CardResult]) -> list[CardResult]:
        """Apply sidebar category filters to a card list."""
        if "all" not in self._current_category_filters:
            filtered = []
            for filter_key in self._current_category_filters:
                if filter_key == "manual":
                    filtered.extend(c for c in cards if c.confidence == Confidence.MANUAL)
                elif filter_key == "high":
                    filtered.extend(c for c in cards if c.confidence == Confidence.HIGH)
                elif filter_key == "needs_review":
                    filtered.extend(c for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW))
                elif filter_key == "errors":
                    filtered.extend(c for c in cards if c.error or c.confidence == Confidence.NONE)
            cards = list({c.id: c for c in filtered}.values())
        return sorted(cards, key=lambda c: c.filename.lower())

    def _build_content_area(self) -> wx.SplitterWindow:
        """Build three-column Mail.app style layout: [sidebar | review | preview]."""
        # Main splitter: [sidebar | content]
        main_splitter = wx.SplitterWindow(
            self._panel,
            style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH
        )

        # Left: Filter sidebar
        self._sidebar = FilterSidebar(
            main_splitter,
            on_category_filter=self._on_category_filter_change,
            on_folder_filter=self._on_folder_filter_change,
        )

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
            on_card_edited=self._on_card_edited,
            on_remove=self._on_remove_card,
        )

        # Preview panel
        self._preview_panel = PreviewPanel(content_splitter)

        # Split nested content splitter vertically
        content_splitter.SplitVertically(self._review_panel, self._preview_panel)
        content_splitter.SetSashGravity(0.5)  # Both panes share extra space equally
        content_splitter.SetMinimumPaneSize(Layout.CONTENT_MIN_PANE)
        self._inner_splitter = content_splitter

        # Split main splitter vertically (sidebar | content)
        main_splitter.SplitVertically(self._sidebar, content_splitter)
        main_splitter.SetMinimumPaneSize(Layout.SIDEBAR_WIDTH)

        # Set initial sash positions after layout
        wx.CallAfter(lambda: main_splitter.SetSashPosition(Layout.SIDEBAR_WIDTH))

        return main_splitter

    def _apply_content_sash_position(self) -> None:
        """Set the content splitter sash to split review/preview equally."""
        def _apply():
            w = self._inner_splitter.GetSize().GetWidth()
            if w > 0:
                self._inner_splitter.SetSashPosition(w // 2)
        wx.CallAfter(_apply)

    def _set_empty_state(self, is_empty: bool) -> None:
        """Toggle between drop overlay (empty) and content splitter (has cards)."""
        self._drop_overlay.Show(is_empty)
        self._content_splitter.Show(not is_empty)
        self._panel.Layout()
        if not is_empty:
            # Re-apply sash position after showing — hiding resets it
            self._apply_content_sash_position()

    def _setup_drop_target(self) -> None:
        """Enable drag-and-drop on the frame."""
        drop_target = FileDropTarget(
            on_drop=self._on_drop,
            on_drag_over=self._on_drag_over,
            on_drag_leave=self._on_drag_leave,
        )
        self._frame.SetDropTarget(drop_target)

    def _on_drag_over(self) -> None:
        """Show drag highlight on overlay or review panel."""
        if self._drop_overlay.IsShown():
            self._drop_overlay.set_drag_active(True)
        else:
            self._review_panel.set_drag_highlight(True)

    def _on_drag_leave(self) -> None:
        """Hide drag highlight."""
        self._drop_overlay.set_drag_active(False)
        self._review_panel.set_drag_highlight(False)

    def _on_drop(self, paths: list[Path]) -> None:
        """Handle dropped files and/or folders (multi-select).

        Args:
            paths: List of dropped paths (files or folders)
        """
        # Clear drag highlights
        self._on_drag_leave()
        # Add to existing cards (don't replace)
        self._load_paths(paths, auto_process=True)

    def _setup_keyboard_shortcuts(self) -> None:
        """Set up keyboard accelerators."""
        # Menu shortcuts (Cmd+O, Cmd+W, Cmd+Q, Cmd+F, Cmd+A, Cmd+Shift+A) handled by menu bar

        # Navigation shortcuts
        self._frame.Bind(wx.EVT_CHAR_HOOK, self._on_key_press)

    def _on_key_press(self, event: wx.KeyEvent) -> None:
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
            self._preview_panel.prev_page()
        elif key == wx.WXK_RIGHT:
            self._preview_panel.next_page()
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

    def _add_files_folders(self) -> None:
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

    def _load_paths(self, paths: list[Path], auto_process: bool = True) -> None:
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
                msg += f"\nSkipped {len(skipped_pdfs)} already loaded"
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

    def _clear_all(self) -> None:
        """Clear all loaded cards (from all sources) and reset UI."""
        # Clear all state (multi-load architecture)
        self._cards_by_hash.clear()
        self._hash_by_path.clear()
        self._pdf_files = []
        self._next_card_id = 0

        self._review_panel.load_cards([])
        self._preview_panel.clear()
        self._sidebar.update_category_counts([])
        self._sidebar.update_folders([])
        self._set_empty_state(True)

        # Disable toolbar tools
        self._toolbar.EnableTool(self._ai_all_id, False)
        self._toolbar.EnableTool(self._rename_id, False)
        self._toolbar.EnableTool(self._clear_id, False)

        # Clear search filter
        self._search_ctrl.SetValue("")

        # Reset sidebar filters
        self._current_category_filters = ["all"]
        self._current_folder_filters = ["all_folders"]
        self._sidebar.set_category_filters(["all"])

        # Show confirmation
        self._show_info_message("All cards cleared", wx.ICON_INFORMATION)

    def _start_processing(self) -> None:
        """Start processing PDFs in background."""
        if not self._pdf_files:
            return

        # Show busy cursor
        wx.BeginBusyCursor()

        # Disable toolbar tools
        self._toolbar.EnableTool(self._rename_id, False)
        self._toolbar.EnableTool(self._ai_all_id, False)

        # Don't clear existing cards (multi-load architecture - accumulate!)
        # Note: Card deduplication happens in _process_cards during processing

        # Show progress dialog
        total = len(self._pdf_files)
        self._progress = ProgressDialog(self._frame, "Processing Cards", total)
        self._progress.Show()

        # Start background thread
        thread = threading.Thread(target=self._process_cards, daemon=True)
        thread.start()

    def _process_cards(self) -> None:
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
            logger.warning("Multiprocessing error: %s", e)
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

    def _process_cards_sequential(self) -> None:
        """Fallback: sequential processing if multiprocessing fails."""
        total = len(self._pdf_files)
        for i, pdf_path in enumerate(self._pdf_files):
            card = None
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

                images = render_all_pages(pdf_path, dpi=PDF_DPI)
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
                if card is None:
                    # Failed before card was created (e.g. hash error) — skip
                    wx.CallAfter(self._update_processing_progress, i + 1, total, pdf_path.name)
                    continue
                card.error = str(e)
                card.confidence = Confidence.NONE

            # Store by hash and update path mapping
            self._cards_by_hash[card.file_hash] = card
            self._hash_by_path[pdf_path] = card.file_hash
            wx.CallAfter(self._update_processing_progress, i + 1, total, pdf_path.name)

        wx.CallAfter(self._processing_complete)

    def _update_processing_progress(self, current: int, total: int, name: str) -> None:
        """Update progress dialog from background thread."""
        if self._progress is not None and not self._progress.IsBeingDeleted():
            self._progress.update_progress(current, f"Processing: {name}")

    def _derive_folders(self) -> list[Path]:
        """Derive sorted unique source folders from all loaded cards."""
        return sorted({p.parent for card in self._cards_by_hash.values() for p in card.file_paths})

    def _processing_complete(self) -> None:
        """Called when processing finishes."""
        # End busy cursor
        if wx.IsBusy():
            wx.EndBusyCursor()

        if self._progress is not None and not self._progress.IsBeingDeleted():
            self._progress.finish()

        # Update folder section FIRST (creates checkboxes before _refresh_display populates counts)
        self._sidebar.update_folders(self._derive_folders())
        # Sync main window state — update_folders resets sidebar to "all_folders"
        # but doesn't fire callback, so we must sync manually
        self._current_folder_filters = self._sidebar.get_selected_folder_filters()

        # Now refresh display (folder checkboxes exist, counts will populate)
        self._refresh_display()

        # Enable toolbar tools
        self._toolbar.EnableTool(self._rename_id, True)
        self._toolbar.EnableTool(self._ai_all_id, True)
        self._toolbar.EnableTool(self._clear_id, True)

        # Show success message with auto-dismiss
        count = len(self._cards_by_hash)
        self._show_info_message(
            f"Processing complete\n{count} card{'s' if count != 1 else ''} loaded",
            wx.ICON_INFORMATION
        )

    def _on_card_select(self, card_id: int | None) -> None:
        """Handle card selection - update preview panel."""
        if card_id is None:
            self._preview_panel.clear()
            return

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

    def _on_name_change(self, card_id: int, new_name: str) -> None:
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
        else:
            # User cleared the name — revert to pre-manual state
            card.manual_override = ""
            if card.original_confidence is not None:
                card.confidence = card.original_confidence
                card.original_confidence = None
            elif card.confidence == Confidence.MANUAL:
                card.confidence = Confidence.NONE
            # Revert method based on remaining data
            if card.ai_analyzed:
                card.method = "ai"
            elif card.family_name:
                card.method = "ocr"
            else:
                card.method = "missing"

            # Clear manual name in database
            if card.file_hash:
                set_manual_name(card.file_hash, "", card.remove_family)

        # Update review panel
        self._review_panel.update_card(card_id, card)

        # Debounce: restart 1-second timer on each keystroke
        self._edit_debounce_timer.Stop()
        self._edit_debounce_timer.StartOnce(Layout.DEBOUNCE_MS)

    def _on_card_edited(self, card_id: int) -> None:
        """Handle discrete card edits (e.g. candidate selection) that change confidence."""
        self._refresh_display()

    def _on_remove_card(self, file_hash: str) -> None:
        """Remove a card from the in-memory table (non-destructive — does not delete files).

        Args:
            file_hash: The content hash of the card to remove
        """
        card = self._cards_by_hash.get(file_hash)
        if not card:
            return

        # Remove all path → hash mappings for this card
        for path in card.file_paths:
            self._hash_by_path.pop(path, None)
            if path in self._pdf_files:
                self._pdf_files.remove(path)

        # Remove the card itself
        del self._cards_by_hash[file_hash]

        # Refresh display (handles filter counts, list reload, empty state)
        self._refresh_display()

    def _on_remove_menu(self, event: wx.CommandEvent) -> None:
        """Handle Edit > Remove — remove all selected cards."""
        for card_id in list(self._review_panel._selected_card_ids):
            card = self._get_card_by_id(card_id)
            if card and card.file_hash:
                self._on_remove_card(card.file_hash)

    def _on_update_remove_menu(self, event: wx.UpdateUIEvent) -> None:
        """Enable Remove menu item only when cards are selected."""
        event.Enable(bool(self._review_panel._selected_card_ids))

    def _on_edit_debounce_fire(self, event: wx.TimerEvent) -> None:
        """Fire after user stops typing for 1 second — refresh filters."""
        self._refresh_display()

    def _ensure_api_key(self) -> bool:
        """Check for an API key; prompt the user if missing. Returns True if a key is available."""
        if get_api_key():
            return True

        # Show info bar with warning (no auto-dismiss for important warnings)
        self._show_info_message(
            "API key not configured\nUse Settings to add your Anthropic API key",
            wx.ICON_WARNING,
            duration_ms=0  # Don't auto-dismiss warnings
        )

        # Also show dialog for immediate action
        api_key = show_api_key_dialog(self._frame)
        if api_key is not None:
            self._sidebar.dismiss_notification()
            return True

        return False

    def _on_ai_request(self, card_id: int) -> None:
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

    def _run_ai_analysis(self, card_id: int, card: CardResult) -> None:
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
                    reprocess_candidates_from_raw(card.file_hash)

            self._load_card_state_from_db(card)

        except Exception as e:
            msg = format_ai_error(e)
            wx.CallAfter(lambda: wx.MessageBox(msg, "AI Error", wx.OK | wx.ICON_ERROR, self._frame))

        wx.CallAfter(self._ai_analysis_complete, card_id, card)

    @staticmethod
    def _load_card_state_from_db(card: CardResult) -> None:
        """Load card state from database into a CardResult object.

        Reads the current card_state for the card's file_hash and updates
        the card's display fields (family_name, confidence, candidates, etc.).
        """
        if not card.file_hash:
            card.confidence = Confidence.NONE
            card.ai_analyzed = True
            return

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

    def _ai_analysis_complete(self, card_id: int, card: CardResult) -> None:
        """Update UI after AI analysis completes."""
        self._review_panel.update_card(card_id, card)
        self._review_panel.set_ai_button_state(card_id, "normal", "AI")
        self._refresh_display()

    def _start_ai_all(self) -> None:
        """Start AI analysis for all cards."""
        if not self._cards_by_hash:
            return

        if not self._ensure_api_key():
            return

        # Show busy cursor
        wx.BeginBusyCursor()

        # Disable toolbar tools
        self._toolbar.EnableTool(self._ai_all_id, False)
        self._toolbar.EnableTool(self._rename_id, False)

        # Show progress
        total = len(self._cards_by_hash)
        self._progress = ProgressDialog(self._frame, "AI Analysis", total)
        self._progress.Show()

        # Start background thread
        thread = threading.Thread(target=self._run_ai_all, daemon=True)
        thread.start()

    def _run_ai_all(self) -> None:
        """Run async AI batch processing in background thread."""
        asyncio.run(self._run_ai_all_async())

    async def _run_ai_all_async(self) -> None:
        """Async batch AI processing with concurrency limit."""
        import anthropic

        semaphore = asyncio.Semaphore(AI_CONCURRENCY)
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
                            reprocess_candidates_from_raw(card.file_hash)

                    self._load_card_state_from_db(card)

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

    def _update_ai_all_progress(self, completed: int, total: int, filename: str, card_id: int, card: CardResult | None) -> None:
        """Update progress during batch AI processing."""
        if self._progress is not None and not self._progress.IsBeingDeleted():
            self._progress.update_progress(completed, f"AI analyzing: {filename}")

        if card is not None:
            self._review_panel.update_card(card_id, card)

    def _ai_all_complete(self, errors: list[tuple[str, str]], auth_aborted: bool = False) -> None:
        """Called when batch AI processing completes."""
        # End busy cursor
        if wx.IsBusy():
            wx.EndBusyCursor()

        if self._progress is not None and not self._progress.IsBeingDeleted():
            self._progress.finish()

        # Enable toolbar tools
        self._toolbar.EnableTool(self._ai_all_id, True)
        self._toolbar.EnableTool(self._rename_id, True)

        # Update sidebar counts and cards table (confidence levels may have changed)
        self._refresh_display()

        if errors:
            suffix = " (auth error)" if auth_aborted else " (with errors)"
            dialog = ErrorListDialog(self._frame, f"AI Analysis{suffix}", errors, auth_aborted)
            dialog.ShowModal()
            dialog.Destroy()
        else:
            # Show success message with auto-dismiss
            count = len(self._cards_by_hash)
            self._show_info_message(
                f"Analysis complete\n{count} card{'s' if count != 1 else ''} analyzed",
                wx.ICON_INFORMATION
            )

    def _start_rename(self) -> None:
        """Start rename workflow."""
        cards = self._review_panel.get_cards()
        year_str = self._year_ctrl.GetValue().strip()

        if not year_str or not year_str.isdigit() or len(year_str) != 4:
            wx.MessageBox("Please enter a valid 4-digit year.", "Invalid Year", wx.OK | wx.ICON_WARNING, self._frame)
            return

        # Build rename plan
        plan = build_rename_plan(cards, year_str)

        # Show confirmation dialog
        dialog = RenameConfirmDialog(self._frame, plan, year_str)
        if dialog.ShowModal() == wx.ID_OK:
            # Execute rename
            results = execute_rename_plan(plan)

            # Update _hash_by_path mapping for renamed files
            for result in results:
                if result.success and result.message == "Renamed":
                    if result.old_path in self._hash_by_path:
                        file_hash = self._hash_by_path.pop(result.old_path)
                        self._hash_by_path[result.new_path] = file_hash

            # Show completion
            errors = sum(1 for r in results if not r.success)
            title = "Rename Complete" if not errors else "Rename Complete (with errors)"
            completion = CompletionDialog(self._frame, title, results)
            completion.ShowModal()
            completion.Destroy()

            # Remove successfully processed paths from cards
            self._remove_completed_results(results)

        dialog.Destroy()

    def _remove_completed_results(self, results: list) -> None:
        """Remove successfully renamed/skip_same paths from cards; drop empty cards.

        Paths from results with status "Renamed", "Already named correctly",
        or duplicates are considered resolved. Paths that failed or had no name
        are kept so the user can address them.
        """
        # Collect paths to remove (use new_path — that's where the file is now)
        resolved_messages = {"Renamed", "Already named correctly"}
        paths_to_remove: set[Path] = set()
        for r in results:
            if r.success and r.message in resolved_messages:
                paths_to_remove.add(r.new_path)

        if not paths_to_remove:
            return

        # Remove paths from cards and tracking dicts
        for path in paths_to_remove:
            file_hash = self._hash_by_path.pop(path, None)
            if path in self._pdf_files:
                self._pdf_files.remove(path)
            if file_hash and file_hash in self._cards_by_hash:
                card = self._cards_by_hash[file_hash]
                if path in card.file_paths:
                    card.file_paths.remove(path)
                # Remove card if it has no remaining paths
                if not card.file_paths:
                    del self._cards_by_hash[file_hash]

        # Rebuild folder list and refresh display
        self._sidebar.update_folders(self._derive_folders())
        self._current_folder_filters = self._sidebar.get_selected_folder_filters()
        self._refresh_display()

        # Disable toolbar tools if no cards remain
        if not self._cards_by_hash:
            self._toolbar.EnableTool(self._ai_all_id, False)
            self._toolbar.EnableTool(self._rename_id, False)
            self._toolbar.EnableTool(self._clear_id, False)
            self._search_ctrl.SetValue("")

    def _show_info_message(self, message: str, icon: int = wx.ICON_INFORMATION, duration_ms: int = Layout.INFO_DISMISS_MS) -> None:
        """Show notification in sidebar bottom.

        Args:
            message: Message to display
            icon: Icon to show (wx.ICON_INFORMATION, wx.ICON_WARNING, wx.ICON_ERROR)
            duration_ms: Time in milliseconds before auto-dismiss (0 = no auto-dismiss)
        """
        self._sidebar.show_notification(message, icon, duration_ms)

    def _on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close event."""
        self._edit_debounce_timer.Stop()
        if self._prefs_editor is not None:
            self._prefs_editor.Dismiss()
        self._frame.Destroy()

    def run(self) -> None:
        """Start the application event loop."""
        self._frame.Show()


class FileDropTarget(wx.FileDropTarget):
    """Custom drop target for files/folders with drag-over feedback."""

    def __init__(
        self,
        on_drop: Callable[[list[Path]], None],
        on_drag_over: Callable[[], None] | None = None,
        on_drag_leave: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._on_drop = on_drop
        self._on_drag_over = on_drag_over
        self._on_drag_leave = on_drag_leave

    def OnDropFiles(self, x: int, y: int, filenames: list[str]) -> bool:
        """Handle dropped files (can be multiple)."""
        if not filenames:
            return False

        paths = [Path(f) for f in filenames]
        wx.CallAfter(self._on_drop, paths)
        return True

    def OnDragOver(self, x: int, y: int, defResult: int) -> int:
        """Show drag highlight when files are dragged over."""
        if self._on_drag_over:
            self._on_drag_over()
        return defResult

    def OnLeave(self) -> None:
        """Hide drag highlight when drag leaves."""
        if self._on_drag_leave:
            self._on_drag_leave()
