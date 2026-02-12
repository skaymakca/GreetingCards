import tkinter as tk
from PIL import Image, ImageTk
from app.gui import styles


class PreviewPanel(tk.Frame):
    """Panel that displays a preview image of a PDF card."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=styles.BG_SECONDARY, **kwargs)
        self._photo = None  # prevent GC

        self.label_title = tk.Label(
            self,
            text="Preview",
            font=styles.FONT_HEADING,
            bg=styles.BG_SECONDARY,
            fg=styles.TEXT_PRIMARY,
            anchor="w",
        )
        self.label_title.pack(fill="x", padx=styles.PAD, pady=(styles.PAD, 4))

        self.canvas = tk.Canvas(
            self, bg=styles.BG_SECONDARY, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True, padx=styles.PAD, pady=(0, styles.PAD))

        self.placeholder = tk.Label(
            self.canvas,
            text="Select a card to preview",
            font=styles.FONT_BODY,
            fg=styles.TEXT_SECONDARY,
            bg=styles.BG_SECONDARY,
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self.canvas.bind("<Configure>", self._on_resize)
        self._current_image = None

    def show_image(self, image: Image.Image, filename: str = ""):
        """Display a PIL Image in the preview panel."""
        self._current_image = image
        self.placeholder.place_forget()
        if filename:
            self.label_title.config(text=f"Preview: {filename}")
        self._render_image()

    def clear(self):
        """Clear the preview."""
        self._current_image = None
        self._photo = None
        self.canvas.delete("all")
        self.label_title.config(text="Preview")
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _on_resize(self, event=None):
        if self._current_image:
            self._render_image()

    def _render_image(self):
        if not self._current_image:
            return
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        img = self._current_image
        iw, ih = img.size
        scale = min(cw / iw, ch / ih, 1.0)
        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(resized)
        x = cw // 2
        y = ch // 2
        self.canvas.create_image(x, y, anchor="center", image=self._photo)
