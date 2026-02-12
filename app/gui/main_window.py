import io
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
from app.gui.dialogs import ProgressDialog, RenameConfirmDialog, CompletionDialog
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
from app.gui.help_dialog import HelpDialog


def _process_pdf_worker(pdf_path_str: str) -> dict:
    """Worker function to process a single PDF in a separate process.

    Returns dict of results (serializable for multiprocessing).
    """
    from pathlib import Path
    from PIL import Image
    from app.core.pdf_renderer import render_all_pages
    from app.core.ocr_engine import extract_text_all_pages
    from app.core.name_extractor import extract_family_names
    from app.core.database import compute_file_hash, get_cached_name, save_name
    from app.models.card import Confidence

    pdf_path = Path(pdf_path_str)
    result = {
        'pdf_path': pdf_path_str,
        'file_hash': None,
        'family_name': '',
        'confidence': 'none',
        'alternates': [],
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
        cached = get_cached_name(file_hash)

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

        if cached:
            result['family_name'] = cached[0]
            result['confidence'] = cached[2]
            result['alternates'] = cached[3]
        else:
            # Run OCR
            if images:
                ocr_text = extract_text_all_pages(images)
                result['ocr_text'] = ocr_text

                names = extract_family_names(ocr_text)
                if names:
                    # Save RAW results to DB
                    raw_family_name = names[0][0]
                    raw_alternates = [n for n, _ in names[1:]]
                    save_name(file_hash, raw_family_name, "ocr", names[0][1].value, raw_alternates)

                    # Reload from DB to get CLEANED/FILTERED version
                    cached = get_cached_name(file_hash)
                    if cached:
                        result['family_name'] = cached[0]
                        result['confidence'] = cached[2]
                        result['alternates'] = cached[3]

    except Exception as e:
        result['error'] = str(e)

    return result


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

        # --- Row 1: Folder selection (left) and Year (right) ---
        row1 = tk.Frame(toolbar, bg=styles.BG_PRIMARY)
        row1.pack(fill="x", padx=styles.PAD, pady=(6, 0))

        # Left side: Browse button + folder path
        left_frame = tk.Frame(row1, bg=styles.BG_PRIMARY)
        left_frame.pack(side="left")

        self._browse_btn = ttk.Button(
            left_frame, text="Browse...", style="Toolbar.TButton",
            command=self._browse_folder,
        )
        self._browse_btn.pack(side="left", padx=(0, 8))

        self._folder_var = tk.StringVar(value="No folder selected")
        self._folder_label = tk.Label(
            left_frame, textvariable=self._folder_var, font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY, anchor="w",
        )
        self._folder_label.pack(side="left")

        # Right side: Year label + entry
        right_frame = tk.Frame(row1, bg=styles.BG_PRIMARY)
        right_frame.pack(side="right")

        tk.Label(
            right_frame, text="Year:", font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 4))

        self._year_var = tk.StringVar(value=str(datetime.now().year - 1))
        year_entry = tk.Entry(
            right_frame, textvariable=self._year_var, font=styles.FONT_BODY,
            width=6, relief="flat", bg=styles.BG_PRIMARY,
        )
        year_entry.pack(side="left")

        # --- Row 2: Action buttons ---
        row2 = tk.Frame(toolbar, bg=styles.BG_PRIMARY)
        row2.pack(fill="x", padx=styles.PAD, pady=(6, 6))

        # AI All button
        self._ai_all_btn = ttk.Button(
            row2, text="AI All", style="ToolbarBold.TButton",
            command=self._start_ai_all, state="disabled",
        )
        self._ai_all_btn.pack(side="left", padx=(0, 4))

        # Rename button
        self._rename_btn = ttk.Button(
            row2, text="Rename All", style="ToolbarBold.TButton",
            command=self._start_rename, state="disabled",
        )
        self._rename_btn.pack(side="left", padx=4)

        # Clear button
        self._clear_btn = ttk.Button(
            row2, text="Clear", style="Toolbar.TButton",
            command=self._clear_all, state="disabled",
        )
        self._clear_btn.pack(side="left", padx=4)

        # Help and Settings buttons (right side)
        self._settings_btn = ttk.Button(
            row2, text="Settings", style="ToolbarSmall.TButton",
            command=self._show_settings,
        )
        self._settings_btn.pack(side="right", padx=0)

        self._help_btn = ttk.Button(
            row2, text="Help", style="ToolbarSmall.TButton",
            command=self._show_help,
        )
        self._help_btn.pack(side="right", padx=(0, 4))

    def _apply_toolbar_icons(self):
        """Load SF Symbol icons and attach them to toolbar buttons."""
        icon_map = {
            "browse": ("folder", 7, self._browse_btn),
            "ai_all": ("sparkles", 7, self._ai_all_btn),
            "rename": ("pencil", 7, self._rename_btn),
            "clear": ("xmark", 7, self._clear_btn),
            "help": ("questionmark.circle", 6, self._help_btn),
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
        self._load_folder(Path(folder), auto_process=True)

    def _load_folder(self, folder: Path, auto_process: bool = False):
        self._folder = folder
        self._folder_var.set(str(self._folder))
        self._pdf_files = sorted(self._folder.glob("*.pdf"))
        count = len(self._pdf_files)
        if count == 0:
            messagebox.showwarning("No PDFs", "No PDF files found in the selected folder.")
        else:
            self._folder_label.config(fg=styles.TEXT_PRIMARY)
            if auto_process:
                self._start_processing()

    def _start_processing(self):
        if not self._pdf_files:
            return
        self._rename_btn.config(state="disabled")
        self._ai_all_btn.config(state="disabled")
        self._cards = []
        self._preview_panel.clear()

        total = len(self._pdf_files)
        self._progress = ProgressDialog(self.root, "Processing Cards", total)
        thread = threading.Thread(target=self._process_cards, daemon=True)
        thread.start()

    def _process_cards(self):
        """Process PDFs in parallel using multiprocessing for CPU-bound tasks."""
        import multiprocessing
        from multiprocessing import Pool, cpu_count
        from PIL import Image

        # Set spawn start method for PyInstaller compatibility
        # This ensures child processes start fresh instead of forking
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            pass  # Already set

        total = len(self._pdf_files)
        # Use half the CPUs (leave room for system/UI)
        num_workers = max(1, cpu_count() // 2)

        # Convert paths to strings for multiprocessing
        pdf_paths_str = [str(p) for p in self._pdf_files]

        try:
            with Pool(num_workers) as pool:
                # Process PDFs in parallel, get results as they complete
                for i, result_dict in enumerate(pool.imap_unordered(_process_pdf_worker, pdf_paths_str)):
                    # Reconstruct CardResult from dict on main thread
                    card = self._dict_to_card(result_dict)
                    self._cards.append(card)

                    # Update progress
                    self.root.after(0, self._update_processing_progress, i + 1, total, card.filename)
        except Exception as e:
            print(f"Multiprocessing error: {e}")
            # Fallback to sequential processing if multiprocessing fails
            self._process_cards_sequential()
            return

        self.root.after(0, self._processing_complete)

    def _dict_to_card(self, result_dict: dict) -> CardResult:
        """Convert result dict from worker to CardResult object."""
        from PIL import Image

        pdf_path = Path(result_dict['pdf_path'])
        card = CardResult(pdf_path=pdf_path)

        card.file_hash = result_dict['file_hash']
        card.family_name = result_dict['family_name']
        card.alternates = result_dict['alternates']
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
            card.ocr_text = f"Error: {result_dict['error']}"
            card.confidence = Confidence.NONE

        return card

    def _process_cards_sequential(self):
        """Fallback: sequential processing if multiprocessing fails."""
        total = len(self._pdf_files)
        for i, pdf_path in enumerate(self._pdf_files):
            card = CardResult(pdf_path=pdf_path)
            try:
                card.file_hash = compute_file_hash(pdf_path)
                cached = get_cached_name(card.file_hash)
                if cached:
                    card.family_name = cached[0]
                    try:
                        card.confidence = Confidence(cached[2])
                    except ValueError:
                        card.confidence = Confidence.MEDIUM
                    card.alternates = cached[3]

                images = render_all_pages(pdf_path, dpi=200)
                if images:
                    card.preview_image = images[0]
                    card.page_images = images

                if not cached:
                    ocr_text = extract_text_all_pages(images)
                    card.ocr_text = ocr_text
                    names = extract_family_names(ocr_text)
                    if names:
                        raw_family_name = names[0][0]
                        raw_alternates = [n for n, _ in names[1:]]
                        save_name(card.file_hash, raw_family_name, "ocr", names[0][1].value, raw_alternates)
                        cached = get_cached_name(card.file_hash)
                        if cached:
                            card.family_name = cached[0]
                            card.confidence = Confidence(cached[2])
                            card.alternates = cached[3]
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
        # Sort cards by filename for stable display order
        sorted_cards = sorted(self._cards, key=lambda c: c.filename.lower())
        self._review_panel.load_cards(sorted_cards)
        self._rename_btn.config(state="normal")
        self._ai_all_btn.config(state="normal")
        self._clear_btn.config(state="normal")

    def _clear_all(self):
        """Clear all cards from the review and preview panels and unset folder."""
        self._cards = []
        self._review_panel.load_cards([])
        self._preview_panel.clear()
        self._rename_btn.config(state="disabled")
        self._ai_all_btn.config(state="disabled")
        self._clear_btn.config(state="disabled")
        # Unset folder
        self._folder = None
        self._pdf_files = []
        self._folder_var.set("No folder selected")
        self._folder_label.config(fg=styles.TEXT_SECONDARY)

    def _on_name_change(self, idx: int, name: str):
        """Persist manual name edits to the database and update confidence dot."""
        if 0 <= idx < len(self._cards):
            card = self._cards[idx]
            if name:
                # Save original confidence before marking as manual
                if card.confidence != Confidence.MANUAL:
                    card.original_confidence = card.confidence
                card.confidence = Confidence.MANUAL
                if card.file_hash:
                    save_name(card.file_hash, name, "manual", "manual", card.alternates or [])
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

    def _show_help(self):
        dialog = HelpDialog(self.root)
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
                # Save previous OCR family name before overwriting
                ocr_family_name = card.family_name if not card.ai_analyzed else ""

                # Combine ALL candidates: AI best, AI alternates, OCR best, OCR alternates
                # Union so user can reselect any if they change their mind
                existing_alternates = card.alternates or []
                all_candidates = [best_name] + alternates + existing_alternates
                if ocr_family_name:
                    all_candidates.append(ocr_family_name)

                # Deduplicate while preserving order
                combined = []
                seen = set()
                for name in all_candidates:
                    if name and name.lower() not in seen:
                        seen.add(name.lower())
                        combined.append(name)

                # Save RAW results to DB
                if card.file_hash:
                    save_name(card.file_hash, best_name, "ai", "", combined)

                    # Reload from DB to get CLEANED/FILTERED version
                    cached = get_cached_name(card.file_hash)
                    if cached:
                        card.family_name = cached[0]
                        card.confidence = Confidence(cached[2])
                        card.alternates = cached[3]
                        card.ai_analyzed = True
                        card.manual_override = ""
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
        self._rename_btn.config(state="disabled")

        total = len(self._cards)
        self._progress = ProgressDialog(self.root, "AI Analysis", total)
        thread = threading.Thread(target=self._run_ai_all, daemon=True)
        thread.start()

    def _run_ai_all(self):
        """Run AI analysis on all cards with concurrency."""
        import asyncio
        asyncio.run(self._run_ai_all_async())

    async def _run_ai_all_async(self):
        """Async version that processes multiple cards concurrently."""
        import asyncio
        from app.core.ai_analyzer import analyze_card_with_ai_async

        total = len(self._cards)
        # Limit concurrent API calls to avoid rate limits
        semaphore = asyncio.Semaphore(3)
        completed = 0

        async def process_card(i: int, card: CardResult):
            nonlocal completed
            if not card.page_images and not card.preview_image:
                completed += 1
                self.root.after(0, self._update_ai_all_progress, completed, total, card.filename, i, None)
                return

            async with semaphore:
                try:
                    # Check AI cache first
                    cached = get_cached_ai_result(card.file_hash) if card.file_hash else None
                    if cached:
                        best_name, alternates = cached
                    else:
                        ai_images = card.page_images or [card.preview_image]
                        best_name, alternates = await analyze_card_with_ai_async(ai_images)
                        if card.file_hash:
                            save_ai_result(card.file_hash, best_name, alternates)

                    if best_name:
                        # Save previous OCR family name before overwriting
                        ocr_family_name = card.family_name if not card.ai_analyzed else ""

                        # Combine ALL candidates: AI best, AI alternates, OCR best, OCR alternates
                        # Union so user can reselect any if they change their mind
                        existing_alternates = card.alternates or []
                        all_candidates = [best_name] + alternates + existing_alternates
                        if ocr_family_name:
                            all_candidates.append(ocr_family_name)

                        # Deduplicate while preserving order
                        combined = []
                        seen = set()
                        for name in all_candidates:
                            if name and name.lower() not in seen:
                                seen.add(name.lower())
                                combined.append(name)

                        # Save RAW results to DB
                        if card.file_hash:
                            save_name(card.file_hash, best_name, "ai", "", combined)

                            # Reload from DB to get CLEANED/FILTERED version
                            cached = get_cached_name(card.file_hash)
                            if cached:
                                card.family_name = cached[0]
                                card.confidence = Confidence(cached[2])
                                card.alternates = cached[3]
                                card.ai_analyzed = True
                                card.manual_override = ""
                    else:
                        card.ai_analyzed = True
                except Exception as e:
                    msg = str(e)
                    self.root.after(0, lambda m=msg, fn=card.filename: messagebox.showerror(
                        "AI Error", f"{fn}: {m}"
                    ))

                completed += 1
                self.root.after(0, self._update_ai_all_progress, completed, total, card.filename, i, card)

        # Process all cards concurrently with semaphore limiting concurrency
        await asyncio.gather(*[process_card(i, card) for i, card in enumerate(self._cards)])

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
            # Count only actual renames (not skips)
            renamed = sum(1 for _, _, ok, msg in results if ok and msg == "Renamed")
            errors = [(old, new, msg) for old, new, ok, msg in results if not ok]

            summary = f"Renamed {renamed} file(s)."
            if errors:
                err_lines = "\n".join(f"  {o.name}: {m}" for o, _, m in errors)
                summary += f"\n\nErrors:\n{err_lines}"

            # Show completion dialog with app icon
            icon_path = Path(__file__).parent.parent.parent / "icon.png"
            dialog = CompletionDialog(self.root, "Rename Complete", summary, icon_path)
            self.root.wait_window(dialog)

            # Clear everything including folder
            self._clear_all()

    def run(self):
        self.root.mainloop()
