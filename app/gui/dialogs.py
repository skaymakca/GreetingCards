import tkinter as tk
from tkinter import ttk
from pathlib import Path
from app.gui import styles
from app.models.card import RenamePlanItem, RenameResult


def _display_path(path: Path) -> str:
    """Format a path as ~/relative for display (or just filename if under home)."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


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
            self, text="Processing...", font=styles.Font.BODY,
            foreground=styles.Color.TEXT_PRIMARY,
        )
        self.label.pack(pady=(20, 8), padx=20)

        self.progress = ttk.Progressbar(self, maximum=total, length=350, mode="determinate")
        self.progress.pack(padx=20)

        self.count_label = ttk.Label(
            self, text=f"0 / {total}", font=styles.Font.SMALL,
            foreground=styles.Color.TEXT_SECONDARY,
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

    def __init__(self, parent, plan: list[RenamePlanItem], year: str):
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
            self, text=f"Rename Plan (Year: {year})", font=styles.Font.TITLE,
            foreground=styles.Color.TEXT_PRIMARY,
        )
        header.pack(pady=(15, 5), padx=15, anchor="w")

        # Summary counts
        ok_count = sum(1 for item in plan if item.status == "ok")
        dup_count = sum(1 for item in plan if item.status == "duplicate")
        error_count = sum(1 for item in plan if item.status == "skip_error")
        skip_count = sum(1 for item in plan if item.status.startswith("skip") and item.status != "skip_error")
        # Count unique directories
        directories = {item.old_path.parent for item in plan}

        summary = f"{ok_count} rename(s)"
        if dup_count:
            summary += f", {dup_count} duplicate(s)"
        if skip_count:
            summary += f", {skip_count} skipped"
        if error_count:
            summary += f", {error_count} error(s)"
        if len(directories) > 1:
            summary += f" across {len(directories)} directories"

        summary_label = ttk.Label(
            self, text=summary, font=styles.Font.BODY,
            foreground=styles.Color.TEXT_SECONDARY,
        )
        summary_label.pack(padx=15, anchor="w")

        # Treeview table with resizable columns
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)

        style = ttk.Style()
        style.configure(
            "Rename.Treeview", font=styles.Font.MONO, rowheight=26,
            background=styles.Color.BG_PRIMARY, fieldbackground=styles.Color.BG_PRIMARY,
            foreground=styles.Color.TEXT_PRIMARY,
        )
        style.configure("Rename.Treeview.Heading", font=styles.Font.SMALL)
        # Remove default state maps so tag_configure colors take effect
        style.map("Rename.Treeview", background=[], foreground=[])

        tree = ttk.Treeview(
            table_frame, columns=("original", "new_name", "status"),
            show="headings", selectmode="none", style="Rename.Treeview",
        )
        # Show full paths only when multiple directories
        multi_dir = len(directories) > 1
        tree.heading("original", text="Original" if multi_dir else "Original File Name", anchor="w")
        tree.heading("new_name", text="New" if multi_dir else "New File Name", anchor="w")
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
            "ok": styles.Color.SUCCESS, "duplicate": styles.Color.TEXT_PRIMARY,
            "skip_no_name": styles.Color.TEXT_SECONDARY, "skip_same": styles.Color.TEXT_SECONDARY,
            "skip_error": styles.Color.ERROR,
        }
        for status_key, fg in STATUS_FG.items():
            tree.tag_configure(f"{status_key}_even", foreground=fg, background=styles.Color.BG_PRIMARY)
            tree.tag_configure(f"{status_key}_odd", foreground=fg, background=styles.Color.BG_SECONDARY)

        for i, item in enumerate(plan):
            old_display = _display_path(item.old_path) if multi_dir else item.old_path.name
            if item.status not in ("skip_no_name", "skip_same", "skip_error"):
                new_display = _display_path(item.new_path) if multi_dir else item.new_path.name
            else:
                new_display = "-"
            status_text = STATUS_LABELS.get(item.status, item.status)
            parity = "even" if i % 2 == 0 else "odd"
            tag = f"{item.status}_{parity}"
            tree.insert("", "end", values=(old_display, new_display, status_text), tags=(tag,))

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
            header_frame, text="\u26A0", font=(styles.Font.FAMILY, 20),
            foreground=styles.Color.ERROR,
        ).pack(side="left", padx=(0, 8))

        summary = f"{len(errors)} error(s)"
        if auth_aborted:
            summary += " — batch aborted"
        ttk.Label(
            header_frame, text=summary, font=styles.Font.HEADING,
            foreground=styles.Color.TEXT_PRIMARY,
        ).pack(side="left")

        # Treeview table
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)

        style = ttk.Style()
        style.configure(
            "Error.Treeview", font=styles.Font.MONO, rowheight=26,
            background=styles.Color.BG_PRIMARY, fieldbackground=styles.Color.BG_PRIMARY,
            foreground=styles.Color.TEXT_PRIMARY,
        )
        style.configure("Error.Treeview.Heading", font=styles.Font.SMALL)
        style.map("Error.Treeview", background=[], foreground=[])

        tree = ttk.Treeview(
            table_frame, columns=("filename", "error"),
            show="headings", selectmode="none", style="Error.Treeview",
        )
        tree.heading("filename", text="File Name", anchor="w")
        tree.heading("error", text="Error", anchor="w")
        tree.column("filename", width=300, minwidth=100, stretch=True)
        tree.column("error", width=300, minwidth=100, stretch=True)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        # Row tags with alternating backgrounds
        for parity in ("even", "odd"):
            bg = styles.Color.BG_PRIMARY if parity == "even" else styles.Color.BG_SECONDARY
            tree.tag_configure(f"error_{parity}", foreground=styles.Color.ERROR, background=bg)

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

    def __init__(self, parent, title: str, results: list[RenameResult]):
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
        renamed = sum(1 for r in results if r.success and r.message == "Renamed")
        skipped = sum(1 for r in results if r.success and r.message != "Renamed")
        errors = sum(1 for r in results if not r.success)

        # Summary header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=15, pady=(15, 5))

        if errors:
            symbol = "\u26A0"
            symbol_color = styles.Color.ERROR
        else:
            symbol = "\u2713"
            symbol_color = styles.Color.SUCCESS

        ttk.Label(
            header_frame, text=symbol, font=(styles.Font.FAMILY, 20),
            foreground=symbol_color,
        ).pack(side="left", padx=(0, 8))

        counts = f"{renamed} renamed, {skipped} skipped"
        if errors:
            counts += f", {errors} failed"
        ttk.Label(
            header_frame, text=counts, font=styles.Font.HEADING,
            foreground=styles.Color.TEXT_PRIMARY,
        ).pack(side="left")

        # Filter to only renamed and error rows (skip rows already shown in confirm dialog)
        visible = [r for r in results if not r.success or r.message == "Renamed"]

        # Treeview table with resizable columns
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=15, pady=10)

        style = ttk.Style()
        style.configure(
            "Complete.Treeview", font=styles.Font.MONO, rowheight=26,
            background=styles.Color.BG_PRIMARY, fieldbackground=styles.Color.BG_PRIMARY,
            foreground=styles.Color.TEXT_PRIMARY,
        )
        style.configure("Complete.Treeview.Heading", font=styles.Font.SMALL)
        style.map("Complete.Treeview", background=[], foreground=[])

        tree = ttk.Treeview(
            table_frame, columns=("filename", "result"),
            show="headings", selectmode="none", style="Complete.Treeview",
        )
        tree.heading("filename", text="File Name", anchor="w")
        tree.heading("result", text="Result", anchor="w")
        tree.column("filename", width=500, minwidth=150, stretch=True)
        tree.column("result", width=70, minwidth=50, stretch=False)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        # Row tags
        for parity in ("even", "odd"):
            bg = styles.Color.BG_PRIMARY if parity == "even" else styles.Color.BG_SECONDARY
            tree.tag_configure(f"ok_{parity}", foreground=styles.Color.SUCCESS, background=bg)
            tree.tag_configure(f"error_{parity}", foreground=styles.Color.ERROR, background=bg)
            tree.tag_configure(f"detail_{parity}", foreground=styles.Color.ERROR, background=bg)

        # Show full paths only when multiple directories
        directories = {(r.new_path if r.success else r.old_path).parent for r in results}
        multi_dir = len(directories) > 1

        for i, r in enumerate(visible):
            parity = "even" if i % 2 == 0 else "odd"
            path = r.new_path if r.success else r.old_path
            display_name = _display_path(path) if multi_dir else path.name
            if r.success:
                tree.insert("", "end", values=(display_name, "OK"), tags=(f"ok_{parity}",))
            else:
                tree.insert("", "end", values=(display_name, "ERROR"), tags=(f"error_{parity}",))
                tree.insert("", "end", values=(f"    {r.message}", ""), tags=(f"detail_{parity}",))

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
