import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from app.models.card import CardResult, Confidence
from app.gui import styles
from app.gui.icons import load_sf_symbol
from app.gui.context_menu import add_entry_context_menu


class _Tooltip:
    """Simple hover tooltip for a widget."""

    def __init__(self, widget: tk.Widget, text: str):
        self._widget = widget
        self.text = text
        self._tw = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, event=None):
        if self._tw:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tw = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, font=styles.FONT_SMALL,
            bg="#333333", fg="#FFFFFF", padx=6, pady=3,
            relief="flat",
        )
        label.pack()

    def _hide(self, event=None):
        if self._tw:
            self._tw.destroy()
            self._tw = None


class ReviewPanel(tk.Frame):
    """Scrollable card list with edit controls for reviewing extracted names."""

    def __init__(
        self,
        parent,
        on_select: Callable[[int], None],
        on_ai_request: Callable[[int], None],
        on_name_change: Callable[[int, str], None] | None = None,
        **kwargs,
    ):
        super().__init__(parent, bg=styles.BG_PRIMARY, **kwargs)
        self._on_select = on_select
        self._on_ai_request = on_ai_request
        self._on_name_change = on_name_change
        self._cards: list[CardResult] = []
        self._rows: list[dict] = []
        self._selected_idx: Optional[int] = -1
        self._suppress_trace = False
        self._ai_icon = load_sf_symbol("sparkles", 6, styles.TEXT_PRIMARY)

        # Header
        header = tk.Frame(self, bg=styles.BG_PRIMARY)
        header.pack(fill="x", padx=styles.PAD, pady=(styles.PAD, 4))
        tk.Label(
            header, text="Cards", font=styles.FONT_HEADING,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(side="left")
        self._count_label = tk.Label(
            header, text="", font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY,
        )
        self._count_label.pack(side="right")

        # Column headers
        col_header = tk.Frame(self, bg=styles.BG_PRIMARY)
        col_header.pack(fill="x", padx=styles.PAD)
        tk.Label(
            col_header, text="", width=2,
            bg=styles.BG_PRIMARY,
        ).pack(side="left", padx=(4, 0))
        tk.Label(
            col_header, text="Filename", font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY, anchor="w", width=28,
        ).pack(side="left", padx=4)
        tk.Label(
            col_header, text="Family Name", font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY, anchor="w",
        ).pack(side="left", padx=4, fill="x", expand=True)

        # Scrollable area
        container = tk.Frame(self, bg=styles.BG_PRIMARY)
        container.pack(fill="both", expand=True, padx=styles.PAD, pady=(4, styles.PAD))

        self._canvas = tk.Canvas(container, bg=styles.BG_PRIMARY, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=styles.BG_PRIMARY)

        self._inner.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas_window = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.bind("<Button-1>", lambda e: self._canvas.focus_set())

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # Bind mousewheel - macOS native behavior responds when mouse is over widget
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._inner.bind("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(-1 * (event.delta // 120 or event.delta), "units")

    def load_cards(self, cards: list[CardResult]):
        """Load card results into the review panel."""
        self._cards = cards
        self._selected_idx = -1
        # Clear existing rows
        for widget in self._inner.winfo_children():
            widget.destroy()
        self._rows.clear()

        self._count_label.config(text=f"{len(cards)} cards")

        for i, card in enumerate(cards):
            self._create_row(i, card)

    def _create_row(self, idx: int, card: CardResult):
        bg = styles.BG_PRIMARY

        row_frame = tk.Frame(self._inner, bg=bg, cursor="hand2")
        row_frame.pack(fill="x", pady=1)

        # Confidence dot with tooltip
        dot_color = styles.CONFIDENCE_COLORS.get(card.confidence.value, styles.TEXT_SECONDARY)
        dot = tk.Canvas(row_frame, width=12, height=12, bg=bg, highlightthickness=0)
        dot.create_oval(2, 2, 10, 10, fill=dot_color, outline="")
        dot.pack(side="left", padx=(8, 4), pady=8)
        tooltip_text = styles.CONFIDENCE_TOOLTIPS.get(card.confidence.value, "")
        dot_tooltip = _Tooltip(dot, tooltip_text)

        # Filename label
        fn_label = tk.Label(
            row_frame, text=card.filename, font=styles.FONT_SMALL,
            bg=bg, fg=styles.TEXT_PRIMARY, anchor="w", width=28,
        )
        fn_label.pack(side="left", padx=4, pady=4)

        # Editable name entry
        name_var = tk.StringVar(value=card.display_name)
        name_entry = tk.Entry(
            row_frame, textvariable=name_var, font=styles.FONT_BODY,
            relief="flat", bg=styles.BG_SECONDARY,
        )
        name_entry.pack(side="left", padx=4, pady=4, fill="x", expand=True)
        name_entry.bind("<Return>", lambda e: row_frame.focus_set())
        name_var.trace_add("write", lambda *a, i=idx, v=name_var: self._on_name_edit(i, v))
        add_entry_context_menu(name_entry)

        # Candidates dropdown
        alt_values = card.alternates if card.alternates else []
        alt_combo = ttk.Combobox(
            row_frame, values=alt_values, font=styles.FONT_SMALL,
            state="readonly" if alt_values else "disabled", width=14,
        )
        if alt_values:
            alt_combo.set("Candidates")
            alt_combo.bind("<<ComboboxSelected>>", lambda e, i=idx, c=alt_combo, v=name_var: self._on_alt_select(i, c, v))
        alt_combo.pack(side="left", padx=4, pady=4)

        # AI button
        ai_btn_kwargs = dict(
            text="AI",
            command=lambda i=idx: self._on_ai_request(i),
            width=3,
        )
        if self._ai_icon:
            ai_btn_kwargs["image"] = self._ai_icon
            ai_btn_kwargs["compound"] = "left"
        ai_btn = ttk.Button(row_frame, **ai_btn_kwargs)
        ai_btn.pack(side="left", padx=(4, 8), pady=4)

        row_data = {
            "frame": row_frame,
            "dot": dot,
            "dot_tooltip": dot_tooltip,
            "fn_label": fn_label,
            "name_var": name_var,
            "name_entry": name_entry,
            "alt_combo": alt_combo,
            "ai_btn": ai_btn,
        }
        self._rows.append(row_data)

        # Click to select
        for widget in [row_frame, dot, fn_label]:
            widget.bind("<Button-1>", lambda e, i=idx: self._select_row(i))

    def _select_row(self, idx: int):
        # Deselect previous
        if 0 <= self._selected_idx < len(self._rows):
            prev = self._rows[self._selected_idx]
            prev["frame"].configure(bg=styles.BG_PRIMARY)
            prev["fn_label"].configure(bg=styles.BG_PRIMARY)
            prev["dot"].configure(bg=styles.BG_PRIMARY)

        self._selected_idx = idx
        row = self._rows[idx]
        row["frame"].focus_set()
        row["frame"].configure(bg=styles.BG_SELECTED)
        row["fn_label"].configure(bg=styles.BG_SELECTED)
        row["dot"].configure(bg=styles.BG_SELECTED)

        self._on_select(idx)

    def _on_name_edit(self, idx: int, var: tk.StringVar):
        if self._suppress_trace:
            return
        if idx < len(self._cards):
            self._cards[idx].manual_override = var.get()
            if self._on_name_change:
                self._on_name_change(idx, var.get())

    def _on_alt_select(self, idx: int, combo: ttk.Combobox, var: tk.StringVar):
        selected = combo.get()
        if selected and selected != "Candidates":
            # Suppress trace to avoid triggering _on_name_change
            self._suppress_trace = True
            var.set(selected)
            self._suppress_trace = False
            # Update the card's family_name and restore original confidence
            if idx < len(self._cards):
                from app.core.database import save_name
                from app.models.card import Confidence

                card = self._cards[idx]
                card.family_name = selected
                card.manual_override = selected

                # Restore original confidence if it was previously manual
                if card.confidence == Confidence.MANUAL and card.original_confidence:
                    card.confidence = card.original_confidence

                # Update the dot to show restored confidence
                self.update_dot(idx, card.confidence)

                # Save to DB with correct confidence (not manual)
                if card.file_hash:
                    # Determine source based on confidence
                    source = "ai" if card.ai_analyzed else "ocr"
                    save_name(card.file_hash, selected, source, card.confidence.value, card.alternates or [])

    def update_dot(self, idx: int, confidence: Confidence):
        """Update just the confidence dot and tooltip for a row."""
        if idx >= len(self._rows):
            return
        row = self._rows[idx]
        dot_color = styles.CONFIDENCE_COLORS.get(confidence.value, styles.TEXT_SECONDARY)
        row["dot"].delete("all")
        row["dot"].create_oval(2, 2, 10, 10, fill=dot_color, outline="")
        row["dot_tooltip"].text = styles.CONFIDENCE_TOOLTIPS.get(confidence.value, "")

    def update_card(self, idx: int, card: CardResult):
        """Update a single card's display after AI analysis."""
        if idx >= len(self._rows):
            return
        self._cards[idx] = card
        row = self._rows[idx]

        # Update confidence dot and tooltip
        self.update_dot(idx, card.confidence)

        # Update name (suppress trace to avoid triggering manual override)
        self._suppress_trace = True
        row["name_var"].set(card.display_name)
        self._suppress_trace = False

        # Update alternates
        if card.alternates:
            row["alt_combo"]["values"] = card.alternates
            row["alt_combo"]["state"] = "readonly"
            row["alt_combo"].set("Candidates")
        else:
            row["alt_combo"]["values"] = []
            row["alt_combo"]["state"] = "disabled"
            row["alt_combo"].set("")

    def get_cards(self) -> list[CardResult]:
        """Return all cards with current edits applied."""
        return self._cards
