import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from app.gui import styles
from app.gui.icons import load_sf_symbol


class PreviewPanel(tk.Frame):
    """Panel that displays a multi-page, zoomable, pannable PDF preview."""

    ZOOM_STEP = 1.25
    MIN_ZOOM = 0.1
    MAX_ZOOM = 10.0

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=styles.BG_PRIMARY, **kwargs)
        self._photo = None  # prevent GC
        self._images: list[Image.Image] = []
        self._page_idx = 0
        self._zoom = 1.0  # 1.0 = fit mode
        self._fit_zoom = 1.0  # computed fit scale
        self._is_fit = True  # whether we're in "fit" mode
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_start = None
        self._cursor_overlay = None  # For custom cursor icon
        self._cursor_icon_zoomin = None
        self._cursor_icon_zoomout = None

        # --- Title bar ---
        self._title_label = tk.Label(
            self, text="Preview", font=styles.FONT_HEADING,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY, anchor="w",
        )
        self._title_label.pack(fill="x", padx=styles.PAD, pady=(styles.PAD, 4))

        # --- Canvas ---
        self._canvas = tk.Canvas(self, bg=styles.BG_PRIMARY, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=0, pady=0)

        self._placeholder = tk.Label(
            self._canvas, text="Select a card to preview",
            font=styles.FONT_BODY, fg=styles.TEXT_SECONDARY, bg=styles.BG_PRIMARY,
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # --- Controls bar ---
        controls = tk.Frame(self, bg=styles.BG_PRIMARY)
        controls.pack(fill="x", padx=styles.PAD, pady=(4, styles.PAD))

        # Page navigation (left side)
        page_frame = tk.Frame(controls, bg=styles.BG_PRIMARY)
        page_frame.pack(side="left")

        self._prev_btn = ttk.Button(
            page_frame, text="\u25C0",
            command=self._prev_page, width=2, state="disabled",
        )
        self._prev_btn.pack(side="left", padx=(0, 2))

        self._page_label = tk.Label(
            page_frame, text="", font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY, width=9,
        )
        self._page_label.pack(side="left", padx=2)

        self._next_btn = ttk.Button(
            page_frame, text="\u25B6",
            command=self._next_page, width=2, state="disabled",
        )
        self._next_btn.pack(side="left", padx=(2, 0))

        # Zoom controls (right side)
        zoom_frame = tk.Frame(controls, bg=styles.BG_PRIMARY)
        zoom_frame.pack(side="right")

        self._fit_btn = ttk.Button(
            zoom_frame, text="Fit",
            command=self._zoom_fit, width=3,
        )
        self._fit_btn.pack(side="left", padx=(0, 2))

        self._zout_btn = ttk.Button(
            zoom_frame, text="\u2212",
            command=self._zoom_out, width=2,
        )
        self._zout_btn.pack(side="left", padx=2)

        self._zoom_label = tk.Label(
            zoom_frame, text="Fit", font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY, width=6,
        )
        self._zoom_label.pack(side="left", padx=2)

        self._zin_btn = ttk.Button(
            zoom_frame, text="+",
            command=self._zoom_in, width=2,
        )
        self._zin_btn.pack(side="left", padx=(2, 0))

        # --- Bindings ---
        self._canvas.bind("<Configure>", self._on_resize)
        # Pan
        self._canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self._canvas.bind("<B1-Motion>", self._on_pan_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_pan_end)
        # Scroll to zoom
        self._canvas.bind("<MouseWheel>", self._on_scroll_zoom)
        # Modifier-click zoom
        self._canvas.bind("<Shift-Button-1>", self._on_shift_click)
        self._canvas.bind("<Control-Button-1>", self._on_ctrl_click)
        self._canvas.bind("<Command-Button-1>", self._on_ctrl_click)  # macOS
        # Cursor change on modifier hover
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)

        # Load zoom cursor icons
        self._cursor_icon_zoomin = load_sf_symbol("plus.magnifyingglass", 20, styles.TEXT_PRIMARY)
        self._cursor_icon_zoomout = load_sf_symbol("minus.magnifyingglass", 20, styles.TEXT_PRIMARY)

    # --- Public API ---

    def show_images(self, images: list[Image.Image], filename: str = ""):
        """Display a list of page images."""
        self._images = images
        self._page_idx = 0
        self._reset_view()
        self._placeholder.place_forget()
        if filename:
            self._title_label.config(text=f"Preview: {filename}")
        self._update_page_controls()
        self._render()

    def show_image(self, image: Image.Image, filename: str = ""):
        """Display a single image (backward compat)."""
        self.show_images([image], filename)

    def clear(self):
        """Clear the preview."""
        self._images = []
        self._page_idx = 0
        self._photo = None
        self._canvas.delete("all")
        self._title_label.config(text="Preview")
        self._page_label.config(text="")
        self._zoom_label.config(text="")
        self._prev_btn.config(state="disabled")
        self._next_btn.config(state="disabled")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # --- Page navigation ---

    def _prev_page(self):
        if self._page_idx > 0:
            self._page_idx -= 1
            self._reset_view()
            self._update_page_controls()
            self._render()

    def _next_page(self):
        if self._page_idx < len(self._images) - 1:
            self._page_idx += 1
            self._reset_view()
            self._update_page_controls()
            self._render()

    def _update_page_controls(self):
        total = len(self._images)
        if total <= 1:
            self._page_label.config(text=f"1 / {total}" if total else "")
            self._prev_btn.config(state="disabled")
            self._next_btn.config(state="disabled")
        else:
            self._page_label.config(text=f"{self._page_idx + 1} / {total}")
            self._prev_btn.config(state="normal" if self._page_idx > 0 else "disabled")
            self._next_btn.config(state="normal" if self._page_idx < total - 1 else "disabled")

    # --- Zoom ---

    def _reset_view(self):
        self._is_fit = True
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom_label.config(text="Fit")

    def _zoom_fit(self):
        self._reset_view()
        self._render()

    def _zoom_in(self):
        self._apply_zoom(self.ZOOM_STEP)

    def _zoom_out(self):
        self._apply_zoom(1.0 / self.ZOOM_STEP)

    def _apply_zoom(self, factor: float):
        if self._is_fit:
            # Transition from fit mode to explicit zoom
            self._zoom = self._fit_zoom
            self._is_fit = False

        new_zoom = self._zoom * factor
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, new_zoom))
        self._zoom = new_zoom
        self._zoom_label.config(text=f"{int(self._zoom / self._fit_zoom * 100)}%")
        self._render()

    def _on_scroll_zoom(self, event):
        if not self._images:
            return
        # macOS gives delta in multiples; normalize
        if event.delta > 0:
            self._apply_zoom(self.ZOOM_STEP)
        elif event.delta < 0:
            self._apply_zoom(1.0 / self.ZOOM_STEP)

    # --- Pan ---

    def _on_shift_click(self, event):
        """Shift+Click to zoom in."""
        if not self._images:
            return
        self._apply_zoom(self.ZOOM_STEP)
        return "break"  # Prevent pan

    def _on_ctrl_click(self, event):
        """Ctrl/Cmd+Click to zoom out."""
        if not self._images:
            return
        self._apply_zoom(1.0 / self.ZOOM_STEP)
        return "break"  # Prevent pan

    def _on_motion(self, event):
        """Update cursor based on modifier keys."""
        if not self._images:
            return

        # Check for Shift (zoom in) or Ctrl/Cmd (zoom out)
        if event.state & 0x0001:  # Shift
            self._show_cursor_overlay(event, self._cursor_icon_zoomin)
            self._canvas.config(cursor="none")
        elif event.state & 0x0004 or event.state & 0x0008:  # Ctrl or Cmd
            self._show_cursor_overlay(event, self._cursor_icon_zoomout)
            self._canvas.config(cursor="none")
        else:
            self._hide_cursor_overlay()
            self._canvas.config(cursor="")

    def _show_cursor_overlay(self, event, icon):
        """Show cursor overlay with SF Symbol icon."""
        if not icon:
            return

        if self._cursor_overlay is None:
            # Create cursor overlay label
            self._cursor_overlay = tk.Label(
                self._canvas, image=icon, bg=styles.BG_PRIMARY,
                borderwidth=0, highlightthickness=0
            )

        self._cursor_overlay.config(image=icon)
        # Position overlay at cursor location with slight offset
        x = event.x + 8
        y = event.y + 8
        self._cursor_overlay.place(x=x, y=y)

    def _hide_cursor_overlay(self):
        """Hide cursor overlay."""
        if self._cursor_overlay:
            self._cursor_overlay.place_forget()

    def _on_leave(self, event):
        """Handle mouse leaving canvas."""
        self._hide_cursor_overlay()
        self._canvas.config(cursor="")

    def _on_pan_start(self, event):
        if not self._images:
            return
        self._drag_start = (event.x, event.y)
        self._canvas.config(cursor="fleur")

    def _on_pan_drag(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        self._pan_x += dx
        self._pan_y += dy
        self._render()

    def _on_pan_end(self, event):
        self._drag_start = None
        self._canvas.config(cursor="")

    # --- Rendering ---

    def _on_resize(self, event=None):
        if self._images:
            self._render()

    def _render(self):
        if not self._images or self._page_idx >= len(self._images):
            return

        self._canvas.delete("all")
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        img = self._images[self._page_idx]
        iw, ih = img.size

        # Compute fit scale (never exceed 1:1)
        self._fit_zoom = min(cw / iw, ch / ih, 1.0)

        if self._is_fit:
            scale = self._fit_zoom
        else:
            scale = self._zoom

        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(resized)

        x = cw / 2 + self._pan_x
        y = ch / 2 + self._pan_y
        self._canvas.create_image(int(x), int(y), anchor="center", image=self._photo)
