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

        self.label = ttk.Label(
            self, text="Processing...", font=styles.FONT_BODY,
            foreground=styles.TEXT_PRIMARY,
        )
        self.label.pack(pady=(20, 8), padx=20)

        self.progress = ttk.Progressbar(self, maximum=total, length=350, mode="determinate")
        self.progress.pack(padx=20)

        self.count_label = ttk.Label(
            self, text=f"0 / {total}", font=styles.FONT_SMALL,
            foreground=styles.TEXT_SECONDARY,
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

        self.result = False

        header = ttk.Label(
            self, text=f"Rename Plan (Year: {year})", font=styles.FONT_TITLE,
            foreground=styles.TEXT_PRIMARY,
        )
        header.pack(pady=(15, 5), padx=15, anchor="w")

        # Summary counts
        ok_count = sum(1 for _, _, s in plan if s == "ok")
        dup_count = sum(1 for _, _, s in plan if s == "duplicate")
        error_count = sum(1 for _, _, s in plan if s == "skip_error")
        skip_count = sum(1 for _, _, s in plan if s.startswith("skip") and s != "skip_error")
        summary = f"{ok_count} rename(s)"
        if dup_count:
            summary += f", {dup_count} duplicate(s)"
        if skip_count:
            summary += f", {skip_count} skipped"
        if error_count:
            summary += f", {error_count} error(s)"

        summary_label = ttk.Label(
            self, text=summary, font=styles.FONT_BODY,
            foreground=styles.TEXT_SECONDARY,
        )
        summary_label.pack(padx=15, anchor="w")

        # Treeview table with resizable columns
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)

        style = ttk.Style()
        style.configure(
            "Rename.Treeview", font=styles.FONT_MONO, rowheight=26,
            background=styles.BG_PRIMARY, fieldbackground=styles.BG_PRIMARY,
            foreground=styles.TEXT_PRIMARY,
        )
        style.configure("Rename.Treeview.Heading", font=styles.FONT_SMALL)
        # Remove default state maps so tag_configure colors take effect
        style.map("Rename.Treeview", background=[], foreground=[])

        tree = ttk.Treeview(
            table_frame, columns=("original", "new_name", "status"),
            show="headings", selectmode="none", style="Rename.Treeview",
        )
        tree.heading("original", text="Original Filename", anchor="w")
        tree.heading("new_name", text="New Filename", anchor="w")
        tree.heading("status", text="Status", anchor="w")
        tree.column("original", width=270, minwidth=100, stretch=True)
        tree.column("new_name", width=270, minwidth=100, stretch=True)
        tree.column("status", width=70, minwidth=50, stretch=False)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        # Row tags: combine status color with alternating background
        STATUS_LABELS = {
            "ok": "OK", "duplicate": "DUP",
            "skip_no_name": "SKIP", "skip_same": "SAME", "skip_error": "ERROR",
        }
        STATUS_FG = {
            "ok": styles.SUCCESS, "duplicate": styles.TEXT_PRIMARY,
            "skip_no_name": styles.TEXT_SECONDARY, "skip_same": styles.TEXT_SECONDARY,
            "skip_error": styles.ERROR,
        }
        for status_key, fg in STATUS_FG.items():
            tree.tag_configure(f"{status_key}_even", foreground=fg, background=styles.BG_PRIMARY)
            tree.tag_configure(f"{status_key}_odd", foreground=fg, background=styles.BG_SECONDARY)

        for i, (old_path, new_path, status) in enumerate(plan):
            new_name = new_path.name if status not in ("skip_no_name", "skip_same", "skip_error") else "-"
            status_text = STATUS_LABELS.get(status, status)
            parity = "even" if i % 2 == 0 else "odd"
            tag = f"{status}_{parity}"
            tree.insert("", "end", values=(old_path.name, new_name, status_text), tags=(tag,))

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=15, pady=(0, 15))

        cancel_btn = ttk.Button(
            btn_frame, text="Cancel",
            command=self._cancel,
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        confirm_btn = ttk.Button(
            btn_frame, text="Rename All",
            command=self._confirm,
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


class ErrorListDialog(tk.Toplevel):
    """Dialog showing AI analysis errors in a structured table."""

    def __init__(self, parent, title: str, errors: list[tuple[str, str]], auth_aborted: bool = False):
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        w, h = 650, 400
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Summary header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=15, pady=(15, 5))

        ttk.Label(
            header_frame, text="\u26A0", font=(styles.FONT_FAMILY, 20),
            foreground=styles.ERROR,
        ).pack(side="left", padx=(0, 8))

        summary = f"{len(errors)} error(s)"
        if auth_aborted:
            summary += " — batch aborted"
        ttk.Label(
            header_frame, text=summary, font=styles.FONT_HEADING,
            foreground=styles.TEXT_PRIMARY,
        ).pack(side="left")

        # Treeview table
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)

        style = ttk.Style()
        style.configure(
            "Error.Treeview", font=styles.FONT_MONO, rowheight=26,
            background=styles.BG_PRIMARY, fieldbackground=styles.BG_PRIMARY,
            foreground=styles.TEXT_PRIMARY,
        )
        style.configure("Error.Treeview.Heading", font=styles.FONT_SMALL)
        style.map("Error.Treeview", background=[], foreground=[])

        tree = ttk.Treeview(
            table_frame, columns=("filename", "error"),
            show="headings", selectmode="none", style="Error.Treeview",
        )
        tree.heading("filename", text="Filename", anchor="w")
        tree.heading("error", text="Error", anchor="w")
        tree.column("filename", width=300, minwidth=100, stretch=True)
        tree.column("error", width=300, minwidth=100, stretch=True)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        # Row tags with alternating backgrounds
        for parity in ("even", "odd"):
            bg = styles.BG_PRIMARY if parity == "even" else styles.BG_SECONDARY
            tree.tag_configure(f"error_{parity}", foreground=styles.ERROR, background=bg)

        for i, (filename, error_msg) in enumerate(errors):
            parity = "even" if i % 2 == 0 else "odd"
            tree.insert("", "end", values=(filename, error_msg), tags=(f"error_{parity}",))

        # OK button
        ok_btn = ttk.Button(
            self, text="OK",
            command=self._close,
        )
        ok_btn.pack(pady=(0, 15))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Return>", lambda e: self._close())
        self.bind("<Escape>", lambda e: self._close())

    def _close(self):
        self.grab_release()
        self.destroy()


class CompletionDialog(tk.Toplevel):
    """Dialog showing rename results in a structured table."""

    def __init__(self, parent, title: str, results: list[tuple[Path, Path, bool, str]]):
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        w, h = 650, 420
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Compute counts
        renamed = sum(1 for _, _, ok, msg in results if ok and msg == "Renamed")
        skipped = sum(1 for _, _, ok, msg in results if ok and msg != "Renamed")
        errors = sum(1 for _, _, ok, _ in results if not ok)

        # Summary header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=15, pady=(15, 5))

        if errors:
            symbol = "\u26A0"
            symbol_color = styles.ERROR
        else:
            symbol = "\u2713"
            symbol_color = styles.SUCCESS

        ttk.Label(
            header_frame, text=symbol, font=(styles.FONT_FAMILY, 20),
            foreground=symbol_color,
        ).pack(side="left", padx=(0, 8))

        counts = f"{renamed} renamed, {skipped} skipped"
        if errors:
            counts += f", {errors} failed"
        ttk.Label(
            header_frame, text=counts, font=styles.FONT_HEADING,
            foreground=styles.TEXT_PRIMARY,
        ).pack(side="left")

        # Filter to only renamed and error rows (skip rows already shown in confirm dialog)
        visible = [(old, new, ok, msg) for old, new, ok, msg in results
                    if not ok or msg == "Renamed"]

        # Treeview table with resizable columns
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)

        style = ttk.Style()
        style.configure(
            "Complete.Treeview", font=styles.FONT_MONO, rowheight=26,
            background=styles.BG_PRIMARY, fieldbackground=styles.BG_PRIMARY,
            foreground=styles.TEXT_PRIMARY,
        )
        style.configure("Complete.Treeview.Heading", font=styles.FONT_SMALL)
        style.map("Complete.Treeview", background=[], foreground=[])

        tree = ttk.Treeview(
            table_frame, columns=("filename", "result"),
            show="headings", selectmode="none", style="Complete.Treeview",
        )
        tree.heading("filename", text="Filename", anchor="w")
        tree.heading("result", text="Result", anchor="w")
        tree.column("filename", width=500, minwidth=150, stretch=True)
        tree.column("result", width=70, minwidth=50, stretch=False)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        # Row tags
        for parity in ("even", "odd"):
            bg = styles.BG_PRIMARY if parity == "even" else styles.BG_SECONDARY
            tree.tag_configure(f"ok_{parity}", foreground=styles.SUCCESS, background=bg)
            tree.tag_configure(f"error_{parity}", foreground=styles.ERROR, background=bg)
            tree.tag_configure(f"detail_{parity}", foreground=styles.ERROR, background=bg)

        for i, (old_path, new_path, ok, msg) in enumerate(visible):
            parity = "even" if i % 2 == 0 else "odd"
            display_name = new_path.name if ok else old_path.name
            if ok:
                tree.insert("", "end", values=(display_name, "OK"), tags=(f"ok_{parity}",))
            else:
                tree.insert("", "end", values=(display_name, "ERROR"), tags=(f"error_{parity}",))
                tree.insert("", "end", values=(f"    {msg}", ""), tags=(f"detail_{parity}",))

        # OK button
        ok_btn = ttk.Button(
            self, text="OK",
            command=self._close,
        )
        ok_btn.pack(pady=(0, 15))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Return>", lambda e: self._close())
        self.bind("<Escape>", lambda e: self._close())

    def _close(self):
        self.grab_release()
        self.destroy()
