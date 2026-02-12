import tkinter as tk
from tkinter import ttk
from pathlib import Path
from app.gui import styles


class ProgressDialog(tk.Toplevel):
    """Modal progress dialog for batch processing."""

    def __init__(self, parent, title: str, total: int):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        w, h = 400, 130
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg=styles.BG_PRIMARY)

        self.label = tk.Label(
            self, text="Processing...", font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        )
        self.label.pack(pady=(20, 8), padx=20)

        self.progress = ttk.Progressbar(self, maximum=total, length=350, mode="determinate")
        self.progress.pack(padx=20)

        self.count_label = tk.Label(
            self, text=f"0 / {total}", font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY,
        )
        self.count_label.pack(pady=(4, 10))

        self._total = total
        self._current = 0
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent close

    def update_progress(self, current: int, message: str = ""):
        self._current = current
        self.progress["value"] = current
        self.count_label.config(text=f"{current} / {self._total}")
        if message:
            self.label.config(text=message)
        self.update_idletasks()

    def finish(self):
        self.grab_release()
        self.destroy()


class RenameConfirmDialog(tk.Toplevel):
    """Dialog showing the rename plan and asking for confirmation."""

    def __init__(self, parent, plan: list[tuple[Path, Path, str]], year: str):
        super().__init__(parent)
        self.title("Confirm Rename")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        w, h = 700, 500
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg=styles.BG_PRIMARY)

        self.result = False

        header = tk.Label(
            self, text=f"Rename Plan (Year: {year})", font=styles.FONT_TITLE,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        )
        header.pack(pady=(15, 5), padx=15, anchor="w")

        # Summary counts
        ok_count = sum(1 for _, _, s in plan if s == "ok")
        dup_count = sum(1 for _, _, s in plan if s == "duplicate")
        skip_count = sum(1 for _, _, s in plan if s.startswith("skip"))
        summary = f"{ok_count} rename(s)"
        if dup_count:
            summary += f", {dup_count} duplicate(s)"
        if skip_count:
            summary += f", {skip_count} skipped"

        summary_label = tk.Label(
            self, text=summary, font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY,
        )
        summary_label.pack(padx=15, anchor="w")

        # Table header
        table_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)

        col_header = tk.Frame(table_frame, bg=styles.BG_SECONDARY)
        col_header.pack(fill="x")
        col_header.columnconfigure(0, weight=1)
        col_header.columnconfigure(1, weight=1)
        col_header.columnconfigure(2, minsize=60)
        tk.Label(
            col_header, text="Original Filename", font=styles.FONT_SMALL,
            bg=styles.BG_SECONDARY, fg=styles.TEXT_SECONDARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(8, 4))
        tk.Label(
            col_header, text="New Filename", font=styles.FONT_SMALL,
            bg=styles.BG_SECONDARY, fg=styles.TEXT_SECONDARY, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(4, 4))
        tk.Label(
            col_header, text="Status", font=styles.FONT_SMALL,
            bg=styles.BG_SECONDARY, fg=styles.TEXT_SECONDARY, anchor="w",
        ).grid(row=0, column=2, sticky="w", padx=(4, 8))

        # Scrollable table body
        body_container = tk.Frame(table_frame, bg=styles.BG_PRIMARY)
        body_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(body_container, bg=styles.BG_PRIMARY, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body_container, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=styles.BG_PRIMARY)
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(2, minsize=60)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(canvas_window, width=e.width))
        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        # Bind mousewheel for native macOS scroll behavior
        def on_mousewheel(e):
            canvas.yview_scroll(-1 * (e.delta // 120 or e.delta), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        inner.bind("<MouseWheel>", on_mousewheel)

        STATUS_LABELS = {
            "ok": "",
            "duplicate": "DUP",
            "skip_no_name": "SKIP",
            "skip_same": "SAME",
        }

        for i, (old_path, new_path, status) in enumerate(plan):
            row_bg = styles.BG_PRIMARY if i % 2 == 0 else styles.BG_SECONDARY

            old_label = tk.Label(
                inner, text=old_path.name, font=styles.FONT_MONO, anchor="w",
                bg=row_bg, fg=styles.TEXT_PRIMARY,
            )
            old_label.grid(row=i, column=0, sticky="ew", padx=(8, 4), pady=1)
            old_label.bind("<MouseWheel>", on_mousewheel)

            new_name = new_path.name if status not in ("skip_no_name", "skip_same") else "-"
            new_fg = styles.TEXT_PRIMARY if status in ("ok", "duplicate") else styles.TEXT_SECONDARY
            new_label = tk.Label(
                inner, text=new_name, font=styles.FONT_MONO, anchor="w",
                bg=row_bg, fg=new_fg,
            )
            new_label.grid(row=i, column=1, sticky="ew", padx=(4, 4), pady=1)
            new_label.bind("<MouseWheel>", on_mousewheel)

            status_text = STATUS_LABELS.get(status, status)
            status_fg = styles.TEXT_SECONDARY
            if status == "duplicate":
                status_fg = styles.WARNING
            elif status.startswith("skip"):
                status_fg = styles.TEXT_SECONDARY
            status_label = tk.Label(
                inner, text=status_text, font=styles.FONT_SMALL, anchor="w",
                bg=row_bg, fg=status_fg,
            )
            status_label.grid(row=i, column=2, sticky="w", padx=(4, 8), pady=1)
            status_label.bind("<MouseWheel>", on_mousewheel)

        # Buttons
        btn_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        btn_frame.pack(fill="x", padx=15, pady=(0, 15))

        cancel_btn = tk.Button(
            btn_frame, text="Cancel", font=styles.FONT_BODY,
            command=self._cancel, width=10,
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        confirm_btn = tk.Button(
            btn_frame, text="Rename All", font=styles.FONT_HEADING,
            command=self._confirm, width=12,
        )
        confirm_btn.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._cancel())

    def _confirm(self):
        self.result = True
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.result = False
        self.grab_release()
        self.destroy()


class CompletionDialog(tk.Toplevel):
    """Dialog showing completion message with app icon."""

    def __init__(self, parent, title: str, message: str, icon_path: Path | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        w, h = 400, 210
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg=styles.BG_PRIMARY)

        content_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        content_frame.pack(expand=True, fill="both", padx=20, pady=(20, 10))

        # Icon (if available)
        self._icon_ref = None
        if icon_path and icon_path.exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                img = img.resize((64, 64), Image.Resampling.LANCZOS)
                self._icon_ref = ImageTk.PhotoImage(img)
                icon_label = tk.Label(
                    content_frame, image=self._icon_ref,
                    bg=styles.BG_PRIMARY,
                )
                icon_label.pack(pady=(5, 12))
            except Exception:
                pass  # Icon optional

        # Message
        msg_label = tk.Label(
            content_frame, text=message, font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
            justify="center", wraplength=350,
        )
        msg_label.pack(pady=(0, 10))

        # OK button
        ok_btn = tk.Button(
            self, text="OK", font=styles.FONT_BODY,
            command=self._close, width=8,
            highlightthickness=0,
        )
        ok_btn.pack(pady=(0, 16))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Return>", lambda e: self._close())
        self.bind("<Escape>", lambda e: self._close())

    def _close(self):
        self.grab_release()
        self.destroy()
