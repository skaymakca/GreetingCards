"""Help dialog showing app instructions and keyboard shortcuts."""
import tkinter as tk
from tkinter import ttk
from app.gui import styles


class HelpDialog(tk.Toplevel):
    """Help window with workflow instructions and keyboard shortcuts."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Help")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        w, h = 600, 650
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Scrollable content
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        sys_bg = ttk.Style().lookup("TFrame", "background")
        canvas = tk.Canvas(container, bg=sys_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Bind mousewheel to canvas and frame for native macOS scroll behavior
        def on_mousewheel(e):
            canvas.yview_scroll(-1 * (e.delta // 120 or e.delta), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        scrollable_frame.bind("<MouseWheel>", on_mousewheel)

        # Store for binding to child widgets
        self._canvas = canvas
        self._scrollable_frame = scrollable_frame
        self._on_mousewheel = on_mousewheel

        # --- Content ---
        self._add_section(scrollable_frame, "Workflow", [
            "1. Browse or drag-drop a folder containing greeting card PDFs",
            "2. Click Process to extract family names using OCR",
            "3. Review extracted names in the cards list",
            "4. Click AI button (per card or AI All) for better accuracy",
            "5. Edit names manually or select from Candidates dropdown",
            "6. Click Rename All to rename files with extracted names",
        ])

        self._add_section(scrollable_frame, "Toolbar Buttons", [
            "Browse — Select a folder of PDF files",
            "Process — Extract names from all cards using OCR",
            "AI All — Analyze all cards with Claude AI (requires API key)",
            "Rename All — Rename files based on extracted names",
            "Clear — Remove all cards and start over",
            "Settings — Configure API key and database",
        ])

        self._add_section(scrollable_frame, "Card List Features", [
            "• Confidence dots show extraction quality (green=high, yellow=medium, red=low, blue=manual)",
            "• Click a row to view the card in the preview panel",
            "• Edit family name directly in the text field",
            "• Checkbox to remove 'Family' suffix from file name (e.g., 'Smith.pdf' instead of 'Smith Family.pdf')",
            "• Candidates dropdown shows alternate name suggestions",
            "• AI button analyzes a single card with Claude AI",
            "• Right-click text fields for Cut, Copy, Paste, Clear",
        ])

        self._add_section(scrollable_frame, "Preview Panel", [
            "• View all pages of the selected card",
            "• Navigate pages with ◀ and ▶ buttons",
            "• Click and drag to pan when zoomed in",
            "• Scroll wheel to zoom in/out",
        ])

        self._add_section(scrollable_frame, "Keyboard Shortcuts", [
            "↑  ↓  — Navigate cards in list (select previous/next)",
            "←  →  — Navigate pages in preview",
            "Esc — Defocus text entries",
            "⌘X, ⌘C, ⌘V — Cut, Copy, Paste (in text fields)",
        ])

        self._add_section(scrollable_frame, "Zoom Controls", [
            "Shift + Click — Zoom in (cursor shows ✚)",
            "Ctrl/⌘ + Click — Zoom out (cursor shows ✖)",
            "Scroll Wheel — Zoom in/out at cursor",
            "Fit button — Reset to fit window",
        ])

        self._add_section(scrollable_frame, "Tips", [
            "• Cards are cached in the database for faster reprocessing",
            "• AI analysis gives more accurate results than OCR alone",
            "• Manual edits override all automatic extractions",
            "• Rebuild database in Settings to clear all cached results",
        ])

        # Close button
        ttk.Button(
            self, text="Close",
            command=self._close,
        ).pack(pady=(0, 16))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda e: self._close())

    def _add_section(self, parent, title: str, items: list[str]):
        """Add a help section with title and bullet points."""
        # Section title
        title_label = ttk.Label(
            parent, text=title, font=styles.Font.HEADING,
            foreground=styles.Color.TEXT_PRIMARY, anchor="w",
        )
        title_label.pack(fill="x", pady=(12, 4))
        title_label.bind("<MouseWheel>", self._on_mousewheel)

        # Section items
        for item in items:
            item_label = ttk.Label(
                parent, text=item, font=styles.Font.SMALL,
                foreground=styles.Color.TEXT_PRIMARY,
                anchor="w", justify="left", wraplength=520,
            )
            item_label.pack(fill="x", padx=(12, 0), pady=2)
            item_label.bind("<MouseWheel>", self._on_mousewheel)

    def _close(self):
        self.grab_release()
        self.destroy()
