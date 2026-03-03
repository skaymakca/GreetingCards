# noinspection GrazieInspection
"""wxPython preview panel for displaying multi-page, zoomable, pannable PDF previews."""

import wx
from PIL import Image

from app.gui import styles, utils

# Preview panel constants
_MODIFIER_POLL_MS = 50
_WARNING_FONT_SIZE = 32
_WARNING_LABEL_OFFSET = 30
_WARNING_TEXT_OFFSET = 20
_WARNING_LINE_SPACING = 4


# noinspection PyMethodMayBeStatic,PyUnusedLocal,PyTypeChecker,GrazieInspection
class PreviewPanel(wx.Panel):
    """Panel that displays a multi-page, zoomable, pannable PDF preview.

    Features:
    - Multi-page navigation with Previous/Next buttons
    - Zoom controls: Fit, +, -, scroll wheel, modifier clicks
    - Pan with click and drag
    - Intelligent fit mode that scales images to canvas size (max 1:1)
    - Cursor updates based on modifier keys (Shift, Ctrl/Cmd)
    """

    ZOOM_STEP = 1.25
    MIN_ZOOM = 0.1
    MAX_ZOOM = 10.0

    def __init__(self, parent: wx.Window, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        # State
        self._images: list[Image.Image] = []
        self._page_idx = 0
        self._zoom = 1.0
        self._fit_zoom = 1.0
        self._is_fit = True
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_start: tuple[int, int] | None = None
        self._error_message = ""
        self._bitmap_cache: wx.Bitmap | None = None

        # Timer for polling modifier keys (to update cursor without mouse movement)
        self._modifier_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_modifier_timer, self._modifier_timer)

        # Load custom SF Symbol cursors (with fallback)
        try:
            from app.gui.icons import load_cursor_from_symbol

            self._zoom_in_cursor = load_cursor_from_symbol(
                "plus.magnifyingglass",
                point_size=7,
                color_hex="#000000",  # Black for good contrast
            )
            self._zoom_out_cursor = load_cursor_from_symbol("minus.magnifyingglass", point_size=7, color_hex="#000000")
        except ImportError, AttributeError, OSError:
            self._zoom_in_cursor = None
            self._zoom_out_cursor = None

        # Fallback to standard cursor if custom loading failed
        if not self._zoom_in_cursor:
            self._zoom_in_cursor = wx.Cursor(wx.CURSOR_MAGNIFIER)
        if not self._zoom_out_cursor:
            self._zoom_out_cursor = wx.Cursor(wx.CURSOR_SIZING)

        self._build_ui()

    def _build_ui(self) -> None:
        """Create the UI components."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        self._title_label = utils.create_static_text(
            self, "PREVIEW", font=styles.Font.SECTION_HEADER(), colour=styles.Color.TEXT_SECONDARY
        )
        sizer.Add(self._title_label, 0, wx.ALL, styles.Layout.PAD)

        # Canvas panel (custom painting) — no explicit bg color; inherits system
        # appearance so it follows dark/light mode natively.
        self._canvas = wx.Panel(self, style=wx.BORDER_NONE)
        self._canvas.Bind(wx.EVT_PAINT, self._on_paint)
        self._canvas.Bind(wx.EVT_SIZE, self._on_resize)

        # Mouse events
        self._canvas.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self._canvas.Bind(wx.EVT_LEFT_DCLICK, self._on_left_down)  # Handle double-clicks too for rapid clicking
        self._canvas.Bind(wx.EVT_MOTION, self._on_motion)
        self._canvas.Bind(wx.EVT_LEFT_UP, self._on_pan_end)
        self._canvas.Bind(wx.EVT_MOUSEWHEEL, self._on_scroll_zoom)
        self._canvas.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self._canvas.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)

        sizer.Add(self._canvas, 1, wx.EXPAND)

        # Controls bar
        controls = wx.Panel(self)
        controls_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Left group: Page navigation [◀] [page] [▶]
        self._prev_btn = wx.Button(controls, label="◀", size=(28, 28))
        self._prev_btn.Bind(wx.EVT_BUTTON, lambda _: self.prev_page())
        self._prev_btn.Enable(False)
        controls_sizer.Add(self._prev_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        self._page_label = utils.create_static_text(
            controls, "", font=styles.Font.SMALL(), colour=styles.Color.TEXT_PRIMARY
        )
        self._page_label.SetMinSize((50, -1))
        self._page_label.SetWindowStyleFlag(wx.ALIGN_CENTRE_HORIZONTAL | wx.ST_NO_AUTORESIZE)
        controls_sizer.Add(self._page_label, 0, wx.ALIGN_CENTER_VERTICAL)

        self._next_btn = wx.Button(controls, label="▶", size=(28, 28))
        self._next_btn.Bind(wx.EVT_BUTTON, lambda _: self.next_page())
        self._next_btn.Enable(False)
        controls_sizer.Add(self._next_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        controls_sizer.AddStretchSpacer()

        # Right group: [Fit] [−] [zoom%] [+]
        self._fit_btn = wx.Button(controls, label="Fit", size=(42, 28))
        self._fit_btn.Bind(wx.EVT_BUTTON, lambda _: self._zoom_fit())
        self._fit_btn.Enable(False)
        controls_sizer.Add(self._fit_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self._zout_btn = wx.Button(controls, label="−", size=(28, 28))
        self._zout_btn.Bind(wx.EVT_BUTTON, lambda _: self._zoom_out())
        self._zout_btn.Enable(False)
        controls_sizer.Add(self._zout_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        self._zoom_label = utils.create_static_text(
            controls, "", font=styles.Font.SMALL(), colour=styles.Color.TEXT_PRIMARY
        )
        self._zoom_label.SetMinSize((40, -1))
        self._zoom_label.SetWindowStyleFlag(wx.ALIGN_CENTRE_HORIZONTAL | wx.ST_NO_AUTORESIZE)
        controls_sizer.Add(self._zoom_label, 0, wx.ALIGN_CENTER_VERTICAL)

        self._zin_btn = wx.Button(controls, label="+", size=(28, 28))
        self._zin_btn.Bind(wx.EVT_BUTTON, lambda _: self._zoom_in())
        self._zin_btn.Enable(False)
        controls_sizer.Add(self._zin_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        controls.SetSizer(controls_sizer)

        sizer.Add(controls, 0, wx.EXPAND | wx.ALL, styles.Layout.PAD)

        self.SetSizer(sizer)

    def refresh_colors(self) -> None:
        """Re-apply mode-dependent colors after an appearance change."""
        self._title_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        self._page_label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        self._zoom_label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        self._canvas.Refresh()

    # --- Public API ---

    def show_images(self, images: list[Image.Image], filename: str = "") -> None:
        """Display a list of page images.

        Args:
            images: List of PIL Image objects (one per page)
            filename: Optional filename to display in title
        """
        self._error_message = ""
        self._images = images
        self._page_idx = 0
        self._reset_view()

        if filename:
            self._title_label.SetLabel(f"PREVIEW: {filename}")
        else:
            self._title_label.SetLabel("PREVIEW")

        self._update_page_controls()
        self._update_zoom_controls()
        self._render()

    def show_image(self, image: Image.Image, filename: str = "") -> None:
        """Display a single image (backward compat).

        Args:
            image: PIL Image object
            filename: Optional filename to display in title
        """
        self.show_images([image], filename)

    def clear(self) -> None:
        """Clear the preview and reset state."""
        self._error_message = ""
        self._images = []
        self._page_idx = 0
        self._bitmap_cache = None
        self._title_label.SetLabel("PREVIEW")
        self._page_label.SetLabel("")
        self._prev_btn.Enable(False)
        self._next_btn.Enable(False)
        self._update_zoom_controls()
        self._canvas.Refresh()

    def show_error(self, message: str, filename: str = "") -> None:
        """Display an error message on the preview canvas.

        Args:
            message: Error message to display
            filename: Optional filename to display in title
        """
        self._images = []
        self._page_idx = 0
        self._bitmap_cache = None
        self._error_message = message

        if filename:
            self._title_label.SetLabel(f"PREVIEW: {filename}")
        else:
            self._title_label.SetLabel("PREVIEW")

        self._page_label.SetLabel("")
        self._prev_btn.Enable(False)
        self._next_btn.Enable(False)
        self._update_zoom_controls()
        self._canvas.Refresh()

    # --- Page navigation ---

    def prev_page(self) -> None:
        """Navigate to previous page."""
        if self._page_idx > 0:
            self._page_idx -= 1
            self._reset_view()
            self._update_page_controls()
            self._render()

    def next_page(self) -> None:
        """Navigate to next page."""
        if self._page_idx < len(self._images) - 1:
            self._page_idx += 1
            self._reset_view()
            self._update_page_controls()
            self._render()

    def _update_page_controls(self) -> None:
        """Update page navigation button states and label."""
        total = len(self._images)
        if total <= 1:
            self._page_label.SetLabel(f"1 / {total}" if total else "")
            self._prev_btn.Enable(False)
            self._next_btn.Enable(False)
        else:
            self._page_label.SetLabel(f"{self._page_idx + 1} / {total}")
            self._prev_btn.Enable(self._page_idx > 0)
            self._next_btn.Enable(self._page_idx < total - 1)

    # --- Zoom ---

    def _update_zoom_controls(self) -> None:
        """Enable zoom buttons when images are loaded, disable otherwise."""
        has_images = bool(self._images)
        self._fit_btn.Enable(has_images)
        self._zout_btn.Enable(has_images)
        self._zin_btn.Enable(has_images)
        if not has_images:
            self._zoom_label.SetLabel("")

    def _reset_view(self) -> None:
        """Reset to fit mode and clear pan offsets."""
        self._is_fit = True
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom_label.SetLabel("Fit")

    def _zoom_fit(self) -> None:
        """Zoom to fit mode."""
        self._reset_view()
        self._render()

    def _zoom_in(self) -> None:
        """Zoom in by ZOOM_STEP."""
        self._apply_zoom(self.ZOOM_STEP)

    def _zoom_out(self) -> None:
        """Zoom out by ZOOM_STEP."""
        self._apply_zoom(1.0 / self.ZOOM_STEP)

    def _apply_zoom(self, factor: float) -> None:
        """Apply a zoom factor.

        Args:
            factor: Zoom multiplier (e.g., 1.25 for zoom in, 0.8 for zoom out)
        """
        if self._is_fit:
            # Transition from fit mode to explicit zoom
            self._zoom = self._fit_zoom
            self._is_fit = False

        new_zoom = self._zoom * factor
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, new_zoom))
        self._zoom = new_zoom

        # Update label to show percentage relative to fit
        percentage = int(self._zoom / self._fit_zoom * 100) if self._fit_zoom > 0 else 100
        self._zoom_label.SetLabel(f"{percentage}%")

        self._render()

    # --- Pan ---

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        """Handle left mouse button down - start pan or modifier zoom.

        Important: Always call event.Skip() to ensure proper focus handling
        and allow default processing (per wxPython MouseEvent documentation).
        """
        if not self._images:
            event.Skip()
            return

        # Temporarily stop timer to avoid interference during click
        self._modifier_timer.Stop()

        # Use bitwise AND to check for modifiers (more forgiving than exact match)
        modifiers = event.GetModifiers()

        if (modifiers & wx.MOD_SHIFT) and not (modifiers & wx.MOD_ALT):
            # Zoom in (Shift pressed, Alt not pressed)
            self._apply_zoom(self.ZOOM_STEP)
            # Restart timer after a brief delay
            wx.CallAfter(self._modifier_timer.Start, _MODIFIER_POLL_MS)
            event.Skip()  # Allow default processing for proper focus
            return
        elif (modifiers & wx.MOD_ALT) and not (modifiers & wx.MOD_SHIFT):
            # Zoom out (Alt pressed, Shift not pressed)
            self._apply_zoom(1.0 / self.ZOOM_STEP)
            # Restart timer after a brief delay
            wx.CallAfter(self._modifier_timer.Start, _MODIFIER_POLL_MS)
            event.Skip()  # Allow default processing for proper focus
            return

        # Otherwise start pan
        self._on_pan_start(event)
        # Restart timer
        wx.CallAfter(self._modifier_timer.Start, _MODIFIER_POLL_MS)
        event.Skip()  # Allow default processing

    def _on_pan_start(self, event: wx.MouseEvent) -> None:
        """Start panning."""
        if not self._images:
            return
        self._drag_start = (event.GetX(), event.GetY())
        self._canvas.SetCursor(wx.Cursor(wx.CURSOR_SIZING))

    def _on_pan_drag(self, event: wx.MouseEvent) -> None:
        """Update pan offsets during drag."""
        if self._drag_start is None:
            return
        x, y = event.GetX(), event.GetY()
        dx = x - self._drag_start[0]
        dy = y - self._drag_start[1]
        self._drag_start = (x, y)
        self._pan_x += dx
        self._pan_y += dy
        self._canvas.Refresh()

    def _on_pan_end(self, event: wx.MouseEvent) -> None:
        """End panning."""
        self._drag_start = None
        self._canvas.SetCursor(wx.NullCursor)

    # --- Mouse events ---

    def _on_scroll_zoom(self, event: wx.MouseEvent) -> None:
        """Handle mouse wheel for zooming."""
        if not self._images:
            return
        rotation = event.GetWheelRotation()
        if rotation > 0:
            self._apply_zoom(self.ZOOM_STEP)
        elif rotation < 0:
            self._apply_zoom(1.0 / self.ZOOM_STEP)

    def _on_motion(self, event: wx.MouseEvent) -> None:
        """Update cursor based on modifiers or handle pan drag."""
        if not self._images:
            return

        if self._drag_start:
            self._on_pan_drag(event)
            return

        # Update cursor based on current modifiers
        self._update_cursor()

    def _on_enter(self, event: wx.MouseEvent) -> None:
        """Update cursor when mouse enters canvas and start modifier polling."""
        if self._images and self._drag_start is None:
            self._update_cursor()
            # Start timer to poll for modifier key changes (50ms = 20 times per second)
            self._modifier_timer.Start(_MODIFIER_POLL_MS)

    def _on_leave(self, event: wx.MouseEvent) -> None:
        """Reset cursor when mouse leaves canvas and stop modifier polling."""
        if self._drag_start is None:
            self._canvas.SetCursor(wx.NullCursor)
        # Stop polling timer when mouse leaves
        self._modifier_timer.Stop()

    def _on_modifier_timer(self, event: wx.TimerEvent) -> None:
        """Timer callback to check for modifier key changes without mouse movement."""
        if not wx.GetApp():
            self._modifier_timer.Stop()
            return
        if self._images and self._drag_start is None:
            self._update_cursor()

    def _update_cursor(self) -> None:
        """Update cursor based on current modifier key state.

        Uses wx.GetMouseState().GetModifiers() to poll modifier keys,
        which works even when no mouse events are firing.
        """
        if not self._images or self._drag_start is not None:
            return

        # Poll keyboard state using GetModifiers()
        mouse_state = wx.GetMouseState()
        modifiers = mouse_state.GetModifiers()

        # Use bitwise AND to check for modifiers
        if (modifiers & wx.MOD_SHIFT) and not (modifiers & wx.MOD_ALT):
            # Zoom in - custom SF Symbol cursor with plus
            self._canvas.SetCursor(self._zoom_in_cursor)
        elif (modifiers & wx.MOD_ALT) and not (modifiers & wx.MOD_SHIFT):
            # Zoom out - custom SF Symbol cursor with minus
            self._canvas.SetCursor(self._zoom_out_cursor)
        else:
            # No modifiers or multiple modifiers - default cursor
            self._canvas.SetCursor(wx.NullCursor)

    # --- Rendering ---

    def _on_resize(self, event: wx.SizeEvent | None) -> None:
        """Handle canvas resize - recompute and repaint."""
        if self._error_message:
            self._canvas.Refresh()
        elif self._images:
            self._render()
        if event:
            event.Skip()

    def _render(self) -> None:
        """Prepare bitmap for current page with zoom and pan."""
        if not self._images or self._page_idx >= len(self._images):
            self._bitmap_cache = None
            self._canvas.Refresh()
            return

        # Get canvas size
        cw, ch = self._canvas.GetSize()
        if cw < 10 or ch < 10:
            return

        # Get current page image
        img = self._images[self._page_idx]
        iw, ih = img.size

        # Compute fit scale (never exceed 1:1)
        self._fit_zoom = min(cw / iw, ch / ih, 1.0)

        # Determine scale
        scale = self._fit_zoom if self._is_fit else self._zoom

        # Scale image
        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Convert to wx.Bitmap
        self._bitmap_cache = utils.pil_to_bitmap(resized)

        # Trigger repaint
        self._canvas.Refresh()

    def _on_paint(self, event: wx.PaintEvent) -> None:
        """Paint the cached bitmap with pan offsets."""
        dc = wx.PaintDC(self._canvas)
        dc.Clear()

        if self._error_message:
            self._paint_error(dc)
            return

        if not self._bitmap_cache:
            self._paint_placeholder(dc)
            return

        # Get canvas center
        cw, ch = self._canvas.GetSize()
        cx, cy = cw // 2, ch // 2

        # Apply pan offsets
        x = cx + int(self._pan_x) - self._bitmap_cache.GetWidth() // 2
        y = cy + int(self._pan_y) - self._bitmap_cache.GetHeight() // 2

        # Draw bitmap
        dc.DrawBitmap(self._bitmap_cache, x, y, useMask=False)

    def _paint_placeholder(self, dc: wx.PaintDC) -> None:
        """Draw placeholder text when no images are loaded."""
        dc.SetTextForeground(styles.Color.TEXT_SECONDARY)
        dc.SetFont(styles.Font.BODY())
        text = "Select a card to preview"
        tw, th = dc.GetTextExtent(text)
        cw, ch = self._canvas.GetSize()
        dc.DrawText(text, (cw - tw) // 2, (ch - th) // 2)

    def _paint_error(self, dc: wx.PaintDC) -> None:
        """Draw error message on canvas."""
        cw, ch = self._canvas.GetSize()
        if cw < 10 or ch < 10:
            return

        cx, cy = cw // 2, ch // 2

        # Draw warning symbol
        dc.SetTextForeground(styles.Color.ERROR)
        dc.SetFont(wx.Font(wx.FontInfo(_WARNING_FONT_SIZE)))
        warning = "⚠"
        tw, th = dc.GetTextExtent(warning)
        dc.DrawText(warning, cx - tw // 2, cy - _WARNING_LABEL_OFFSET - th // 2)

        # Draw error message
        dc.SetFont(styles.Font.BODY())
        lines = self._wrap_text(dc, self._error_message, cw - 40)
        y_offset = cy + _WARNING_TEXT_OFFSET
        for line in lines:
            tw, th = dc.GetTextExtent(line)
            dc.DrawText(line, cx - tw // 2, y_offset)
            y_offset += th + _WARNING_LINE_SPACING

    def _wrap_text(self, dc: wx.DC, text: str, max_width: int) -> list[str]:
        """Wrap text to fit within max_width.

        Args:
            dc: Device context for measuring text
            text: Text to wrap
            max_width: Maximum width in pixels

        Returns:
            List of wrapped lines
        """
        words = text.split()
        lines = []
        current_line: list[str] = []

        for word in words:
            test_line = " ".join(current_line + [word])
            tw, _ = dc.GetTextExtent(test_line)

            if tw <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines if lines else [text]
