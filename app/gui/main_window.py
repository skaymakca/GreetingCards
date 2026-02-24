"""wxPython Main Window for Greeting Cards application."""

import asyncio
import io
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import wx
import wx.adv

logger = logging.getLogger(__name__)

from app.core.constants import AI_CONCURRENCY, OCR_WORKERS
from app.gui.styles import Color, Font, Layout
from app.gui.preview_panel import PreviewPanel
from app.gui.review_panel import ReviewPanelMasterDetail
from app.gui.filter_sidebar import FilterSidebar
from app.gui.dialogs import ProgressDialog, RenameConfirmDialog, CompletionDialog, ErrorListDialog
from app.gui.settings_dialog import create_preferences_editor, get_commit_hash
from app.gui.help_dialog import show_help
from app.gui.changelog_dialog import show_changelog
from app.gui.licenses_dialog import show_licenses
from app.gui.icons import load_sf_symbol, load_menu_icon
from app.gui.api_key_dialog import show_api_key_dialog
from app.models.card import CardResult, Confidence, PdfWorkerResult, RenameResult
from app.core.pdf_worker import process_pdf_worker
from app.core.ai_analyzer import analyze_card_with_ai_async, format_ai_error
from app.core.config import get_api_key
from app.core.renamer import build_rename_plan, execute_rename_plan
from app.core.database import (
    get_card_state, save_raw_ai,
    set_manual_name, reprocess_candidates_from_raw, clear_ai_results
)

# Messages indicating a rename result is resolved (path moved or already correct)
_RESOLVED_MESSAGES = {"Renamed", "Already named correctly"}


def _plural(count: int, word: str) -> str:
    """Return e.g. '3 cards' or '1 card'."""
    return f"{count} {word}{'s' if count != 1 else ''}"


def _load_drop_background() -> wx.Bitmap | None:
    """Load and process the drop target background image.

    Applies Brightness(0.75) and Color(0.5) via PIL, returns wx.Bitmap.
    """
    try:
        from PIL import Image, ImageEnhance

        from app.core.paths import get_runtime_content_path
        img_path = get_runtime_content_path("images/drop-target-background.png")

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
        logger.debug("Failed to load drop background image")
        return None


class _DropOverlay(wx.Panel):
    """Full content-area drop overlay with background image and drop zone hint."""

    def __init__(self, parent: wx.Window) -> None:
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

        # Background image scaled to fraction of overlay area, centered
        img_area_w = int(w * Layout.DROP_BG_SCALE)
        img_area_h = int(h * Layout.DROP_BG_SCALE)
        bg = self._scale_bg(img_area_w, img_area_h)
        if bg:
            bw = bg.GetWidth()
            bh = bg.GetHeight()
            img_x = (w - bw) / 2
            img_y = (h - bh) / 2 - h * Layout.DROP_IMG_SHIFT
            gc.DrawBitmap(bg, img_x, img_y, bw, bh)
            img_bottom = img_y + bh
        else:
            img_bottom = h * Layout.DROP_BG_SCALE

        # Text halfway between image bottom and overlay bottom
        text_center_y = (img_bottom + h) / 2

        # Primary text
        primary = "Drop PDF files or folders here"
        gc.SetFont(Font.BODY(), Color.TEXT_SECONDARY)
        tw, th = gc.GetTextExtent(primary)[:2]
        tx = (w - tw) / 2
        ty = text_center_y - th - Layout.DROP_TEXT_GAP
        gc.DrawText(primary, tx, ty)

        # Secondary text
        secondary = "or use File \u2192 Open (\u2318O)"
        gc.SetFont(Font.SMALL(), Color.TEXT_SECONDARY)
        tw2, th2 = gc.GetTextExtent(secondary)[:2]
        tx2 = (w - tw2) / 2
        ty2 = text_center_y + Layout.DROP_TEXT_GAP
        gc.DrawText(secondary, tx2, ty2)


class MainWindow:
    """Main application window with toolbar and content panels."""

    def __init__(self) -> None:
        # Create frame
        self._frame = wx.Frame(
            None,
            title="Greeting Cards",
            size=(Layout.WINDOW_WIDTH, Layout.WINDOW_HEIGHT)
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
        self._ai_target_cards: list[CardResult] = []  # Cards for current AI batch
        self._processing_files: list[Path] = []  # Files currently being processed
        self._state_lock = threading.Lock()  # Protects _cards_by_hash, _hash_by_path, _next_card_id

        # Preferences editor (lazy-init)
        self._prefs_editor: wx.PreferencesEditor | None = None
        self._progress: ProgressDialog | None = None

        # Debounce timer for name edits (fires _refresh_display after user stops typing)
        self._edit_debounce_timer = wx.Timer(self._frame)
        self._frame.Bind(wx.EVT_TIMER, self._on_edit_debounce_fire, self._edit_debounce_timer)

        # Build UI
        self._setup_menu_bar()
        self._build_ui()
        self._setup_drop_target()
        self._setup_keyboard_shortcuts()

        # Dark mode detection + initial color refresh
        from app.gui import appearance
        Color.refresh()
        appearance.start_observer(self._on_appearance_changed)

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

        self._ai_menu_id = wx.NewIdRef()
        ai_item = file_menu.Append(self._ai_menu_id, "AI Analyze\tCtrl+Shift+I")
        ai_icon = load_menu_icon("sparkles")
        if ai_icon:
            ai_item.SetBitmap(ai_icon)

        self._clear_ai_menu_id = wx.NewIdRef()
        clear_ai_item = file_menu.Append(self._clear_ai_menu_id, "Clear AI Results")
        clear_ai_icon = load_menu_icon("eraser")
        if clear_ai_icon:
            clear_ai_item.SetBitmap(clear_ai_icon)

        file_menu.AppendSeparator()

        self._rename_menu_id = wx.NewIdRef()
        rename_item = file_menu.Append(self._rename_menu_id, "Rename Files...\tCtrl+R")
        rename_icon = load_menu_icon("pencil")
        if rename_icon:
            rename_item.SetBitmap(rename_icon)

        self._clear_menu_id = wx.NewIdRef()
        clear_item = file_menu.Append(self._clear_menu_id, "Clear All")
        clear_icon = load_menu_icon("xmark.circle")
        if clear_icon:
            clear_item.SetBitmap(clear_icon)

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
        self._whats_new_id = wx.NewIdRef()
        help_menu.Append(self._whats_new_id, "What's New")
        self._licenses_id = wx.NewIdRef()
        help_menu.Append(self._licenses_id, "Licenses")
        menubar.Append(help_menu, "&Help")

        self._frame.SetMenuBar(menubar)

        # Bind events
        self._frame.Bind(wx.EVT_MENU, lambda e: self._show_about(), id=wx.ID_ABOUT)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._add_files_folders(), id=wx.ID_OPEN)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._show_preferences(), id=wx.ID_PREFERENCES)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._frame.Close(), id=wx.ID_CLOSE)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._frame.Close(), id=wx.ID_EXIT)
        self._frame.Bind(wx.EVT_MENU, lambda e: show_changelog(self._frame), id=self._whats_new_id)
        self._frame.Bind(wx.EVT_MENU, lambda e: show_help(self._frame), id=wx.ID_HELP)
        self._frame.Bind(wx.EVT_MENU, lambda e: show_licenses(self._frame), id=self._licenses_id)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._search_ctrl.SetFocus(), id=self._find_menu_id)
        self._frame.Bind(wx.EVT_MENU, self._on_select_all, id=wx.ID_SELECTALL)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._review_panel.select_none(), id=self._select_none_id)
        self._frame.Bind(wx.EVT_MENU, self._on_remove_menu, id=self._remove_menu_id)
        self._frame.Bind(wx.EVT_UPDATE_UI, self._on_update_remove_menu, id=self._remove_menu_id)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._start_ai_all(), id=self._ai_menu_id)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._start_rename(), id=self._rename_menu_id)
        self._frame.Bind(wx.EVT_MENU, lambda e: self._clear_all(), id=self._clear_menu_id)
        self._frame.Bind(wx.EVT_MENU, self._on_clear_ai_results, id=self._clear_ai_menu_id)
        self._frame.Bind(wx.EVT_UPDATE_UI, self._on_update_action_menu, id=self._ai_menu_id)
        self._frame.Bind(wx.EVT_UPDATE_UI, self._on_update_action_menu, id=self._rename_menu_id)
        self._frame.Bind(wx.EVT_UPDATE_UI, self._on_update_action_menu, id=self._clear_menu_id)
        self._frame.Bind(wx.EVT_UPDATE_UI, self._on_update_action_menu, id=self._clear_ai_menu_id)

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
        info.SetCopyright(f"(c) {datetime.now().year}")
        # Do not call SetIcon() — it forces the generic About box on macOS.
        # The native About panel automatically uses the app bundle icon
        # from Contents/Resources/icon.icns via CFBundleIconFile in Info.plist.
        # Only set the commit hash as the version — the native About panel
        # already shows CFBundleShortVersionString from Info.plist as the main version.
        info.SetDescription("Open-source licenses: Help > Licenses")
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
            shortHelp="Analyze cards with AI to extract family names (\u21e7\u2318I)"
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
        year_label.SetFont(Font.BODY())
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

    def _enable_action_tools(self, *, ai: bool | None = None, rename: bool | None = None, clear: bool | None = None) -> None:
        """Enable or disable action toolbar tools. Pass None to leave unchanged."""
        if ai is not None:
            self._toolbar.EnableTool(self._ai_all_id, ai)
        if rename is not None:
            self._toolbar.EnableTool(self._rename_id, rename)
        if clear is not None:
            self._toolbar.EnableTool(self._clear_id, clear)

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
            filtered: list[CardResult] = []
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
            on_ai_analyze=lambda cards: self._start_ai_all(cards=cards),
        )

        # Preview panel
        self._preview_panel = PreviewPanel(content_splitter)

        # Split nested content splitter vertically
        content_splitter.SplitVertically(self._review_panel, self._preview_panel)
        content_splitter.SetSashGravity(Layout.CONTENT_SASH_GRAVITY)  # Cards panel gets slightly more space
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
        def _apply() -> None:
            w = self._inner_splitter.GetSize().GetWidth()
            if w > 0:
                self._inner_splitter.SetSashPosition(int(w * Layout.CONTENT_SASH_GRAVITY))
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
        if path.is_file():
            if path.suffix.lower() == '.pdf':
                return [path.resolve()]
            return []

        # Recursive directory scan
        pdf_paths = [p.resolve() for p in path.rglob("*.[pP][dD][fF]")]
        return sorted(pdf_paths)

    def _add_files_folders(self) -> None:
        """Add PDF files or folders (unified picker - multi-load architecture)."""
        from app.gui.utils import open_files_and_folders

        paths = open_files_and_folders("Add PDF Files or Folders", ["pdf"])
        if paths:
            self._load_paths(paths, auto_process=True)

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
            msg = f"Found {_plural(len(new_pdfs), 'new PDF')}"
            if skipped_pdfs:
                msg += f"\nSkipped {len(skipped_pdfs)} already loaded"
            self._show_info_message(msg, wx.ICON_INFORMATION)
        elif not all_pdfs:
            self._show_info_message("No PDF files found", wx.ICON_WARNING, duration_ms=0)

        # 5. Process new PDFs
        if new_pdfs and auto_process:
            self._start_processing(new_pdfs)

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
        self._enable_action_tools(ai=False, rename=False, clear=False)

        # Clear search filter
        self._search_ctrl.SetValue("")

        # Reset sidebar filters
        self._current_category_filters = ["all"]
        self._current_folder_filters = ["all_folders"]
        self._sidebar.set_category_filters(["all"])

        # Show confirmation
        self._show_info_message("All cards cleared", wx.ICON_INFORMATION)

    def _on_clear_ai_results(self, event: wx.CommandEvent) -> None:
        """Clear AI results for selected or visible cards."""
        if not self._cards_by_hash:
            return

        cards, scope = self._get_target_cards()
        if not cards:
            return

        n = len(cards)
        scope_word = "selected" if scope == "selected" else "visible"
        result = wx.MessageBox(
            f"This will clear AI results for {n} {scope_word} card(s).\n\n"
            "OCR results, manual entries, and preferences preserved.\n"
            "Cards can be re-analyzed afterwards.\n\n"
            "Continue?",
            "Clear AI Results",
            wx.YES_NO | wx.ICON_QUESTION,
            self._frame
        )
        if result != wx.YES:
            return

        file_hashes = [card.file_hash for card in cards if card.file_hash]
        changed = clear_ai_results(file_hashes)

        # Reload card state from DB
        for card in cards:
            if card.file_hash:
                self._load_card_state_from_db(card)

        self._refresh_display()
        self._show_info_message(
            f"AI results cleared for {n} card(s). {changed} reverted to OCR names.",
            wx.ICON_INFORMATION
        )

    def _start_processing(self, files: list[Path] | None = None) -> None:
        """Start processing PDFs in background.

        Args:
            files: Specific files to process. If None, processes self._pdf_files.
        """
        files_to_process = files or self._pdf_files
        if not files_to_process:
            return

        # Snapshot the file list for the background thread
        self._processing_files = list(files_to_process)

        # Show busy cursor
        wx.BeginBusyCursor()

        # Disable toolbar tools
        self._enable_action_tools(ai=False, rename=False)

        # Don't clear existing cards (multi-load architecture - accumulate!)
        # Note: Card deduplication happens in _process_cards during processing

        # Show progress dialog
        total = len(self._processing_files)
        self._progress = ProgressDialog(self._frame, "Processing Cards", total)
        self._progress.Show()

        # Start background thread
        thread = threading.Thread(target=self._process_cards, daemon=True)
        thread.start()

    def _process_cards(self) -> None:
        """Process PDFs using ProcessPoolExecutor (runs in background thread)."""
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed

        # Set spawn method for PyInstaller
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError as exc:
            if "context has already been set" not in str(exc):
                raise

        total = len(self._processing_files)
        pdf_paths_str = [str(p) for p in self._processing_files]
        completed = 0

        with ProcessPoolExecutor(max_workers=min(total, OCR_WORKERS)) as executor:
            futures = {
                executor.submit(process_pdf_worker, path_str): path_str
                for path_str in pdf_paths_str
            }
            for future in as_completed(futures):
                worker_result = future.result()
                pdf_path = Path(worker_result.pdf_path)
                file_hash = worker_result.file_hash

                # Content-based deduplication: check if we already have this content
                with self._state_lock:
                    if file_hash and file_hash in self._cards_by_hash:
                        # Duplicate content - add path to existing card
                        existing_card = self._cards_by_hash[file_hash]
                        if pdf_path not in existing_card.file_paths:
                            existing_card.file_paths.append(pdf_path)
                        card = existing_card
                    else:
                        # New content - create new card
                        card_id = self._next_card_id
                        self._next_card_id += 1

                        card = self._worker_result_to_card(worker_result, card_id)
                        if file_hash is not None:
                            self._cards_by_hash[file_hash] = card

                    # Always update path → hash mapping
                    if file_hash is not None:
                        self._hash_by_path[pdf_path] = file_hash

                # Update UI (thread-safe with wx.CallAfter)
                completed += 1
                wx.CallAfter(self._update_processing_progress, completed, total, card.filename)

        wx.CallAfter(self._processing_complete)

    def _worker_result_to_card(self, wr: PdfWorkerResult, card_id: int) -> CardResult:
        """Convert PdfWorkerResult from worker to CardResult with assigned ID."""
        from PIL import Image

        pdf_path = Path(wr.pdf_path)
        card = CardResult(
            id=card_id,
            file_paths=[pdf_path],
            primary_path=pdf_path,
            file_hash=wr.file_hash or "",
            family_name=wr.family_name,
            alternates=wr.alternates,
            candidates=wr.candidates,
            remove_family=wr.remove_family,
            selected_candidate_id=wr.selected_candidate_id,
            method=wr.method,
            ocr_text=wr.ocr_text,
        )

        try:
            card.confidence = Confidence(wr.confidence)
        except ValueError:
            card.confidence = Confidence.NONE

        # Deserialize images from bytes
        if wr.preview_image_bytes:
            card.preview_image = Image.open(io.BytesIO(wr.preview_image_bytes))

        if wr.page_images_bytes:
            card.page_images = [
                Image.open(io.BytesIO(img_bytes))
                for img_bytes in wr.page_images_bytes
            ]

        if wr.error:
            card.error = wr.error
            card.confidence = Confidence.NONE

        return card

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
        self._enable_action_tools(ai=True, rename=True, clear=True)

        # Show success message
        count = len(self._cards_by_hash)
        self._show_info_message(
            f"Processing complete\n{_plural(count, 'card')} loaded",
            wx.ICON_INFORMATION,
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

            # Clear manual name in database
            if card.file_hash:
                set_manual_name(card.file_hash, "", card.remove_family)

            # Reload state from DB to get the best candidate name
            self._load_card_state_from_db(card)

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
        for card_id in list(self._review_panel.selected_card_ids):
            card = self._get_card_by_id(card_id)
            if card and card.file_hash:
                self._on_remove_card(card.file_hash)

    def _on_update_remove_menu(self, event: wx.UpdateUIEvent) -> None:
        """Enable Remove menu item only when cards are selected."""
        event.Enable(bool(self._review_panel.selected_card_ids))

    def _on_update_action_menu(self, event: wx.UpdateUIEvent) -> None:
        """Enable/disable AI, Rename, Clear, Clear AI menu items and update labels dynamically."""
        menu_to_tool = {
            self._ai_menu_id: self._ai_all_id,
            self._rename_menu_id: self._rename_id,
            self._clear_menu_id: self._clear_id,
            self._clear_ai_menu_id: self._clear_id,
        }
        tool_id = menu_to_tool.get(event.GetId())
        if tool_id is not None:
            enabled = self._toolbar.GetToolEnabled(tool_id)
            event.Enable(enabled)

            # Dynamic labels for scoped actions
            scoped_labels = {
                self._ai_menu_id: ("AI Analyze", "\tCtrl+Shift+I"),
                self._clear_ai_menu_id: ("Clear AI Results", ""),
            }
            if event.GetId() in scoped_labels:
                base, shortcut = scoped_labels[event.GetId()]
                if enabled and self._cards_by_hash:
                    cards, scope = self._get_target_cards()
                    n = len(cards)
                    scope_label = "Selected" if scope == "selected" else "Visible"
                    event.SetText(f"{base} {scope_label} ({n}){shortcut}")
                else:
                    event.SetText(f"{base}{shortcut}")

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

    def _get_target_cards(self) -> tuple[list[CardResult], str]:
        """Return (cards, scope) based on selection state.

        If 2+ cards are selected, returns those cards with scope "selected".
        Otherwise returns all visible (filtered) cards with scope "visible".
        """
        selected_ids = self._review_panel.selected_card_ids
        if len(selected_ids) >= 2:
            cards = self._review_panel.get_cards_by_ids(selected_ids)
            return cards, "selected"
        return self._review_panel.get_cards(), "visible"

    def _on_ai_request(self, card_id: int) -> None:
        """Handle AI button click for single card — delegates to batch path."""
        card = self._get_card_by_id(card_id)
        if not card or card.error:
            return

        if not card.page_images and not card.preview_image:
            wx.MessageBox(
                "No preview image available for AI analysis.",
                "No Image",
                wx.OK | wx.ICON_WARNING,
                self._frame
            )
            return

        if not self._ensure_api_key():
            return

        # Disable AI button before delegating (after API key check so
        # cancelling the key dialog doesn't leave the button stuck disabled)
        self._review_panel.set_ai_button_state(card_id, "disabled")

        self._start_ai_all(cards=[card], title="AI Analysis")

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
            try:
                card.confidence = Confidence(card_state.confidence)
            except ValueError:
                card.confidence = Confidence.NONE
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
            # No DB state — reset to clean state
            card.family_name = ""
            card.confidence = Confidence.NONE
            card.method = "missing"
            card.candidates = []
            card.alternates = []
            card.selected_candidate_id = None
            card.manual_override = ""
            card.ai_analyzed = True

    def _start_ai_all(self, cards: list[CardResult] | None = None, title: str | None = None) -> None:
        """Start AI analysis for given cards, selected cards, or all visible cards.

        Args:
            cards: Explicit card list (e.g. single card from detail button).
                   If None, determines scope from selection state.
            title: Progress dialog title. If None, auto-generated from scope.
        """
        if not self._cards_by_hash:
            return

        if not self._ensure_api_key():
            return

        # Determine target cards and title
        if cards is None:
            cards, scope = self._get_target_cards()
            n = len(cards)
            if scope == "selected":
                title = f"AI Analysis \u2014 {n} Selected"
            else:
                title = f"AI Analysis \u2014 {n} Cards"
        elif title is None:
            title = "AI Analysis"

        if not cards:
            return

        self._ai_target_cards = cards

        # Show busy cursor
        wx.BeginBusyCursor()

        # Disable toolbar tools
        self._enable_action_tools(ai=False, rename=False)

        # Show progress
        total = len(cards)
        self._progress = ProgressDialog(self._frame, title, total)
        self._progress.Show()

        # Start background thread
        thread = threading.Thread(target=self._run_ai_all, daemon=True)
        thread.start()

    def _run_ai_all(self) -> None:
        """Run async AI batch processing in background thread."""
        try:
            asyncio.run(self._run_ai_all_async())
        except Exception as e:
            error_msg = str(e)
            logger.error("AI batch processing failed: %s", error_msg)
            wx.CallAfter(self._ai_all_complete, [("Batch", error_msg)])

    async def _run_ai_all_async(self) -> None:
        """Async batch AI processing with concurrency limit."""
        import anthropic

        target_cards = self._ai_target_cards
        semaphore = asyncio.Semaphore(AI_CONCURRENCY)
        completed = 0
        total = len(target_cards)
        auth_failed = asyncio.Event()
        errors: list[tuple[str, str]] = []

        async def process_card(card_id: int, card: CardResult) -> None:
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
                        source = card.page_images or []
                        if not source and card.preview_image is not None:
                            source = [card.preview_image]
                        ai_images = [img for img in source if img is not None]
                        if not ai_images:
                            completed += 1
                            wx.CallAfter(self._update_ai_all_progress, completed, total, card.filename, card_id, None)
                            return
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
        await asyncio.gather(*[process_card(card.id, card) for card in target_cards])

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
        self._enable_action_tools(ai=True, rename=True)

        # Update sidebar counts and cards table (confidence levels may have changed)
        self._refresh_display()

        if errors:
            suffix = " (auth error)" if auth_aborted else " (with errors)"
            dialog = ErrorListDialog(self._frame, f"AI Analysis{suffix}", errors, auth_aborted)
            dialog.ShowModal()
            dialog.Destroy()
        else:
            # Show success message with auto-dismiss
            count = len(self._ai_target_cards) or len(self._cards_by_hash)
            self._show_info_message(
                f"Analysis complete\n{_plural(count, 'card')} analyzed",
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
        dialog = RenameConfirmDialog(self._frame, plan)
        if dialog.ShowModal() == wx.ID_OK:
            # Execute rename
            results = execute_rename_plan(plan)

            # Update _hash_by_path mapping for renamed files
            for result in results:
                if result.success and result.message in _RESOLVED_MESSAGES:
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

    def _remove_completed_results(self, results: list[RenameResult]) -> None:
        """Remove successfully renamed/skip_same paths from cards; drop empty cards.

        Paths with message "Renamed" or "Already named correctly" are considered
        resolved. Paths that failed or had no name are kept for the user to address.
        """
        # Collect paths to remove (use new_path — that's where the file is now)
        paths_to_remove: set[Path] = set()
        for r in results:
            if r.success and r.message in _RESOLVED_MESSAGES:
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
            self._enable_action_tools(ai=False, rename=False, clear=False)
            self._search_ctrl.SetValue("")

    def _show_info_message(self, message: str, icon: int = wx.ICON_INFORMATION, duration_ms: int = Layout.INFO_DISMISS_MS) -> None:
        """Show notification in sidebar bottom.

        Args:
            message: Message to display
            icon: Icon to show (wx.ICON_INFORMATION, wx.ICON_WARNING, wx.ICON_ERROR)
            duration_ms: Time in milliseconds before auto-dismiss (0 = no auto-dismiss)
        """
        self._sidebar.show_notification(message, icon, duration_ms)

    def _on_appearance_changed(self) -> None:
        """Handle macOS dark/light mode switch."""
        from app.gui.appearance import is_dark_mode
        from app.gui import icons

        mode = "Dark" if is_dark_mode() else "Light"
        logger.info("Appearance changed to %s mode", mode)

        # Refresh color palette and icon cache
        Color.refresh()
        icons.clear_cache()

        # Update toolbar icons in-place
        self._refresh_toolbar_icons()

        # Re-apply colors on long-lived panels
        self._sidebar.refresh_colors()
        self._preview_panel.refresh_colors()
        self._review_panel.refresh_colors()

        # Repaint all windows; call refresh_colors() on those that support it
        for window in wx.GetTopLevelWindows():
            if hasattr(window, "refresh_colors"):
                window.refresh_colors()
            window.Refresh()
            window.Update()

    def _refresh_toolbar_icons(self) -> None:
        """Re-render toolbar icons for current appearance."""
        icon_map = {
            self._browse_id: "folder.badge.plus",
            self._ai_all_id: "sparkles",
            self._rename_id: "pencil",
            self._clear_id: "xmark.circle",
        }
        for tool_id, symbol in icon_map.items():
            bmp = load_sf_symbol(symbol, point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
            self._toolbar.SetToolNormalBitmap(tool_id, wx.BitmapBundle(bmp))
        self._toolbar.Realize()

    # --- End dark mode ---

    def _on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close event."""
        from app.gui import appearance
        appearance.stop_observer()

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
    ) -> None:
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
