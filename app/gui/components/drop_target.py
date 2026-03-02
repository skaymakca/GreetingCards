"""Drop target overlay and file drop target for the main window."""

import logging
from collections.abc import Callable
from pathlib import Path

import wx
from PIL import Image, ImageEnhance

from app.core.paths import get_runtime_content_path
from app.gui.styles import Color, Font, Layout

logger = logging.getLogger(__name__)


def load_drop_background() -> wx.Bitmap | None:
    """Load and process the drop target background image.

    Applies Brightness(0.75) and Color(0.5) via PIL, returns wx.Bitmap.
    """
    # noinspection PyBroadException
    try:
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


# noinspection PyUnusedLocal
class DropOverlay(wx.Panel):
    """Full content-area drop overlay with background image and drop zone hint."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent)
        self._bg_source = load_drop_background()
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
        tw2, _th2 = gc.GetTextExtent(secondary)[:2]
        tx2 = (w - tw2) / 2
        ty2 = text_center_y + Layout.DROP_TEXT_GAP
        gc.DrawText(secondary, tx2, ty2)


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

    # noinspection PyPep8Naming
    def OnDragOver(self, x: int, y: int, defResult: int) -> int:
        """Show drag highlight when files are dragged over."""
        if self._on_drag_over:
            self._on_drag_over()
        return defResult

    def OnLeave(self) -> None:
        """Hide drag highlight when drag leaves."""
        if self._on_drag_leave:
            self._on_drag_leave()
