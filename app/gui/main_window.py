import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
from datetime import datetime

from tkinterdnd2 import DND_FILES, TkinterDnD

from app.gui import styles
from app.gui.icons import load_sf_symbol
from app.gui.preview_panel import PreviewPanel
from app.gui.review_panel import ReviewPanel
from app.gui.dialogs import ProgressDialog, RenameConfirmDialog
from app.models.card import CardResult, Confidence
from app.core.pdf_renderer import render_pdf_page, render_all_pages
from app.core.ocr_engine import extract_text_all_pages
from app.core.name_extractor import extract_family_names
from app.core.ai_analyzer import analyze_card_with_ai
from app.core.config import get_api_key
from app.core.renamer import build_rename_plan, execute_rename_plan
from app.core.database import (
    compute_file_hash, get_cached_name, save_name,
    get_cached_ai_result, save_ai_result,
)
from app.gui.settings_dialog import SettingsDialog, ApiKeyPrompt


class MainWindow:
    """Root window, toolbar, and orchestration."""

    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("Greeting Card Analyzer")
        self.root.geometry(f"{styles.WINDOW_WIDTH}x{styles.WINDOW_HEIGHT}")
        self.root.configure(bg=styles.BG_PRIMARY)
        self.root.minsize(800, 500)

        self._folder: Path | None = None
        self._cards: list[CardResult] = []
        self._pdf_files: list[Path] = []

        self._icons = {}
        self._setup_ttk_styles()
        self._build_toolbar()
        self._apply_toolbar_icons()
        self._build_main_area()
        self._setup_drop_target()
        self._setup_keyboard_nav()

    def _setup_ttk_styles(self):
        s = ttk.Style()
        s.configure("Toolbar.TButton", font=styles.FONT_BODY)
        s.configure("ToolbarBold.TButton", font=styles.FONT_HEADING)
        s.configure("ToolbarSmall.TButton", font=styles.FONT_SMALL)

    def _build_toolbar(self):
        toolbar = tk.Frame(self.root, bg=styles.BG_PRIMARY, height=styles.TOOLBAR_HEIGHT)
        toolbar.pack(fill="x", side="top")
        toolbar.pack_propagate(False)

        # Bottom border for visual separation
        border = tk.Frame(self.root, bg=styles.BG_PRIMARY, height=1)
        border.pack(fill="x", side="top")

        # Folder selection
        tk.Label(
            toolbar, text="Folder:", font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(side="left", padx=(styles.PAD, 4))

        self._folder_var = tk.StringVar(value="No folder selected")
        self._folder_label = tk.Label(
            toolbar, textvariable=self._folder_var, font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY, anchor="w", width=40,
        )
        self._folder_label.pack(side="left", padx=4)

        self._browse_btn = ttk.Button(
            toolbar, text="Browse...", style="Toolbar.TButton",
            command=self._browse_folder,
        )
        self._browse_btn.pack(side="left", padx=4)

        # Separator
        tk.Frame(toolbar, width=2, bg=styles.TEXT_SECONDARY).pack(
            side="left", fill="y", padx=8, pady=8
        )

        # Year entry
        tk.Label(
            toolbar, text="Year:", font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(side="left", padx=(4, 4))

        self._year_var = tk.StringVar(value=str(datetime.now().year - 1))
        year_entry = tk.Entry(
            toolbar, textvariable=self._year_var, font=styles.FONT_BODY,
            width=6, relief="flat", bg=styles.BG_PRIMARY,
        )
        year_entry.pack(side="left", padx=4)

        # Process button
        self._process_btn = ttk.Button(
            toolbar, text="Process", style="ToolbarBold.TButton",
            command=self._start_processing, state="disabled",
        )
        self._process_btn.pack(side="left", padx=(12, 4))

        # AI All button
        self._ai_all_btn = ttk.Button(
            toolbar, text="AI All", style="ToolbarBold.TButton",
            command=self._start_ai_all, state="disabled",
        )
        self._ai_all_btn.pack(side="left", padx=4)

        # Rename button
        self._rename_btn = ttk.Button(
            toolbar, text="Rename All", style="ToolbarBold.TButton",
            command=self._start_rename, state="disabled",
        )
        self._rename_btn.pack(side="left", padx=4)

        # Clear button
        self._clear_btn = ttk.Button(
            toolbar, text="Clear", style="Toolbar.TButton",
            command=self._clear_all, state="disabled",
        )
        self._clear_btn.pack(side="left", padx=4)

        # Settings button (right side)
        self._settings_btn = ttk.Button(
            toolbar, text="Settings", style="ToolbarSmall.TButton",
            command=self._show_settings,
        )
        self._settings_btn.pack(side="right", padx=(4, styles.PAD))

    def _apply_toolbar_icons(self):
        """Load SF Symbol icons and attach them to toolbar buttons."""
        icon_map = {
            "browse": ("folder", 7, self._browse_btn),
            "process": ("play.fill", 7, self._process_btn),
            "ai_all": ("sparkles", 7, self._ai_all_btn),
            "rename": ("pencil", 7, self._rename_btn),
            "clear": ("xmark", 7, self._clear_btn),
            "settings": ("gearshape", 6, self._settings_btn),
        }
        for key, (symbol, size, btn) in icon_map.items():
            icon = load_sf_symbol(symbol, size, styles.TEXT_PRIMARY)
            if icon:
                self._icons[key] = icon
                btn.config(image=icon, compound="left")

    def _build_main_area(self):
        main = tk.PanedWindow(
            self.root, orient="horizontal", bg=styles.BG_PRIMARY,
            sashwidth=4, sashrelief="flat",
        )
        main.pack(fill="both", expand=True)

        # Review panel (left)
        self._review_panel = ReviewPanel(
            main,
            on_select=self._on_card_select,
            on_ai_request=self._on_ai_request,
            on_name_change=self._on_name_change,
        )
        main.add(self._review_panel, minsize=500, stretch="always")

        # Preview panel (right)
        self._preview_panel = PreviewPanel(main)
        main.add(self._preview_panel, minsize=300, width=styles.PREVIEW_WIDTH, stretch="never")

    def _setup_keyboard_nav(self):
        self.root.bind("<Up>", self._on_key_up)
        self.root.bind("<Down>", self._on_key_down)
        self.root.bind("<Left>", self._on_key_left)
        self.root.bind("<Right>", self._on_key_right)
        self.root.bind("<Escape>", self._on_escape)

    def _is_entry_focused(self) -> bool:
        """Check if focus is in a text entry widget (don't hijack typing)."""
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, tk.Text))

    def _on_key_up(self, event):
        if self._is_entry_focused():
            return
        idx = self._review_panel._selected_idx
        if idx > 0:
            self._review_panel._select_row(idx - 1)

    def _on_key_down(self, event):
        if self._is_entry_focused():
            return
        idx = self._review_panel._selected_idx
        if idx < len(self._cards) - 1:
            self._review_panel._select_row(idx + 1)

    def _on_key_left(self, event):
        if self._is_entry_focused():
            return
        self._preview_panel._prev_page()

    def _on_key_right(self, event):
        if self._is_entry_focused():
            return
        self._preview_panel._next_page()

    def _on_escape(self, event):
        """Defocus any text entry by shifting focus to the root window."""
        self.root.focus_set()

    def _setup_drop_target(self):
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        path = event.data.strip()
        # macOS wraps paths with braces if they contain spaces
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        dropped = Path(path)
        if dropped.is_dir():
            self._load_folder(dropped, auto_process=True)
        elif dropped.is_file() and dropped.suffix.lower() == ".pdf":
            self._load_folder(dropped.parent, auto_process=True)

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select Greeting Cards Folder")
        if not folder:
            return
        self._load_folder(Path(folder))

    def _load_folder(self, folder: Path, auto_process: bool = False):
        self._folder = folder
        self._folder_var.set(str(self._folder))
        self._pdf_files = sorted(self._folder.glob("*.pdf"))
        count = len(self._pdf_files)
        if count == 0:
            messagebox.showwarning("No PDFs", "No PDF files found in the selected folder.")
            self._process_btn.config(state="disabled")
        else:
            self._process_btn.config(state="normal")
            self._folder_label.config(fg=styles.TEXT_PRIMARY)
            if auto_process:
                self._start_processing()

    def _start_processing(self):
        if not self._pdf_files:
            return
        self._process_btn.config(state="disabled")
        self._rename_btn.config(state="disabled")
        self._ai_all_btn.config(state="disabled")
        self._cards = []
        self._preview_panel.clear()

        total = len(self._pdf_files)
        self._progress = ProgressDialog(self.root, "Processing Cards", total)
        thread = threading.Thread(target=self._process_cards, daemon=True)
        thread.start()

    def _process_cards(self):
        total = len(self._pdf_files)
        for i, pdf_path in enumerate(self._pdf_files):
            card = CardResult(pdf_path=pdf_path)
            try:
                # Compute file hash for caching
                card.file_hash = compute_file_hash(pdf_path)

                # Check DB cache first
                cached = get_cached_name(card.file_hash)
                if cached:
                    card.family_name = cached[0]
                    try:
                        card.confidence = Confidence(cached[2])
                    except ValueError:
                        card.confidence = Confidence.MEDIUM

                # Always render preview
                images = render_all_pages(pdf_path, dpi=200)
                if images:
                    card.preview_image = images[0]
                    card.page_images = images

                # Only run OCR if no cached name
                if not cached:
                    ocr_text = extract_text_all_pages(images)
                    card.ocr_text = ocr_text

                    names = extract_family_names(ocr_text)
                    if names:
                        card.family_name = names[0][0]
                        card.confidence = names[0][1]
                        card.alternates = [n for n, _ in names[1:]]
                        save_name(card.file_hash, card.family_name, "ocr", card.confidence.value)
            except Exception as e:
                card.ocr_text = f"Error: {e}"
                card.confidence = Confidence.NONE

            self._cards.append(card)
            self.root.after(0, self._update_processing_progress, i + 1, total, pdf_path.name)

        self.root.after(0, self._processing_complete)

    def _update_processing_progress(self, current: int, total: int, name: str):
        if hasattr(self, "_progress") and self._progress.winfo_exists():
            self._progress.update_progress(current, f"Processing: {name}")

    def _processing_complete(self):
        if hasattr(self, "_progress") and self._progress.winfo_exists():
            self._progress.finish()
        self._review_panel.load_cards(self._cards)
        self._process_btn.config(state="normal")
        self._rename_btn.config(state="normal")
        self._ai_all_btn.config(state="normal")
        self._clear_btn.config(state="normal")

    def _clear_all(self):
        """Clear all cards from the review and preview panels."""
        self._cards = []
        self._review_panel.load_cards([])
        self._preview_panel.clear()
        self._rename_btn.config(state="disabled")
        self._ai_all_btn.config(state="disabled")
        self._clear_btn.config(state="disabled")

    def _on_name_change(self, idx: int, name: str):
        """Persist manual name edits to the database and update confidence dot."""
        if 0 <= idx < len(self._cards):
            card = self._cards[idx]
            if name:
                card.confidence = Confidence.MANUAL
                if card.file_hash:
                    save_name(card.file_hash, name, "manual", "manual")
            self._review_panel.update_dot(idx, card.confidence)

    def _on_card_select(self, idx: int):
        if 0 <= idx < len(self._cards):
            card = self._cards[idx]
            if card.page_images:
                self._preview_panel.show_images(card.page_images, card.filename)
            elif card.preview_image:
                self._preview_panel.show_images([card.preview_image], card.filename)
            else:
                self._preview_panel.clear()

    def _ensure_api_key(self) -> bool:
        """Check for an API key; prompt the user if missing. Returns True if a key is available."""
        if get_api_key():
            return True
        dialog = ApiKeyPrompt(self.root)
        self.root.wait_window(dialog)
        return dialog.result and get_api_key() is not None

    def _show_settings(self):
        dialog = SettingsDialog(self.root, on_db_reset=self._clear_all)
        self.root.wait_window(dialog)

    def _on_ai_request(self, idx: int):
        if idx >= len(self._cards):
            return
        if not self._ensure_api_key():
            return
        card = self._cards[idx]
        if not card.page_images and not card.preview_image:
            messagebox.showwarning("No Image", "No preview image available for AI analysis.")
            return

        # Disable the AI button for this card while processing
        self._review_panel._rows[idx]["ai_btn"].config(state="disabled", text="...")

        thread = threading.Thread(
            target=self._run_ai_analysis, args=(idx, card), daemon=True
        )
        thread.start()

    def _run_ai_analysis(self, idx: int, card: CardResult):
        try:
            # Check AI cache first
            cached = get_cached_ai_result(card.file_hash) if card.file_hash else None
            if cached:
                best_name, alternates = cached
            else:
                ai_images = card.page_images or [card.preview_image]
                best_name, alternates = analyze_card_with_ai(ai_images)
                if card.file_hash:
                    save_ai_result(card.file_hash, best_name, alternates)

            if best_name:
                card.family_name = best_name
                card.confidence = Confidence.HIGH
                card.alternates = alternates
                card.ai_analyzed = True
                card.manual_override = ""
                if card.file_hash:
                    save_name(card.file_hash, best_name, "ai")
            else:
                card.confidence = Confidence.NONE
                card.ai_analyzed = True
        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("AI Error", msg))

        self.root.after(0, self._ai_analysis_complete, idx, card)

    def _ai_analysis_complete(self, idx: int, card: CardResult):
        self._review_panel.update_card(idx, card)
        if idx < len(self._review_panel._rows):
            self._review_panel._rows[idx]["ai_btn"].config(state="normal", text="AI")

    def _start_ai_all(self):
        if not self._cards:
            return
        if not self._ensure_api_key():
            return
        self._ai_all_btn.config(state="disabled")
        self._process_btn.config(state="disabled")
        self._rename_btn.config(state="disabled")

        total = len(self._cards)
        self._progress = ProgressDialog(self.root, "AI Analysis", total)
        thread = threading.Thread(target=self._run_ai_all, daemon=True)
        thread.start()

    def _run_ai_all(self):
        total = len(self._cards)
        for i, card in enumerate(self._cards):
            if not card.page_images and not card.preview_image:
                self.root.after(0, self._update_ai_all_progress, i + 1, total, card.filename, i, None)
                continue
            try:
                # Check AI cache first
                cached = get_cached_ai_result(card.file_hash) if card.file_hash else None
                if cached:
                    best_name, alternates = cached
                else:
                    ai_images = card.page_images or [card.preview_image]
                    best_name, alternates = analyze_card_with_ai(ai_images)
                    if card.file_hash:
                        save_ai_result(card.file_hash, best_name, alternates)

                if best_name:
                    card.family_name = best_name
                    card.confidence = Confidence.HIGH
                    card.alternates = alternates
                    card.ai_analyzed = True
                    card.manual_override = ""
                    if card.file_hash:
                        save_name(card.file_hash, best_name, "ai")
                else:
                    card.ai_analyzed = True
            except Exception as e:
                msg = str(e)
                self.root.after(0, lambda m=msg, fn=card.filename: messagebox.showerror(
                    "AI Error", f"{fn}: {m}"
                ))

            self.root.after(0, self._update_ai_all_progress, i + 1, total, card.filename, i, card)

        self.root.after(0, self._ai_all_complete)

    def _update_ai_all_progress(self, current: int, total: int, name: str, idx: int, card):
        if hasattr(self, "_progress") and self._progress.winfo_exists():
            self._progress.update_progress(current, f"AI analyzing: {name}")
        if card is not None:
            self._review_panel.update_card(idx, card)

    def _ai_all_complete(self):
        if hasattr(self, "_progress") and self._progress.winfo_exists():
            self._progress.finish()
        self._ai_all_btn.config(state="normal")
        self._process_btn.config(state="normal")
        self._rename_btn.config(state="normal")

    def _start_rename(self):
        cards = self._review_panel.get_cards()
        year = self._year_var.get().strip()
        if not year:
            messagebox.showwarning("No Year", "Please enter a year.")
            return

        plan = build_rename_plan(cards, year)

        dialog = RenameConfirmDialog(self.root, plan, year)
        self.root.wait_window(dialog)

        if dialog.result:
            results = execute_rename_plan(plan)
            success = sum(1 for _, _, ok, _ in results if ok)
            errors = [(old, new, msg) for old, new, ok, msg in results if not ok]

            summary = f"Renamed {success} file(s)."
            if errors:
                err_lines = "\n".join(f"  {o.name}: {m}" for o, _, m in errors)
                summary += f"\n\nErrors:\n{err_lines}"

            messagebox.showinfo("Rename Complete", summary)

            # Clear the screen and refresh file list
            self._clear_all()
            if self._folder:
                self._pdf_files = sorted(self._folder.glob("*.pdf"))
                if self._pdf_files:
                    self._process_btn.config(state="normal")

    def run(self):
        self.root.mainloop()
